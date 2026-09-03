"""Сквозные UI-тесты 2B с временной SQLite и fake completion-клиентом."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
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
from chat_controller import ChatSessionController  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from ui.chat_view import ChatWorkspaceView  # noqa: E402

NOW = datetime(2026, 8, 1, tzinfo=UTC)
TEST_CREDENTIAL = "definitely-fake-chat-ui-credential"


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


class FakeCatalogService:
    def __init__(self, catalog: ModelCatalog) -> None:
        self.catalog = catalog

    async def get_catalog(self, api_key: str) -> ModelCatalog:
        _ = api_key
        return self.catalog

    def clear_cache(self) -> None:
        return None


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


class FakeCompletionClient:
    def __init__(self, results: list[ChatCompletionResult]) -> None:
        self.results = results
        self.calls = 0

    async def complete(self, *args, **kwargs) -> ChatCompletionResult:
        _ = (args, kwargs)
        self.calls += 1
        return self.results.pop(0)


class BlockingCompletionClient(FakeCompletionClient):
    def __init__(self, result: ChatCompletionResult) -> None:
        super().__init__([result])
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, *args, **kwargs) -> ChatCompletionResult:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        _ = (args, kwargs)
        return self.results.pop(0)


class ChatUiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database = AuthDatabase(self.temp_dir.name)
        self.chat_repository = SqliteChatRepository(database.path)
        self.message_repository = SqliteMessageRepository(database.path)
        self.chat_service = ChatService(self.chat_repository, now=lambda: NOW)
        self.budget_service = ChatBudgetService(
            self.message_repository,
            now=lambda: NOW,
        )
        self.paid_model = CatalogModel(
            id="vendor/paid-ui",
            name="Paid UI",
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
        self.page = FakePage()

    async def test_free_send_updates_sqlite_ui_title_and_budget(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        controller, client = self._controller([_success("saved answer")])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = "first local question"
        view.composer._apply_state()

        await view.composer._handle_click(
            ft.Event(name="click", control=view.composer.send_button)
        )

        self.assertEqual(view.editor_value, "")
        self.assertEqual(client.calls, 1)
        self.assertEqual(
            [
                message.content
                for message in self.chat_repository.list_messages(chat_id)
            ],
            ["first local question", "saved answer"],
        )
        state = controller._workspace_state
        assert state is not None
        self.assertEqual(state.chat.title, "first local question")
        self.assertEqual(state.budget.total_tokens_used, 30)
        self.assertEqual(state.remaining.tokens, 8162)
        assert controller._workspace_view is not None
        assert controller._workspace_view.message_history is not None
        self.assertEqual(
            len(controller._workspace_view.message_history.control.controls),
            2,
        )

    async def test_preflight_error_keeps_editor_text(self) -> None:
        chat = await self.chat_service.create_chat(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=self.catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )
        controller, client = self._controller([_success("unused")])
        await self._activate(controller)
        await controller.select_chat(chat.id)
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = "keep this text"
        view.composer._apply_state()

        await view.composer._handle_click(
            ft.Event(name="click", control=view.composer.send_button)
        )

        self.assertEqual(view.editor_value, "keep this text")
        self.assertEqual(client.calls, 0)
        self.assertEqual(self.chat_repository.list_messages(chat.id), [])

    async def test_retry_click_event_never_replaces_turn_id(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        controller, client = self._controller(
            [
                _known_error(ChatErrorType.INVALID_REQUEST),
                _success("retry answer"),
            ]
        )
        await self._activate(controller)
        await controller.select_chat(chat_id)
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = "retry question"
        view.composer._apply_state()
        await view.composer._handle_click(
            ft.Event(name="click", control=view.composer.send_button)
        )
        self.assertEqual(client.calls, 1)

        view = controller._workspace_view
        assert view is not None
        retry_button = _find_retry_button(view)
        handler = cast(
            Callable[[ft.Event[ft.TextButton]], Awaitable[None]],
            retry_button.on_click,
        )
        await handler(ft.Event(name="click", control=retry_button))

        self.assertEqual(client.calls, 2)
        self.assertEqual(len(self.message_repository.list_turns(chat_id)), 1)
        self.assertEqual(
            [
                message.content
                for message in self.chat_repository.list_messages(chat_id)
            ],
            ["retry question", "retry answer"],
        )

    async def test_existing_unconfigured_chat_can_configure_limits(self) -> None:
        chat = await self.chat_service.create_chat(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=self.catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )
        controller, _client = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat.id)

        await controller.request_configure_limits(chat.id)
        self.assertEqual(len(self.page.dialogs), 1)
        await controller.submit_existing_chat_limits("2000", "128", None)

        budget = self.message_repository.get_chat_budget(chat.id)
        assert budget is not None
        self.assertTrue(budget.limits_configured)
        self.assertEqual(budget.token_limit, 2000)
        self.assertEqual(budget.max_completion_tokens, 128)
        self.assertEqual(self.page.dialogs, [])
        assert controller._workspace_view is not None
        assert controller._workspace_view.composer is not None
        self.assertFalse(controller._workspace_view.composer.message_field.disabled)

    async def test_paid_budget_increase_requires_second_confirmation(self) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        controller, _client = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)

        await controller.request_edit_limits(chat_id)
        await controller.submit_existing_chat_limits("8192", "256", "3")

        self.assertEqual(len(self.page.dialogs), 2)
        unchanged = self.message_repository.get_chat_budget(chat_id)
        assert unchanged is not None
        self.assertEqual(unchanged.cost_limit_usd, Decimal("2"))

        controller.cancel_cost_increase()
        self.assertEqual(len(self.page.dialogs), 1)
        await controller.submit_existing_chat_limits("8192", "256", "3")
        await controller.confirm_cost_increase()

        updated = self.message_repository.get_chat_budget(chat_id)
        assert updated is not None
        self.assertEqual(updated.cost_limit_usd, Decimal("3"))
        self.assertEqual(self.page.dialogs, [])

    async def test_paid_ui_never_posts_before_confirmation(self) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        controller, client = self._controller([_success("paid answer", cost="0.01")])
        await self._activate(controller)
        await controller.select_chat(chat_id)

        await controller.submit_message("paid question")

        self.assertEqual(client.calls, 0)
        self.assertEqual(len(self.page.dialogs), 1)
        self.assertEqual(self.chat_repository.list_messages(chat_id), [])

        await controller.confirm_paid_request()

        self.assertEqual(client.calls, 1)
        self.assertEqual(self.page.dialogs, [])
        self.assertEqual(len(self.chat_repository.list_messages(chat_id)), 2)

    async def test_price_change_requires_reconfirmation_before_paid_dialog(
        self,
    ) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        self.paid_model = replace(
            self.paid_model,
            prompt_price_per_token=Decimal("0.000002"),
        )
        controller, client = self._controller([_success("answer", cost="0.01")])
        await self._activate(controller)
        await controller.select_chat(chat_id)

        await controller.submit_message("paid after price change")

        self.assertEqual(client.calls, 0)
        self.assertEqual(len(self.page.dialogs), 1)
        preview = controller._workspace_controller.pending_preview
        self.assertIsNotNone(preview)
        assert preview is not None
        self.assertIsNotNone(preview.price_change)

        await controller.confirm_price_change()
        self.assertEqual(client.calls, 0)
        self.assertEqual(len(self.page.dialogs), 1)
        await controller.confirm_paid_request()

        self.assertEqual(client.calls, 1)
        updated = self.chat_repository.get_chat(chat_id)
        assert updated is not None
        self.assertEqual(updated.prompt_price_per_token, Decimal("0.000002"))

    async def test_price_change_after_paid_dialog_still_blocks_post(self) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        catalog_client = FakeCatalogClient((self.paid_model,))
        controller, client = self._controller(
            [_success("unused", cost="0.01")],
            catalog_client=catalog_client,
        )
        await self._activate(controller)
        await controller.select_chat(chat_id)
        await controller.submit_message("price changes while dialog is open")
        self.assertEqual(len(self.page.dialogs), 1)

        catalog_client.models = (
            replace(
                self.paid_model,
                completion_price_per_token=Decimal("0.000004"),
            ),
        )
        await controller.confirm_paid_request()

        self.assertEqual(client.calls, 0)
        self.assertEqual(len(self.page.dialogs), 1)
        preview = controller._workspace_controller.pending_preview
        self.assertIsNotNone(preview)
        assert preview is not None
        self.assertIsNotNone(preview.price_change)

    async def test_double_click_and_old_chat_result_are_guarded(self) -> None:
        first_id = await self._create_chat(ChatMode.FREE)
        second_id = await self._create_chat(
            ChatMode.FREE,
            now=NOW + timedelta(microseconds=1),
        )
        client = BlockingCompletionClient(_success("late answer"))
        controller, _ = self._controller([], completion_client=client)
        await self._activate(controller)
        await controller.select_chat(first_id)
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = "first"
        view.composer._apply_state()

        first = asyncio.create_task(
            view.composer._handle_click(
                ft.Event(name="click", control=view.composer.send_button)
            )
        )
        await asyncio.wait_for(client.started.wait(), timeout=0.5)
        view.composer.message_field.value = "duplicate"
        await view.composer._handle_click(
            ft.Event(name="click", control=view.composer.send_button)
        )
        await controller.select_chat(second_id)
        client.release.set()
        await first

        self.assertEqual(client.calls, 1)
        self.assertEqual(controller.selected_chat_id, second_id)
        assert controller._workspace_state is not None
        self.assertEqual(controller._workspace_state.chat.id, second_id)
        self.assertFalse(controller._workspace_state.sending)
        assert controller._workspace_view is not None
        assert controller._workspace_view.composer is not None
        self.assertFalse(controller._workspace_view.composer.message_field.disabled)
        self.assertEqual(self.chat_repository.list_messages(second_id), [])
        self.assertEqual(len(self.chat_repository.list_messages(first_id)), 2)

    async def test_lock_does_not_apply_late_send_result_to_ui_session(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        client = BlockingCompletionClient(_success("late answer"))
        controller, _ = self._controller([], completion_client=client)
        await self._activate(controller)
        await controller.select_chat(chat_id)
        active = asyncio.create_task(controller.submit_message("question"))
        await asyncio.wait_for(client.started.wait(), timeout=0.5)

        await controller.lock_application()
        client.release.set()
        await active

        self.assertFalse(controller.session_active)
        self.assertFalse(controller.workspace_visible)
        self.assertIsNone(controller._workspace_state)
        self.assertEqual(len(self.chat_repository.list_messages(chat_id)), 2)

    async def test_unknown_warning_requires_confirmed_release(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        controller, _client = self._controller([_timeout()])
        await self._activate(controller)
        await controller.select_chat(chat_id)

        await controller.submit_message("ambiguous")

        state = controller._workspace_state
        assert state is not None
        self.assertEqual(state.budget.state, BudgetState.ACCOUNTING_UNKNOWN)
        assert controller._workspace_view is not None
        self.assertIsNotNone(controller._workspace_view.release_unknown_button)
        unknown_turn = next(
            turn for turn in state.turns if turn.accounting_status.value == "unknown"
        )

        await controller.request_release_unknown(unknown_turn.id)
        controller.cancel_release_unknown()
        unchanged = self.message_repository.get_chat_budget(chat_id)
        assert unchanged is not None
        self.assertEqual(unchanged.state, BudgetState.ACCOUNTING_UNKNOWN)

        await controller.request_release_unknown(unknown_turn.id)
        await controller.confirm_release_unknown()
        released = self.message_repository.get_chat_budget(chat_id)
        assert released is not None
        self.assertEqual(released.state, BudgetState.READY)
        self.assertEqual(released.reserved_tokens, 0)

    async def test_401_invalidates_session_but_403_does_not(self) -> None:
        first_id = await self._create_chat(ChatMode.FREE)
        controller, _client = self._controller(
            [_known_error(ChatErrorType.AUTHENTICATION)]
        )
        await self._activate(controller)
        await controller.select_chat(first_id)

        await controller.submit_message("authentication check")

        self.assertEqual(controller.key_validity, KeyValidityState.INVALID)
        self.assertEqual(len(self.chat_repository.list_messages(first_id)), 1)

        second_id = await self._create_chat(
            ChatMode.FREE,
            now=NOW + timedelta(microseconds=2),
        )
        controller, _client = self._controller(
            [_known_error(ChatErrorType.PERMISSION_DENIED)]
        )
        await self._activate(controller)
        await controller.select_chat(second_id)

        await controller.submit_message("permission check")

        self.assertEqual(controller.key_validity, KeyValidityState.VALID)
        self.assertEqual(len(self.chat_repository.list_messages(second_id)), 1)

    async def test_402_and_429_are_presented_without_sensitive_data(self) -> None:
        paid_id = await self._create_chat(ChatMode.PAID)
        controller, _client = self._controller(
            [_known_error(ChatErrorType.PAYMENT_REQUIRED)]
        )
        await self._activate(controller)
        await controller.select_chat(paid_id)
        await controller.submit_message("paid failure")
        await controller.confirm_paid_request()
        assert controller._workspace_view is not None
        assert controller._workspace_view.composer is not None
        payment_message = controller._workspace_view.composer.status.value
        self.assertIn("недостатке средств", payment_message)
        self.assertNotIn(TEST_CREDENTIAL, payment_message)

        free_id = await self._create_chat(
            ChatMode.FREE,
            now=NOW + timedelta(microseconds=3),
        )
        controller, _client = self._controller(
            [_known_error(ChatErrorType.RATE_LIMIT_EXCEEDED, retry_after=23)]
        )
        await self._activate(controller)
        await controller.select_chat(free_id)
        await controller.submit_message("rate limited")
        assert controller._workspace_view is not None
        assert controller._workspace_view.composer is not None
        rate_message = controller._workspace_view.composer.status.value
        self.assertIn("23 с", rate_message)
        self.assertNotIn(TEST_CREDENTIAL, rate_message)

    async def _create_chat(
        self,
        mode: ChatMode,
        *,
        now: datetime | None = None,
    ) -> str:
        service = (
            self.chat_service
            if now is None
            else ChatService(self.chat_repository, now=lambda: now)
        )
        model = FREE_ROUTER_MODEL if mode is ChatMode.FREE else self.paid_model
        chat = await service.create_chat_with_limits(
            mode,
            model,
            catalog=self.catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            token_limit=8192,
            max_completion_tokens=256,
            cost_limit_usd=None if mode is ChatMode.FREE else Decimal("2"),
            paid_confirmed=mode is ChatMode.PAID,
        )
        return chat.id

    def _controller(
        self,
        results: list[ChatCompletionResult],
        *,
        completion_client: FakeCompletionClient | None = None,
        catalog_client: FakeCatalogClient | None = None,
    ) -> tuple[ChatSessionController, FakeCompletionClient]:
        client = completion_client or FakeCompletionClient(results)
        validator = FakeKeyValidator()
        sending = MessageSendingService(
            self.chat_service,
            self.message_repository,
            client,
            catalog_client or FakeCatalogClient((self.paid_model,)),
            validator,
            now=lambda: NOW,
        )

        async def no_op() -> None:
            return None

        controller = ChatSessionController(
            cast(ft.Page, self.page),
            cast(KeyValidator, validator),
            self.chat_service,
            cast(ModelCatalogService, FakeCatalogService(self.catalog)),
            self.budget_service,
            sending,
            on_lock=no_op,
            on_replace_key=no_op,
            on_storage_error=lambda _message: None,
        )
        return controller, client

    async def _activate(self, controller: ChatSessionController) -> None:
        await controller.activate(
            TEST_CREDENTIAL,
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )


def _success(
    content: str,
    *,
    cost: str = "0",
) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=content,
        generation_id="fake-generation",
        requested_model_id="fake-requested",
        actual_model_id="fake-actual",
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
        requested_model_id="fake-requested",
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        error_type=ChatErrorType.TIMEOUT,
        accounting_unknown=True,
    )


def _known_error(
    error_type: ChatErrorType,
    *,
    retry_after: int | None = None,
) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=None,
        generation_id=None,
        requested_model_id="fake-requested",
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        error_type=error_type,
        retry_after=retry_after,
    )


def _find_retry_button(view: ChatWorkspaceView) -> ft.TextButton:
    assert view.message_history is not None
    for row in view.message_history.control.controls:
        if not isinstance(row, ft.Row):
            continue
        for bubble in row.controls:
            if not isinstance(bubble, ft.Container) or not isinstance(
                bubble.content,
                ft.Column,
            ):
                continue
            for control in bubble.content.controls:
                if isinstance(control, ft.TextButton):
                    return control
    raise AssertionError("Кнопка повтора не найдена")


if __name__ == "__main__":
    unittest.main()
