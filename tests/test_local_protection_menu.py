"""A cold desktop can request preparation before a ScreenSaver owner exists."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import set_language  # noqa: E402
from platform_security.local_protection import (  # noqa: E402
    CheckResult,
    CheckState,
    ProtectionSnapshot,
)
from tests import test_chat_menu as fixtures  # noqa: E402
from ui.security_status import protection_notice  # noqa: E402


class LocalProtectionMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fx = fixtures.ChatMenuTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    async def test_cold_owner_missing_empty_workspace_can_start_preparation(self):
        start = AsyncMock()
        view = self.fx.view(
            protection_status=ProtectionSnapshot(
                CheckResult(), CheckResult(), False, True, False
            ),
            on_test_screen_lock=start,
        )
        self.addCleanup(view.dispose)
        view.update_workspace(
            [],
            None,
            None,
            key_validity=view._key_validity,
            key_limit=view._key_limit,
            key_validation_in_progress=False,
        )
        await view.open_protection()
        button = view.screen_test_button
        assert button is not None
        self.assertFalse(button.disabled)
        status = view._protection_status
        assert status is not None
        self.assertFalse(status.screen_connected)
        self.assertFalse(start.called)
        await self.fx.click(button)
        start.assert_awaited_once()
        self.assertFalse(view.protection_open)

    async def test_running_check_disables_duplicate_start_even_without_owner(self):
        view = self.fx.view(
            protection_status=ProtectionSnapshot(
                CheckResult(CheckState.RUNNING, "preparing"),
                CheckResult(),
                False,
                True,
                True,
            ),
            on_test_screen_lock=AsyncMock(),
        )
        self.addCleanup(view.dispose)
        await view.open_protection()
        button = view.screen_test_button
        assert button is not None
        self.assertTrue(button.disabled)

    async def test_confirmed_screen_keeps_green_when_sleep_is_untested(self):
        view = self.fx.view(
            protection_status=ProtectionSnapshot(
                CheckResult(CheckState.CONFIRMED, "screen_confirmed"),
                CheckResult(),
                True,
                True,
                False,
            ),
            on_test_screen_lock=AsyncMock(),
        )
        self.addCleanup(view.dispose)
        await view.open_protection()
        assert view.protection_button is not None
        assert view.screen_test_button is not None
        self.assertEqual(view.protection_button.icon_color, ft.Colors.GREEN_300)
        self.assertFalse(view.screen_test_button.disabled)
        status = view._protection_status
        assert status is not None
        self.assertEqual(status.sleep.state, CheckState.UNTESTED)

    def test_failure_reasons_have_distinct_localized_explanations(self):
        for language in ("en", "ru"):
            set_language(language)
            notices = []
            for code in (
                "preparation_timeout",
                "locker_contract_unavailable",
                "normal_reaction_unproven",
                "observation_unavailable",
                "request_unavailable",
                "observer_changed",
                "timeout",
                "unlock_timeout",
            ):
                notice = protection_notice(
                    ProtectionSnapshot(
                        CheckResult(CheckState.UNTESTED, code),
                        CheckResult(),
                        False,
                        True,
                        False,
                    )
                )
                self.assertTrue(notice)
                self.assertNotIn("local_protection.", notice)
                self.assertNotIn(code, notice)
                notices.append(notice)
            self.assertEqual(len(notices), len(set(notices)))
