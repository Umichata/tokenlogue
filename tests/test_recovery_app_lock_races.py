"""AppController returns to PIN and follows durable backend state after OS events."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthStatus  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402


class RecoveryAppLockRaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.app = self.fx.controller
        self.addAsyncCleanup(self.app.close_protection_checks)

    async def grant(self):
        await self.app.request_system_recovery()
        await self.app.request_system_recovery()
        token = self.app._pending_recovery_token
        assert token is not None
        return token

    async def test_lock_before_native_reply_rejects_late_reply_and_keeps_old_pin(self):
        self.fx.provider.release = asyncio.Event()
        await self.app.request_system_recovery()
        challenge = asyncio.create_task(self.app.request_system_recovery())
        await self.fx.provider.started.wait()
        self.app.prepare_system_lock("screen_lock")
        self.fx.provider.release.set()
        await challenge
        await self.app.wait_system_lock()
        self.assertIsNone(self.app._pin_setup_view)
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertEqual(
            (await self.fx.auth.login("0123")).status, AuthStatus.AUTHENTICATED
        )
        self.fx.auth.lock_access()

    async def test_sleep_after_grant_disposes_pin_choice_and_rejects_old_save(self):
        token = await self.grant()
        old = self.app._pin_setup_view
        assert old is not None
        old.pin_field.value = "4567"
        self.app.prepare_system_lock("sleep")
        await self.app.wait_system_lock()
        await self.app.confirm_recovery("4567", token)
        self.assertEqual(old.pin_field.value, "")
        self.assertIsNone(self.app._pending_recovery_token)
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertEqual(
            (await self.fx.auth.login("0123")).status, AuthStatus.AUTHENTICATED
        )
        self.fx.auth.lock_access()

    async def test_lock_after_durable_save_before_final_reply_uses_new_pin_without_reopening(
        self,
    ):
        token = await self.grant()
        entered, release = asyncio.Event(), asyncio.Event()
        get_key = self.fx.credentials.get_api_key

        async def delayed():
            value = await get_key()
            entered.set()
            await release.wait()
            return value

        with patch.object(self.fx.credentials, "get_api_key", delayed):
            saving = asyncio.create_task(self.app.confirm_recovery("4567", token))
            await entered.wait()
            self.app.prepare_system_lock("screen_lock")
            release.set()
            await saving
            await self.app.wait_system_lock()
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertFalse(self.app._chat_controller.session_active)
        self.assertIsNone(self.app._pin_setup_view)
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertEqual(
            (await self.fx.auth.login("0123")).status, AuthStatus.INVALID_PIN
        )
        self.assertEqual(
            (await self.fx.auth.login("4567")).status, AuthStatus.AUTHENTICATED
        )
        self.fx.auth.lock_access()

    async def test_android_language_change_cancels_sensitive_grant_without_pin_reset(
        self,
    ):
        token = await self.grant()
        self.fx.page.platform = ft.PagePlatform.ANDROID
        self.app.handle_language_change()
        await self.app.wait_system_lock()
        await self.app.confirm_recovery("4567", token)
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertIsNone(self.app._pending_recovery_token)
        self.assertEqual(
            (await self.fx.auth.login("0123")).status, AuthStatus.AUTHENTICATED
        )
        self.fx.auth.lock_access()
