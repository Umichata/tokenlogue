"""Linux использует общий путь восстановления и синхронный отзыв доступа."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from app import AppController  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import AuthStatus, InitialRoute  # noqa: E402
from auth.service import AuthService  # noqa: E402
from chat.accounting import ChatBudgetService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from i18n import configure_localization  # noqa: E402
from platform_security.device_recovery import (  # noqa: E402
    RecoveryProvider,
    RecoveryStatus,
)
from preferences import PreferencesStore  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.data_protection import DATA_KEY_ALIAS  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests import test_app as fixtures  # noqa: E402
from tests import (
    test_encryption_initialization as initialization_fixtures,  # noqa: E402
)
from tests.test_app_recovery import RecoveryAuth  # noqa: E402
from tests.test_data_protection import Provider  # noqa: E402
from tests.test_encryption_initialization import snapshot  # noqa: E402


class LinuxPage(fixtures.FakePage):
    platform = ft.PagePlatform.LINUX


class LinuxParityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.page = LinuxPage()
        self.auth = RecoveryAuth()
        self.controller = fixtures._make_controller(self.page, self.auth)
        self.addCleanup(self.controller.dispose)
        await self.controller.start()

    async def test_linux_forgot_pin_stays_visible_when_provider_unavailable(self):
        self.auth.recovery_available = False
        self.controller._show_pin_login()
        view = self.controller._pin_login_view
        assert view is not None
        self.assertIsNotNone(view.forgot_pin_button)
        await self.controller.request_recovery()
        self.assertIsNotNone(self.controller._code_entry_view)
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(self.controller._chat_controller.session_active)
        self.assertEqual(self.auth.recovery_calls, 0)

    async def test_real_session_event_seals_synchronously_before_flush(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def flush():
            entered.set()
            await release.wait()
            return True

        with patch.object(self.controller._chat_controller, "flush_drafts", flush):
            self.controller.prepare_system_lock("screen_lock")
            self.assertGreater(self.auth.lock_access_calls, 0)
            self.assertIsNone(self.controller._pin_login_view)
            self.assertFalse(self.controller._chat_controller.session_active)
            await asyncio.wait_for(entered.wait(), 2)
            release.set()
            await self.controller.wait_system_lock()
        self.assertIsNotNone(self.controller._pin_login_view)
        self.assertFalse(self.controller._chat_controller.session_active)

    async def test_linux_focus_loss_does_not_cancel_own_prompt(self):
        await self.controller.request_system_recovery()
        task = asyncio.create_task(self.controller.request_system_recovery())
        try:
            await asyncio.wait_for(self.auth.recovery_started.wait(), 2)
            view = self.controller._recovery_view
            for state in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE):
                event = type("Event", (), {"state": state})()
                await self.controller.handle_lifecycle_change(
                    cast(ft.AppLifecycleStateChangeEvent, event)
                )
            self.assertIs(self.controller._recovery_view, view)
            self.assertEqual(self.auth.cancel_recovery_calls, 0)
            self.auth.recovery_release.set()
            await task
            self.assertIsNotNone(self.controller._pin_setup_view)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class LinuxRecoveryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Общий путь использует SQLite и fake SecureStorage, без системных aliases."""

    async def asyncSetUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.fixture = initialization_fixtures.EncryptionInitializationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.provider = Provider()
        self.page = LinuxPage()
        self.protection = self.fixture.protection()
        self.credentials = FletSecureCredentials(self.fixture.storage)
        self.validator = cast(KeyValidator, fixtures.FakeKeyValidator())
        self.auth = AuthService(
            self.validator,
            self.credentials,
            self.fixture.database,
            protection=self.protection,
            recovery_provider=cast(RecoveryProvider, self.provider),
            pin_hasher=self.fixture.hasher,
        )
        self.controller = AppController(
            cast(ft.Page, self.page),
            self.auth,
            self.validator,
            ChatService(
                SqliteChatRepository(
                    self.fixture.database.path, access=self.fixture.access
                )
            ),
            cast(ModelCatalogService, fixtures.FakeCatalogService()),
            ChatBudgetService(
                SqliteMessageRepository(
                    self.fixture.database.path, access=self.fixture.access
                )
            ),
            cast(MessageSendingService, object()),
            ChatDraftService(
                SqliteDraftRepository(
                    self.fixture.database.path, access=self.fixture.access
                )
            ),
            data_access=self.fixture.access,
        )
        self.addCleanup(self.controller.dispose)
        self.updates = patch.object(ft.Control, "update", return_value=None)
        self.updates.start()
        self.addCleanup(self.updates.stop)
        await self.controller.start()
        self.fixture.storage.read_keys.clear()

    async def challenge(self):
        self.fixture.storage.read_keys.clear()
        await self.controller.request_system_recovery()
        self.assertIsNotNone(self.controller._recovery_view)
        self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.read_keys)
        await self.controller.request_system_recovery()

    async def assert_success(self, *, protected):
        fx = self.fixture
        if protected:
            await self.protection.unlock("0123", fx.stored())
            self.protection.lock()
        old_key = fx.storage.values.get(DATA_KEY_ALIAS)
        registration = fx.stored().registration_id
        api_key = await self.credentials.get_api_key()
        await self.challenge()
        self.assertFalse(fx.access.unlocked)
        self.assertFalse(self.controller._chat_controller.session_active)
        token = self.controller._pending_recovery_token
        assert token is not None
        await self.controller.confirm_recovery("4567", token)
        self.assertTrue(fx.access.unlocked)
        self.assertTrue(self.controller._chat_controller.session_active)
        with fx.access.authorize("read") as cipher:
            current = snapshot(fx.database.path, cipher)
        for table in fx.original:
            if table != "auth_state":
                self.assertEqual(current[table], fx.original[table], table)
        self.assertEqual(fx.stored().registration_id, registration)
        self.assertEqual(await self.credentials.get_api_key(), api_key)
        key = fx.storage.values[DATA_KEY_ALIAS]
        if old_key is not None:
            self.assertEqual(key, old_key)
        self.controller.prepare_close()
        await self.controller.flush_drafts()
        self.assertFalse(fx.access.unlocked)
        restarted = fx.restart()
        auth = AuthService(
            self.validator,
            self.credentials,
            fx.database,
            protection=restarted,
            pin_hasher=fx.hasher,
            recovery_provider=cast(RecoveryProvider, self.provider),
        )
        self.assertEqual((await auth.initialize()).initial_route, InitialRoute.PIN)
        self.assertEqual((await auth.login("0123")).status, AuthStatus.INVALID_PIN)
        self.assertFalse(fx.access.unlocked)
        self.assertEqual((await auth.login("4567")).status, AuthStatus.AUTHENTICATED)
        self.assertEqual(fx.storage.values[DATA_KEY_ALIAS], key)
        restarted.lock()

    async def test_schema6_first_key_migration_through_app_and_restart(self):
        await self.assert_success(protected=False)

    async def test_schema7_same_key_and_all_data_after_recovery_restart(self):
        await self.assert_success(protected=True)

    async def test_denial_timeout_unavailable_never_read_dek_or_show_pin_choice(self):
        before = self.fixture.database.path.read_bytes()
        aliases = dict(self.fixture.storage.values)
        for status in (
            RecoveryStatus.CANCELLED,
            RecoveryStatus.TIMEOUT,
            RecoveryStatus.UNAVAILABLE,
            RecoveryStatus.ERROR,
        ):
            with self.subTest(status=status):
                self.provider.status = status
                await self.challenge()
                self.assertIsNone(self.controller._pin_setup_view)
                self.assertFalse(self.fixture.access.unlocked)
                self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.read_keys)
                self.assertEqual(self.fixture.database.path.read_bytes(), before)
                self.assertEqual(self.fixture.storage.values, aliases)
                await self.controller.cancel_recovery()

    async def test_missing_protected_dek_cannot_be_replaced(self):
        fx = self.fixture
        await self.protection.unlock("0123", fx.stored())
        self.protection.lock()
        del fx.storage.values[DATA_KEY_ALIAS]
        before = fx.database.path.read_bytes()
        aliases = dict(fx.storage.values)
        await self.challenge()
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(fx.access.unlocked)
        self.assertEqual(fx.database.path.read_bytes(), before)
        self.assertEqual(fx.storage.values, aliases)

    async def test_system_lock_rejects_late_proof_and_keeps_database_closed(self):
        self.provider.release = asyncio.Event()
        await self.controller.request_system_recovery()
        pending = asyncio.create_task(self.controller.request_system_recovery())
        await self.provider.started.wait()
        self.controller.prepare_system_lock("sleep")
        self.assertFalse(self.fixture.access.unlocked)
        self.assertIsNone(self.controller._recovery_view)
        self.provider.release.set()
        await pending
        await self.controller.wait_system_lock()
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertIsNotNone(self.controller._pin_login_view)
        self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.read_keys)
        self.assertFalse(self.fixture.access.unlocked)

    async def test_language_change_revokes_active_challenge_before_callback(self):
        self.provider.release = asyncio.Event()
        await self.controller.request_system_recovery()
        pending = asyncio.create_task(self.controller.request_system_recovery())
        await self.provider.started.wait()
        self.controller.handle_language_change()
        self.assertIsNone(self.controller._recovery_view)
        self.assertFalse(self.fixture.access.unlocked)
        self.provider.release.set()
        await pending
        await self.controller.wait_system_lock()
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertNotIn(DATA_KEY_ALIAS, self.fixture.storage.read_keys)

    async def test_language_change_clears_unused_new_pin_grant(self):
        await self.challenge()
        token = self.controller._pending_recovery_token
        assert token is not None
        choice = self.controller._pin_setup_view
        assert choice is not None
        choice.pin_field.value = "4567"
        self.controller.handle_language_change()
        self.assertIsNone(self.controller._pending_recovery_token)
        self.assertEqual(choice.pin_field.value, "")
        await self.controller.wait_system_lock()
        await self.controller.confirm_recovery("4567", token)
        self.assertFalse(self.fixture.access.unlocked)
        self.assertTrue(
            self.fixture.hasher.verify("0123", self.fixture.stored().pin_record)
        )

    async def test_new_pin_write_failure_keeps_old_pin_and_allows_fresh_retry(self):
        fx = self.fixture
        await self.protection.unlock("0123", fx.stored())
        self.protection.lock()
        old_key = fx.storage.values[DATA_KEY_ALIAS]
        await self.challenge()
        token = self.controller._pending_recovery_token
        assert token is not None
        with patch.object(
            fx.database, "save_auth_state", side_effect=OSError("fixture-write-failure")
        ):
            await self.controller.confirm_recovery("4567", token)
        self.assertFalse(fx.access.unlocked)
        self.assertEqual(fx.storage.values[DATA_KEY_ALIAS], old_key)
        self.assertTrue(fx.hasher.verify("0123", fx.stored().pin_record))
        await self.controller.cancel_recovery()
        await self.challenge()
        token = self.controller._pending_recovery_token
        assert token is not None
        await self.controller.confirm_recovery("4567", token)
        self.assertTrue(fx.access.unlocked)

    async def test_screen_lock_persists_latest_real_encrypted_draft_before_pin(self):
        fx = self.fixture
        await self.controller.submit_pin("0123")
        self.assertTrue(fx.access.unlocked)
        view = self.controller._chat_controller._workspace_view
        assert view is not None
        chat_id = self.controller._chat_controller.selected_chat_id
        assert chat_id is not None
        view.restore_editor("SYNTHETIC_LAST_LINUX_DRAFT — 🙂")
        self.controller.prepare_system_lock("screen_lock")
        self.assertFalse(fx.access.unlocked)
        self.assertFalse(self.controller._chat_controller.session_active)
        await self.controller.wait_system_lock()
        self.assertIsNotNone(self.controller._pin_login_view)
        self.assertFalse(fx.access.unlocked)
        await self.controller.submit_pin("0123")
        repo = SqliteDraftRepository(fx.database.path, access=fx.access)
        saved = repo.get_draft(chat_id)
        self.assertEqual(saved.text, "SYNTHETIC_LAST_LINUX_DRAFT — 🙂")


class LinuxCompositionCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_start_closes_watcher_before_propagating(self):
        import main as composition

        watcher = SimpleNamespace(
            start=AsyncMock(side_effect=asyncio.CancelledError), aclose=AsyncMock()
        )
        controller = SimpleNamespace(prepare_system_lock=lambda *_: None)
        with patch(
            "platform_security.linux_session.LinuxSessionWatcher", return_value=watcher
        ):
            with self.assertRaises(asyncio.CancelledError):
                await composition.start_linux_session_watch(
                    cast(AppController, controller)
                )
        watcher.aclose.assert_awaited_once()
