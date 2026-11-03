"""Переносимый Linux-путь проходит через App, Auth и настоящую временную SQLite."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthStatus  # noqa: E402
from auth.service import AuthService  # noqa: E402
from platform_security.device_recovery import RecoveryProvider  # noqa: E402
from storage.data_protection import DATA_BINDING_ALIAS, DATA_KEY_ALIAS  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402
from tests.test_encryption_initialization import snapshot  # noqa: E402


class PortableRecoveryAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.controller = self.fx.controller
        self.auth = self.fx.auth
        self.auth._recovery_provider = None
        self.storage = self.fx.fixture.storage

    async def test_unenrolled_closed_profile_does_not_bootstrap_or_read_key(self):
        self.storage.read_keys.clear()
        await self.controller.request_recovery()
        view = self.controller._code_entry_view
        self.assertIsNotNone(view)
        self.assertIsNone(self.controller._recovery_view)
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertFalse(
            DATA_KEY_ALIAS in self.storage.read_keys, "No DEK before proof"
        )
        result = await self.auth.begin_recovery_code("0123")
        self.assertIsNone(result.recovery_code_issue)
        self.assertFalse(
            DATA_KEY_ALIAS in self.storage.read_keys, "No closed enrollment"
        )

    async def test_open_session_requires_repeat_pin_then_saved_confirmation(self):
        await self.controller.submit_pin("0123")
        await self.controller.request_recovery_code_settings()
        self.assertIsNotNone(self.controller._code_pin_view)
        await self.controller.begin_recovery_code("0123")
        self.assertIsNotNone(self.controller._code_display_view)
        self.assertFalse(await self.auth.recovery_code_enrolled())

    async def test_primary_linux_flow_never_calls_optional_system_provider(self):
        self.auth._recovery_provider = cast(RecoveryProvider, self.fx.provider)
        with patch.object(
            self.fx.provider,
            "authenticate",
            side_effect=AssertionError("Unexpected system call"),
        ) as system:
            await self.controller.request_recovery()
            self.assertIsNotNone(self.controller._code_entry_view)
            self.assertFalse(system.called)

    async def saved_code(self):
        await self.controller.submit_pin("0123")
        await self.controller.request_recovery_code_settings()
        await self.controller.begin_recovery_code("0123")
        view = self.controller._code_display_view
        assert view is not None
        value = view._code
        await self.controller.confirm_recovery_code(value)
        self.assertTrue(await self.auth.recovery_code_enrolled())
        self.assertTrue(view._code == "", "Closed display no longer contains code")
        return value

    async def test_complete_code_recovery_preserves_data_and_offers_replacement(self):
        code = await self.saved_code()
        fx = self.fx.fixture
        old_key = self.storage.values[DATA_KEY_ALIAS]
        await self.controller.lock_application()
        self.storage.read_keys.clear()
        await self.controller.request_recovery()
        self.assertFalse(DATA_KEY_ALIAS in self.storage.read_keys, "No pre-proof key")
        await self.controller.submit_recovery_code(code.lower())
        self.assertIsNotNone(self.controller._pin_setup_view)
        self.assertFalse(fx.access.unlocked)
        token = self.controller._pending_recovery_token
        assert token is not None
        await self.controller.confirm_recovery("4567", token)
        self.assertTrue(fx.access.unlocked)
        self.assertIsNotNone(self.controller._code_pin_view)
        self.assertFalse(await self.auth.recovery_code_enrolled())
        self.assertTrue(self.storage.values[DATA_KEY_ALIAS] == old_key, "Same DEK")
        with fx.access.authorize("read") as cipher:
            after = snapshot(fx.database.path, cipher)
        for table in fx.original:
            if table != "auth_state":
                self.assertTrue(
                    after[table] == fx.original[table], "Preserved content table"
                )
        await self.controller.cancel_recovery_code_settings()
        self.controller.prepare_close()
        await self.controller.flush_drafts()
        protection = fx.restart()
        restarted = AuthService(
            self.fx.validator,
            self.fx.credentials,
            fx.database,
            protection=protection,
            pin_hasher=fx.hasher,
        )
        await restarted.initialize()
        self.assertEqual((await restarted.login("0123")).status, AuthStatus.INVALID_PIN)
        self.assertEqual(
            (await restarted.login("4567")).status, AuthStatus.AUTHENTICATED
        )
        self.assertFalse(await restarted.recovery_code_enrolled())
        protection.lock()

    async def test_cancel_reissue_keeps_previous_code_and_clears_display(self):
        old = await self.saved_code()
        await self.controller.request_recovery_code_settings()
        await self.controller.begin_recovery_code("0123")
        candidate = self.controller._code_display_view
        assert candidate is not None
        await self.controller.cancel_recovery_code_settings()
        self.assertTrue(candidate._code == "", "Secret cleared")
        await self.controller.lock_application()
        await self.controller.request_recovery()
        await self.controller.submit_recovery_code(old)
        self.assertIsNotNone(self.controller._pin_setup_view)

    async def test_lock_during_code_check_rejects_late_result_before_dek(self):
        code = await self.saved_code()
        await self.controller.lock_application()
        await self.controller.request_recovery()
        entered, release = asyncio.Event(), asyncio.Event()
        original_get = self.storage.get
        held = False

        async def delayed(key):
            nonlocal held
            result = await original_get(key)
            if key == DATA_BINDING_ALIAS and not held:
                held = True
                entered.set()
                await release.wait()
            return result

        self.storage.read_keys.clear()
        with patch.object(self.storage, "get", side_effect=delayed):
            pending = asyncio.create_task(self.controller.submit_recovery_code(code))
            await entered.wait()
            self.controller.prepare_system_lock("screen_lock")
            self.assertFalse(self.fx.fixture.access.unlocked)
            release.set()
            await pending
            await self.controller.wait_system_lock()
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(
            DATA_KEY_ALIAS in self.storage.read_keys, "Stale proof cannot read DEK"
        )

    async def test_language_change_clears_issue_and_old_callback_cannot_save(self):
        await self.controller.submit_pin("0123")
        await self.controller.request_recovery_code_settings()
        await self.controller.begin_recovery_code("0123")
        view = self.controller._code_display_view
        assert view is not None
        value = view._code
        self.controller.handle_language_change()
        self.assertTrue(view._code == "", "Code revoked synchronously")
        self.assertFalse(self.fx.fixture.access.unlocked)
        await self.controller.wait_system_lock()
        await self.controller.confirm_recovery_code(value)
        self.assertFalse(await self.auth.recovery_code_enrolled())
        self.assertIsNone(self.controller._code_display_view)

    async def test_duplicate_saved_callback_cannot_rotate_again(self):
        await self.controller.submit_pin("0123")
        await self.controller.request_recovery_code_settings()
        await self.controller.begin_recovery_code("0123")
        view = self.controller._code_display_view
        assert view is not None
        value = view._code
        await self.controller.confirm_recovery_code(value)
        binding = self.storage.values[DATA_BINDING_ALIAS]
        await self.controller.confirm_recovery_code(value)
        self.assertTrue(
            self.storage.values[DATA_BINDING_ALIAS] == binding, "One commit"
        )

    async def test_pending_pin_fault_has_safe_visible_retry_then_reconciles(self):
        code = await self.saved_code()
        await self.controller.lock_application()
        await self.controller.request_recovery()
        await self.controller.submit_recovery_code(code)
        token = self.controller._pending_recovery_token
        assert token is not None
        with patch.object(
            self.fx.fixture.database,
            "save_auth_state",
            side_effect=OSError("synthetic-write-failure"),
        ):
            await self.controller.confirm_recovery("4567", token)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertIsNone(self.controller._code_entry_view)
        await self.controller.start()
        self.assertIsNotNone(self.controller._pin_login_view)
        await self.controller.submit_pin("4567")
        self.assertTrue(self.fx.fixture.access.unlocked)
