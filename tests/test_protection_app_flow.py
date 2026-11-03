"""Adapter-controlled cycles test real AppController revoke, not native OS lock."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.local_protection import (  # noqa: E402
    CheckState,
    LocalProtectionChecks,
    ObserverContext,
    ScreenState,
)
from tests import test_linux_parity as fixtures  # noqa: E402
from ui.styles import WARNING_COLOR  # noqa: E402


class Adapter:
    def __init__(self, app, *, normal=True):
        self.app = app
        self.screen_context = ObserverContext(
            "linux", "synthetic-session", 1, "synthetic-owner"
        )
        self.locked = False
        self.normal = normal
        self.requests = 0
        self.open_at_request = False

    async def read_screen_state(self, context):
        return ScreenState(context, self.locked)

    async def request_screen_lock(self, context):
        self.requests += 1
        before = self.app.protection_app_state()
        self.open_at_request = before.opened
        self.locked = True
        if self.normal:
            self.app.prepare_system_lock("screen_lock")
            self.app.record_normal_protection("screen", context, before)
        await asyncio.sleep(0.01)


class ProtectionAppFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.app = self.fx.controller
        self.addAsyncCleanup(self.app.close_protection_checks)
        checks = self.app._local_protection
        assert checks is not None
        self.checks: LocalProtectionChecks = checks
        self.checks._poll_interval = 0.001
        self.checks._reaction_grace = 0
        self.checks._cycle_timeout = 0.3
        await self.app.submit_pin("0123")

    async def until(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.005)
        self.fail("Synthetic protection cycle did not settle")

    async def test_real_backend_seal_and_pin_required_for_adapter_confirmed_cycle(self):
        adapter = Adapter(self.app)
        self.app.set_screen_lock_adapter(adapter)
        chat = self.app._chat_controller
        view = chat._workspace_view
        assert view is not None
        assert view.protection_button is not None
        selected = chat.selected_chat_id
        view.restore_editor("synthetic draft before screen test")
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(view.protection_button.icon_color, WARNING_COLOR)
        await self.app.request_screen_lock_test()
        self.assertTrue(adapter.open_at_request)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertFalse(chat.session_active)
        await self.app.wait_system_lock()
        adapter.locked = False
        await self.until(
            lambda: self.checks.snapshot.screen.state is CheckState.CONFIRMED
        )
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.UNTESTED)
        self.app.handle_language_change()
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)
        await self.app.submit_pin("0123")
        restored = chat._workspace_view
        assert restored is not None
        self.assertEqual(restored.editor_value, "synthetic draft before screen test")
        self.assertEqual(chat.selected_chat_id, selected)

    async def test_confirmed_os_lock_missing_normal_reaction_is_red_even_after_emergency_pin(
        self,
    ):
        adapter = Adapter(self.app, normal=False)
        self.app.set_screen_lock_adapter(adapter)
        await self.app.request_screen_lock_test()
        await self.until(
            lambda: self.checks.snapshot.screen.state is CheckState.PROBLEM
        )
        await self.app.wait_system_lock()
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertIsNotNone(self.app._pin_login_view)
        adapter.locked = False
        await asyncio.sleep(0.02)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.PROBLEM)

    async def test_closed_application_never_requests_os_lock(self):
        adapter = Adapter(self.app)
        self.app.set_screen_lock_adapter(adapter)
        await self.app.lock_application()
        await self.app.request_screen_lock_test()
        self.assertEqual(adapter.requests, 0)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.UNTESTED)
