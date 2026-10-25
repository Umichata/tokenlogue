"""Жизненный цикл Android проверяется без устройства и настоящих секретов."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import AppController  # noqa: E402
from auth.models import (  # noqa: E402
    AuthResult,
    AuthStatus,
    InitialRoute,
    KeyLimitInfo,
    KeyValidityState,
)
from tests.test_app import (  # noqa: E402
    BlockingFakeKeyValidator,
    FakeAuthService,
    FakePage,
    _make_controller,
)


class AndroidPage(FakePage):
    platform = ft.PagePlatform.ANDROID


def lifecycle(state: ft.AppLifecycleState) -> ft.AppLifecycleStateChangeEvent:
    return cast(ft.AppLifecycleStateChangeEvent, SimpleNamespace(state=state))


class AppLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.page = AndroidPage()
        self.auth = FakeAuthService(initial_route=InitialRoute.PIN)
        self.controller = _make_controller(self.page, self.auth)
        self.addCleanup(self.controller.dispose)
        self.control_updates = patch.object(ft.Control, "update", return_value=None)
        self.control_updates.start()
        self.addCleanup(self.control_updates.stop)

    async def activate(self, controller: AppController | None = None) -> None:
        await (controller or self.controller)._activate_session(
            "synthetic-session-key",
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )

    async def test_hide_revokes_access_before_slow_flush_and_resume_requires_pin(
        self,
    ) -> None:
        await self.activate()
        await self.controller.request_reset()
        self.assertTrue(self.page.dialogs)
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_flush() -> bool:
            started.set()
            await release.wait()
            return True

        with patch.object(
            self.controller._chat_controller, "flush_drafts", delayed_flush
        ):
            hiding = asyncio.create_task(
                self.controller.handle_lifecycle_change(
                    lifecycle(ft.AppLifecycleState.HIDE)
                )
            )
            await started.wait()
            self.assertFalse(self.controller._chat_controller.session_active)
            self.assertFalse(self.controller._chat_controller.workspace_visible)
            self.assertFalse(self.page.dialogs)
            self.assertIsNone(self.controller._pin_login_view)
            shield = self.page.controls[0]
            await self.controller.handle_lifecycle_change(
                lifecycle(ft.AppLifecycleState.RESUME)
            )
            self.assertIs(self.page.controls[0], shield)
            release.set()
            await hiding
        self.assertIsNotNone(self.controller._pin_login_view)
        self.assertFalse(self.controller._chat_controller.session_active)
        self.assertEqual(self.auth.reset_calls, 0)
        self.auth.login_result = AuthResult(
            AuthStatus.AUTHENTICATED,
            api_key="synthetic-session-key",
            key_validity=KeyValidityState.VALID,
        )
        await self.controller.submit_pin("0123")
        self.assertTrue(self.controller._chat_controller.session_active)
        self.assertFalse(self.controller._disposed)

    async def test_repeated_hide_pause_coalesces_while_flush_pending(self) -> None:
        await self.activate()
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_flush() -> bool:
            started.set()
            await release.wait()
            return True

        with patch.object(
            self.controller._chat_controller,
            "flush_drafts",
            AsyncMock(side_effect=delayed_flush),
        ) as flush:
            hiding = asyncio.create_task(
                self.controller.handle_lifecycle_change(
                    lifecycle(ft.AppLifecycleState.HIDE)
                )
            )
            await started.wait()
            await self.controller.handle_lifecycle_change(
                lifecycle(ft.AppLifecycleState.HIDE)
            )
            await self.controller.handle_lifecycle_change(
                lifecycle(ft.AppLifecycleState.PAUSE)
            )
            release.set()
            await hiding
            await self.controller.handle_lifecycle_change(
                lifecycle(ft.AppLifecycleState.PAUSE)
            )
            self.assertEqual(flush.await_count, 1)
        self.assertEqual(self.auth.cancel_calls, 1)
        self.assertIsNotNone(self.controller._pin_login_view)

    async def test_setup_validation_late_result_cannot_restore_pin_setup(self) -> None:
        self.auth.initial_route = InitialRoute.SETUP
        await self.controller.start()
        old = self.controller._key_view
        assert old is not None
        old.key_field.value = "synthetic-pending-key"
        checking = asyncio.create_task(self.controller.submit_key(old.key_field.value))
        await self.auth.started.wait()
        hiding = asyncio.create_task(
            self.controller.handle_lifecycle_change(
                lifecycle(ft.AppLifecycleState.PAUSE)
            )
        )
        await asyncio.sleep(0)
        self.assertEqual(old.key_field.value, "")
        self.assertIsNone(self.controller._key_view)
        self.assertGreater(self.auth.cancel_calls, 0)
        self.auth.release.set()
        await asyncio.gather(checking, hiding)
        self.assertIsNotNone(self.controller._key_view)
        self.assertIsNot(self.controller._key_view, old)
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertFalse(self.controller._chat_controller.session_active)

    async def test_late_successful_pin_login_cannot_unlock_after_pause(self) -> None:
        await self.controller.start()
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_login(_pin: str) -> AuthResult:
            started.set()
            await release.wait()
            return AuthResult(
                AuthStatus.AUTHENTICATED,
                api_key="synthetic-session-key",
                key_validity=KeyValidityState.VALID,
            )

        with patch.object(self.auth, "login", delayed_login):
            logging_in = asyncio.create_task(self.controller.submit_pin("0123"))
            await started.wait()
            hiding = asyncio.create_task(
                self.controller.handle_lifecycle_change(
                    lifecycle(ft.AppLifecycleState.PAUSE)
                )
            )
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(logging_in, hiding)
        self.assertFalse(self.controller._chat_controller.session_active)
        self.assertIsNotNone(self.controller._pin_login_view)

    async def test_late_status_result_cannot_revive_workspace_after_pause(self) -> None:
        validator = BlockingFakeKeyValidator(ignore_cancellation=True)
        controller = _make_controller(self.page, self.auth, key_validator=validator)
        self.addCleanup(controller.dispose)
        await controller._activate_session(
            "synthetic-session-key", KeyValidityState.UNKNOWN, KeyLimitInfo.unknown()
        )
        await validator.started.wait()
        await controller.handle_lifecycle_change(lifecycle(ft.AppLifecycleState.PAUSE))
        pin_view = controller._pin_login_view
        validator.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertFalse(controller._chat_controller.session_active)
        self.assertIs(controller._pin_login_view, pin_view)
        self.assertFalse(controller._chat_controller.workspace_visible)

    async def test_storage_failure_is_visible_after_lock(self) -> None:
        await self.activate()
        with patch.object(
            self.controller._chat_controller,
            "flush_drafts",
            AsyncMock(return_value=False),
        ):
            await self.controller.handle_lifecycle_change(
                lifecycle(ft.AppLifecycleState.PAUSE)
            )
        view = self.controller._pin_login_view
        assert view is not None
        self.assertIn("Не удалось сохранить черновик", view.message.value or "")
        self.assertFalse(self.controller._chat_controller.session_active)

    async def test_main_wires_lifecycle_and_retains_final_close_cleanup(self) -> None:
        import main as composition

        controller = MagicMock()
        controller.start = AsyncMock()
        controller.flush_drafts = AsyncMock(return_value=True)
        controller.cancel_system_recovery = AsyncMock()
        controller.handle_lifecycle_change = AsyncMock()
        order = []
        controller.prepare_close.side_effect = lambda: order.append("prepare")
        controller.cancel_system_recovery.side_effect = lambda: order.append("cancel")
        controller.flush_drafts.side_effect = lambda: order.append("flush")
        controller.dispose.side_effect = lambda: order.append("dispose")
        with (
            patch.object(composition, "configure_page"),
            patch.object(
                composition,
                "AuthDatabase",
                return_value=SimpleNamespace(path="synthetic-unused.sqlite3"),
            ),
            patch.object(composition, "AppController", return_value=controller),
        ):
            await composition.main(cast(ft.Page, self.page))
        self.assertIs(
            getattr(self.page, "on_app_lifecycle_state_change"),
            controller.handle_lifecycle_change,
        )
        controller.start.assert_awaited_once()
        await getattr(self.page, "on_close")()
        controller.flush_drafts.assert_awaited_once()
        controller.dispose.assert_called_once()
        self.assertEqual(order, ["prepare", "cancel", "flush", "dispose"])
        self.assertIs(
            getattr(self.page, "on_close"), getattr(self.page, "on_disconnect")
        )

    async def test_inactive_and_linux_lifecycle_do_not_lock(self) -> None:
        await self.activate()
        await self.controller.handle_lifecycle_change(
            lifecycle(ft.AppLifecycleState.INACTIVE)
        )
        self.assertTrue(self.controller._chat_controller.session_active)
        self.page.platform = ft.PagePlatform.LINUX
        for state in (
            ft.AppLifecycleState.HIDE,
            ft.AppLifecycleState.PAUSE,
            ft.AppLifecycleState.RESUME,
        ):
            await self.controller.handle_lifecycle_change(lifecycle(state))
        self.assertTrue(self.controller._chat_controller.session_active)
        self.assertEqual(self.auth.cancel_calls, 0)
