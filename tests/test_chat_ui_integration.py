"""Сквозные UI-тесты 2B с временной SQLite и fake completion-клиентом."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import unittest
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import BudgetState, ChatBudgetService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
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
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from ui.chat_view import ChatWorkspaceView  # noqa: E402

NOW = datetime(2026, 8, 1, tzinfo=UTC)
TEST_CREDENTIAL = "definitely-fake-chat-ui-credential"


class FakePage:
    def __init__(self) -> None:
        self.controls: list[ft.Control] = []
        self._dialogs: list[ft.DialogControl] = []
        self.drawer: ft.NavigationDrawer | None = None
        self.width = 400
        self.height = 700

    @property
    def dialogs(self) -> list[ft.DialogControl]:
        return [dialog for dialog in self._dialogs if dialog.open]

    def add(self, control: ft.Control) -> None:
        self.controls.append(control)

    def update(self) -> None:
        return None

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        dialog.open = True
        self._dialogs.append(dialog)

    def pop_dialog(self) -> ft.DialogControl | None:
        dialog = self.dialogs[-1] if self.dialogs else None
        if dialog is not None:
            dialog.open = False
        return dialog

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


@dataclass
class _PausedOperation:
    task: asyncio.Task[None]
    release: asyncio.Event


class ChatUiIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database = AuthDatabase(self.temp_dir.name)
        self.chat_repository = SqliteChatRepository(database.path)
        self.message_repository = SqliteMessageRepository(database.path)
        self.draft_repository = SqliteDraftRepository(database.path)
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

    async def test_paid_preview_navigation_failure_releases_owned_pending(self) -> None:
        await self._navigate_during_paid_operation("preview", denied=True)

    async def test_paid_preview_navigation_success_releases_owned_pending(self) -> None:
        await self._navigate_during_paid_operation("preview")

    async def test_paid_retry_navigation_releases_owned_pending(self) -> None:
        for denied in (False, True):
            with self.subTest(denied=denied):
                await self._navigate_during_paid_operation("retry", denied=denied)

    async def test_paid_preview_return_to_same_chat_rejects_old_generation(
        self,
    ) -> None:
        await self._navigate_during_paid_operation("preview", return_to_first=True)

    async def test_price_reconfirm_navigation_finishes_without_reverting_price(
        self,
    ) -> None:
        for failure in (False, True):
            with self.subTest(failure=failure):
                await self._navigate_during_paid_operation("reconfirm", failure=failure)

    async def test_price_reconfirm_return_to_same_chat_rejects_old_generation(
        self,
    ) -> None:
        await self._navigate_during_paid_operation("reconfirm", return_to_first=True)

    async def test_repreview_after_reconfirmation_navigation_releases_pending(
        self,
    ) -> None:
        for stage in ("repreview", "retry-repreview"):
            for failure in (False, True):
                with self.subTest(stage=stage, failure=failure):
                    await self._navigate_during_paid_operation(stage, failure=failure)

    async def test_preview_storage_exception_finishes_owned_pending(self) -> None:
        await self._preview_storage_exception(retry=False)

    async def test_retry_storage_exception_finishes_owned_pending(self) -> None:
        await self._preview_storage_exception(retry=True)

    async def _preview_storage_exception(self, *, retry: bool) -> None:
        for navigate in (False, True):
            with self.subTest(navigate=navigate):
                self.page = FakePage()
                first_id = await self._create_chat(ChatMode.PAID)
                second_id = await self._create_chat(ChatMode.FREE)
                if retry:
                    seed, _ = self._controller(
                        [_known_error(ChatErrorType.INVALID_REQUEST)]
                    )
                    await self._activate(seed)
                    await seed.select_chat(first_id)
                    await seed.submit_message("failed paid request")
                    await seed.confirm_paid_request()
                    await seed.lock_application()
                controller, client = self._controller([_success("next answer")])
                await self._activate(controller)
                await controller.select_chat(first_id)
                self._set_editor(controller, "draft before local error")
                before = self.message_repository.list_turns(first_id)
                sending = controller._interaction._sending_service
                method = "preview_failed_turn" if retry else "preview_message"
                original = getattr(sending, method)
                repository = self.message_repository if retry else self.chat_repository
                read_name = "get_turn" if retry else "list_messages"
                read = getattr(repository, read_name)
                entered, release = asyncio.Event(), asyncio.Event()

                def read_then_fail(*args, **kwargs):
                    read(*args, **kwargs)
                    raise sqlite3.OperationalError("synthetic SQLite preview failure")

                async def delayed(*args, **kwargs):
                    entered.set()
                    await asyncio.wait_for(release.wait(), 3)
                    with patch.object(repository, read_name, read_then_fail):
                        return await original(*args, **kwargs)

                with patch.object(sending, method, delayed):
                    task = asyncio.create_task(
                        controller.request_retry_turn(before[0].id)
                        if retry
                        else controller.submit_message("draft before local error")
                    )
                    try:
                        await asyncio.wait_for(entered.wait(), 3)
                        self.assertTrue(controller._interaction.busy)
                        if navigate:
                            await controller.select_chat(second_id)
                            self._set_editor(controller, "next free draft")
                        foreign = ft.AlertDialog(title=ft.Text("Independent dialog"))
                        self.page.show_dialog(foreign)
                    finally:
                        release.set()
                        result = await asyncio.wait_for(
                            asyncio.gather(task, return_exceptions=True), 3
                        )
                self.assertEqual(result, [None])
                workspace = controller._workspace_controller
                self.assertIsNone(workspace._pending_send)
                self.assertFalse(controller._interaction.busy)
                view = controller._workspace_view
                assert view is not None and view.composer is not None
                self.assertFalse(view.composer.busy)
                self.assertEqual(self.page.dialogs, [foreign])
                self.assertEqual(
                    view.composer.status.value,
                    "" if navigate else "Локальную операцию не удалось завершить.",
                )
                self.assertEqual(client.calls, 0)
                self.assertEqual(self.message_repository.list_turns(first_id), before)
                self.page.pop_dialog()
                await controller.select_chat(first_id)
                assert controller._workspace_view is not None
                self.assertEqual(
                    controller._workspace_view.editor_value, "draft before local error"
                )
                await controller.select_chat(second_id)
                self._set_editor(controller, "next free draft")
                await controller.submit_message("next free draft")
                self.assertEqual(client.calls, 1)
                self.assertEqual(len(self.message_repository.list_turns(second_id)), 1)
                self.assertEqual(
                    self.draft_repository.get_draft(first_id).text,
                    "draft before local error",
                )
                await controller.lock_application()

    async def test_old_preview_or_reconfirm_cannot_clear_new_session_pending(
        self,
    ) -> None:
        for stage in ("preview", "reconfirm", "repreview"):
            with self.subTest(stage=stage):
                self.paid_model = self.catalog.paid_models[0]
                self.page = FakePage()
                first_id = await self._create_chat(ChatMode.PAID)
                second_id = await self._create_chat(ChatMode.FREE)
                if stage != "preview":
                    self.paid_model = replace(
                        self.paid_model, prompt_price_per_token=Decimal("0.000003")
                    )
                client = BlockingCompletionClient(_success("new session answer"))
                controller, _ = self._controller([], completion_client=client)
                await self._activate(controller)
                await controller.select_chat(first_id)
                self._set_editor(controller, "old paid draft")
                action = controller.submit_message("old paid draft")
                if stage != "preview":
                    await action
                    self.assertEqual(len(self.page.dialogs), 1)
                    action = controller.confirm_price_change()
                method = (
                    "reconfirm_price" if stage == "reconfirm" else "preview_message"
                )
                service_method = (
                    "reconfirm_model_price"
                    if stage == "reconfirm"
                    else "preview_message"
                )
                interaction = controller._interaction
                original = getattr(interaction, method)
                returned = asyncio.Event()
                release_result = asyncio.Event()

                async def delayed_result(*args, **kwargs):
                    result = None
                    error = None
                    try:
                        result = await original(*args, **kwargs)
                    except Exception as caught:
                        error = caught
                    returned.set()
                    await asyncio.wait_for(release_result.wait(), 3)
                    if error is not None:
                        raise error
                    return result

                with patch.object(interaction, method, delayed_result):
                    async with self._pause_call(
                        interaction._sending_service, service_method, action
                    ) as old:
                        try:
                            self.assertTrue(interaction.busy)
                            await controller.lock_application()
                            await self._activate(controller)
                            await controller.select_chat(second_id)
                            old.release.set()
                            await asyncio.wait_for(returned.wait(), 3)
                            self.assertFalse(interaction.busy)
                            self._set_editor(controller, "new session question")
                            new = asyncio.create_task(
                                controller.submit_message("new session question")
                            )
                            try:
                                await asyncio.wait_for(client.started.wait(), 3)
                                workspace = controller._workspace_controller
                                pending = workspace._pending_send
                                self.assertIsNotNone(pending)
                                view = controller._workspace_view
                                state = controller._workspace_state
                                foreign = ft.AlertDialog(title=ft.Text("New session"))
                                self.page.show_dialog(foreign)
                                release_result.set()
                                await asyncio.wait_for(old.task, 3)
                                self.assertIs(workspace._pending_send, pending)
                                self.assertIs(controller._workspace_view, view)
                                self.assertIs(controller._workspace_state, state)
                                self.assertEqual(self.page.dialogs, [foreign])
                                self.assertTrue(interaction.busy)
                                assert view is not None and view.composer is not None
                                self.assertTrue(view.composer.busy)
                                self.assertEqual(view.composer.status.value, "")
                                self.page.pop_dialog()
                            finally:
                                client.release.set()
                                await asyncio.wait_for(new, 3)
                        finally:
                            release_result.set()
                self.assertEqual(client.calls, 1)
                self.assertEqual(len(self.message_repository.list_turns(second_id)), 1)
                self.assertEqual(self.message_repository.list_turns(first_id), [])
                self.assertEqual(
                    self.draft_repository.get_draft(first_id).text, "old paid draft"
                )
                self.assertEqual(len(self.chat_repository.list_messages(second_id)), 2)
                await controller.lock_application()

    async def test_current_reconfirm_error_is_shown_and_next_send_works(self) -> None:
        for method in ("reconfirm_model_price", "preview_message"):
            with self.subTest(method=method):
                self.paid_model = self.catalog.paid_models[0]
                self.page = FakePage()
                chat_id = await self._create_chat(ChatMode.PAID)
                self.paid_model = replace(
                    self.paid_model, prompt_price_per_token=Decimal("0.000003")
                )
                controller, client = self._controller([_success("answer", cost="0.01")])
                await self._activate(controller)
                await controller.select_chat(chat_id)
                self._set_editor(controller, "paid draft")
                await controller.submit_message("paid draft")
                async with self._pause_call(
                    controller._interaction._sending_service,
                    method,
                    controller.confirm_price_change(),
                    error=RuntimeError("synthetic current error"),
                ) as operation:
                    self.assertTrue(controller._interaction.busy)
                    operation.release.set()
                    await asyncio.wait_for(operation.task, 3)
                view = controller._workspace_view
                assert view is not None and view.composer is not None
                self.assertFalse(view.composer.busy)
                self.assertEqual(
                    view.composer.status.value,
                    "Локальную операцию не удалось завершить.",
                )
                self.assertNotIn("synthetic current error", view.composer.status.value)
                self.assertEqual(view.editor_value, "paid draft")
                self.assertEqual(
                    self.draft_repository.get_draft(chat_id).text, "paid draft"
                )
                self.assertEqual(self.page.dialogs, [])
                self.assertEqual(client.calls, 0)
                self.assertEqual(self.message_repository.list_turns(chat_id), [])
                await controller.submit_message("paid draft")
                self.assertEqual(len(self.page.dialogs), 1)
                await controller.confirm_paid_request()
                self.assertEqual(client.calls, 1)
                self.assertEqual(len(self.message_repository.list_turns(chat_id)), 1)
                await controller.lock_application()

    async def test_navigation_preserves_started_paid_charge_and_unknown_reserve(
        self,
    ) -> None:
        for result in (_success("paid answer", cost="0.01"), _timeout()):
            with self.subTest(error=result.error_type):
                self.page = FakePage()
                first_id = await self._create_chat(ChatMode.PAID)
                second_id = await self._create_chat(ChatMode.FREE)
                client = BlockingCompletionClient(result)
                controller, _ = self._controller([], completion_client=client)
                await self._activate(controller)
                await controller.select_chat(first_id)
                self._set_editor(controller, "paid question")
                await controller.submit_message("paid question")
                operation = asyncio.create_task(controller.confirm_paid_request())
                try:
                    await asyncio.wait_for(client.started.wait(), 3)
                    reserved = self.message_repository.get_chat_budget(first_id)
                    assert reserved is not None
                    self.assertGreater(reserved.reserved_tokens, 0)
                    self.assertGreater(reserved.cost_reserved_usd, 0)
                    await controller.select_chat(second_id)
                    self._set_editor(controller, "independent free draft")
                finally:
                    client.release.set()
                    await asyncio.wait_for(operation, 3)
                self.assertEqual(client.calls, 1)
                self.assertEqual(len(self.message_repository.list_turns(first_id)), 1)
                budget = self.message_repository.get_chat_budget(first_id)
                assert budget is not None
                if result.accounting_unknown:
                    self.assertEqual(budget.state, BudgetState.ACCOUNTING_UNKNOWN)
                    self.assertEqual(budget.reserved_tokens, reserved.reserved_tokens)
                    self.assertEqual(
                        budget.cost_reserved_usd, reserved.cost_reserved_usd
                    )
                else:
                    self.assertEqual(budget.total_tokens_used, 30)
                    self.assertEqual(budget.cost_used_usd, Decimal("0.01"))
                    self.assertEqual(budget.reserved_tokens, 0)
                self.assertEqual(self.draft_repository.get_draft(first_id).text, "")
                client.results.append(_success("independent answer"))
                await controller.submit_message("independent free draft")
                self.assertEqual(client.calls, 2)
                self.assertEqual(len(self.message_repository.list_turns(second_id)), 1)
                self.assertEqual(
                    self.message_repository.get_chat_budget(first_id), budget
                )
                await controller.lock_application()

    async def _navigate_during_paid_operation(
        self,
        stage: str,
        *,
        denied: bool = False,
        failure: bool = False,
        return_to_first: bool = False,
    ) -> None:
        self.paid_model = self.catalog.paid_models[0]
        self.page = FakePage()
        first_id = await self._create_chat(ChatMode.PAID)
        second_id = await self._create_chat(ChatMode.FREE)
        retry = stage in ("retry", "retry-repreview")
        if retry:
            seed, seed_client = self._controller(
                [_known_error(ChatErrorType.INVALID_REQUEST)]
            )
            await self._activate(seed)
            await seed.select_chat(first_id)
            await seed.submit_message("failed paid question")
            await seed.confirm_paid_request()
            self.assertEqual(seed_client.calls, 1)
            await seed.lock_application()
        if denied:
            await self.budget_service.update_chat_limits(
                first_id,
                token_limit=16,
                max_completion_tokens=16,
                cost_limit_usd=Decimal("2"),
                cost_increase_confirmed=False,
            )
        if stage in ("reconfirm", "repreview", "retry-repreview"):
            self.paid_model = replace(
                self.paid_model,
                prompt_price_per_token=self.paid_model.prompt_price_per_token * 2,
            )
        controller, client = self._controller([_success("new free answer")])
        await self._activate(controller)
        await controller.select_chat(first_id)
        workspace = controller._workspace_controller
        first_draft = "unsent paid draft" if retry else "paid question"
        self._set_editor(controller, first_draft)
        turns_before = self.message_repository.list_turns(first_id)
        messages_before = self.chat_repository.list_messages(first_id)
        target = controller._interaction._sending_service
        method = "preview_failed_turn" if retry else "preview_message"
        if retry:
            turn_id = turns_before[0].id
            operation = controller.request_retry_turn(turn_id)
        else:
            operation = controller.submit_message(first_draft)
        if stage in ("reconfirm", "repreview", "retry-repreview"):
            await operation
            self.assertEqual(len(self.page.dialogs), 1)
            self.assertIsNotNone(workspace.pending_preview)
            if stage == "reconfirm":
                method = "reconfirm_model_price"
            operation = controller.confirm_price_change()
        async with self._pause_call(
            target,
            method,
            operation,
            error=RuntimeError("synthetic reconfirm failure") if failure else None,
        ) as paused:
            self.assertTrue(controller._interaction.busy)
            self.assertIsNotNone(workspace._pending_send)
            await controller.select_chat(second_id)
            self._set_editor(controller, "second unsent draft")
            if return_to_first:
                await controller.select_chat(first_id)
            foreign_dialog = ft.AlertDialog(title=ft.Text("Independent dialog"))
            self.page.show_dialog(foreign_dialog)
            paused.release.set()
            await asyncio.wait_for(paused.task, timeout=3)
        self.assertFalse(controller._interaction.busy)
        self.assertIsNone(workspace._pending_send)
        self.assertIsNone(workspace.pending_preview)
        self.assertEqual(self.page.dialogs, [foreign_dialog])
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        self.assertFalse(view.composer.busy)
        self.assertEqual(view.composer.status.value, "")
        self.assertEqual(client.calls, 0)
        self.assertEqual(self.message_repository.list_turns(first_id), turns_before)
        self.assertEqual(self.chat_repository.list_messages(first_id), messages_before)
        if stage in ("reconfirm", "repreview", "retry-repreview"):
            stored = self.chat_repository.get_chat(first_id)
            assert stored is not None
            self.assertEqual(
                stored.prompt_price_per_token, self.paid_model.prompt_price_per_token
            )
        self.page.pop_dialog()
        await controller.select_chat(first_id)
        assert controller._workspace_view is not None
        self.assertEqual(controller._workspace_view.editor_value, first_draft)
        await controller.select_chat(second_id)
        assert controller._workspace_view is not None
        self.assertEqual(controller._workspace_view.editor_value, "second unsent draft")
        self.assertEqual(self.draft_repository.get_draft(first_id).text, first_draft)
        self.assertEqual(
            self.draft_repository.get_draft(second_id).text, "second unsent draft"
        )
        await asyncio.wait_for(controller.submit_message("second unsent draft"), 3)
        self.assertEqual(client.calls, 1)
        self.assertEqual(len(self.message_repository.list_turns(second_id)), 1)
        self.assertEqual(
            [
                message.content
                for message in self.chat_repository.list_messages(second_id)
            ],
            ["second unsent draft", "new free answer"],
        )
        self.assertEqual(self.draft_repository.get_draft(first_id).text, first_draft)
        self.assertEqual(self.draft_repository.get_draft(second_id).text, "")
        await controller.lock_application()

    def _set_editor(self, controller: ChatSessionController, text: str) -> None:
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = text
        view.composer._apply_state()

    async def test_old_send_error_after_relogin_does_not_reach_other_chat(self) -> None:
        await self._finish_send_after_transition(relogin=True, same_chat=False)

    async def test_old_send_error_after_relogin_does_not_reach_same_chat(self) -> None:
        await self._finish_send_after_transition(relogin=True, same_chat=True)

    async def test_old_limits_read_after_relogin_does_not_open_dialog(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        controller, _ = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        entered = asyncio.Event()
        release = asyncio.Event()
        original = controller._interaction.load_state
        calls = 0

        async def delayed_load(target: str):
            nonlocal calls
            calls += 1
            state = await original(target)
            if calls == 1:
                entered.set()
                await asyncio.wait_for(release.wait(), timeout=3)
            return state

        with patch.object(controller._interaction, "load_state", delayed_load):
            operation = asyncio.create_task(controller.request_edit_limits(chat_id))
            try:
                await asyncio.wait_for(entered.wait(), timeout=3)
                await controller.lock_application()
                await self._activate(controller)
                await controller.select_chat(chat_id)
                self.assertEqual(self.page.dialogs, [])
                release.set()
                await asyncio.wait_for(operation, timeout=3)
                self.assertEqual(self.page.dialogs, [])
            finally:
                release.set()
                await asyncio.wait_for(operation, timeout=3)

    async def _finish_send_after_transition(
        self,
        *,
        relogin: bool,
        same_chat: bool,
        result: ChatCompletionResult | None = None,
    ) -> None:
        first_id = await self._create_chat(ChatMode.FREE)
        second_id = await self._create_chat(
            ChatMode.FREE, now=NOW + timedelta(microseconds=1)
        )
        controller, client = self._controller(
            [result or _known_error(ChatErrorType.RATE_LIMIT_EXCEEDED, retry_after=23)]
        )
        await self._activate(controller)
        await controller.select_chat(first_id)
        entered = asyncio.Event()
        release = asyncio.Event()
        original = self.chat_service.list_chats
        calls = 0

        async def delayed_list():
            nonlocal calls
            calls += 1
            chats = await original()
            # Первый запрос обновляет резерв, второй - завершённый результат.
            if calls == 2:
                entered.set()
                await asyncio.wait_for(release.wait(), timeout=3)
            return chats

        with patch.object(self.chat_service, "list_chats", delayed_list):
            operation = asyncio.create_task(controller.submit_message("old question"))
            try:
                await asyncio.wait_for(entered.wait(), timeout=3)
                if relogin:
                    await controller.lock_application()
                    await self._activate(controller)
                target = first_id if same_chat else second_id
                await controller.select_chat(target)
                view = controller._workspace_view
                assert view is not None and view.composer is not None
                self.assertEqual(view.composer.status.value, "")
                release.set()
                await asyncio.wait_for(operation, timeout=3)
                self.assertIs(controller._workspace_view, view)
                self.assertEqual(view.composer.status.value, "")
                self.assertEqual(controller.selected_chat_id, target)
                self.assertEqual(client.calls, 1)
                turns = self.message_repository.list_turns(first_id)
                self.assertEqual(len(turns), 1)
                self.assertEqual(
                    turns[0].error_type,
                    result.error_type if result else ChatErrorType.RATE_LIMIT_EXCEEDED,
                )
                self.assertEqual(
                    len(self.chat_repository.list_messages(first_id)),
                    2 if result else 1,
                )
                budget = self.message_repository.get_chat_budget(first_id)
                assert budget is not None
                self.assertEqual(budget.reserved_tokens, 0)
            finally:
                release.set()
                await asyncio.wait_for(operation, timeout=3)

    async def test_old_send_error_after_chat_change_is_hidden(self) -> None:
        await self._finish_send_after_transition(relogin=False, same_chat=False)

    async def test_old_length_notice_after_relogin_is_hidden(self) -> None:
        await self._finish_send_after_transition(
            relogin=True,
            same_chat=True,
            result=replace(_success("truncated answer"), finish_reason="length"),
        )

    async def test_current_error_and_length_survive_view_replacement(self) -> None:
        for result, expected in (
            (_known_error(ChatErrorType.RATE_LIMIT_EXCEEDED, retry_after=23), "23 с"),
            (
                replace(_success("short answer"), finish_reason="length"),
                "ограничению длины",
            ),
        ):
            with self.subTest(result=result.error_type):
                chat_id = await self._create_chat(ChatMode.FREE)
                controller, client = self._controller([result])
                await self._activate(controller)
                await controller.select_chat(chat_id)
                original = controller._workspace_controller._refresh_workspace
                views = []

                async def replace_view(scroll: bool) -> None:
                    views.append(controller._workspace_view)
                    controller._clear_workspace()
                    await original(scroll)

                with patch.object(
                    controller._workspace_controller, "_refresh_workspace", replace_view
                ):
                    await controller.submit_message("current question")
                view = controller._workspace_view
                assert view is not None and view.composer is not None
                self.assertEqual(len(views), 2)
                self.assertIsNot(view, views[-1])
                self.assertIn(expected, view.composer.status.value)
                self.assertEqual(client.calls, 1)

    async def test_limits_read_background_chat_change_or_new_view_is_ignored(
        self,
    ) -> None:
        for transition in ("background", "other-chat", "same-chat-relogin", "new-view"):
            for failure in (False, True):
                with self.subTest(transition=transition, failure=failure):
                    chat_id = await self._create_chat(ChatMode.FREE)
                    other_id = await self._create_chat(ChatMode.FREE)
                    controller, _ = self._controller([])
                    await self._activate(controller)
                    await controller.select_chat(chat_id)
                    async with self._pause_call(
                        controller._interaction,
                        "load_state",
                        controller.request_edit_limits(chat_id),
                        error=RuntimeError("synthetic read failure")
                        if failure
                        else None,
                    ) as operation:
                        if transition == "background":
                            await controller.lock_application()
                        elif transition == "other-chat":
                            await controller.select_chat(other_id)
                        elif transition == "same-chat-relogin":
                            await controller.lock_application()
                            await self._activate(controller)
                            await controller.select_chat(chat_id)
                        else:
                            controller._clear_workspace()
                            await controller._refresh_workspace_from_interaction(False)
                        view = controller._workspace_view
                        state = controller._workspace_state
                        operation.release.set()
                        await asyncio.wait_for(operation.task, timeout=3)
                        self.assertEqual(len(self.page.dialogs), 0)
                        self.assertIs(controller._workspace_view, view)
                        self.assertIs(controller._workspace_state, state)
                        if view is not None:
                            assert view.composer is not None
                            self.assertEqual(view.composer.status.value, "")

    async def test_limits_read_does_not_replace_competing_dialog(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        controller, _ = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        async with self._pause_call(
            controller._interaction,
            "load_state",
            controller.request_edit_limits(chat_id),
        ) as operation:
            await controller.request_edit_limits(chat_id)
            self.assertEqual(len(self.page.dialogs), 1)
            current = controller._workspace_controller._limits_dialog
            operation.release.set()
            await asyncio.wait_for(operation.task, timeout=3)
            self.assertEqual(len(self.page.dialogs), 1)
            self.assertIs(controller._workspace_controller._limits_dialog, current)

    async def test_current_limits_read_exception_is_displayed(self) -> None:
        chat_id = await self._create_chat(ChatMode.FREE)
        controller, _ = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        async with self._pause_call(
            controller._interaction,
            "load_state",
            controller.request_edit_limits(chat_id),
            error=RuntimeError("synthetic read failure"),
        ) as operation:
            operation.release.set()
            await asyncio.wait_for(operation.task, timeout=3)
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        self.assertEqual(view.composer.status.value, "Не удалось загрузить лимиты чата")

    async def test_preview_failure_after_relogin_does_not_change_new_workspace(
        self,
    ) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        await self.budget_service.update_chat_limits(
            chat_id,
            token_limit=16,
            max_completion_tokens=16,
            cost_limit_usd=Decimal("2"),
            cost_increase_confirmed=False,
        )
        controller, client = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        async with self._pause_call(
            self.chat_service,
            "list_chats",
            controller.submit_message("too long for limit"),
        ) as operation:
            await controller.lock_application()
            await self._activate(controller)
            await controller.select_chat(chat_id)
            view = controller._workspace_view
            state = controller._workspace_state
            operation.release.set()
            await asyncio.wait_for(operation.task, timeout=3)
            self.assertIs(controller._workspace_view, view)
            self.assertIs(controller._workspace_state, state)
            assert view is not None and view.composer is not None
            self.assertEqual(view.composer.status.value, "")
            self.assertEqual(client.calls, 0)
            self.assertEqual(self.message_repository.list_turns(chat_id), [])

    async def test_current_preview_failure_survives_view_replacement(self) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        await self.budget_service.update_chat_limits(
            chat_id,
            token_limit=16,
            max_completion_tokens=16,
            cost_limit_usd=Decimal("2"),
            cost_increase_confirmed=False,
        )
        controller, client = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        previous = controller._workspace_view
        original = controller._workspace_controller._refresh_workspace

        async def replace_view(scroll: bool) -> None:
            controller._clear_workspace()
            await original(scroll)

        with patch.object(
            controller._workspace_controller, "_refresh_workspace", replace_view
        ):
            await controller.submit_message("too long for limit")
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        self.assertIsNot(view, previous)
        self.assertIn("остатка общего лимита токенов", view.composer.status.value)
        self.assertFalse(view.composer.busy)
        self.assertEqual(client.calls, 0)
        self.assertEqual(self.message_repository.list_turns(chat_id), [])

    async def test_stale_limits_save_preserves_committed_accounting_only(self) -> None:
        first_id = await self._create_chat(ChatMode.FREE)
        second_id = await self._create_chat(ChatMode.FREE)
        controller, _ = self._controller([])
        await self._activate(controller)
        await controller.select_chat(first_id)
        await controller.request_edit_limits(first_id)
        async with self._pause_call(
            controller._interaction,
            "save_limits",
            controller.submit_existing_chat_limits("2000", "128", None),
        ) as operation:
            await controller.lock_application()
            await self._activate(controller)
            await controller.select_chat(second_id)
            state = controller._workspace_state
            operation.release.set()
            await asyncio.wait_for(operation.task, timeout=3)
            self.assertIs(controller._workspace_state, state)
            self.assertEqual(len(self.page.dialogs), 0)
            budget = self.message_repository.get_chat_budget(first_id)
            assert budget is not None
            self.assertEqual(budget.token_limit, 2000)
            self.assertEqual(budget.max_completion_tokens, 128)

    async def test_stale_price_confirmation_error_does_not_change_new_workspace(
        self,
    ) -> None:
        chat_id = await self._create_chat(ChatMode.PAID)
        self.paid_model = replace(
            self.paid_model, prompt_price_per_token=Decimal("0.000002")
        )
        controller, client = self._controller([])
        await self._activate(controller)
        await controller.select_chat(chat_id)
        await controller.submit_message("price changes")
        self.assertEqual(len(self.page.dialogs), 1)
        async with self._pause_call(
            controller._interaction,
            "reconfirm_price",
            controller.confirm_price_change(),
            error=RuntimeError("synthetic price error"),
        ) as operation:
            await controller.lock_application()
            await self._activate(controller)
            await controller.select_chat(chat_id)
            view = controller._workspace_view
            operation.release.set()
            await asyncio.wait_for(operation.task, timeout=3)
            assert view is not None and view.composer is not None
            self.assertEqual(view.composer.status.value, "")
            self.assertEqual(len(self.page.dialogs), 0)
            self.assertEqual(client.calls, 0)

    async def test_stale_unknown_release_does_not_change_new_workspace(self) -> None:
        for failure in (False, True):
            with self.subTest(failure=failure):
                first_id = await self._create_chat(ChatMode.FREE)
                second_id = await self._create_chat(ChatMode.FREE)
                controller, client = self._controller([_timeout()])
                await self._activate(controller)
                await controller.select_chat(first_id)
                await controller.submit_message("timeout question")
                turn = self.message_repository.list_turns(first_id)[0]
                await controller.request_release_unknown(turn.id)
                async with self._pause_call(
                    controller._interaction,
                    "release_unknown",
                    controller.confirm_release_unknown(),
                    error=RuntimeError("synthetic release error") if failure else None,
                ) as operation:
                    await controller.lock_application()
                    await self._activate(controller)
                    await controller.select_chat(second_id)
                    view = controller._workspace_view
                    state = controller._workspace_state
                    operation.release.set()
                    await asyncio.wait_for(operation.task, timeout=3)
                    self.assertIs(controller._workspace_state, state)
                    assert view is not None and view.composer is not None
                    self.assertEqual(view.composer.status.value, "")
                    self.assertEqual(len(self.page.dialogs), 0)
                    self.assertEqual(client.calls, 1)
                    budget = self.message_repository.get_chat_budget(first_id)
                    assert budget is not None
                    self.assertEqual(budget.reserved_tokens, 0)

    async def test_background_preserves_paid_charge_and_unknown_reservation(
        self,
    ) -> None:
        for result in (_success("accounted answer", cost="0.01"), _timeout()):
            with self.subTest(result=result.error_type):
                chat_id = await self._create_chat(ChatMode.PAID)
                client = BlockingCompletionClient(result)
                controller, _ = self._controller([], completion_client=client)
                await self._activate(controller)
                await controller.select_chat(chat_id)
                await controller.submit_message("accounted question")
                operation = asyncio.create_task(controller.confirm_paid_request())
                try:
                    await asyncio.wait_for(client.started.wait(), timeout=3)
                    reserved = self.message_repository.get_chat_budget(chat_id)
                    assert reserved is not None
                    self.assertGreater(reserved.reserved_tokens, 0)
                    self.assertGreater(reserved.cost_reserved_usd, Decimal("0"))
                    await controller.lock_application()
                    client.release.set()
                    await asyncio.wait_for(operation, timeout=3)
                    self.assertIsNone(controller._workspace_state)
                    self.assertIsNone(controller._workspace_view)
                    self.assertEqual(len(self.page.dialogs), 0)
                    self.assertEqual(client.calls, 1)
                    budget = self.message_repository.get_chat_budget(chat_id)
                    assert budget is not None
                    self.assertEqual(
                        len(self.message_repository.list_turns(chat_id)), 1
                    )
                    if result.accounting_unknown:
                        self.assertEqual(budget.state, BudgetState.ACCOUNTING_UNKNOWN)
                        self.assertEqual(
                            budget.reserved_tokens, reserved.reserved_tokens
                        )
                        self.assertEqual(
                            budget.cost_reserved_usd, reserved.cost_reserved_usd
                        )
                    else:
                        self.assertEqual(budget.total_tokens_used, 30)
                        self.assertEqual(budget.cost_used_usd, Decimal("0.01"))
                        self.assertEqual(budget.reserved_tokens, 0)
                        self.assertEqual(
                            len(self.chat_repository.list_messages(chat_id)), 2
                        )
                finally:
                    client.release.set()
                    await asyncio.wait_for(operation, timeout=3)

    @asynccontextmanager
    async def _pause_call(
        self,
        target: object,
        method: str,
        awaitable: Awaitable[None],
        *,
        error: Exception | None = None,
    ):
        """Задерживает только первый результат реального SQLite-обработчика."""
        original = getattr(target, method)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def delayed(*args, **kwargs):
            nonlocal calls
            calls += 1
            number = calls
            result = await original(*args, **kwargs)
            if number == 1:
                entered.set()
                await asyncio.wait_for(release.wait(), timeout=3)
                if error is not None:
                    raise error
            return result

        async def run_operation() -> None:
            await awaitable

        with patch.object(target, method, delayed):
            task = asyncio.create_task(run_operation())
            try:
                await asyncio.wait_for(entered.wait(), timeout=3)
                yield _PausedOperation(task, release)
            finally:
                release.set()
                await asyncio.wait_for(task, timeout=3)

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
            ChatDraftService(self.draft_repository),
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
