"""First-run protection uses the real protected AppController session boundary."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from app import AppController  # noqa: E402
from auth.models import AuthResult, AuthStatus  # noqa: E402
from auth.pin import PinHasher  # noqa: E402
from auth.service import AuthService  # noqa: E402
from chat.accounting import ChatBudgetService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from i18n import configure_localization, set_language  # noqa: E402
from platform_security.local_protection import (  # noqa: E402
    CheckState,
    ObserverContext,
    ScreenState,
)
from preferences import PreferencesStore  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.data_access import DataAccess  # noqa: E402
from storage.data_protection import DataProtection  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests import test_app as app_fixtures  # noqa: E402
from tests import test_auth_service as auth_fixtures  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402
from tests.test_secure_credentials import FakeSecureStorage  # noqa: E402


class DeferredLockReply:
    def __init__(self, app):
        self.app = app
        self.screen_context = ObserverContext("linux", "fixture", 1, "fixture")
        self.requested = asyncio.Event()
        self.release = asyncio.Event()
        self.locked = False

    async def read_screen_state(self, context):
        return ScreenState(context, self.locked)

    async def request_screen_lock(self, context):
        before = self.app.protection_app_state()
        self.locked = True
        self.app.prepare_system_lock("screen_lock")
        self.app.record_normal_protection("screen", context, before)
        self.requested.set()
        await self.release.wait()


class ProtectionOperationBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_seal_reaches_PIN_while_OS_request_reply_is_pending(self):
        fx = fixtures.LinuxRecoveryIntegrationTests()
        await fx.asyncSetUp()
        self.addCleanup(fx.doCleanups)
        app = fx.controller
        self.addAsyncCleanup(app.close_protection_checks)
        await app.submit_pin("0123")
        adapter = DeferredLockReply(app)
        app.set_screen_lock_adapter(adapter)
        task = asyncio.create_task(app.request_screen_lock_test())
        try:
            await asyncio.wait_for(adapter.requested.wait(), 0.5)
            for _ in range(20):
                if app.protection_app_state().pin_visible:
                    break
                await asyncio.sleep(0.005)
            self.assertTrue(app.protection_app_state().pin_visible)
            self.assertFalse(app._operation_lock.locked())
            self.assertFalse(fx.fixture.access.unlocked)
            self.assertFalse(app._chat_controller.session_active)
        finally:
            adapter.release.set()
            await task
            await app.wait_system_lock()


class ProtectionOnboardingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.preferences_path = Path(self.temporary.name) / "preferences.json"
        self.preferences = PreferencesStore(self.preferences_path)
        configure_localization(self.preferences)
        self.addCleanup(configure_localization, PreferencesStore())
        self.database = AuthDatabase(self.temporary.name)
        self.storage = FakeSecureStorage()
        self.hasher = PinHasher(iterations=100)
        self.validator = auth_fixtures.StubValidator(
            KeyValidationResult(
                KeyValidationStatus.ACCEPTED, limit_remaining=Decimal("1")
            )
        )
        updates = patch.object(ft.Control, "update")
        updates.start()
        self.addCleanup(updates.stop)
        self.app = self.new_controller()
        await self.app.start()

    def new_controller(self, platform=ft.PagePlatform.LINUX):
        page = fixtures.LinuxPage()
        page.platform = platform
        self.page = page
        self.access = DataAccess()
        self.auth = AuthService(
            self.validator,
            FletSecureCredentials(self.storage),
            self.database,
            pin_hasher=self.hasher,
            protection=DataProtection(
                self.database.path,
                self.database,
                self.storage,
                self.access,
                pin_hasher=self.hasher,
            ),
        )
        app = AppController(
            cast(ft.Page, page),
            self.auth,
            self.validator,
            ChatService(SqliteChatRepository(self.database.path, access=self.access)),
            cast(ModelCatalogService, app_fixtures.FakeCatalogService()),
            ChatBudgetService(
                SqliteMessageRepository(self.database.path, access=self.access)
            ),
            cast(MessageSendingService, object()),
            ChatDraftService(
                SqliteDraftRepository(self.database.path, access=self.access)
            ),
            data_access=self.access,
        )
        self.addCleanup(app.dispose)
        self.addAsyncCleanup(app.close_protection_checks)
        return app

    async def register(self):
        await self.app.submit_key("synthetic-onboarding-key-no-network")
        token = self.app._pending_setup_token
        assert token is not None
        await self.app.confirm_pin_setup("0123", token)

    async def eventually(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.005)
        self.fail("Synthetic lifecycle did not settle")

    def checks(self):
        checks = self.app._local_protection
        assert checks is not None
        return checks

    async def test_opt_in_app_trace_reports_key_to_PIN_milestones_without_values(self):
        events = []
        self.assertIsNone(self.app._protection_trace)
        self.app.set_protection_trace(events.append)
        await self.app.start()
        key = "synthetic-trace-credential-never-in-records"
        await self.app.submit_key(key)
        token = self.app._pending_setup_token
        assert token is not None
        expected = [
            "app_started",
            "key_entry_build",
            "key_entry_shown",
            "key_submit_started",
            "key_result",
            "pin_setup_build",
            "pin_setup_shown",
        ]
        app_events = [item for item in events if item["event"] in expected]
        self.assertEqual([item["event"] for item in app_events], expected)
        result = next(item for item in app_events if item["event"] == "key_result")
        self.assertEqual(result["auth_status"], AuthStatus.PIN_CHOICE_REQUIRED.value)
        self.assertTrue(result["same_key_view"])
        self.assertTrue(result["setup_token_present"])
        shown = app_events[-1]
        self.assertTrue(shown["pin_setup_view"])
        self.assertTrue(shown["pin_setup_visible"])
        self.assertFalse(shown["key_view"])
        allowed = {
            "event",
            "page_linux",
            "key_view",
            "pin_setup_view",
            "pin_setup_visible",
            "same_key_view",
            "disposed",
            "suspending",
            "in_background",
            "session_open",
            "data_open",
            "pin_visible",
            "setup_token_present",
            "auth_status",
            "exception_class",
            "system_reason",
        }
        for item in app_events:
            self.assertLessEqual(item.keys(), allowed)
            for name, value in item.items():
                if name not in {
                    "event",
                    "auth_status",
                    "exception_class",
                    "system_reason",
                }:
                    self.assertIs(type(value), bool)
        encoded = json.dumps(events)
        self.assertNotIn(key, encoded)
        self.assertNotIn(token, encoded)
        count = len(events)
        self.app.set_protection_trace(None)
        await self.app.start()
        self.assertEqual(len(events), count)

    async def test_key_result_trace_precedes_rejection_of_a_late_old_view(self):
        entered, release = asyncio.Event(), asyncio.Event()
        events = []
        self.app.set_protection_trace(events.append)
        private_token = "synthetic-late-token-not-to-record"
        private_message = "synthetic-private-response-not-to-record"

        async def delayed(_key):
            entered.set()
            await release.wait()
            return AuthResult(
                AuthStatus.PIN_CHOICE_REQUIRED,
                private_message,
                pending_setup_token=private_token,
            )

        with patch.object(self.auth, "start_setup", delayed):
            task = asyncio.create_task(self.app.submit_key("synthetic-unused-key"))
            try:
                await asyncio.wait_for(entered.wait(), 0.5)
                self.app._show_pin_login()
                release.set()
                await task
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        result = next(item for item in events if item["event"] == "key_result")
        self.assertFalse(result["same_key_view"])
        self.assertTrue(result["setup_token_present"])
        self.assertEqual(result["auth_status"], AuthStatus.PIN_CHOICE_REQUIRED.value)
        self.assertFalse(any(item["event"] == "pin_setup_build" for item in events))
        self.assertNotIn(private_token, json.dumps(events))
        self.assertNotIn(private_message, json.dumps(events))

    async def test_builder_failure_trace_records_only_class_and_preserves_exception(
        self,
    ):
        events = []
        self.app.set_protection_trace(events.append)
        private_message = "synthetic-private-builder-detail-not-to-record"
        failure = ValueError(private_message)
        with patch("app.PinSetupView", side_effect=failure):
            with self.assertRaises(ValueError) as caught:
                await self.app.submit_key("synthetic-trace-key-no-network")
        self.assertIs(caught.exception, failure)
        failed = next(item for item in events if item["event"] == "pin_setup_failed")
        self.assertEqual(failed["exception_class"], "ValueError")
        self.assertFalse(any(item["event"] == "pin_setup_shown" for item in events))
        self.assertNotIn(private_message, json.dumps(events))

    async def test_failed_trace_sink_cannot_block_normal_key_to_PIN_transition(self):
        def unavailable(_event):
            raise OSError("synthetic sink unavailable")

        self.app.set_protection_trace(unavailable)
        await self.app.start()
        await self.app.submit_key("synthetic-trace-key-no-network")
        self.assertIsNotNone(self.app._pin_setup_view)
        self.assertIsNone(self.app._key_view)

    async def test_system_event_trace_uses_known_reasons_and_never_field_values(self):
        events = []
        self.app.set_protection_trace(events.append)
        await self.app.submit_key("synthetic-trace-key-no-network")
        setup = self.app._pin_setup_view
        assert setup is not None
        setup.pin_field.value = "3141"
        self.app.prepare_system_lock("screen_lock")
        await self.app.wait_system_lock()
        self.app.prepare_system_lock("synthetic-untrusted-reason-not-to-record")
        await self.app.wait_system_lock()
        system = [item for item in events if item["event"] == "system_event"]
        self.assertEqual(system[0]["system_reason"], "screen_lock")
        self.assertTrue(system[0]["pin_setup_visible"])
        self.assertNotIn("system_reason", system[-1])
        encoded = json.dumps(events)
        self.assertNotIn('"3141"', encoded)
        self.assertNotIn("synthetic-untrusted-reason-not-to-record", encoded)

    async def test_real_registration_shows_step_after_commit_and_operation_unlock(self):
        complete = self.auth.complete_setup
        before_commit = []

        async def capture(pin, token):
            before_commit.append(
                (
                    self.preferences.local_protection_onboarding,
                    self.database.get_auth_state(),
                )
            )
            return await complete(pin, token)

        offer = AsyncMock()
        with (
            patch.object(self.auth, "complete_setup", capture),
            patch.object(self.app, "_offer_code_settings", offer),
        ):
            await self.register()
        self.assertEqual(before_commit, [("pending", None)])
        self.assertIsNotNone(self.database.get_auth_state())
        self.assertTrue(self.access.unlocked)
        self.assertTrue(self.app.protection_app_state().opened)
        self.assertFalse(self.app._operation_lock.locked())
        self.assertFalse(self.app._chat_controller.workspace_visible)
        view = self.app._protection_setup_view
        assert view is not None
        self.assertEqual(self.page.controls, [view.control])
        self.assertFalse(view.start_button.disabled)
        self.assertEqual(self.preferences.local_protection_onboarding, "pending")
        offer.assert_not_awaited()

    async def test_first_step_requests_no_OS_lock_before_explicit_start(self):
        adapter = DeferredLockReply(self.app)
        self.app.set_screen_lock_adapter(adapter)
        await self.register()
        self.assertFalse(adapter.requested.is_set())
        self.assertTrue(self.app.protection_app_state().opened)
        self.assertTrue(await self.app._chat_controller.prepare_screen_lock_test())
        adapter.release.set()
        await self.app.request_screen_lock_test()
        await self.app.wait_system_lock()
        self.assertTrue(adapter.requested.is_set())
        self.assertFalse(self.access.unlocked)
        self.assertIsNotNone(self.app._pin_login_view)

    async def test_late_workspace_and_key_refresh_cannot_read_chats_during_first_step(
        self,
    ):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        chat = self.app._chat_controller
        generation = chat.session_generation
        request = chat._workspace_request_id
        with patch.object(
            chat._chat_service, "list_chats", AsyncMock(return_value=[])
        ) as read_chats:
            await chat._refresh_workspace_from_interaction(False)
            await chat._refresh_after_key_validation(generation)
            await chat._show_workspace(expected_generation=generation)
        read_chats.assert_not_awaited()
        self.assertEqual(chat._workspace_request_id, request)
        self.assertFalse(chat._workspace_request_matches(generation, request))
        self.assertFalse(chat.workspace_visible)
        self.assertEqual(self.page.controls, [view.control])

    async def test_restart_resumes_pending_step_after_normal_PIN_login(self):
        await self.register()
        registration = self.database.get_auth_state()
        assert registration is not None
        self.app.dispose()
        self.preferences = PreferencesStore(self.preferences_path)
        configure_localization(self.preferences)
        self.app = self.new_controller()
        await self.app.start()
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertIsNone(self.app._protection_setup_view)
        await self.app.submit_pin("0123")
        self.assertIsNotNone(self.app._protection_setup_view)
        self.assertFalse(self.app._chat_controller.workspace_visible)
        restored = self.database.get_auth_state()
        assert restored is not None
        self.assertEqual(restored.registration_id, registration.registration_id)

    async def test_restart_between_durable_registration_and_step_render_resumes(self):
        with patch.object(self.app, "_resume_protection_setup", AsyncMock()):
            await self.register()
        self.assertIsNone(self.app._protection_setup_view)
        self.assertEqual(self.preferences.local_protection_onboarding, "pending")
        self.assertIsNotNone(self.database.get_auth_state())
        self.app.dispose()
        self.preferences = PreferencesStore(self.preferences_path)
        configure_localization(self.preferences)
        self.app = self.new_controller()
        await self.app.start()
        self.assertIsNotNone(self.app._pin_login_view)
        await self.app.submit_pin("0123")
        self.assertIsNotNone(self.app._protection_setup_view)
        self.assertFalse(self.app._chat_controller.workspace_visible)

    async def test_real_app_seal_PIN_login_and_same_check_result_complete_first_step(
        self,
    ):
        await self.register()
        adapter = DeferredLockReply(self.app)
        self.app.set_screen_lock_adapter(adapter)
        checks = self.app._local_protection
        assert checks is not None
        checks._poll_interval = 0.001
        first = self.app._protection_setup_view
        assert first is not None
        task = asyncio.create_task(
            first._start(ft.Event(name="click", control=first.start_button))
        )
        try:
            await asyncio.wait_for(adapter.requested.wait(), 0.5)
            self.app.record_screen_transition(adapter.screen_context, True)
            await self.app.wait_system_lock()
            self.assertIsNone(self.app._protection_setup_view)
            self.assertIsNotNone(self.app._pin_login_view)
            self.assertFalse(self.access.unlocked)
            adapter.locked = False
            self.app.record_screen_transition(adapter.screen_context, False)
            adapter.release.set()
            await task
            await self.eventually(
                lambda: checks.snapshot.screen.state is CheckState.CONFIRMED
            )
            pin_view = self.app._pin_login_view
            assert pin_view is not None
            self.assertEqual(pin_view.notice.color, ft.Colors.GREEN_300)
            self.assertEqual(checks.snapshot.sleep.state, CheckState.UNTESTED)
            await self.app.submit_pin("0123")
            completed = self.app._protection_setup_view
            assert completed is not None
            self.assertIsNot(completed, first)
            self.assertEqual(self.preferences.local_protection_onboarding, "done")
            self.assertEqual(checks.snapshot.screen.state, CheckState.CONFIRMED)
            self.assertFalse(self.app._chat_controller.workspace_visible)
            self.assertFalse(completed.manual_notice.visible)
            set_language("en")
            self.app.handle_language_change()
            self.assertIs(self.app._protection_setup_view, completed)
            self.assertEqual(checks.snapshot.screen.state, CheckState.CONFIRMED)
            with patch.object(self.app, "_offer_code_settings", AsyncMock()):
                await self.app._continue_protection_setup(completed)
            self.assertTrue(self.app._chat_controller.workspace_visible)
            workspace = self.app._chat_controller._workspace_view
            assert workspace is not None
            await workspace.open_menu()
            self.assertEqual(checks.snapshot.screen.state, CheckState.CONFIRMED)
        finally:
            adapter.release.set()
            await asyncio.gather(task, return_exceptions=True)

    async def test_manual_continue_is_usable_but_does_not_confirm_protection(self):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        with patch.object(self.app, "_offer_code_settings", AsyncMock()):
            await self.app._continue_protection_setup(view)
        self.assertTrue(self.app._chat_controller.workspace_visible)
        self.assertIsNone(self.app._protection_setup_view)
        self.assertEqual(self.preferences.local_protection_onboarding, "done")
        self.assertEqual(self.checks().snapshot.screen.state, CheckState.UNTESTED)
        self.assertTrue(self.access.unlocked)

    async def test_done_marker_never_restores_green_in_a_new_process(self):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        with patch.object(self.app, "_offer_code_settings", AsyncMock()):
            await self.app._continue_protection_setup(view)
        self.app.dispose()
        self.preferences = PreferencesStore(self.preferences_path)
        configure_localization(self.preferences)
        self.app = self.new_controller()
        await self.app.start()
        await self.app.submit_pin("0123")
        self.assertIsNone(self.app._protection_setup_view)
        self.assertTrue(self.app._chat_controller.workspace_visible)
        self.assertEqual(self.checks().snapshot.screen.state, CheckState.UNTESTED)

    async def test_language_keeps_same_step_and_performs_no_OS_request(self):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        original = view.control
        adapter = DeferredLockReply(self.app)
        self.app.set_screen_lock_adapter(adapter)
        set_language("en")
        self.app.handle_language_change()
        self.assertIs(self.app._protection_setup_view, view)
        self.assertIs(view.control, original)
        self.assertEqual(self.preferences.local_protection_onboarding, "pending")
        self.assertFalse(adapter.requested.is_set())
        self.assertTrue(self.access.unlocked)

    async def test_Android_registration_has_no_desktop_step_or_marker(self):
        self.app.dispose()
        self.app = self.new_controller(ft.PagePlatform.ANDROID)
        await self.app.start()
        await self.register()
        self.assertIsNone(self.app._protection_setup_view)
        self.assertIsNone(self.preferences.local_protection_onboarding)
        self.assertTrue(self.app._chat_controller.workspace_visible)
        self.assertIsNone(self.app._local_protection)

    async def test_existing_key_replacement_does_not_restart_onboarding(self):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        with patch.object(self.app, "_offer_code_settings", AsyncMock()):
            await self.app._continue_protection_setup(view)
        original = self.database.get_auth_state()
        assert original is not None
        registration = original.registration_id
        await self.app.request_reset()
        await self.app.confirm_reset()
        self.assertIsNotNone(self.app._key_view)
        await self.app.submit_key("synthetic-replacement-no-network")
        self.assertIsNone(self.app._protection_setup_view)
        self.assertTrue(self.app._chat_controller.workspace_visible)
        self.assertEqual(self.preferences.local_protection_onboarding, "done")
        restored = self.database.get_auth_state()
        assert restored is not None
        self.assertEqual(restored.registration_id, registration)

    async def test_no_adapter_has_visible_failure_and_retry_not_permanent_spinner(self):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        await view._start(ft.Event(name="click", control=view.start_button))
        self.assertFalse(view.start_button.disabled)
        self.assertFalse(view.continue_button.disabled)
        self.assertFalse(self.checks().snapshot.screen_test_running)
        self.assertEqual(self.checks().snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(self.checks().snapshot.screen.code, "request_unavailable")

    async def test_busy_request_has_a_short_explanation_without_starting_OS_lock(self):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        adapter = DeferredLockReply(self.app)
        self.app.set_screen_lock_adapter(adapter)
        async with self.app._operation_lock:
            await self.app.request_screen_lock_test()
        self.assertTrue(view.message.visible)
        self.assertFalse(adapter.requested.is_set())
        self.assertFalse(view.start_button.disabled)
        self.assertEqual(self.checks().snapshot.screen.state, CheckState.UNTESTED)

    async def test_preferences_failure_before_registration_keeps_unsaved_profile_safe(
        self,
    ):
        await self.app.submit_key("synthetic-onboarding-key-no-network")
        token = self.app._pending_setup_token
        assert token is not None
        with patch.object(
            self.preferences,
            "set_local_protection_onboarding",
            side_effect=OSError("synthetic preferences unavailable"),
        ):
            await self.app.confirm_pin_setup("0123", token)
        self.assertIsNone(self.database.get_auth_state())
        self.assertFalse(self.access.unlocked)
        self.assertIsNone(self.app._protection_setup_view)
        setup = self.app._pin_setup_view
        assert setup is not None
        self.assertTrue(setup.message.visible)

    async def test_acknowledgement_write_error_does_not_make_saved_profile_unusable(
        self,
    ):
        await self.register()
        view = self.app._protection_setup_view
        assert view is not None
        with (
            patch.object(
                self.preferences,
                "set_local_protection_onboarding",
                side_effect=OSError("synthetic preferences unavailable"),
            ),
            patch.object(self.app, "_offer_code_settings", AsyncMock()),
        ):
            await self.app._continue_protection_setup(view)
        self.assertTrue(self.app._chat_controller.workspace_visible)
        self.assertTrue(self.access.unlocked)
        self.assertEqual(self.preferences.local_protection_onboarding, "pending")
        self.assertTrue(self.app._onboarding_handled_in_process)


class OnboardingPreferencesTests(unittest.TestCase):
    def test_concurrent_marker_and_language_sidebar_keep_all_saved_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = PreferencesStore(path)
            entered, release, other_done = (
                threading.Event(),
                threading.Event(),
                threading.Event(),
            )
            save = store._save
            failures = []

            def delayed_save(language, visible, onboarding):
                if threading.current_thread() is writer:
                    entered.set()
                    if not release.wait(3):
                        raise TimeoutError("Synthetic preference write did not release")
                save(language, visible, onboarding)

            def marker():
                try:
                    store.set_local_protection_onboarding("pending")
                except Exception as error:
                    failures.append(type(error).__name__)

            def language_and_sidebar():
                try:
                    store.set_language("en")
                    store.set_wide_sidebar_visible(False)
                except Exception as error:
                    failures.append(type(error).__name__)
                finally:
                    other_done.set()

            writer = threading.Thread(target=marker)
            other = threading.Thread(target=language_and_sidebar)
            with patch.object(store, "_save", delayed_save):
                writer.start()
                try:
                    self.assertTrue(entered.wait(2))
                    other.start()
                    # Before serialization, this worker commits stale field snapshots
                    # while the marker writer is paused. With a mutex it waits safely.
                    other_done.wait(0.2)
                finally:
                    release.set()
                    writer.join(3)
                    if other.ident is not None:
                        other.join(3)
            self.assertFalse(writer.is_alive())
            self.assertFalse(other.is_alive())
            self.assertEqual(failures, [])
            restored = PreferencesStore(path)
            self.assertEqual(restored.language, "en")
            self.assertFalse(restored.wide_sidebar_visible)
            self.assertEqual(restored.local_protection_onboarding, "pending")

    def test_marker_survives_language_and_sidebar_without_saving_a_PASS(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            store = PreferencesStore(path)
            store.set_local_protection_onboarding("pending")
            store.set_language("en")
            store.set_wide_sidebar_visible(False)
            reopened = PreferencesStore(path)
            self.assertEqual(reopened.local_protection_onboarding, "pending")
            self.assertEqual(
                json.loads(path.read_text()),
                {
                    "language": "en",
                    "wide_sidebar_visible": False,
                    "local_protection_onboarding": "pending",
                },
            )
            reopened.set_local_protection_onboarding("done")
            self.assertEqual(PreferencesStore(path).local_protection_onboarding, "done")
