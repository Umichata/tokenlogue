"""Замена ключа проходит через настоящее меню и защищённую сессию без сети."""

from __future__ import annotations

# ruff: noqa: E402
import asyncio
import hashlib
import inspect
import sqlite3
import sys
import unittest
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService
from api.openrouter import KeyValidationResult, KeyValidationStatus
from app import AppController
from auth.contracts import KeyValidator
from auth.models import AuthStatus, KeyLimitInfo, KeyValidityState
from auth.service import AuthService
from chat.accounting import AccountingStatus, ChatBudgetService, TurnStatus
from chat.drafts import ChatDraftService
from chat.models import FREE_ROUTER_MODEL, ChatMode, ModelCatalog
from chat.sending import MessageSendingService
from chat.service import ChatService
from i18n import configure_localization, localize_tree, set_language
from platform_security.device_recovery import DeviceRecovery, RecoveryStatus
from preferences import PreferencesStore
from storage.chat_repository import SqliteChatRepository
from storage.data_protection import DATA_KEY_ALIAS
from storage.draft_repository import SqliteDraftRepository
from storage.message_repository import SqliteMessageRepository
from storage.secure_credentials import API_KEY_STORAGE_NAME, FletSecureCredentials
from tests import test_chat_controller as controller_fixtures
from tests import test_encryption_initialization as encryption_fixtures
from tests import test_message_sending as sending_fixtures
from tests.test_chat_menu import texts
from tests.test_data_protection import Provider
from ui.auth_view import KeyEntryView


class MenuPage(controller_fixtures.FakePage):
    def __init__(self) -> None:
        super().__init__()
        self.height = 700
        self.platform = ft.PagePlatform.LINUX

    def run_task(self, handler: Any, *args: Any) -> asyncio.Task[Any]:
        return asyncio.create_task(handler(*args))


class Validator:
    """Синтетические значения остаются только внутри памяти теста."""

    def __init__(self) -> None:
        self.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED, limit_remaining=Decimal("5")
        )
        self.calls = 0
        self.fingerprints: list[str] = []

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        self.calls += 1
        self.fingerprints.append(hashlib.sha256(api_key.encode()).hexdigest())
        return self.result


async def click(button: ft.TextButton | ft.Button) -> None:
    handler = cast(Callable[[ft.Event], Any], button.on_click)
    assert callable(handler)
    result = handler(ft.Event(name="click", control=button))
    if inspect.isawaitable(result):
        await result


class KeyReplacementMenuTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        # Используем только подготовку синтетической SQLite из прежнего теста.
        # Его тестовые методы не запускаются и пользовательские базы не читаются.
        self.fixture = encryption_fixtures.EncryptionInitializationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.temporary.cleanup)
        self.protection = self.fixture.protection()
        self.validator = Validator()
        self.credentials = FletSecureCredentials(self.fixture.storage)
        self.auth = AuthService(
            self.validator,
            self.credentials,
            self.fixture.database,
            pin_hasher=self.fixture.hasher,
            protection=self.protection,
        )
        self.page = MenuPage()
        self.chat_service = ChatService(
            SqliteChatRepository(self.fixture.database.path, self.fixture.access)
        )
        self.repository = SqliteMessageRepository(
            self.fixture.database.path, self.fixture.access
        )
        self.drafts = ChatDraftService(
            SqliteDraftRepository(self.fixture.database.path, self.fixture.access)
        )
        self.model = sending_fixtures._paid_model()
        self.completion = sending_fixtures.BlockingCompletionClient(
            sending_fixtures._success(cost="0.00003")
        )
        sending = MessageSendingService(
            self.chat_service,
            self.repository,
            self.completion,
            sending_fixtures.FakeCatalogClient((self.model,)),
            self.validator,
        )
        self.app = AppController(
            cast(ft.Page, self.page),
            self.auth,
            self.validator,
            self.chat_service,
            cast(
                ModelCatalogService,
                controller_fixtures.FakeCatalogService(
                    ModelCatalog(
                        free_models=(FREE_ROUTER_MODEL,),
                        paid_models=(),
                        available=True,
                    )
                ),
            ),
            ChatBudgetService(self.repository),
            sending,
            self.drafts,
            data_access=self.fixture.access,
        )
        self.addCleanup(self.app.dispose)
        await self.app.start()
        await self.app.submit_pin("0123")
        self.chat = self.app._chat_controller
        await controller_fixtures._wait_for_key_validation(self.chat)
        self.assertTrue(self.chat.session_active)
        self.assertTrue(self.fixture.access.unlocked)
        with self.fixture.access.authorize("read") as cipher:
            self.fixture_cipher = cipher
        self.original_state = self.snapshot()
        self.original_storage = dict(self.fixture.storage.values)

    def snapshot(self) -> dict:
        # Независимо сверяем байты своей синтетической базы и при закрытом UI.
        # Ключ проверяющего удерживается только в этом тесте, не в приложении.
        result = encryption_fixtures.snapshot(
            self.fixture.database.path, self.fixture_cipher
        )
        with sqlite3.connect(self.fixture.database.path) as connection:
            origins = dict(connection.execute("SELECT id,title_origin FROM chats"))
        for row in result["chats"]:
            row["title_origin"] = origins[row["id"]]
        return result

    def assert_protected_state_preserved(self, expected: dict | None = None) -> None:
        self.assertEqual(self.snapshot(), expected or self.original_state)
        for alias, value in self.original_storage.items():
            if alias != API_KEY_STORAGE_NAME:
                self.assertEqual(self.fixture.storage.values[alias], value)
        self.assertEqual(set(self.fixture.storage.values), set(self.original_storage))
        state = self.fixture.database.get_auth_state()
        assert state is not None
        self.assertTrue(self.fixture.hasher.verify("0123", state.pin_record))

    async def confirm_from_menu(self) -> None:
        _view, button = await self.menu_button()
        await click(button)
        dialog = cast(ft.AlertDialog, self.page.dialogs[-1])
        await click(cast(ft.Button, dialog.actions[1]))
        self.assertIsNotNone(self.app._key_view)
        self.assertTrue(self.protection.replacement_pending)

    async def relogin(self) -> None:
        await self.app.lock_application()
        self.assertFalse(self.chat.session_active)
        self.assertFalse(self.fixture.access.unlocked)
        await self.app.submit_pin("0123")
        await controller_fixtures._wait_for_key_validation(self.chat)
        self.assertTrue(self.chat.session_active)
        self.assertTrue(self.fixture.access.unlocked)

    async def menu_button(self) -> tuple[Any, ft.TextButton]:
        view = self.chat._workspace_view
        assert view is not None
        await view.open_menu()
        button = view.replace_key_button
        self.assertIsNotNone(button, "Авторизованное меню должно содержать замену")
        assert button is not None
        self.assertTrue(button.visible)
        self.assertFalse(button.disabled)
        return view, button

    async def test_valid_key_menu_reaches_one_protected_confirmation(self) -> None:
        self.assertIs(self.chat.key_validity, KeyValidityState.VALID)
        view, button = await self.menu_button()
        await click(button)
        self.assertFalse(view.menu_open)
        self.assertTrue(self.app._reset_dialog_open)
        self.assertEqual(len(self.page.dialogs), 1)
        self.assertFalse(self.protection.replacement_pending)
        await click(button)
        self.assertEqual(len(self.page.dialogs), 1)
        self.app.cancel_reset()
        self.assertTrue(self.chat.session_active)
        self.assertTrue(self.fixture.access.unlocked)

    async def test_each_key_state_click_reaches_confirmation(self) -> None:
        for validity in KeyValidityState:
            with self.subTest(validity=validity):
                self.chat._key_validity = validity
                self.chat._key_limit = KeyLimitInfo.unknown()
                view, button = await self.menu_button()
                await click(button)
                self.assertFalse(view.menu_open)
                self.assertTrue(self.app._reset_dialog_open)
                self.assertEqual(len(self.page.dialogs), 1)
                self.app.cancel_reset()
                self.assertTrue(self.chat.session_active)

    async def test_empty_workspace_keeps_replacement_and_real_controller_confirmation(
        self,
    ) -> None:
        for chat in await self.chat_service.list_chats():
            self.assertTrue(await self.chat_service.delete_chat(chat.id))
        await self.chat._show_workspace(
            expected_generation=self.chat._session_generation
        )
        self.assertIsNone(self.chat._selected_chat_id)
        view, button = await self.menu_button()
        self.assertIsNone(view.composer)
        await click(button)
        self.assertTrue(self.app._reset_dialog_open)
        self.assertEqual(len(self.page.dialogs), 1)
        self.app.cancel_reset()
        self.assertTrue(self.chat.session_active)
        self.assertEqual(self.fixture.storage.values, self.original_storage)

    async def test_visible_menu_action_does_not_retain_invalid_only_controller_guard(
        self,
    ) -> None:
        self.chat._key_validity = KeyValidityState.INVALID
        _view, button = await self.menu_button()
        self.chat._key_validity = KeyValidityState.VALID
        await click(button)
        self.assertTrue(self.app._reset_dialog_open)
        self.assertEqual(len(self.page.dialogs), 1)

    async def test_cancel_keeps_editor_old_credentials_and_same_pin_after_relogin(
        self,
    ) -> None:
        view, button = await self.menu_button()
        assert view.composer is not None
        draft = "  Synthetic edited draft\nРусский текст 🙂  "
        view.composer.set_value(draft)
        await click(button)
        dialog = cast(ft.AlertDialog, self.page.dialogs[-1])
        await click(cast(ft.TextButton, dialog.actions[0]))
        self.assertTrue(self.chat.session_active)
        self.assertEqual(view.editor_value, draft)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()
        await self.relogin()
        restored = self.chat._workspace_view
        assert restored is not None
        self.assertEqual(restored.editor_value, draft)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        current = self.snapshot()
        previous = self.original_state["chat_drafts"]
        rows = current["chat_drafts"]
        changed = [row for row, old in zip(rows, previous) if row != old]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]["content"], draft)
        self.assertEqual(
            changed[0]["revision"],
            next(
                row["revision"]
                for row in previous
                if row["chat_id"] == changed[0]["chat_id"]
            )
            + 1,
        )
        for table in set(current) - {"chat_drafts"}:
            self.assertEqual(current[table], self.original_state[table])

    async def test_success_preserves_all_protected_rows_metadata_and_pin(self) -> None:
        view = self.chat._workspace_view
        assert view is not None and view.composer is not None
        draft = "Replacement preserves newest unsaved editor\n🙂"
        view.composer.set_value(draft)
        await self.confirm_from_menu()
        flushed_state = self.snapshot()
        rows = flushed_state["chat_drafts"]
        self.assertTrue(any(row["content"] == draft for row in rows))
        new_key = "synthetic-replacement-no-network"
        await self.app.submit_key(new_key)
        self.assertTrue(self.chat.session_active)
        self.assertFalse(self.protection.replacement_pending)
        self.assertEqual(await self.credentials.get_api_key(), new_key)
        self.assert_protected_state_preserved(flushed_state)
        await self.relogin()
        self.assertEqual(await self.credentials.get_api_key(), new_key)
        self.assertEqual(self.chat._session_api_key, new_key)
        self.assertEqual(
            self.validator.fingerprints[-1],
            hashlib.sha256(new_key.encode()).hexdigest(),
        )
        self.assert_protected_state_preserved(flushed_state)

    async def test_invalid_new_key_retains_old_credentials_then_retry_works(
        self,
    ) -> None:
        await self.confirm_from_menu()
        view = self.app._key_view
        self.validator.result = KeyValidationResult(KeyValidationStatus.INVALID)
        await self.app.submit_key("synthetic-invalid-no-network")
        self.assertIs(self.app._key_view, view)
        self.assertFalse(self.chat.session_active)
        self.assertTrue(self.protection.replacement_pending)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED, limit_remaining=Decimal("5")
        )
        await self.app.submit_key("synthetic-valid-retry-no-network")
        self.assertTrue(self.chat.session_active)
        self.assert_protected_state_preserved()

    async def test_network_error_retains_old_credentials_then_retry_works(self) -> None:
        await self.confirm_from_menu()
        self.validator.result = KeyValidationResult(KeyValidationStatus.NETWORK_ERROR)
        await self.app.submit_key("synthetic-network-no-network")
        self.assertIsNotNone(self.app._key_view)
        self.assertTrue(self.protection.replacement_pending)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED, limit_remaining=Decimal("5")
        )
        await self.app.submit_key("synthetic-valid-after-network")
        self.assertTrue(self.chat.session_active)
        self.assert_protected_state_preserved()

    async def test_secure_storage_write_failure_preserves_old_key_and_all_data(
        self,
    ) -> None:
        await self.confirm_from_menu()
        self.fixture.storage.fail_set_key = API_KEY_STORAGE_NAME
        await self.app.submit_key("synthetic-write-failure")
        self.assertTrue(self.protection.replacement_pending)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()
        self.fixture.storage.fail_set_key = None
        await self.app.submit_key("synthetic-valid-after-write-failure")
        self.assertTrue(self.chat.session_active)
        self.assert_protected_state_preserved()

    async def test_secure_storage_readback_failure_restores_old_key_and_retry_works(
        self,
    ) -> None:
        await self.confirm_from_menu()
        new_key = "synthetic-readback-failure"
        original_get = self.fixture.storage.get
        failed = False

        async def inconsistent_readback(alias):
            nonlocal failed
            value = await original_get(alias)
            if alias == API_KEY_STORAGE_NAME and value == new_key and not failed:
                failed = True
                return None
            return value

        with patch.object(self.fixture.storage, "get", inconsistent_readback):
            await self.app.submit_key(new_key)
        self.assertTrue(failed)
        self.assertTrue(self.protection.replacement_pending)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()
        await self.app.submit_key(new_key)
        self.assertTrue(self.chat.session_active)
        self.assertEqual(await self.credentials.get_api_key(), new_key)
        self.assert_protected_state_preserved()

    async def test_replacement_form_localizes_without_clearing_secret_or_signup_text(
        self,
    ) -> None:
        await self.confirm_from_menu()
        view = self.app._key_view
        assert view is not None
        view.key_field.value = "synthetic-draft-secret"
        self.assertTrue(view.key_field.password)
        self.assertNotIn("synthetic-draft-secret", repr(view.key_field))
        for language, existing, first_setup in (
            ("ru", "PIN", "PIN"),
            ("en", "PIN", "PIN"),
        ):
            set_language(language)
            localize_tree(view.control)
            combined = " ".join(texts(view.control))
            self.assertIn(existing, combined)
            self.assertNotIn("choose a PIN", combined)
            self.assertNotIn("выберите PIN", combined)
            self.assertEqual(view.key_field.value, "synthetic-draft-secret")
            self.assertIn(
                first_setup, " ".join(texts(KeyEntryView(self.app.submit_key).control))
            )

    async def test_locked_new_api_key_cannot_bypass_pin_or_read_dek(self) -> None:
        await self.app.lock_application()
        self.fixture.storage.read_keys.clear()
        checks = self.validator.calls
        before = self.fixture.database.path.read_bytes()
        await self.app.request_reset()
        self.assertFalse(self.app._reset_dialog_open)
        self.assertFalse(self.protection.replacement_pending)
        self.assertIsNone(self.app._key_view)
        denied = await self.auth.start_setup("synthetic-locked-bypass-attempt")
        self.assertIs(denied.status, AuthStatus.PIN_REQUIRED)
        await self.app.submit_key("synthetic-locked-bypass-attempt")
        self.assertEqual(self.validator.calls, checks)
        self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.read_keys)
        self.assertFalse(self.fixture.access.unlocked)
        self.assertEqual(self.fixture.database.path.read_bytes(), before)
        self.assertEqual(self.fixture.storage.values, self.original_storage)

    async def test_missing_existing_dek_stays_closed_without_creating_key_or_empty_db(
        self,
    ) -> None:
        await self.app.lock_application()
        self.fixture.storage.values.pop(DATA_KEY_ALIAS)
        before = self.fixture.database.path.read_bytes()
        await self.app.submit_pin("0123")
        self.assertFalse(self.chat.session_active)
        self.assertFalse(self.fixture.access.unlocked)
        self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.values)
        self.assertEqual(self.fixture.database.path.read_bytes(), before)
        self.assertIsNone(self.app._key_view)

    async def test_cancelled_system_recovery_retains_pin_without_reading_dek(
        self,
    ) -> None:
        await self.app.lock_application()
        provider = Provider(RecoveryStatus.CANCELLED)
        service = AuthService(
            self.validator,
            self.credentials,
            self.fixture.database,
            pin_hasher=self.fixture.hasher,
            protection=self.protection,
            recovery_provider=cast(DeviceRecovery, provider),
        )
        self.fixture.storage.read_keys.clear()
        result = await service.recover_pin()
        self.assertIs(result.status, AuthStatus.STORAGE_ERROR)
        self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.read_keys)
        self.assertFalse(self.protection.replacement_pending)
        self.assertFalse(self.fixture.access.unlocked)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        result = await service.login("0123")
        self.assertIs(result.status, AuthStatus.AUTHENTICATED)
        self.assert_protected_state_preserved()

    async def test_key_check_busy_keeps_menu_and_action_then_reenables(self) -> None:
        view, button = await self.menu_button()
        original_dialog = view._menu_dialog
        previous_callback = cast(Callable[[ft.Event], Any], button.on_click)
        blocker = controller_fixtures.BlockingKeyValidator(
            KeyValidationResult(KeyValidationStatus.RESTRICTED)
        )
        self.chat._key_validator = cast(KeyValidator, blocker)
        await self.chat.request_key_revalidation()
        await blocker.started.wait()
        self.assertTrue(view.menu_open)
        self.assertIs(view._menu_dialog, original_dialog)
        self.assertIs(view.replace_key_button, button)
        self.assertTrue(button.visible)
        self.assertTrue(button.disabled)
        await click(button)
        await self.chat.request_key_replacement()
        self.assertFalse(self.app._reset_dialog_open)
        self.assertFalse(self.protection.replacement_pending)
        blocker.release.set()
        await controller_fixtures._wait_for_key_validation(self.chat)
        self.assertTrue(view.menu_open)
        self.assertIs(view._menu_dialog, original_dialog)
        self.assertIs(view.replace_key_button, button)
        self.assertTrue(button.visible)
        self.assertFalse(button.disabled)
        self.assertIs(self.chat.key_validity, KeyValidityState.RESTRICTED)
        assert callable(previous_callback)
        old_result = previous_callback(ft.Event(name="click", control=button))
        if inspect.isawaitable(old_result):
            await old_result
        self.assertFalse(self.app._reset_dialog_open)
        set_language("en")
        localize_tree(view.control)
        localize_tree(original_dialog)
        await click(button)
        self.assertTrue(self.app._reset_dialog_open)
        self.assertEqual(len(self.page.dialogs), 1)
        self.app.cancel_reset()
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()

    async def test_inflight_synthetic_send_keeps_reserve_completion_and_reenables_action(
        self,
    ) -> None:
        chat = await self.chat_service.create_chat_with_limits(
            ChatMode.PAID,
            self.model,
            catalog=ModelCatalog(
                free_models=(FREE_ROUTER_MODEL,),
                paid_models=(self.model,),
                available=True,
            ),
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(Decimal("5")),
            token_limit=16384,
            max_completion_tokens=1024,
            cost_limit_usd=Decimal("1"),
            paid_confirmed=True,
        )
        await self.chat.select_chat(chat.id)
        view = self.chat._workspace_view
        assert view is not None and view.composer is not None
        draft = "Synthetic completion stays within fake gateway"
        view.composer.set_value(draft)
        await self.chat.submit_message(draft)
        self.assertIsNotNone(self.chat._workspace_controller.pending_preview)
        await self.chat.request_key_replacement()
        self.assertFalse(self.app._reset_dialog_open)
        self.assertEqual(self.completion.calls, [])
        operation = asyncio.create_task(self.chat.confirm_paid_request())
        self.addAsyncCleanup(self._release_completion, operation)
        await asyncio.wait_for(self.completion.started.wait(), timeout=2)
        await view.open_menu()
        button = view.replace_key_button
        assert button is not None
        self.assertTrue(button.visible)
        self.assertTrue(button.disabled)
        before = self.snapshot()
        budget = self.repository.get_chat_budget(chat.id)
        assert budget is not None
        self.assertGreater(budget.reserved_tokens, 0)
        self.assertGreater(budget.cost_reserved_usd, 0)
        await click(button)
        await self.chat.request_key_replacement()
        self.assertFalse(self.app._reset_dialog_open)
        self.assertFalse(self.protection.replacement_pending)
        self.assertFalse(operation.done())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.completion.release.set()
        await asyncio.wait_for(operation, timeout=2)
        self.assertEqual(len(self.completion.calls), 1)
        messages = self.chat_service._repository.list_messages(chat.id)
        self.assertEqual([message.content for message in messages], [draft, "answer"])
        turns = self.repository.list_turns(chat.id)
        self.assertEqual(len(turns), 1)
        self.assertIs(turns[0].status, TurnStatus.SENT)
        self.assertIs(turns[0].accounting_status, AccountingStatus.FINAL)
        budget = self.repository.get_chat_budget(chat.id)
        assert budget is not None
        self.assertEqual(budget.reserved_tokens, 0)
        self.assertEqual(budget.cost_reserved_usd, Decimal("0"))
        self.assertEqual(budget.cost_used_usd, Decimal("0.00003"))
        self.assertEqual(self.drafts.current(chat.id).text, "")
        self.assertTrue(view.menu_open)
        self.assertIs(view.replace_key_button, button)
        self.assertTrue(button.visible)
        self.assertFalse(button.disabled)
        await click(button)
        self.assertTrue(self.app._reset_dialog_open)
        self.assertEqual(len(self.completion.calls), 1)
        self.app.cancel_reset()

    async def test_late_old_key_status_cannot_overwrite_successful_replacement(
        self,
    ) -> None:
        blocker = controller_fixtures.BlockingKeyValidator(
            KeyValidationResult(KeyValidationStatus.INVALID),
            ignore_cancellation=True,
        )
        self.chat._key_validator = cast(KeyValidator, blocker)
        await self.chat.request_key_revalidation()
        await blocker.started.wait()
        old_task = self.chat._key_validation_task
        assert old_task is not None

        async def finish_old_check() -> None:
            blocker.release.set()
            await old_task

        self.addAsyncCleanup(finish_old_check)
        await self.app.lock_application()
        self.chat._key_validator = self.validator
        await self.app.submit_pin("0123")
        await controller_fixtures._wait_for_key_validation(self.chat)
        await self.confirm_from_menu()
        new_key = "synthetic-key-after-late-status"
        await self.app.submit_key(new_key)
        self.assertTrue(self.chat.session_active)
        self.assertIs(self.chat.key_validity, KeyValidityState.VALID)
        self.assertEqual(self.chat._session_api_key, new_key)
        blocker.release.set()
        await asyncio.wait_for(old_task, timeout=2)
        self.assertTrue(self.chat.session_active)
        self.assertIs(self.chat.key_validity, KeyValidityState.VALID)
        self.assertEqual(self.chat.key_limit.remaining, Decimal("5"))
        self.assertEqual(self.chat._session_api_key, new_key)
        self.assertEqual(await self.credentials.get_api_key(), new_key)
        self.assert_protected_state_preserved()

    async def _release_completion(self, operation: asyncio.Task) -> None:
        self.completion.release.set()
        await operation

    async def test_old_confirmation_cannot_confirm_new_dialog(self) -> None:
        _view, button = await self.menu_button()
        await click(button)
        first = cast(ft.AlertDialog, self.page.dialogs[-1])
        old_confirm = cast(ft.Button, first.actions[1])
        self.app.cancel_reset()
        _view, button = await self.menu_button()
        await click(button)
        second = self.page.dialogs[-1]
        await click(old_confirm)
        self.assertTrue(self.app._reset_dialog_open)
        self.assertIs(self.page.dialogs[-1], second)
        self.assertFalse(self.protection.replacement_pending)
        self.assertTrue(self.chat.session_active)
        self.assertEqual(self.fixture.storage.values, self.original_storage)

    async def test_old_menu_and_confirmation_cannot_act_after_lock_relogin(
        self,
    ) -> None:
        _view, button = await self.menu_button()
        await click(button)
        dialog = cast(ft.AlertDialog, self.page.dialogs[-1])
        confirm = cast(ft.Button, dialog.actions[1])
        await self.relogin()
        await click(button)
        await click(confirm)
        self.assertFalse(self.app._reset_dialog_open)
        self.assertFalse(self.protection.replacement_pending)
        self.assertTrue(self.chat.session_active)
        self.assertEqual(self.fixture.storage.values, self.original_storage)
        self.assert_protected_state_preserved()

    async def test_background_rejects_old_menu_and_confirmation(self) -> None:
        self.page.platform = ft.PagePlatform.ANDROID
        _view, button = await self.menu_button()
        await click(button)
        dialog = cast(ft.AlertDialog, self.page.dialogs[-1])
        confirm = cast(ft.Button, dialog.actions[1])
        await self.app.handle_lifecycle_change(
            cast(
                ft.AppLifecycleStateChangeEvent,
                SimpleNamespace(state=ft.AppLifecycleState.PAUSE),
            )
        )
        await click(button)
        await click(confirm)
        self.assertFalse(self.chat.session_active)
        self.assertFalse(self.app._reset_dialog_open)
        self.assertFalse(self.protection.replacement_pending)
        self.assertFalse(self.fixture.access.unlocked)
        self.assertEqual(self.fixture.storage.values, self.original_storage)

    async def test_disposed_app_rejects_saved_menu_and_confirmation(self) -> None:
        _view, button = await self.menu_button()
        await click(button)
        dialog = cast(ft.AlertDialog, self.page.dialogs[-1])
        confirm = cast(ft.Button, dialog.actions[1])
        self.app.dispose()
        await click(button)
        await click(confirm)
        await self.chat.request_key_replacement()
        self.assertFalse(self.chat.session_active)
        self.assertFalse(self.app._reset_dialog_open)
        self.assertFalse(self.protection.replacement_pending)
        self.assertFalse(self.fixture.access.unlocked)
        self.assertEqual(self.fixture.storage.values, self.original_storage)


if __name__ == "__main__":
    unittest.main()
