"""Интеграционные офлайн-тесты отправки, истории, retry и recovery."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState, PinRecord  # noqa: E402
from chat.accounting import (  # noqa: E402
    AccountingStatus,
    BudgetReservation,
    BudgetState,
    ChatBudgetService,
    TurnStatus,
)
from chat.context import ContextMessage  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    Message,
    MessageRole,
    MessageStatus,
    ProviderPriceLimit,
)
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=UTC)
TEST_CREDENTIAL = "message-test-credential"


class FakeCompletionClient:
    def __init__(self, results: list[ChatCompletionResult]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    async def complete(
        self,
        api_key: str,
        requested_model_id: str,
        messages,
        max_completion_tokens: int,
        provider_price_limit: ProviderPriceLimit,
    ) -> ChatCompletionResult:
        _ = api_key
        self.calls.append(
            {
                "model": requested_model_id,
                "messages": messages,
                "max_completion_tokens": max_completion_tokens,
                "price_limit": provider_price_limit,
            }
        )
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
        self.calls = 0

    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...] | None:
        _ = api_key
        self.calls += 1
        return self.models


class FakeKeyValidator:
    def __init__(self, result: KeyValidationResult | None = None) -> None:
        self.result = result or KeyValidationResult(
            KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT
        )
        self.calls = 0

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        _ = api_key
        self.calls += 1
        return self.result


class MessageSendingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = AuthDatabase(self.temp_dir.name)
        self.chat_repository = SqliteChatRepository(self.database.path)
        self.message_repository = SqliteMessageRepository(self.database.path)
        self.chat_service = ChatService(self.chat_repository, now=lambda: NOW)
        self.budget_service = ChatBudgetService(self.message_repository)
        self.paid_model = _paid_model()
        self.catalog = FakeCatalogClient((self.paid_model,))
        self.validator = FakeKeyValidator()
        self.key_updates: list[KeyValidityState] = []

    async def test_empty_message_is_rejected_without_reservation(self) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient([_success(cost="0")])

        result = await self._service(client).send_message(
            "free",
            "   \n  ",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertEqual(result.error_type, ChatErrorType.INVALID_REQUEST)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.chat_repository.list_messages("free"), [])

    async def test_free_success_saves_history_usage_and_local_title(self) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient([_success(cost="0")])
        service = self._service(client)

        result = await service.send_message(
            "free",
            "  first   local title  ",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertTrue(result.successful)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(
            client.calls[0]["price_limit"],
            ProviderPriceLimit.zero(),
        )
        messages = self.chat_repository.list_messages("free")
        self.assertEqual(
            [
                (message.role, message.content, message.status.value)
                for message in messages
            ],
            [
                (MessageRole.USER, "first   local title", "sent"),
                (MessageRole.ASSISTANT, "answer", "sent"),
            ],
        )
        budget = self.message_repository.get_chat_budget("free")
        assert budget is not None
        self.assertEqual(budget.prompt_tokens_used, 20)
        self.assertEqual(budget.completion_tokens_used, 10)
        self.assertEqual(budget.total_tokens_used, 30)
        self.assertEqual(budget.reserved_tokens, 0)
        turns = self.message_repository.list_turns("free")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].generation_id, "generation")
        self.assertEqual(turns[0].actual_model_id, "actual")
        self.assertEqual(turns[0].finish_reason, "stop")
        self.assertEqual(turns[0].prompt_tokens, 20)
        self.assertEqual(turns[0].completion_tokens, 10)
        self.assertEqual(turns[0].total_tokens, 30)
        self.assertEqual(turns[0].accounting_status, AccountingStatus.FINAL)
        chat = self.chat_repository.get_chat("free")
        assert chat is not None
        self.assertEqual(chat.title, "first local title")

    async def test_success_does_not_overwrite_user_defined_title(self) -> None:
        await self._create_and_configure_free("free")
        self.chat_repository.rename_chat("free", "Моё название", NOW)

        await self._service(FakeCompletionClient([_success(cost="0")])).send_message(
            "free",
            "message that would become a title",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        chat = self.chat_repository.get_chat("free")
        assert chat is not None
        self.assertEqual(chat.title, "Моё название")

    async def test_paid_success_uses_fresh_checks_and_exact_cost(self) -> None:
        await self._create_and_configure_paid("paid")
        client = FakeCompletionClient([_success(cost="0.000123456789")])
        service = self._service(client)

        result = await service.send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertTrue(result.successful)
        self.assertEqual(self.validator.calls, 1)
        self.assertEqual(self.catalog.calls, 1)
        budget = self.message_repository.get_chat_budget("paid")
        assert budget is not None
        self.assertEqual(budget.cost_used_usd, Decimal("0.000123456789"))
        self.assertEqual(budget.cost_reserved_usd, Decimal("0"))
        self.assertEqual(
            client.calls[0]["price_limit"],
            ProviderPriceLimit(
                prompt_per_token=Decimal("0.000001"),
                completion_per_token=Decimal("0.000002"),
                request=Decimal("0.01"),
            ),
        )

    async def test_paid_request_without_confirmation_never_calls_network_clients(
        self,
    ) -> None:
        await self._create_and_configure_paid("paid")
        client = FakeCompletionClient([_success(cost="0.01")])

        result = await self._service(client).send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )

        self.assertEqual(
            result.error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(client.calls, [])
        self.assertEqual(self.catalog.calls, 0)
        self.assertEqual(self.validator.calls, 0)
        self.assertEqual(self.chat_repository.list_messages("paid"), [])

    async def test_paid_preview_has_reserve_and_send_repeats_preflight(self) -> None:
        await self._create_and_configure_paid("paid")
        client = FakeCompletionClient([_success(cost="0.001")])
        service = self._service(client)

        preview = await service.preview_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )

        self.assertTrue(preview.allowed)
        self.assertIsNotNone(preview.estimated_prompt_tokens)
        self.assertIsNotNone(preview.max_completion_tokens)
        self.assertIsNotNone(preview.reserved_cost_usd)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.validator.calls, 1)
        self.assertEqual(self.catalog.calls, 1)

        result = await service.send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertTrue(result.successful)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(self.validator.calls, 2)
        self.assertEqual(self.catalog.calls, 2)

    async def test_actual_usage_over_reserve_is_recorded_and_exhausts_budget(
        self,
    ) -> None:
        await self._create_and_configure_paid(
            "paid",
            token_limit=200,
            max_completion_tokens=32,
        )
        oversized = ChatCompletionResult(
            content="answer",
            generation_id="generation",
            requested_model_id="requested",
            actual_model_id="actual",
            finish_reason="stop",
            prompt_tokens=300,
            completion_tokens=200,
            total_tokens=400,
            cost_usd=Decimal("20"),
            error_type=None,
        )

        result = await self._service(FakeCompletionClient([oversized])).send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertTrue(result.successful)
        budget = self.message_repository.get_chat_budget("paid")
        assert budget is not None
        self.assertEqual(budget.total_tokens_used, 500)
        self.assertEqual(budget.cost_used_usd, Decimal("20"))
        self.assertEqual(budget.state, BudgetState.EXHAUSTED)

    async def test_unexpected_nonzero_free_cost_exhausts_local_guard(self) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient([_success(cost="0.01")])

        await self._service(client).send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        budget = self.message_repository.get_chat_budget("free")
        assert budget is not None
        self.assertEqual(budget.cost_used_usd, Decimal("0.01"))
        self.assertEqual(budget.state, BudgetState.EXHAUSTED)

    async def test_effective_completion_is_reduced_by_model_and_budget(self) -> None:
        limited = _paid_model(provider_max_completion_tokens=40)
        self.paid_model = limited
        self.catalog.models = (limited,)
        await self._create_and_configure_paid(
            "paid",
            token_limit=100,
            max_completion_tokens=80,
        )
        client = FakeCompletionClient([_success(cost="0.001")])

        result = await self._service(client).send_message(
            "paid",
            "x" * 10,
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertTrue(result.successful)
        effective = client.calls[0]["max_completion_tokens"]
        self.assertIsInstance(effective, int)
        assert isinstance(effective, int)
        self.assertLessEqual(effective, 40)
        self.assertGreaterEqual(effective, 16)

    async def test_oversized_current_prompt_is_blocked_before_http(self) -> None:
        await self._create_and_configure_free(
            "free",
            token_limit=100,
            max_completion_tokens=16,
        )
        client = FakeCompletionClient([_success(cost="0")])

        result = await self._service(client).send_message(
            "free",
            "x" * 100,
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertFalse(result.successful)
        self.assertEqual(result.error_type, ChatErrorType.TOKEN_LIMIT_EXCEEDED)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.chat_repository.list_messages("free"), [])

    async def test_specific_free_model_is_blocked_if_it_becomes_paid(self) -> None:
        free_model = CatalogModel(
            id="vendor/specific-free",
            name="Specific free",
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            context_length=4096,
            provider_max_completion_tokens=128,
        )
        self.chat_repository.create_chat(_chat("free", ChatMode.FREE, free_model))
        await self.budget_service.configure_chat_limits(
            "free",
            token_limit=1000,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("0"),
            updated_at=NOW,
        )
        became_paid = CatalogModel(
            id=free_model.id,
            name=free_model.name,
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            request_price=Decimal("0.01"),
            context_length=4096,
            provider_max_completion_tokens=128,
        )
        self.catalog.models = (became_paid,)
        client = FakeCompletionClient([_success(cost="0")])

        result = await self._service(client).send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertEqual(result.error_type, ChatErrorType.MODEL_PRICE_UNSAFE)
        self.assertEqual(client.calls, [])

    async def test_price_increase_requires_reconfirmation_before_http(self) -> None:
        await self._create_and_configure_paid("paid")
        raised = _paid_model(prompt=Decimal("0.000002"))
        self.catalog.models = (raised,)
        client = FakeCompletionClient([_success(cost="0.001")])

        result = await self._service(client).send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertEqual(
            result.error_type,
            ChatErrorType.PRICE_RECONFIRMATION_REQUIRED,
        )
        self.assertIsNotNone(result.price_change)
        assert result.price_change is not None
        self.assertEqual(result.price_change.confirmed.prompt, Decimal("0.000001"))
        self.assertEqual(result.price_change.current.prompt, Decimal("0.000002"))
        self.assertEqual(client.calls, [])

        with self.assertRaises(ValueError):
            await self._service(client).reconfirm_model_price(
                "paid",
                api_key=TEST_CREDENTIAL,
                confirmed=False,
            )
        service = self._service(client)
        await service.reconfirm_model_price(
            "paid",
            api_key=TEST_CREDENTIAL,
            confirmed=True,
        )
        accepted = await service.send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )
        self.assertTrue(accepted.successful)

    async def test_paid_estimate_cannot_exceed_known_key_limit(self) -> None:
        await self._create_and_configure_paid("paid")
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED,
            limit_remaining=Decimal("0.001"),
        )
        client = FakeCompletionClient([_success(cost="0.001")])

        result = await self._service(client).send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(Decimal("1")),
            paid_confirmed=True,
        )

        self.assertEqual(result.error_type, ChatErrorType.KEY_LIMIT_EXCEEDED)
        self.assertEqual(client.calls, [])

    async def test_paid_estimate_cannot_exceed_local_cost_budget(self) -> None:
        self.chat_repository.create_chat(_chat("paid", ChatMode.PAID, self.paid_model))
        await self.budget_service.configure_chat_limits(
            "paid",
            token_limit=1000,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("0.001"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )
        client = FakeCompletionClient([_success(cost="0.001")])

        result = await self._service(client).send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertEqual(result.error_type, ChatErrorType.COST_LIMIT_EXCEEDED)
        self.assertEqual(client.calls, [])

    async def test_timeout_retains_unknown_reservation_and_blocks_next_send(
        self,
    ) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient([_ambiguous_timeout()])
        service = self._service(client)

        first = await service.send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        second = await service.send_message(
            "free",
            "another",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertTrue(first.accounting_unknown)
        self.assertEqual(second.error_type, ChatErrorType.ACCOUNTING_UNKNOWN)
        budget = self.message_repository.get_chat_budget("free")
        assert budget is not None
        self.assertGreater(budget.reserved_tokens, 0)
        self.assertEqual(budget.state, BudgetState.ACCOUNTING_UNKNOWN)

    async def test_partial_finish_error_is_saved_as_incomplete_failed_answer(
        self,
    ) -> None:
        await self._create_and_configure_free("free")
        partial = _result_with_finish_reason(
            "error",
            error_type=ChatErrorType.PROVIDER_UNAVAILABLE,
            content="partial",
        )

        result = await self._service(FakeCompletionClient([partial])).send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertFalse(result.successful)
        messages = self.chat_repository.list_messages("free")
        self.assertEqual(messages[1].content, "partial")
        self.assertEqual(messages[1].status.value, "failed")
        turn = self.message_repository.list_turns("free")[0]
        self.assertEqual(turn.accounting_status, AccountingStatus.FINAL)
        self.assertEqual(turn.status, TurnStatus.FAILED)

    async def test_length_response_is_saved_as_successful_and_truncated(self) -> None:
        await self._create_and_configure_free("free")
        length_result = _result_with_finish_reason("length")

        result = await self._service(
            FakeCompletionClient([length_result])
        ).send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertTrue(result.successful)
        self.assertTrue(result.truncated)
        self.assertEqual(
            [
                message.status.value
                for message in self.chat_repository.list_messages("free")
            ],
            ["sent", "sent"],
        )

    async def test_retry_reuses_user_message_and_turn_without_duplicates(self) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient(
            [
                _known_error(ChatErrorType.INVALID_REQUEST),
                _success(cost="0"),
            ]
        )
        service = self._service(client)
        first = await service.send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        assert first.turn_id is not None

        retried = await service.retry_failed_turn(
            first.turn_id,
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertTrue(retried.successful)
        messages = self.chat_repository.list_messages("free")
        self.assertEqual(
            len([message for message in messages if message.role is MessageRole.USER]),
            1,
        )
        self.assertEqual(
            len(
                [
                    message
                    for message in messages
                    if message.role is MessageRole.ASSISTANT
                ]
            ),
            1,
        )
        turns = self.message_repository.list_turns("free")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].id, first.turn_id)
        self.assertEqual(turns[0].status, TurnStatus.SENT)

        second_retry = await service.retry_failed_turn(
            first.turn_id,
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        self.assertEqual(second_retry.error_type, ChatErrorType.TURN_NOT_RETRYABLE)

    async def test_retry_updates_existing_partial_assistant_without_duplicate(
        self,
    ) -> None:
        await self._create_and_configure_free("free")
        unknown_partial = ChatCompletionResult(
            content="partial",
            generation_id="generation-partial",
            requested_model_id="requested",
            actual_model_id="actual",
            finish_reason="error",
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            error_type=ChatErrorType.PROVIDER_UNAVAILABLE,
            accounting_unknown=True,
        )
        client = FakeCompletionClient([unknown_partial, _success(cost="0")])
        service = self._service(client)
        first = await service.send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        assert first.turn_id is not None
        await self.budget_service.release_unknown_reservation(
            first.turn_id,
            confirmed=True,
            updated_at=NOW,
        )

        retried = await service.retry_failed_turn(
            first.turn_id,
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertTrue(retried.successful)
        messages = self.chat_repository.list_messages("free")
        assistants = [
            message for message in messages if message.role is MessageRole.ASSISTANT
        ]
        self.assertEqual(len(assistants), 1)
        self.assertEqual(assistants[0].content, "answer")
        self.assertEqual(assistants[0].status.value, "sent")

    async def test_concurrent_send_is_rejected(self) -> None:
        await self._create_and_configure_free("free")
        client = BlockingCompletionClient(_success(cost="0"))
        service = self._service(client)

        active = asyncio.create_task(
            service.send_message(
                "free",
                "first",
                api_key=TEST_CREDENTIAL,
                key_validity=KeyValidityState.UNKNOWN,
                key_limit=KeyLimitInfo.unknown(),
            )
        )
        await asyncio.wait_for(client.started.wait(), timeout=0.5)
        duplicate = await service.send_message(
            "free",
            "second",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        client.release.set()
        await active

        self.assertEqual(duplicate.error_type, ChatErrorType.TURN_ALREADY_ACTIVE)
        self.assertEqual(len(client.calls), 1)

    async def test_reservation_callback_runs_before_completion_returns(self) -> None:
        await self._create_and_configure_free("free")
        client = BlockingCompletionClient(_success(cost="0"))
        reserved = asyncio.Event()
        reserved_turns: list[str] = []

        async def on_reserved(turn_id: str) -> None:
            reserved_turns.append(turn_id)
            reserved.set()

        task = asyncio.create_task(
            self._service(client).send_message(
                "free",
                "hello",
                api_key=TEST_CREDENTIAL,
                key_validity=KeyValidityState.UNKNOWN,
                key_limit=KeyLimitInfo.unknown(),
                on_reserved=on_reserved,
            )
        )

        await asyncio.wait_for(reserved.wait(), timeout=0.5)
        messages = self.chat_repository.list_messages("free")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].status.value, "pending")
        self.assertEqual(len(reserved_turns), 1)
        self.assertFalse(task.done())

        client.release.set()
        await task

    async def test_cancellation_after_send_keeps_unknown_reservation(self) -> None:
        await self._create_and_configure_free("free")
        client = BlockingCompletionClient(_success(cost="0"))
        service = self._service(client)
        task = asyncio.create_task(
            service.send_message(
                "free",
                "hello",
                api_key=TEST_CREDENTIAL,
                key_validity=KeyValidityState.UNKNOWN,
                key_limit=KeyLimitInfo.unknown(),
            )
        )
        await asyncio.wait_for(client.started.wait(), timeout=0.5)

        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        budget = self.message_repository.get_chat_budget("free")
        assert budget is not None
        self.assertEqual(budget.state, BudgetState.ACCOUNTING_UNKNOWN)
        self.assertGreater(budget.reserved_tokens, 0)

    async def test_recovery_marks_pending_unknown_and_preserves_reserve(self) -> None:
        await self._create_and_configure_paid("paid")
        self.message_repository.reserve_turn(
            BudgetReservation(
                turn_id="in-flight",
                user_message_id="user-in-flight",
                chat_id="paid",
                reserved_tokens=50,
                reserved_cost_usd=Decimal("0.2"),
                created_at=NOW,
            ),
            content="question",
            requested_model_id=self.paid_model.id,
            retry=False,
        )
        self.message_repository.mark_request_sent("in-flight", NOW)

        AuthDatabase(self.temp_dir.name)

        turn = self.message_repository.get_turn("in-flight")
        budget = self.message_repository.get_chat_budget("paid")
        assert turn is not None and budget is not None
        self.assertEqual(turn.status, TurnStatus.FAILED)
        self.assertEqual(turn.accounting_status, AccountingStatus.UNKNOWN)
        self.assertEqual(turn.error_type, ChatErrorType.INTERRUPTED)
        self.assertEqual(budget.reserved_tokens, 50)
        self.assertEqual(budget.cost_reserved_usd, Decimal("0.2"))
        self.assertEqual(budget.state, BudgetState.ACCOUNTING_UNKNOWN)
        self.assertEqual(
            [
                message.status.value
                for message in self.chat_repository.list_messages("paid")
            ],
            ["failed"],
        )

    async def test_complete_history_and_current_message_are_sent_once_in_order(
        self,
    ) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient(
            [
                _success(cost="0", content="answer one"),
                _success(cost="0", content="answer two"),
                _success(cost="0", content="answer three"),
            ]
        )
        service = self._service(client)
        for text in ("question one", "question two", "question three"):
            result = await service.send_message(
                "free",
                text,
                api_key=TEST_CREDENTIAL,
                key_validity=KeyValidityState.UNKNOWN,
                key_limit=KeyLimitInfo.unknown(),
            )
            self.assertTrue(result.successful)

        sent = cast(tuple[ContextMessage, ...], client.calls[2]["messages"])
        self.assertEqual(
            [(item.role, item.content) for item in sent],
            [
                (MessageRole.USER, "question one"),
                (MessageRole.ASSISTANT, "answer one"),
                (MessageRole.USER, "question two"),
                (MessageRole.ASSISTANT, "answer two"),
                (MessageRole.USER, "question three"),
            ],
        )

    async def test_full_history_is_not_silently_trimmed(self) -> None:
        await self._create_and_configure_free(
            "free",
            token_limit=20_000,
            max_completion_tokens=64,
        )
        for message in (
            Message(
                id="large-user",
                chat_id="free",
                turn_id="large-turn",
                role=MessageRole.USER,
                content="u" * 4100,
                status=MessageStatus.SENT,
                requested_model_id=FREE_ROUTER_MODEL.id,
                actual_model_id=None,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                created_at=NOW,
            ),
            Message(
                id="large-assistant",
                chat_id="free",
                turn_id="large-turn",
                role=MessageRole.ASSISTANT,
                content="a" * 4100,
                status=MessageStatus.SENT,
                requested_model_id=FREE_ROUTER_MODEL.id,
                actual_model_id=FREE_ROUTER_MODEL.id,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                created_at=NOW,
            ),
        ):
            self.chat_repository.create_message(message)
        client = FakeCompletionClient([_success(cost="0")])

        result = await self._service(client).send_message(
            "free",
            "next",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        self.assertEqual(result.error_type, ChatErrorType.CONTEXT_LENGTH_EXCEEDED)
        self.assertEqual(client.calls, [])
        self.assertEqual(len(self.chat_repository.list_messages("free")), 2)

    async def test_context_never_contains_messages_from_another_chat(self) -> None:
        await self._create_and_configure_free("first")
        await self._create_and_configure_free("second")
        first_client = FakeCompletionClient(
            [_success(cost="0", content="secret-other")]
        )
        await self._service(first_client).send_message(
            "first",
            "other question",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        second_client = FakeCompletionClient([_success(cost="0")])

        await self._service(second_client).send_message(
            "second",
            "current",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )

        sent_messages = second_client.calls[0]["messages"]
        self.assertNotIn("secret-other", repr(sent_messages))

    async def test_401_updates_key_state_without_deleting_auth(self) -> None:
        await self._create_and_configure_free("free")
        record = PinRecord(
            version=1,
            algorithm="pbkdf2_hmac_sha256",
            iterations=1000,
            salt=b"s" * 16,
            verifier=b"v" * 32,
        )
        self.database.save_auth_state("registration", record)
        client = FakeCompletionClient([_known_error(ChatErrorType.AUTHENTICATION)])

        await self._service(client).send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )

        self.assertEqual(self.key_updates, [KeyValidityState.INVALID])
        self.assertIsNotNone(self.database.get_auth_state())

    async def test_chat_403_does_not_change_global_key_validity(self) -> None:
        await self._create_and_configure_free("free")
        client = FakeCompletionClient([_known_error(ChatErrorType.PERMISSION_DENIED)])

        await self._service(client).send_message(
            "free",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )

        self.assertEqual(self.key_updates, [])

    async def test_402_does_not_mark_local_cost_budget_exhausted(self) -> None:
        await self._create_and_configure_paid("paid")
        client = FakeCompletionClient([_known_error(ChatErrorType.PAYMENT_REQUIRED)])

        result = await self._service(client).send_message(
            "paid",
            "hello",
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )

        self.assertEqual(result.error_type, ChatErrorType.PAYMENT_REQUIRED)
        budget = self.message_repository.get_chat_budget("paid")
        assert budget is not None
        self.assertEqual(budget.cost_used_usd, Decimal("0"))
        self.assertEqual(budget.cost_reserved_usd, Decimal("0"))
        self.assertEqual(budget.state, BudgetState.READY)

    async def test_paid_never_posts_for_disallowed_key_states(self) -> None:
        cases = (
            (KeyValidityState.UNKNOWN, KeyLimitInfo.unknown()),
            (KeyValidityState.INVALID, KeyLimitInfo.unknown()),
            (KeyValidityState.RESTRICTED, KeyLimitInfo.unknown()),
            (
                KeyValidityState.VALID,
                KeyLimitInfo.from_validated_remaining(Decimal("0")),
            ),
        )
        for index, (validity, limit) in enumerate(cases):
            chat_id = f"paid-{index}"
            await self._create_and_configure_paid(chat_id)
            client = FakeCompletionClient([_success(cost="0.01")])

            result = await self._service(client).send_message(
                chat_id,
                "hello",
                api_key=TEST_CREDENTIAL,
                key_validity=validity,
                key_limit=limit,
                paid_confirmed=True,
            )

            self.assertEqual(result.error_type, ChatErrorType.KEY_NOT_VALID)
            self.assertEqual(client.calls, [])

    def _service(self, completion_client) -> MessageSendingService:
        return MessageSendingService(
            self.chat_service,
            self.message_repository,
            completion_client,
            self.catalog,
            self.validator,
            on_key_validity_changed=self.key_updates.append,
            now=lambda: NOW,
        )

    async def _create_and_configure_free(
        self,
        chat_id: str,
        *,
        token_limit: int = 1000,
        max_completion_tokens: int = 64,
    ) -> None:
        self.chat_repository.create_chat(
            _chat(chat_id, ChatMode.FREE, FREE_ROUTER_MODEL)
        )
        await self.budget_service.configure_chat_limits(
            chat_id,
            token_limit=token_limit,
            max_completion_tokens=max_completion_tokens,
            cost_limit_usd=Decimal("0"),
            updated_at=NOW,
        )

    async def _create_and_configure_paid(
        self,
        chat_id: str,
        *,
        token_limit: int = 1000,
        max_completion_tokens: int = 64,
    ) -> None:
        self.chat_repository.create_chat(_chat(chat_id, ChatMode.PAID, self.paid_model))
        await self.budget_service.configure_chat_limits(
            chat_id,
            token_limit=token_limit,
            max_completion_tokens=max_completion_tokens,
            cost_limit_usd=Decimal("10"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )


def _chat(chat_id: str, mode: ChatMode, model: CatalogModel) -> Chat:
    return Chat(
        id=chat_id,
        title="Новый чат",
        mode=mode,
        requested_model_id=model.id,
        requested_model_name=model.name,
        prompt_price_per_token=model.prompt_price_per_token,
        completion_price_per_token=model.completion_price_per_token,
        created_at=NOW,
        updated_at=NOW,
        request_price=model.request_price,
        internal_reasoning_price_per_token=model.internal_reasoning_price_per_token,
        input_cache_read_price_per_token=model.input_cache_read_price_per_token,
        input_cache_write_price_per_token=model.input_cache_write_price_per_token,
        pricing_overrides=model.pricing_overrides,
        pricing_snapshot_complete=model.pricing_is_complete,
    )


def _paid_model(
    *,
    prompt: Decimal = Decimal("0.000001"),
    provider_max_completion_tokens: int = 128,
) -> CatalogModel:
    return CatalogModel(
        id="vendor/paid",
        name="Paid",
        prompt_price_per_token=prompt,
        completion_price_per_token=Decimal("0.000002"),
        request_price=Decimal("0.01"),
        context_length=4096,
        provider_max_completion_tokens=provider_max_completion_tokens,
    )


def _success(
    *,
    cost: str,
    content: str = "answer",
) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=content,
        generation_id="generation",
        requested_model_id="requested",
        actual_model_id="actual",
        finish_reason="stop",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
        cost_usd=Decimal(cost),
        error_type=None,
    )


def _result_with_finish_reason(
    finish_reason: str,
    *,
    error_type: ChatErrorType | None = None,
    content: str = "answer",
) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=content,
        generation_id="generation",
        requested_model_id="requested",
        actual_model_id="actual",
        finish_reason=finish_reason,
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
        cost_usd=Decimal("0"),
        error_type=error_type,
    )


def _known_error(error_type: ChatErrorType) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=None,
        generation_id=None,
        requested_model_id="requested",
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        error_type=error_type,
        accounting_unknown=False,
    )


def _ambiguous_timeout() -> ChatCompletionResult:
    return ChatCompletionResult(
        content=None,
        generation_id=None,
        requested_model_id="requested",
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        error_type=ChatErrorType.TIMEOUT,
        accounting_unknown=True,
    )


if __name__ == "__main__":
    unittest.main()
