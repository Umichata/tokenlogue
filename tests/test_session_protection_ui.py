"""Защита остаётся видимой после входа и до показа резервного секрета."""

from __future__ import annotations

import unittest

from platform_security.local_protection import CheckState, ObserverContext
from tests import test_linux_parity as fixtures
from ui.styles import WARNING_COLOR


class SessionProtectionUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.controller = self.fx.controller

    async def test_partial_monitoring_is_visible_after_login(self):
        self.controller.set_session_watch_status(
            system_events=True, screen_events=False
        )
        self.controller.set_screen_lock_adapter(
            None, ObserverContext("linux", "synthetic", 1, "synthetic-system")
        )
        await self.controller.submit_pin("0123")
        workspace = self.controller._chat_controller._workspace_view
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertIsNotNone(workspace.protection_button)
        assert workspace.protection_button is not None
        self.assertTrue(workspace.protection_button.visible)
        status = workspace._protection_status
        assert status is not None
        self.assertTrue(status.sleep_connected)
        self.assertFalse(status.screen_connected)
        self.assertEqual(status.screen.state, CheckState.UNTESTED)
        self.assertEqual(status.sleep.state, CheckState.UNTESTED)
        self.assertEqual(workspace.protection_button.icon_color, WARNING_COLOR)

    async def test_warning_precedes_code_and_updates_without_reissuing(self):
        self.controller.set_session_watch_status(
            system_events=True, screen_events=False
        )
        await self.controller.submit_pin("0123")
        await self.controller.request_recovery_code_settings()
        repeated = self.controller._code_pin_view
        self.assertIsNotNone(repeated)
        assert repeated is not None
        self.assertTrue(repeated.protection_notice.visible)
        await self.controller.begin_recovery_code("0123")
        display = self.controller._code_display_view
        self.assertIsNotNone(display)
        assert display is not None
        self.assertTrue(display.protection_notice.visible)
        issue_id = self.controller._pending_code_issue_id
        self.controller.set_session_watch_status(system_events=True, screen_events=True)
        # Connected subscriptions do not prove either mechanism worked.
        self.assertTrue(display.protection_notice.visible)
        checks = self.controller._local_protection
        assert checks is not None
        self.assertEqual(checks.snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(self.controller._pending_code_issue_id, issue_id)
