"""Офлайн-тесты контроллера активного чата и generation guards."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import BudgetState, ChatBudgetService  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    ChatMode,
    ModelCatalog,
)
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from chat_interaction_controller import (  # noqa: E402
    ChatInteractionController,
    ChatSessionContext,
)
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402

NOW = datetime(2026, 6, 1, tzinfo=UTC)
TEST_CREDENTIAL = "definitely-fake-ui-test-credential"


class FakeCompletionClient:
    def __init__(self, results: list[ChatCompletionResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, object]] = []

    async def complete(
        self,
        api_key: str,
        requested_model_id: str,
        messages,
        max_completion_tokens: int,
        provider_price_limit,
    ) -> ChatCompletionResult:
        self.calls.append((requested_model_id, messages))
        _ = (api_key, max_completion_tokens, provider_price_limit)
        return self.results.pop(0)


class BlockingCompletionClient(FakeCompletionClient):
    def __init__(self, result: ChatCompletionResult) -> None:
        super().__init__([result])
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, *args, **kwargs) -> ChatCompletionResult:
        self.started.set()
        await self.release.wait()
        return await super().complete(*args, **kwargs)


class FakeCatalogClient:
    def __init__(self, models: tuple[CatalogModel, ...]) -> None:
        self.models = models

    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...]:
        _ = api_key
        return self.models


class FakeKeyValidator:
    async def validate_key(self, api_key: str) -> KeyValidationResult:
        _ = api_key
        return KeyValidationResult(KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT)


class ChatInteractionControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = AuthDatabase(self.temp_dir.name)
        self.chat_repository = SqliteChatRepository(self.database.path)
        self.message_repository = SqliteMessageRepository(self.database.path)
        self.chat_service = ChatService(self.chat_repository, now=lambda: NOW)
        self.budget_service = ChatBudgetService(
            self.message_repository,
            now=lambda: NOW,
        )
        self.paid_model = CatalogModel(
            id="vendor/paid-ui-test",
            name="Paid UI test",
            prompt_price_per_token=Decimal("0.000001"),
            completion_price_per_token=Decimal("0.000002"),
            context_length=4096,
            provider_max_completion_tokens=256,
        )
        self.catalog = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(self.paid_model,),
            available=True,
        )
        self.catalog_client = FakeCatalogClient((self.paid_model,))
        self.session: ChatSessionContext | None = ChatSessionContext(
            TEST_CREDENTIAL,
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )
        self.key_updates: list[tuple[KeyValidityState, KeyLimitInfo]] = []

    async def test_history_is_restored_by_a_new_controller(self) -> None:
        chat_id = await self._create_free_chat()
        first = self._controller(FakeCompletionClient([_success("answer")]))
        first.activate()
        await first.select_chat(chat_id)

        outcome = await first.send_message(
            chat_id,
            "question",
            paid_confirmed=False,
        )
        self.assertTrue(outcome.applied)
        self.assertTrue(outcome.result.successful)

        restarted = self._controller(FakeCompletionClient([]))
        restarted.activate()
        restored = await restarted.select_chat(chat_id)

        self.assertEqual(
            [message.content for message in restored.messages],
            ["question", "answer"],
        )
        self.assertEqual(restored.budget.total_tokens_used, 30)

    async def test_switching_chats_keeps_histories_separate(self) -> None:
        first_id = await self._create_free_chat()
        second_id = await self._create_free_chat()
        controller = self._controller(FakeCompletionClient([_success("first-answer")]))
        controller.activate()
        await controller.select_chat(first_id)
        await controller.send_message(first_id, "first-question", paid_confirmed=False)

        second = await controller.select_chat(second_id)

        self.assertEqual(second.messages, ())
        self.assertEqual(
            [
                message.content
                for message in self.chat_repository.list_messages(first_id)
            ],
            ["first-question", "first-answer"],
        )

    async def test_one_global_request_and_late_old_chat_result_is_not_applied(
        self,
    ) -> None:
        first_id = await self._create_free_chat()
        second_id = await self._create_free_chat()
        client = BlockingCompletionClient(_success("late-answer"))
        controller = self._controller(client)
        controller.activate()
        await controller.select_chat(first_id)
        active = asyncio.create_task(
            controller.send_message(first_id, "first", paid_confirmed=False)
        )
        await asyncio.wait_for(client.started.wait(), timeout=0.5)

        await controller.select_chat(second_id)
        duplicate = await controller.send_message(
            second_id,
            "second",
            paid_confirmed=False,
        )
        client.release.set()
        late = await active

        self.assertEqual(
            duplicate.result.error_type,
            ChatErrorType.TURN_ALREADY_ACTIVE,
        )
        self.assertFalse(late.applied)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(self.chat_repository.list_messages(second_id), [])

    async def test_deactivation_ignores_late_result(self) -> None:
        chat_id = await self._create_free_chat()
        client = BlockingCompletionClient(_success("late-answer"))
        controller = self._controller(client)
        controller.activate()
        await controller.select_chat(chat_id)
        active = asyncio.create_task(
            controller.send_message(chat_id, "question", paid_confirmed=False)
        )
        await asyncio.wait_for(client.started.wait(), timeout=0.5)

        controller.deactivate()
        self.session = None
        client.release.set()
        outcome = await active

        self.assertFalse(outcome.applied)
        self.assertIsNone(outcome.state)

    async def test_paid_send_requires_preview_and_explicit_confirmation(self) -> None:
        chat_id = await self._create_paid_chat()
        client = FakeCompletionClient([_success("paid-answer", cost="0.01")])
        controller = self._controller(client)
        controller.activate()
        await controller.select_chat(chat_id)

        preview = await controller.preview_message(chat_id, "paid question")
        denied = await controller.send_message(
            chat_id,
            "paid question",
            paid_confirmed=False,
        )

        self.assertTrue(preview.allowed)
        self.assertEqual(
            denied.result.error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(client.calls, [])

        accepted = await controller.send_message(
            chat_id,
            "paid question",
            paid_confirmed=True,
        )

        self.assertTrue(accepted.result.successful)
        self.assertEqual(len(client.calls), 1)
        assert accepted.state is not None
        self.assertEqual(accepted.state.budget.cost_used_usd, Decimal("0.01"))

    async def test_unknown_reserve_requires_explicit_release(self) -> None:
        chat_id = await self._create_free_chat()
        controller = self._controller(FakeCompletionClient([_timeout()]))
        controller.activate()
        await controller.select_chat(chat_id)

        outcome = await controller.send_message(
            chat_id,
            "ambiguous",
            paid_confirmed=False,
        )
        assert outcome.state is not None and outcome.result.turn_id is not None
        self.assertEqual(outcome.state.budget.state, BudgetState.ACCOUNTING_UNKNOWN)
        self.assertGreater(outcome.state.budget.reserved_tokens, 0)

        with self.assertRaises(ValueError):
            await controller.release_unknown(
                chat_id,
                outcome.result.turn_id,
                confirmed=False,
            )
        released = await controller.release_unknown(
            chat_id,
            outcome.result.turn_id,
            confirmed=True,
        )

        self.assertEqual(released.budget.reserved_tokens, 0)
        self.assertEqual(released.budget.state, BudgetState.READY)

    async def test_safe_error_models_never_contain_session_credential(self) -> None:
        chat_id = await self._create_free_chat()
        errors = (
            ChatErrorType.AUTHENTICATION,
            ChatErrorType.PAYMENT_REQUIRED,
            ChatErrorType.PERMISSION_DENIED,
            ChatErrorType.RATE_LIMIT_EXCEEDED,
        )
        controller = self._controller(
            FakeCompletionClient([_known_error(error) for error in errors])
        )
        controller.activate()
        await controller.select_chat(chat_id)

        for error in errors:
            with self.subTest(error=error):
                outcome = await controller.send_message(
                    chat_id,
                    error.value,
                    paid_confirmed=False,
                )
                self.assertNotIn(TEST_CREDENTIAL, repr(outcome))
                self.assertNotIn(TEST_CREDENTIAL, outcome.result.safe_message or "")

    async def _create_free_chat(self) -> str:
        chat = await self.chat_service.create_chat_with_limits(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=self.catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            token_limit=8192,
            max_completion_tokens=256,
            cost_limit_usd=None,
        )
        return chat.id

    async def _create_paid_chat(self) -> str:
        chat = await self.chat_service.create_chat_with_limits(
            ChatMode.PAID,
            self.paid_model,
            catalog=self.catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            token_limit=8192,
            max_completion_tokens=256,
            cost_limit_usd=Decimal("2"),
            paid_confirmed=True,
        )
        return chat.id

    def _controller(self, completion_client) -> ChatInteractionController:
        sending = MessageSendingService(
            self.chat_service,
            self.message_repository,
            completion_client,
            self.catalog_client,
            FakeKeyValidator(),
            now=lambda: NOW,
        )
        return ChatInteractionController(
            self.chat_service,
            self.budget_service,
            sending,
            session_provider=lambda: self.session,
            on_key_state_changed=lambda validity, limit: self.key_updates.append(
                (validity, limit)
            ),
        )


def _success(
    content: str,
    *,
    cost: str = "0",
) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=content,
        generation_id="fake-generation",
        requested_model_id="fake-requested-model",
        actual_model_id="fake-actual-model",
        finish_reason="stop",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
        cost_usd=Decimal(cost),
        error_type=None,
    )


def _timeout() -> ChatCompletionResult:
    return ChatCompletionResult(
        content=None,
        generation_id=None,
        requested_model_id="fake-requested-model",
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        error_type=ChatErrorType.TIMEOUT,
        accounting_unknown=True,
    )


def _known_error(error_type: ChatErrorType) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=None,
        generation_id=None,
        requested_model_id="fake-requested-model",
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        error_type=error_type,
    )


if __name__ == "__main__":
    unittest.main()
