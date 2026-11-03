"""Таймер отображает backend-срок, включая пропущенные ticks и смену языка."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization, localize_tree, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests import test_app as fixtures  # noqa: E402
from ui.recovery_code_view import (  # noqa: E402
    RecoveryCodeEntryView,
    RecoveryCodePinView,
)


class PinCountdownTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.page = fixtures.FakePage()
        self.auth = fixtures.FakeAuthService()
        self.app = fixtures._make_controller(self.page, self.auth)
        self.addCleanup(self.app.dispose)
        self.app._show_pin_login()
        self.app._cancel_lock_task()

    async def test_reopened_pin_screen_rechecks_lock_when_route_passes_no_countdown(
        self,
    ):
        backend = AsyncMock(return_value=300)
        with patch.object(self.auth, "pin_lock_seconds_remaining", backend):
            self.app._code_entry_view = RecoveryCodeEntryView(
                AsyncMock(), AsyncMock(), enrolled=False
            )
            await self.app.cancel_recovery()
            view = self.app._pin_login_view
            assert view is not None
            self.assertTrue(view._locked)
            self.assertIn("05:00", view.message.value)
            backend.assert_awaited_once()
            self.app._cancel_lock_task()

    async def test_delayed_ticks_read_backend_and_display_minutes_seconds(self):
        view = self.app._pin_login_view
        assert view is not None
        backend = AsyncMock(side_effect=[300, 299, 42, 0])
        displayed = []

        async def sleep(_seconds):
            displayed.append(str(view.message.value))

        with (
            patch.object(self.auth, "pin_lock_seconds_remaining", backend),
            patch("app.asyncio.sleep", sleep),
        ):
            await self.app._lock_countdown(view)
        self.assertEqual(backend.await_count, 4)
        self.assertEqual(
            displayed,
            [tr("auth.lock_countdown", time=v) for v in ("05:00", "04:59", "00:42")],
        )
        self.assertFalse(view._locked)
        self.assertEqual(view.message.value, tr("auth.lock_expired"))

    async def test_language_change_preserves_backend_lock_and_recovery_actions(self):
        view = self.app._pin_login_view
        assert view is not None
        view.set_locked(299)
        for language in ("ru", "en"):
            set_language(language)
            localize_tree(view.control)
            self.app.handle_language_change()
            self.assertTrue(view.pin_field.disabled)
            self.assertIn("04:59", view.message.value)
            self.assertFalse(hasattr(view, "reset_button"))
        with patch.object(
            self.auth, "pin_lock_seconds_remaining", new=AsyncMock(return_value=0)
        ):
            await self.app._lock_countdown(view)
        self.assertFalse(view._locked)

    async def test_repeat_pin_locks_input_but_allows_cancel_and_uses_same_timer(self):
        view = RecoveryCodePinView(AsyncMock(), AsyncMock())
        self.app._code_pin_view = view
        self.app._pin_login_view = None
        view.set_locked(300)
        self.assertTrue(view.pin_field.disabled)
        self.assertTrue(view.confirm_button.disabled)
        self.assertFalse(view.cancel_button.disabled)
        with patch.object(
            self.auth, "pin_lock_seconds_remaining", new=AsyncMock(return_value=0)
        ):
            await self.app._lock_countdown(view)
        self.assertFalse(view.pin_field.disabled)
        self.assertTrue(view.confirm_button.disabled)

    async def test_old_view_and_failed_backend_read_never_unlock_current_input(self):
        old = self.app._pin_login_view
        assert old is not None
        self.app._show_pin_login()
        backend = AsyncMock(return_value=0)
        with patch.object(self.auth, "pin_lock_seconds_remaining", backend):
            await self.app._lock_countdown(old)
        backend.assert_not_awaited()
        current = self.app._pin_login_view
        assert current is not None
        current.set_locked(300)
        with patch.object(
            self.auth,
            "pin_lock_seconds_remaining",
            new=AsyncMock(side_effect=OSError("synthetic")),
        ):
            await self.app._lock_countdown(current)
        self.assertTrue(current.pin_field.disabled)
        self.assertEqual(current.message.value, tr("protection.unavailable"))
