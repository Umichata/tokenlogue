"""Системное восстановление связано с экраном, эпохой и явным сохранением PIN."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, PropertyMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthResult, AuthStatus, InitialRoute  # noqa: E402
from i18n import configure_localization, localize_tree, set_language  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests import test_app as fixtures  # noqa: E402


class RecoveryAuth(fixtures.FakeAuthService):
    recovery_available = True
    data_protection_enabled = True

    def __init__(self):
        super().__init__(initial_route=InitialRoute.PIN)
        self.recovery_started = asyncio.Event()
        self.recovery_release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.recovery_calls = 0
        self.cancel_recovery_calls = 0
        self.lock_access_calls = 0
        self.completed: list[tuple[str, str]] = []
        self.order: list[str] = []

    def lock_access(self):
        self.lock_access_calls += 1
        self.cancel_pending_setup()

    async def recover_pin(self):
        self.recovery_calls += 1
        self.recovery_started.set()
        await self.recovery_release.wait()
        return AuthResult(
            AuthStatus.PIN_CHOICE_REQUIRED, pending_setup_token="synthetic-proof"
        )

    async def complete_recovery(self, pin, token):
        self.completed.append((pin, token))
        return AuthResult(AuthStatus.AUTHENTICATED, api_key="synthetic-key")

    async def cancel_recovery(self):
        self.cancel_recovery_calls += 1
        self.cancelled.set()

    async def reset_authentication(self):
        self.order.append("reset")
        return await super().reset_authentication()


class AppRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.page = fixtures.FakePage()
        setattr(self.page, "platform", ft.PagePlatform.ANDROID)
        self.auth = RecoveryAuth()
        self.controller = fixtures._make_controller(self.page, self.auth)
        self.addCleanup(self.controller.dispose)
        await self.controller.start()

    async def start_challenge(self):
        task = asyncio.create_task(self.controller.request_recovery())
        await self.auth.recovery_started.wait()
        return task

    async def test_single_native_challenge_then_explicit_new_pin(self):
        task = await self.start_challenge()
        view = self.controller._recovery_view
        self.assertIsNotNone(view)
        self.assertFalse(self.controller._chat_controller.session_active)
        await self.controller.request_recovery()
        set_language("en")
        localize_tree(self.page.controls)
        await self.controller.handle_lifecycle_change(
            cast(
                ft.AppLifecycleStateChangeEvent,
                SimpleNamespace(state=ft.AppLifecycleState.INACTIVE),
            )
        )
        self.assertIs(self.controller._recovery_view, view)
        self.assertEqual(self.auth.recovery_calls, 1)
        self.assertEqual(self.auth.cancel_recovery_calls, 0)
        self.auth.recovery_release.set()
        await task
        choice = self.controller._pin_setup_view
        assert choice is not None
        self.assertEqual(choice.confirm_button.content, "Save new PIN")
        self.assertEqual(self.auth.completed, [])
        with patch.object(
            self.controller._chat_controller, "activate", new_callable=AsyncMock
        ) as activate:
            await self.controller.confirm_recovery("0123", "synthetic-proof")
            activate.assert_awaited_once()
            await self.controller.confirm_recovery("9999", "synthetic-proof")
            activate.assert_awaited_once()
        self.assertEqual(self.auth.completed, [("0123", "synthetic-proof")])

    async def test_linux_does_not_offer_device_recovery(self):
        setattr(self.page, "platform", ft.PagePlatform.LINUX)
        self.controller._show_pin_login()
        view = self.controller._pin_login_view
        assert view is not None
        self.assertIsNone(view.forgot_pin_button)
        await self.controller.request_recovery()
        self.assertEqual(self.auth.recovery_calls, 0)

    async def test_unsupported_android_shows_specific_recovery_limit(self):
        self.auth.recovery_available = False
        self.controller._show_pin_login()
        view = self.controller._pin_login_view
        assert view is not None
        self.assertIsNone(view.forgot_pin_button)
        self.assertIn("Android 11", self.controller._protection_notice())
        self.assertNotIn("Linux", self.controller._protection_notice())
        set_language("en")
        self.assertIn(
            "Recovery is currently unavailable here",
            self.controller._protection_notice(),
        )
        await self.controller.request_recovery()
        self.assertEqual(self.auth.recovery_calls, 0)

    async def test_confirmed_pin_save_cannot_be_cancelled_by_an_old_queued_action(self):
        self.auth.recovery_release.set()
        await self.controller.request_recovery()
        entered, released = asyncio.Event(), asyncio.Event()

        async def complete(pin, token):
            self.auth.completed.append((pin, token))
            entered.set()
            await released.wait()
            return AuthResult(AuthStatus.AUTHENTICATED, api_key="synthetic-key")

        with (
            patch.object(self.auth, "complete_recovery", side_effect=complete),
            patch.object(
                self.controller._chat_controller, "activate", new_callable=AsyncMock
            ) as activate,
        ):
            pending = asyncio.create_task(
                self.controller.confirm_recovery("0123", "synthetic-proof")
            )
            await entered.wait()
            epoch = self.controller._security_epoch
            await self.controller.cancel_recovery()
            self.assertEqual(self.controller._security_epoch, epoch)
            self.assertEqual(self.auth.cancel_recovery_calls, 0)
            released.set()
            await pending
            activate.assert_awaited_once()

    async def test_prepare_close_rejects_late_system_success_and_resume(self):
        task = await self.start_challenge()
        epoch = self.controller._security_epoch
        self.controller.prepare_close()
        self.assertTrue(self.controller._closing)
        self.assertNotEqual(self.controller._security_epoch, epoch)
        self.assertIsNone(self.controller._recovery_view)
        await self.controller.cancel_system_recovery()
        self.auth.recovery_release.set()
        await task
        await self.controller.handle_lifecycle_change(
            cast(
                ft.AppLifecycleStateChangeEvent,
                SimpleNamespace(state=ft.AppLifecycleState.RESUME),
            )
        )
        await self.controller.start()
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertIsNone(self.controller._pin_login_view)
        self.assertFalse(self.controller._chat_controller.session_active)
        self.assertEqual(self.auth.cancel_recovery_calls, 1)
        self.assertEqual(self.auth.completed, [])

    async def test_cancelled_prompt_cannot_reopen_new_choice_after_late_success(self):
        task = await self.start_challenge()
        await self.controller.cancel_recovery()
        view = self.controller._pin_login_view
        self.assertIsNotNone(view)
        self.assertEqual(self.auth.cancel_recovery_calls, 1)
        self.auth.recovery_release.set()
        await task
        self.assertIs(self.controller._pin_login_view, view)
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(self.controller._chat_controller.session_active)
        self.assertEqual(self.auth.completed, [])

    async def test_hide_revokes_before_await_and_rejects_native_late_success(self):
        task = await self.start_challenge()
        lifecycle = asyncio.create_task(
            self.controller.handle_lifecycle_change(
                cast(
                    ft.AppLifecycleStateChangeEvent,
                    SimpleNamespace(state=ft.AppLifecycleState.HIDE),
                )
            )
        )
        await self.auth.cancelled.wait()
        self.assertGreaterEqual(self.auth.lock_access_calls, 1)
        self.assertIsNone(self.controller._recovery_view)
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(self.controller._chat_controller.session_active)
        self.auth.recovery_release.set()
        await task
        await lifecycle
        view = self.controller._pin_login_view
        self.assertIsNotNone(view)
        await self.controller.handle_lifecycle_change(
            cast(
                ft.AppLifecycleStateChangeEvent,
                SimpleNamespace(state=ft.AppLifecycleState.RESUME),
            )
        )
        self.assertIs(self.controller._pin_login_view, view)
        self.assertFalse(self.controller._chat_controller.session_active)

    async def test_cancel_new_pin_keeps_old_access_and_rejects_old_button(self):
        self.auth.recovery_release.set()
        await self.controller.request_recovery()
        choice = self.controller._pin_setup_view
        assert choice is not None
        await self.controller.cancel_recovery()
        await self.controller.confirm_recovery("4567", "synthetic-proof")
        self.assertEqual(self.auth.completed, [])
        self.assertEqual(choice.pin_field.value, "")
        self.assertIsNotNone(self.controller._pin_login_view)

    async def test_protected_replacement_flushes_before_deactivation_and_auth_reset(
        self,
    ):
        controller = self.controller
        controller._pin_login_view = None

        async def flush():
            self.auth.order.append("flush")
            return True

        with (
            patch.object(
                type(controller._chat_controller),
                "session_active",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                controller._chat_controller, "flush_drafts", side_effect=flush
            ),
            patch.object(
                controller._chat_controller,
                "deactivate",
                side_effect=lambda: self.auth.order.append("deactivate"),
            ),
        ):
            await controller.request_reset()
            await controller.confirm_reset()
        self.assertLess(
            self.auth.order.index("flush"), self.auth.order.index("deactivate")
        )
        self.assertLess(
            self.auth.order.index("deactivate"), self.auth.order.index("reset")
        )
        self.assertIsNotNone(controller._key_view)

    async def test_failed_flush_prevents_protected_key_replacement(self):
        controller = self.controller
        controller._pin_login_view = None
        with (
            patch.object(
                type(controller._chat_controller),
                "session_active",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                controller._chat_controller,
                "flush_drafts",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(controller._chat_controller, "deactivate") as deactivate,
        ):
            await controller.request_reset()
            await controller.confirm_reset()
            deactivate.assert_not_called()
        self.assertEqual(self.auth.reset_calls, 0)


if __name__ == "__main__":
    unittest.main()
