"""Тесты координации локальных чат-сценариев без реальной сети."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import BudgetState, ChatBudget, ChatBudgetService  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    ModelCatalog,
)
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from chat_controller import ChatSessionController  # noqa: E402


class FakePage:
    def __init__(self) -> None:
        self.controls: list[ft.Control] = []
        self.dialogs: list[ft.DialogControl] = []
        self.drawer: ft.NavigationDrawer | None = None
        self.width = 400

    def add(self, control: ft.Control) -> None:
        self.controls.append(control)

    def update(self) -> None:
        return None

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> ft.DialogControl | None:
        return self.dialogs.pop() if self.dialogs else None

    async def show_drawer(self) -> None:
        return None

    async def close_drawer(self) -> None:
        return None


class FakeChatService:
    def __init__(
        self,
        chats: list[Chat] | None = None,
        budget_service: FakeBudgetService | None = None,
    ) -> None:
        self.chats = list(chats or [])
        self.budget_service = budget_service
        self.create_calls: list[
            tuple[ChatMode, CatalogModel, int, int, Decimal, bool]
        ] = []
        self.delete_calls = 0

    async def create_chat_with_limits(
        self,
        mode: ChatMode,
        model: CatalogModel,
        *,
        catalog: ModelCatalog,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal,
        paid_confirmed: bool = False,
    ) -> Chat:
        _ = (catalog, key_validity, key_limit)
        self.create_calls.append(
            (
                mode,
                model,
                token_limit,
                max_completion_tokens,
                cost_limit_usd,
                paid_confirmed,
            )
        )
        timestamp = datetime(2026, 3, 1, tzinfo=UTC)
        chat = Chat(
            id=f"chat-{len(self.create_calls)}",
            title="Новый чат",
            mode=mode,
            requested_model_id=model.id,
            requested_model_name=model.name,
            prompt_price_per_token=model.prompt_price_per_token,
            completion_price_per_token=model.completion_price_per_token,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.chats.insert(0, chat)
        if self.budget_service is not None:
            self.budget_service.budgets[chat.id] = _budget(
                chat.id,
                configured=True,
                token_limit=token_limit,
                max_completion_tokens=max_completion_tokens,
                cost_limit=cost_limit_usd,
            )
        return chat

    async def list_chats(self) -> list[Chat]:
        return list(self.chats)

    async def get_chat(self, chat_id: str) -> Chat | None:
        return next((chat for chat in self.chats if chat.id == chat_id), None)

    async def delete_chat(self, chat_id: str) -> bool:
        self.delete_calls += 1
        original_length = len(self.chats)
        self.chats = [chat for chat in self.chats if chat.id != chat_id]
        return len(self.chats) != original_length

    async def rename_chat(self, chat_id: str, title: str) -> bool:
        _ = (chat_id, title)
        return True

    async def list_messages(self, chat_id: str) -> list[object]:
        _ = chat_id
        return []


class FakeBudgetService:
    def __init__(self) -> None:
        self.budgets: dict[str, ChatBudget] = {}

    async def get_chat_budget(self, chat_id: str) -> ChatBudget:
        return self.budgets.setdefault(chat_id, _budget(chat_id, configured=False))

    async def list_chat_turns(self, chat_id: str) -> list[object]:
        _ = chat_id
        return []


class FakeCatalogService:
    def __init__(self, catalog: ModelCatalog) -> None:
        self.catalog = catalog
        self.get_calls = 0
        self.clear_calls = 0

    async def get_catalog(self, api_key: str) -> ModelCatalog:
        _ = api_key
        self.get_calls += 1
        return self.catalog

    def clear_cache(self) -> None:
        self.clear_calls += 1


class FakeKeyValidator:
    def __init__(self, result: KeyValidationResult) -> None:
        self.result = result
        self.calls = 0

    async def validate_key(self, _api_key: str) -> KeyValidationResult:
        self.calls += 1
        return self.result


class BlockingKeyValidator(FakeKeyValidator):
    def __init__(
        self,
        result: KeyValidationResult,
        *,
        ignore_cancellation: bool = False,
    ) -> None:
        super().__init__(result)
        self.ignore_cancellation = ignore_cancellation
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def validate_key(self, _api_key: str) -> KeyValidationResult:
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            if not self.ignore_cancellation:
                raise
            await self.release.wait()
        return self.result


class RaisingKeyValidator(FakeKeyValidator):
    async def validate_key(self, _api_key: str) -> KeyValidationResult:
        self.calls += 1
        raise RuntimeError("injected background failure")


class ChatControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.paid_model = CatalogModel(
            id="vendor/paid",
            name="Paid model",
            prompt_price_per_token=Decimal("0.000001"),
            completion_price_per_token=Decimal("0.000002"),
        )
        self.catalog = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(self.paid_model,),
            available=True,
        )
        self.page = FakePage()
        self.budget_service = FakeBudgetService()
        self.chat_service = FakeChatService(budget_service=self.budget_service)
        self.catalog_service = FakeCatalogService(self.catalog)
        self.key_validator = FakeKeyValidator(_available_key())
        self.available_limit = KeyLimitInfo.from_validated_remaining(Decimal("5"))
        self.lock_calls = 0
        self.replace_calls = 0
        self.storage_errors: list[str] = []

    def _controller(self) -> ChatSessionController:
        async def on_lock() -> None:
            self.lock_calls += 1

        async def on_replace_key() -> None:
            self.replace_calls += 1

        return ChatSessionController(
            cast(ft.Page, self.page),
            cast(KeyValidator, self.key_validator),
            cast(ChatService, self.chat_service),
            cast(ModelCatalogService, self.catalog_service),
            cast(ChatBudgetService, self.budget_service),
            cast(MessageSendingService, object()),
            on_lock=on_lock,
            on_replace_key=on_replace_key,
            on_storage_error=self.storage_errors.append,
        )

    async def test_activation_lists_chats_without_loading_catalog(self) -> None:
        controller = self._controller()

        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )

        self.assertTrue(controller.session_active)
        self.assertTrue(controller.workspace_visible)
        self.assertEqual(self.catalog_service.get_calls, 0)

    async def test_unknown_session_opens_before_slow_http_finishes(self) -> None:
        self.chat_service.chats = [_existing_chat()]
        blocking = BlockingKeyValidator(_available_key())
        self.key_validator = blocking
        controller = self._controller()

        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )

        self.assertTrue(controller.workspace_visible)
        self.assertEqual(controller.key_validity, KeyValidityState.UNKNOWN)
        self.assertTrue(controller.key_validation_in_progress)
        await asyncio.wait_for(blocking.started.wait(), timeout=0.2)
        self.assertFalse(blocking.release.is_set())

        blocking.release.set()
        await _wait_for_key_validation(controller)
        self.assertEqual(controller.key_validity, KeyValidityState.VALID)
        self.assertEqual(controller.key_limit.remaining, Decimal("5"))

    async def test_timeout_keeps_local_history_and_unknown_state(self) -> None:
        chat = _existing_chat()
        self.chat_service.chats = [chat]
        self.key_validator.result = KeyValidationResult(KeyValidationStatus.TIMEOUT)
        controller = self._controller()

        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await _wait_for_key_validation(controller)

        self.assertTrue(controller.session_active)
        self.assertTrue(controller.workspace_visible)
        self.assertEqual(controller.key_validity, KeyValidityState.UNKNOWN)
        self.assertEqual(self.chat_service.chats, [chat])

    async def test_background_exception_is_consumed_and_keeps_unknown(self) -> None:
        self.key_validator = RaisingKeyValidator(_available_key())
        controller = self._controller()

        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await _wait_for_key_validation(controller)

        self.assertEqual(controller.key_validity, KeyValidityState.UNKNOWN)
        self.assertTrue(controller.session_active)

    async def test_401_marks_invalid_without_deleting_local_history(self) -> None:
        chat = _existing_chat()
        self.chat_service.chats = [chat]
        self.key_validator.result = KeyValidationResult(KeyValidationStatus.INVALID)
        controller = self._controller()

        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await _wait_for_key_validation(controller)

        self.assertTrue(controller.session_active)
        self.assertEqual(controller.key_validity, KeyValidityState.INVALID)
        self.assertEqual(self.chat_service.chats, [chat])
        await controller.request_new_chat()
        self.assertEqual(self.catalog_service.get_calls, 0)
        await controller.request_key_replacement()
        self.assertEqual(self.replace_calls, 1)

    async def test_403_marks_restricted_without_deleting_local_history(self) -> None:
        chat = _existing_chat()
        self.chat_service.chats = [chat]
        self.key_validator.result = KeyValidationResult(KeyValidationStatus.RESTRICTED)
        controller = self._controller()

        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await _wait_for_key_validation(controller)

        self.assertTrue(controller.session_active)
        self.assertEqual(controller.key_validity, KeyValidityState.RESTRICTED)
        self.assertEqual(self.chat_service.chats, [chat])
        await controller.request_new_chat()
        self.assertEqual(self.catalog_service.get_calls, 1)

    async def test_only_one_key_validation_can_run_at_a_time(self) -> None:
        blocking = BlockingKeyValidator(_available_key())
        self.key_validator = blocking
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await asyncio.wait_for(blocking.started.wait(), timeout=0.2)

        await asyncio.gather(
            controller.request_key_revalidation(),
            controller.request_key_revalidation(),
        )

        self.assertEqual(blocking.calls, 1)
        blocking.release.set()
        await _wait_for_key_validation(controller)

    async def test_late_key_result_is_ignored_after_lock(self) -> None:
        blocking = BlockingKeyValidator(
            _available_key(),
            ignore_cancellation=True,
        )
        self.key_validator = blocking
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await asyncio.wait_for(blocking.started.wait(), timeout=0.2)

        await controller.lock_application()
        blocking.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertFalse(controller.session_active)
        self.assertFalse(controller.workspace_visible)
        self.assertEqual(controller.key_validity, KeyValidityState.UNKNOWN)
        self.assertEqual(self.lock_calls, 1)

    async def test_late_key_result_is_ignored_after_reset_deactivation(self) -> None:
        blocking = BlockingKeyValidator(
            _available_key(),
            ignore_cancellation=True,
        )
        self.key_validator = blocking
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await asyncio.wait_for(blocking.started.wait(), timeout=0.2)

        controller.deactivate()
        blocking.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertFalse(controller.session_active)
        self.assertFalse(controller.workspace_visible)
        self.assertEqual(controller.key_validity, KeyValidityState.UNKNOWN)

    async def test_successful_retry_changes_unknown_to_valid_and_unlocks_paid(
        self,
    ) -> None:
        self.key_validator.result = KeyValidationResult(KeyValidationStatus.TIMEOUT)
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await _wait_for_key_validation(controller)
        self.assertEqual(controller.key_validity, KeyValidityState.UNKNOWN)

        self.key_validator.result = _available_key()
        await controller.request_key_revalidation()
        await _wait_for_key_validation(controller)

        self.assertEqual(controller.key_validity, KeyValidityState.VALID)
        self.assertEqual(controller.key_limit.remaining, Decimal("5"))
        await controller.request_new_chat()
        await controller.select_chat_mode(ChatMode.PAID)
        self.assertEqual(controller._pending_mode, ChatMode.PAID)

    async def test_switches_between_existing_chats(self) -> None:
        first = _existing_chat()
        second = Chat(
            id="second-chat",
            title="Второй чат",
            mode=first.mode,
            requested_model_id=first.requested_model_id,
            requested_model_name=first.requested_model_name,
            prompt_price_per_token=first.prompt_price_per_token,
            completion_price_per_token=first.completion_price_per_token,
            created_at=first.created_at,
            updated_at=first.updated_at,
        )
        self.chat_service.chats = [first, second]
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )

        await controller.select_chat(second.id)

        self.assertEqual(controller.selected_chat_id, second.id)
        self.assertTrue(controller.workspace_visible)

    async def test_free_chat_flow_creates_without_paid_confirmation(self) -> None:
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )

        await controller.request_new_chat()
        await controller.select_chat_mode(ChatMode.FREE)
        await controller.select_chat_model(FREE_ROUTER_MODEL)
        self.assertEqual(self.chat_service.create_calls, [])

        await controller.submit_new_chat_limits("1000", "64", None)

        self.assertEqual(self.catalog_service.get_calls, 1)
        self.assertEqual(
            self.chat_service.create_calls,
            [
                (
                    ChatMode.FREE,
                    FREE_ROUTER_MODEL,
                    1000,
                    64,
                    Decimal("0"),
                    False,
                )
            ],
        )
        self.assertTrue(controller.workspace_visible)

    async def test_paid_limits_cancel_and_explicit_creation(self) -> None:
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )
        await controller.request_new_chat()
        await controller.select_chat_mode(ChatMode.PAID)

        await controller.select_chat_model(self.paid_model)
        self.assertEqual(self.chat_service.create_calls, [])

        await controller.back_to_model_selection()
        self.assertEqual(self.chat_service.create_calls, [])
        self.assertEqual(self.page.dialogs, [])

        await controller.select_chat_model(self.paid_model)
        await controller.submit_new_chat_limits("2000", "128", "2.50")

        self.assertEqual(
            self.chat_service.create_calls,
            [
                (
                    ChatMode.PAID,
                    self.paid_model,
                    2000,
                    128,
                    Decimal("2.50"),
                    True,
                )
            ],
        )
        self.assertEqual(self.page.dialogs, [])

    async def test_unavailable_catalog_keeps_paid_mode_closed(self) -> None:
        unavailable = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(),
            available=False,
            warning="Каталог недоступен",
        )
        self.catalog_service.catalog = unavailable
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )

        await controller.request_new_chat()
        await controller.select_chat_mode(ChatMode.PAID)

        self.assertIsNone(controller._pending_mode)
        self.assertEqual(self.chat_service.create_calls, [])

    async def test_zero_limit_keeps_free_open_and_paid_closed(self) -> None:
        zero_limit = KeyLimitInfo.from_validated_remaining(Decimal("0"))
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            zero_limit,
        )

        await controller.request_new_chat()
        await controller.select_chat_mode(ChatMode.PAID)
        self.assertIsNone(controller._pending_mode)

        await controller.select_chat_mode(ChatMode.FREE)
        await controller.select_chat_model(FREE_ROUTER_MODEL)
        await controller.submit_new_chat_limits("1000", "64", None)

        self.assertEqual(
            self.chat_service.create_calls,
            [
                (
                    ChatMode.FREE,
                    FREE_ROUTER_MODEL,
                    1000,
                    64,
                    Decimal("0"),
                    False,
                )
            ],
        )

    async def test_null_limit_allows_opening_paid_selection(self) -> None:
        no_individual_limit = KeyLimitInfo.from_validated_remaining(None)
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            no_individual_limit,
        )

        await controller.request_new_chat()
        await controller.select_chat_mode(ChatMode.PAID)

        self.assertEqual(controller._pending_mode, ChatMode.PAID)

    async def test_delete_requires_confirmation_and_cancel_is_safe(self) -> None:
        chat = _existing_chat()
        self.chat_service.chats = [chat]
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )

        await controller.request_delete_chat(chat.id)
        controller.cancel_delete_chat()
        self.assertEqual(self.chat_service.delete_calls, 0)
        self.assertEqual(self.page.dialogs, [])

        await controller.request_delete_chat(chat.id)
        await controller.confirm_delete_chat(chat.id)
        self.assertEqual(self.chat_service.delete_calls, 1)
        self.assertEqual(self.chat_service.chats, [])
        self.assertIsNone(controller.selected_chat_id)

    async def test_deleting_active_chat_selects_remaining_chat(self) -> None:
        first = _existing_chat()
        second = Chat(
            id="remaining-chat",
            title="Оставшийся чат",
            mode=ChatMode.FREE,
            requested_model_id=FREE_ROUTER_MODEL.id,
            requested_model_name=FREE_ROUTER_MODEL.name,
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            created_at=first.created_at,
            updated_at=first.updated_at,
        )
        self.chat_service.chats = [first, second]
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )
        await controller.select_chat(first.id)

        await controller.request_delete_chat(first.id)
        await controller.confirm_delete_chat(first.id)

        self.assertEqual(controller.selected_chat_id, second.id)

    async def test_lock_drops_memory_state_without_deleting_chats(self) -> None:
        chat = _existing_chat()
        self.chat_service.chats = [chat]
        controller = self._controller()
        await controller.activate(
            "session-test-credential",
            KeyValidityState.VALID,
            self.available_limit,
        )

        await controller.lock_application()

        self.assertFalse(controller.session_active)
        self.assertFalse(controller.workspace_visible)
        self.assertEqual(self.chat_service.chats, [chat])
        self.assertEqual(self.chat_service.delete_calls, 0)
        self.assertEqual(self.lock_calls, 1)


def _existing_chat() -> Chat:
    timestamp = datetime(2026, 3, 1, tzinfo=UTC)
    return Chat(
        id="existing-chat",
        title="Существующий чат",
        mode=ChatMode.FREE,
        requested_model_id=FREE_ROUTER_MODEL.id,
        requested_model_name=FREE_ROUTER_MODEL.name,
        prompt_price_per_token=Decimal("0"),
        completion_price_per_token=Decimal("0"),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _budget(
    chat_id: str,
    *,
    configured: bool,
    token_limit: int | None = None,
    max_completion_tokens: int | None = None,
    cost_limit: Decimal | None = None,
) -> ChatBudget:
    return ChatBudget(
        chat_id=chat_id,
        limits_configured=configured,
        token_limit=token_limit,
        max_completion_tokens=max_completion_tokens,
        prompt_tokens_used=0,
        completion_tokens_used=0,
        total_tokens_used=0,
        reserved_tokens=0,
        cost_limit_usd=cost_limit,
        cost_used_usd=Decimal("0"),
        cost_reserved_usd=Decimal("0"),
        state=BudgetState.READY if configured else BudgetState.UNCONFIGURED,
        updated_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _available_key() -> KeyValidationResult:
    return KeyValidationResult(
        KeyValidationStatus.ACCEPTED,
        limit_remaining=Decimal("5"),
    )


async def _wait_for_key_validation(controller: ChatSessionController) -> None:
    async def wait_until_finished() -> None:
        while controller.key_validation_in_progress:
            await asyncio.sleep(0.001)

    await asyncio.wait_for(wait_until_finished(), timeout=0.5)


if __name__ == "__main__":
    unittest.main()
