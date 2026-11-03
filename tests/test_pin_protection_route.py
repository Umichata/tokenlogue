"""PIN protection navigation uses actual AuthService and disposable SQLite only."""

from __future__ import annotations

import asyncio
import hashlib
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from storage.profile_deletion import ProfileDeletion  # noqa: E402
from tests import test_app as app_fixtures  # noqa: E402
from tests import test_linux_parity as linux_fixtures  # noqa: E402
from ui.auth_view import PinLoginView  # noqa: E402
from ui.protection_panel import Mechanism, ProtectionPanel  # noqa: E402


class PinProtectionRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = linux_fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.fixture.temporary.cleanup)
        self.addCleanup(configure_localization, PreferencesStore())
        self.addCleanup(self.fx.updates.stop)
        self.app = self.fx.controller
        self.addCleanup(self.app.dispose)
        self.addAsyncCleanup(self.app.close_protection_checks)
        self.screen = AsyncMock()
        self.sleep = AsyncMock()
        for name, replacement in (
            ("request_screen_lock_test", self.screen),
            ("request_sleep_test", self.sleep),
        ):
            replacement_patch = patch.object(self.app, name, replacement)
            replacement_patch.start()
            self.addCleanup(replacement_patch.stop)
        for control in (ft.IconButton, ft.TextField):
            focus = patch.object(control, "focus", new_callable=AsyncMock)
            focus.start()
            self.addCleanup(focus.stop)

    def pin_view(self) -> PinLoginView:
        view = self.app._pin_login_view
        assert view is not None
        return view

    async def click(self, button):
        await button.on_click(ft.Event(name="click", control=button))

    async def choose(self, mechanism: Mechanism = "screen") -> ProtectionPanel:
        await self.app.show_pin_protection(self.pin_view())
        panel = self.app._pin_protection_panel
        assert panel is not None
        await self.click(
            panel.screen_test_button
            if mechanism == "screen"
            else panel.sleep_test_button
        )
        self.assertFalse(panel.is_open)
        self.assertIsNotNone(self.app._protection_test_intent)
        return panel

    def assert_no_request(self):
        self.screen.assert_not_awaited()
        self.sleep.assert_not_awaited()

    async def test_passive_shield_keeps_pin_and_never_reads_credentials_or_database(
        self,
    ):
        view = self.pin_view()
        shield = self.app._pin_protection_shield
        assert shield is not None
        self.assertIs(view.header.row.controls[-1], shield)
        view.pin_field.value = "01"
        self.fx.fixture.storage.read_keys.clear()
        mutations = len(self.fx.fixture.storage.mutations)
        digest = hashlib.sha256(self.fx.fixture.database.path.read_bytes()).hexdigest()
        await self.click(shield)
        panel = self.app._pin_protection_panel
        assert panel is not None
        self.assertTrue(panel.is_open)
        self.assertFalse(panel.screen_test_button.disabled)
        self.assertFalse(panel.sleep_test_button.disabled)
        self.assertFalse(view.notice.visible)
        self.assertEqual(view.pin_field.value, "01")
        self.assertEqual(self.fx.fixture.storage.read_keys, [])
        self.assertEqual(len(self.fx.fixture.storage.mutations), mutations)
        self.assertEqual(
            hashlib.sha256(self.fx.fixture.database.path.read_bytes()).hexdigest(),
            digest,
        )
        await panel.dismiss()
        self.assertEqual(view.pin_field.value, "01")
        self.assertFalse(self.app.protection_app_state().opened)
        self.assert_no_request()

    async def test_wrong_pin_keeps_normal_guard_then_real_pin_requires_explicit_start(
        self,
    ):
        view = self.pin_view()
        panel = await self.choose("screen")
        intent = self.app._protection_test_intent
        self.assertTrue(view.protection_prompt.visible)
        await self.app.submit_pin("9999")
        self.assertIs(self.app._pin_login_view, view)
        self.assertIs(self.app._protection_test_intent, intent)
        self.assertFalse(self.app.protection_app_state().opened)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertTrue(view.message.visible)
        self.assert_no_request()
        await self.app.submit_pin("0123")
        self.assertTrue(self.app.protection_app_state().opened)
        self.assertTrue(self.fx.fixture.access.unlocked)
        self.assertIsNone(self.app._pin_login_view)
        self.assertIs(self.app._pin_protection_panel, panel)
        self.assertTrue(panel.is_open)
        self.assertEqual(panel.selected_test, "screen")
        self.assertTrue(panel.selection.visible)
        self.assertFalse(panel.start_button.disabled)
        self.assert_no_request()
        await self.click(panel.start_button)
        self.screen.assert_awaited_once()
        self.sleep.assert_not_awaited()
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(panel.is_open)
        await self.click(panel.start_button)
        self.screen.assert_awaited_once()

    async def test_sleep_route_does_not_suspend_on_normal_pin_and_cancel_consumes_choice(
        self,
    ):
        panel = await self.choose("sleep")
        await self.app.submit_pin("0123")
        self.assertTrue(panel.is_open)
        self.assertEqual(panel.selected_test, "sleep")
        self.assert_no_request()
        await self.click(panel.cancel_button)
        self.assertIsNone(self.app._protection_test_intent)
        await self.click(panel.start_button)
        self.assert_no_request()
        self.assertTrue(self.app.protection_app_state().opened)

    async def test_handoff_cancel_button_keeps_pin_and_later_login_has_no_test(self):
        view = self.pin_view()
        view.pin_field.value = "01"
        panel = await self.choose("sleep")
        self.assertEqual(view.pin_field.value, "01")
        self.assertIsNotNone(self.app._protection_test_intent)
        await self.click(view.cancel_protection_button)
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(view.protection_prompt.visible)
        self.assertEqual(view.pin_field.value, "01")
        await self.app.submit_pin("0123")
        self.assertFalse(panel.is_open)
        self.assert_no_request()

    async def test_escape_outside_and_close_cancel_reopened_pre_auth_panel(self):
        for reason in ("escape", "outside", "close"):
            with self.subTest(reason=reason):
                panel = await self.choose()
                await self.app.show_pin_protection(self.pin_view())
                self.assertTrue(panel.is_open)
                if reason == "close":
                    await self.click(panel.close_button)
                else:
                    dialog = self.fx.page.dialogs[-1]
                    await panel._native_dismissed(
                        ft.Event(name="dismiss", control=dialog)
                    )
                self.assertIsNone(self.app._protection_test_intent)
                self.assertFalse(self.pin_view().protection_prompt.visible)
                self.assertFalse(panel.is_open)
                self.assert_no_request()

    async def test_pin_lockout_keeps_countdown_and_passive_panel_without_bypass(self):
        view = self.pin_view()
        for _ in range(6):
            await self.app.submit_pin("9999")
            if view._locked:
                break
        self.assertTrue(view._locked)
        self.assertTrue(view.submit_button.disabled)
        countdown = str(view.message.value)
        await self.choose()
        self.assertTrue(view._locked)
        self.assertEqual(str(view.message.value), countdown)
        self.assertTrue(view.protection_prompt.visible)
        await self.app.submit_pin("0123")
        self.assertFalse(self.app.protection_app_state().opened)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertIs(self.app._pin_login_view, view)
        self.assertTrue(view._locked)
        self.assert_no_request()

    async def test_real_timer_expires_handoff_before_future_normal_login(self):
        self.app._protection_intent_lifetime = 0.01
        panel = await self.choose()
        timer = self.app._protection_intent_expiry
        assert timer is not None
        await asyncio.wait_for(asyncio.shield(timer), 1)
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(self.pin_view().protection_prompt.visible)
        await self.app.submit_pin("0123")
        self.assertFalse(panel.is_open)
        self.assert_no_request()

    async def test_expired_authorized_intent_cannot_start_even_before_timer_dispatch(
        self,
    ):
        panel = await self.choose("sleep")
        await self.app.submit_pin("0123")
        intent = self.app._protection_test_intent
        assert intent is not None
        self.app._protection_intent_clock = lambda: intent.expires_at + 1
        await self.click(panel.start_button)
        self.assertIsNone(self.app._protection_test_intent)
        self.assert_no_request()

    async def test_epoch_composition_and_original_control_guard_unconfirmed_route(self):
        for changed in ("epoch", "composition", "control"):
            with self.subTest(changed=changed):
                await self.choose()
                intent = self.app._protection_test_intent
                assert intent is not None
                if changed == "epoch":
                    intent.epoch -= 1
                elif changed == "composition":
                    intent.composition = object()
                else:
                    self.fx.page.controls[:] = [ft.Container()]
                self.assertIsNone(
                    self.app._current_protection_intent(authenticated=False)
                )
                self.assertIsNone(self.app._protection_test_intent)
                self.fx.page.controls[:] = [self.pin_view().control]
                self.assert_no_request()

    async def test_authorized_session_and_origin_control_cannot_target_changed_workspace(
        self,
    ):
        for changed in ("session", "control"):
            with self.subTest(changed=changed):
                panel = await self.choose("screen")
                await self.app.submit_pin("0123")
                intent = self.app._protection_test_intent
                assert intent is not None
                if changed == "session":
                    assert intent.authorized_session is not None
                    intent.authorized_session -= 1
                else:
                    intent.authorized_control = ft.Container()
                await self.click(panel.start_button)
                self.assertIsNone(self.app._protection_test_intent)
                self.assert_no_request()
                await self.app.lock_application()
                self.assertIsNotNone(self.app._pin_login_view)

    async def test_recovery_and_profile_deletion_entry_cancel_without_running_or_deleting(
        self,
    ):
        self.fx.auth._profile_deletion = ProfileDeletion(
            self.fx.fixture.database.path, self.fx.fixture.storage
        )
        panel = await self.choose()
        await self.app.request_profile_deletion()
        self.assertIsNotNone(self.app._profile_deletion_view)
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(panel.is_open)
        self.app.cancel_profile_deletion()
        await self.choose("sleep")
        await self.app.request_recovery()
        self.assertIsNotNone(self.app._code_entry_view)
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(panel.is_open)
        self.assert_no_request()

    async def test_system_lock_during_real_pin_authentication_revokes_pending_route(
        self,
    ):
        panel = await self.choose()
        authenticated, release = asyncio.Event(), asyncio.Event()
        ordinary_login = self.fx.auth.login

        async def delayed_reply(pin):
            result = await ordinary_login(pin)
            authenticated.set()
            await release.wait()
            return result

        with patch.object(self.fx.auth, "login", delayed_reply):
            login = asyncio.create_task(self.app.submit_pin("0123"))
            await asyncio.wait_for(authenticated.wait(), 1)
            self.app.prepare_system_lock("sleep")
            self.assertTrue(self.app._protection_test_intent is None)
            self.assertFalse(self.fx.fixture.access.unlocked)
            self.assertFalse(panel.is_open)
            release.set()
            await login
            await self.app.wait_system_lock()
        self.assertFalse(self.app.protection_app_state().opened)
        self.assert_no_request()

    async def test_expiry_while_real_pin_reply_is_pending_cannot_restore_test_choice(
        self,
    ):
        self.app._protection_intent_lifetime = 0.01
        panel = await self.choose("sleep")
        timer = self.app._protection_intent_expiry
        assert timer is not None
        authenticated, release = asyncio.Event(), asyncio.Event()
        ordinary_login = self.fx.auth.login

        async def delayed_reply(pin):
            result = await ordinary_login(pin)
            authenticated.set()
            await release.wait()
            return result

        with patch.object(self.fx.auth, "login", delayed_reply):
            login = asyncio.create_task(self.app.submit_pin("0123"))
            await asyncio.wait_for(authenticated.wait(), 1)
            await asyncio.wait_for(asyncio.shield(timer), 1)
            release.set()
            await login
        self.assertTrue(self.app.protection_app_state().opened)
        self.assertTrue(self.app._protection_test_intent is None)
        self.assertFalse(panel.is_open)
        self.assert_no_request()

    async def test_new_system_lock_invalidates_before_awaiting_flush(self):
        panel = await self.choose()
        self.app.prepare_system_lock("screen_lock")
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(panel.is_open)
        await self.app.wait_system_lock()
        self.assertIsNotNone(self.app._pin_login_view)
        await self.app.submit_pin("0123")
        self.assertFalse(panel.is_open)
        self.assert_no_request()

    async def test_replace_key_request_cancels_authorized_intent_before_dialog(self):
        panel = await self.choose()
        await self.app.submit_pin("0123")
        await self.app.request_reset()
        self.assertTrue(self.app._reset_dialog_open)
        self.assertIsNone(self.app._protection_test_intent)
        self.assertFalse(panel.is_open)
        self.app.cancel_reset()
        self.assert_no_request()

    async def test_restart_constructor_does_not_restore_ephemeral_intent_from_storage(
        self,
    ):
        await self.choose("sleep")
        await self.app.close_protection_checks()
        self.app.dispose()
        page = linux_fixtures.LinuxPage()
        restarted = app_fixtures._make_controller(
            page, cast(app_fixtures.FakeAuthService, self.fx.auth)
        )
        self.addCleanup(restarted.dispose)
        self.addAsyncCleanup(restarted.close_protection_checks)
        await restarted.start()
        self.assertIsNotNone(restarted._pin_login_view)
        self.assertIsNone(restarted._protection_test_intent)
        self.assertIsNone(restarted._pin_protection_panel)
        self.assert_no_request()
