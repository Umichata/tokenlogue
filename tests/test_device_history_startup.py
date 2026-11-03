"""Real Linux composition restores advisory metadata without OS lock or auth."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as composition  # noqa: E402
from app import AppController  # noqa: E402
from auth.models import InitialRoute  # noqa: E402
from i18n import configure_localization  # noqa: E402
from platform_security.device_protection_store import (
    DeviceProtectionStore,  # noqa: E402
)
from platform_security.local_protection import (  # noqa: E402
    SCREEN_CONTRACT,
    SLEEP_CONTRACT,
    CheckState,
    DeviceCheckRecord,
)
from preferences import PreferencesStore  # noqa: E402
from tests.test_app import FakeAuthService, FakeKeyValidator  # noqa: E402
from tests.test_app_close import ClosingPage  # noqa: E402
from tests.test_secure_credentials import FakeSecureStorage  # noqa: E402


class DeviceHistoryStartupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(configure_localization, PreferencesStore())
        self.directory = Path(self.temporary.name)
        self.store = DeviceProtectionStore(
            self.directory / "device", machine_identity=b"a" * 32, user_id=1001
        )
        self.store.save(
            "screen", DeviceCheckRecord(CheckState.CONFIRMED, 100, 100, SCREEN_CONTRACT)
        )
        self.store.save(
            "sleep", DeviceCheckRecord(CheckState.CONFIRMED, 101, 101, SLEEP_CONTRACT)
        )

    async def compose(self):
        page = ClosingPage()
        controllers = []
        watcher = SimpleNamespace(
            enable_saved_screen_monitoring=Mock(),
            aclose=AsyncMock(),
            request_screen_lock=AsyncMock(),
            request_sleep=AsyncMock(),
        )

        def controller(*args, **kwargs):
            value = AppController(*args, **kwargs)
            controllers.append(value)
            return value

        with (
            patch.dict(
                os.environ, {"FLET_APP_STORAGE_DATA": str(self.directory / "profile")}
            ),
            patch.object(
                DeviceProtectionStore,
                "for_current_linux_account",
                return_value=self.store,
            ),
            patch.object(
                composition,
                "FletSecureCredentials",
                return_value=SimpleNamespace(storage_backend=FakeSecureStorage()),
            ),
            patch.object(
                composition,
                "start_linux_session_watch",
                AsyncMock(return_value=watcher),
            ),
            patch.object(
                composition,
                "AuthService",
                return_value=FakeAuthService(initial_route=InitialRoute.PIN),
            ),
            patch.object(
                composition, "OpenRouterClient", return_value=FakeKeyValidator()
            ),
            patch.object(composition, "ModelCatalogClient"),
            patch.object(composition, "ChatCompletionsClient"),
            patch.object(composition, "AppController", side_effect=controller),
            patch.object(ft.Control, "update"),
        ):
            await composition.main(cast(ft.Page, page))
        self.addAsyncCleanup(getattr(page, "on_close"))
        return controllers[0], watcher

    async def test_saved_checks_restore_monitoring_without_requesting_os_actions(self):
        app, watcher = await self.compose()
        checks = app._local_protection
        assert checks is not None
        self.assertEqual(checks.history, self.store.load())
        self.assertTrue(app.protection_app_state().revoked)
        self.assertIsNotNone(app._pin_login_view)
        self.assertFalse(app._chat_controller.session_active)
        watcher.enable_saved_screen_monitoring.assert_called_once()
        watcher.request_screen_lock.assert_not_awaited()
        watcher.request_sleep.assert_not_awaited()

    async def test_corrupt_history_keeps_pin_and_never_restores_green(self):
        next(self.store.directory.glob("history-*.json")).write_text("{corrupt")
        app, watcher = await self.compose()
        checks = app._local_protection
        assert checks is not None
        self.assertIsNone(checks.history.screen)
        self.assertIsNone(checks.history.sleep)
        self.assertTrue(checks.snapshot.persistence_error)
        self.assertTrue(app.protection_app_state().revoked)
        self.assertIsNotNone(app._pin_login_view)
        watcher.enable_saved_screen_monitoring.assert_not_called()
        watcher.request_sleep.assert_not_awaited()
