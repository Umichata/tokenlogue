"""Public protection navigation preserves inputs and delegates all privileged work."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization, set_language, tr  # noqa: E402
from platform_security.local_protection import CheckResult, CheckState  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests import test_chat_menu as menu_fixtures  # noqa: E402
from tests.test_chat_menu import texts, walk  # noqa: E402
from tests.test_chat_view import FakePage  # noqa: E402
from tests.test_device_protection_ui import confirmed_snapshot  # noqa: E402
from ui.auth_view import PinLoginView  # noqa: E402
from ui.protection_panel import (  # noqa: E402
    ProtectionPanel,
    protection_shield,
    update_protection_shield,
)
from ui.styles import ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR  # noqa: E402


class SharedProtectionPanelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.page = FakePage(420)
        self.selected = AsyncMock()
        self.started = AsyncMock()
        self.closed = []
        self.panel = ProtectionPanel(
            cast(ft.Page, self.page),
            on_test=self.selected,
            on_start=self.started,
            on_close=self.closed.append,
            locked=True,
        )
        self.addCleanup(self.panel.close)
        self.snapshot = confirmed_snapshot()
        self.shield = protection_shield(self.snapshot, AsyncMock())

    async def click(self, button):
        await button.on_click(ft.Event(name="click", control=button))

    async def test_viewing_from_pin_never_authorizes_or_launches_an_os_action(self):
        login = AsyncMock()
        pin = PinLoginView(login, protection_shield=self.shield)
        pin.pin_field.value = "01"
        self.panel.open(self.snapshot, shield=self.shield)
        self.assertTrue(self.panel.is_open)
        self.assertFalse(self.panel.screen_test_button.disabled)
        self.assertFalse(self.panel.sleep_test_button.disabled)
        self.assertIn(
            tr("protection_panel.sign_in_explanation"), texts(self.panel.content)
        )
        self.selected.assert_not_awaited()
        self.started.assert_not_awaited()
        login.assert_not_awaited()
        await self.click(self.panel.sleep_test_button)
        self.selected.assert_awaited_once_with("sleep")
        self.started.assert_not_awaited()
        self.assertEqual(pin.pin_field.value, "01")

    async def test_auth_handoff_and_user_close_are_distinct_and_restore_shield_focus(
        self,
    ):
        self.panel.open(self.snapshot, shield=self.shield)
        old_dialog = self.page.dialogs[-1]
        self.panel.close("auth_handoff")
        self.assertEqual(self.closed, ["auth_handoff"])
        # A delayed native dismiss of the old dialog cannot cancel its successor.
        self.panel.open(self.snapshot, shield=self.shield)
        await self.panel._native_dismissed(ft.Event(name="dismiss", control=old_dialog))
        self.assertTrue(self.panel.is_open)
        with patch.object(self.shield, "focus", AsyncMock()) as focus:
            await self.panel._native_dismissed(
                ft.Event(name="dismiss", control=self.page.dialogs[-1])
            )
            focus.assert_awaited_once()
        self.assertEqual(self.closed, ["auth_handoff", "user"])
        self.assertFalse(self.panel.is_open)

    async def test_signing_in_does_not_start_selected_test_and_requires_explicit_start(
        self,
    ):
        self.panel.set_context(locked=False)
        self.panel.open(
            self.snapshot, selected_test="screen", confirm_test=True, shield=self.shield
        )
        self.assertTrue(self.panel.selection.visible)
        self.assertFalse(self.panel.start_button.disabled)
        self.started.assert_not_awaited()
        self.selected.assert_not_awaited()
        await self.click(self.panel.start_button)
        self.started.assert_awaited_once_with("screen")
        self.selected.assert_not_awaited()
        self.panel.close()
        await self.click(self.panel.start_button)
        self.started.assert_awaited_once()

    async def test_pending_start_rejects_second_click_without_parallel_request(self):
        reached, finish = asyncio.Event(), asyncio.Event()

        async def deferred(mechanism):
            self.assertEqual(mechanism, "sleep")
            reached.set()
            await finish.wait()

        self.panel._on_start = deferred
        self.panel.set_context(locked=False)
        self.panel.open(self.snapshot, selected_test="sleep", confirm_test=True)
        first = asyncio.create_task(self.click(self.panel.start_button))
        await reached.wait()
        self.assertTrue(self.panel.start_button.disabled)
        self.assertTrue(self.panel.screen_test_button.disabled)
        await self.click(self.panel.start_button)
        await self.click(self.panel.screen_test_button)
        self.selected.assert_not_awaited()
        finish.set()
        await first
        self.assertFalse(self.panel.start_button.disabled)

    async def test_history_times_and_present_warnings_survive_stable_control_refresh(
        self,
    ):
        self.panel.open(self.snapshot)
        screen, sleep = self.panel.screen_test_button, self.panel.sleep_test_button
        for language in ("en", "ru"):
            set_language(language)
            status = replace(
                self.snapshot, screen_connected=False, persistence_error=True
            )
            self.panel.refresh(status)
            displayed = texts(self.panel.content)
            self.assertEqual(sum("2025-01-01" in line for line in displayed), 2)
            self.assertIn(tr("local_protection.screen_monitor_warning"), displayed)
            self.assertIn(tr("local_protection.save_failed"), displayed)
            self.assertIs(self.panel.screen_test_button, screen)
            self.assertIs(self.panel.sleep_test_button, sleep)
            update_protection_shield(self.shield, status)
            self.assertEqual(self.shield.icon_color, WARNING_COLOR)
        self.selected.assert_not_awaited()
        self.started.assert_not_awaited()

    async def test_shield_uses_existing_readiness_and_never_paints_problem_green(self):
        for status, color in (
            (self.snapshot, SUCCESS_COLOR),
            (replace(self.snapshot, sleep_connected=False), WARNING_COLOR),
            (replace(self.snapshot, screen_stale=True), WARNING_COLOR),
            (replace(self.snapshot, persistence_error=True), WARNING_COLOR),
            (
                replace(
                    self.snapshot,
                    sleep=CheckResult(CheckState.PROBLEM, "normal_seal_failed"),
                ),
                ERROR_COLOR,
            ),
        ):
            with self.subTest(color=color):
                update_protection_shield(self.shield, status)
                self.assertEqual(self.shield.icon_color, color)
                self.assertTrue(self.shield.tooltip)
                self.assertEqual(self.shield.width, 48)
                self.assertEqual(self.shield.height, 48)
                assert self.shield.style is not None
                assert isinstance(self.shield.style.side, dict)
                self.assertIn(ft.ControlState.FOCUSED, self.shield.style.side)

    async def test_narrow_panel_scrolls_with_close_outside_scroll_content(self):
        self.panel.open(self.snapshot)
        dialog = self.page.dialogs[-1]
        assert isinstance(dialog, ft.AlertDialog)
        self.assertFalse(dialog.modal)
        self.assertEqual(dialog.alignment, ft.Alignment.TOP_RIGHT)
        self.assertNotIn(self.panel.close_button, list(walk(self.panel.content)))
        for width, height in ((1280, 750), (420, 700), (360, 640), (700, 360)):
            self.panel.resize(width, height)
            assert self.panel._container.width is not None
            assert self.panel._container.height is not None
            self.assertLessEqual(self.panel._container.width, width - 64)
            self.assertLessEqual(self.panel._container.height, height - 172)
            self.assertIsInstance(self.panel.content, ft.ListView)

    async def test_android_uses_common_panel_without_desktop_test_controls(self):
        android = ProtectionPanel(
            cast(ft.Page, self.page), on_test=self.selected, desktop_tests=False
        )
        self.addCleanup(android.close)
        android.open(self.snapshot)
        nodes = list(walk(android.content))
        self.assertIn(android.platform_notice, nodes)
        self.assertNotIn(android.screen_test_button, nodes)
        self.assertNotIn(android.sleep_test_button, nodes)
        self.assertNotIn(android.start_button, nodes)
        await self.click(android.sleep_test_button)
        self.selected.assert_not_awaited()


class ProtectionWorkspacePreservationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = menu_fixtures.ChatMenuTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    async def test_chat_shield_and_menu_entry_open_the_same_panel_without_inline_copy(
        self,
    ):
        view = self.fixture.view(protection_status=confirmed_snapshot())
        self.addCleanup(view.dispose)
        await view.open_menu()
        assert view._menu_list is not None
        displayed = texts(view._menu_list)
        self.assertIn(tr("protection_panel.open"), displayed)
        self.assertNotIn(tr("local_protection.test_screen"), displayed)
        self.assertNotIn(tr("local_protection.test_sleep"), displayed)
        entry = next(
            c
            for c in walk(view._menu_list)
            if isinstance(c, ft.TextButton) and c.content == tr("protection_panel.open")
        )
        await self.fixture.click(entry)
        self.assertFalse(view.menu_open)
        self.assertTrue(view.protection_open)
        panel = view.protection_panel
        panel.close()
        assert view.protection_button is not None
        await self.fixture.click(view.protection_button)
        self.assertIs(view.protection_panel, panel)
        self.assertTrue(panel.is_open)
        self.assertEqual(self.fixture.calls, [])

    async def test_protection_status_resize_and_dismiss_preserve_exact_draft_and_editor(
        self,
    ):
        view = self.fixture.view(protection_status=confirmed_snapshot())
        self.addCleanup(view.dispose)
        assert view.composer is not None and view.message_history is not None
        composer, history = view.composer, view.message_history
        field = composer.message_field
        draft = "  Synthetic draft\n`code` 🙂\n "
        composer.set_value(draft)
        await view.open_protection()
        panel = view.protection_panel
        original_layout = view._layout.content
        view.set_protection_status(
            replace(confirmed_snapshot(), screen_connected=False)
        )
        self.assertIs(view._layout.content, original_layout)
        with patch.object(ft.Control, "update"):
            for width, height in ((1280, 750), (360, 700), (700, 360)):
                view._handle_size_change(
                    cast(
                        ft.LayoutSizeChangeEvent,
                        SimpleNamespace(width=width, height=height),
                    )
                )
        await panel.dismiss()
        self.assertIs(view.composer, composer)
        self.assertIs(view.message_history, history)
        self.assertIs(composer.message_field, field)
        self.assertEqual(view.editor_value, draft)
        self.assertEqual(self.fixture.calls, [])

    async def test_android_header_has_shared_shield_and_far_right_options(self):
        setattr(self.fixture.page, "platform", ft.PagePlatform.ANDROID)
        view = self.fixture.view()
        self.addCleanup(view.dispose)
        assert view.protection_button is not None
        self.assertEqual(view.protection_button.tooltip, tr("protection_panel.open"))
        header = next(
            c
            for c in walk(view.control)
            if isinstance(c, ft.Row) and view.menu_button in c.controls
        )
        self.assertIs(header.controls[-1], view.menu_button)
        await self.fixture.click(view.protection_button)
        self.assertTrue(view.protection_open)
        nodes = list(walk(view.protection_panel.content))
        self.assertNotIn(view.protection_panel.screen_test_button, nodes)
        self.assertNotIn(view.protection_panel.sleep_test_button, nodes)
