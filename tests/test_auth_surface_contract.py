"""Общая шапка и безопасные действия формы без клиента и настоящего профиля."""

from __future__ import annotations

import sys
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization, localize_tree, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui.auth_view import KeyEntryView, PinLoginView, PinSetupView  # noqa: E402
from ui.branding import AuthHeader  # noqa: E402
from ui.language_selector import LanguageSelector  # noqa: E402
from ui.profile_deletion_view import ProfileDeletionDialog  # noqa: E402


class AuthSurfaceContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_shared_header_keeps_shield_last_and_notice_outside_pin_form(self):
        show_details = AsyncMock()
        shield = ft.IconButton(icon=ft.Icons.SHIELD_OUTLINED, on_click=show_details)
        login = AsyncMock()
        view = PinLoginView(
            login, notice="Synthetic protection status", protection_shield=shield
        )
        self.assertIsInstance(view.header, AuthHeader)
        self.assertIs(view.header.row.controls[-1], shield)
        self.assertEqual(
            sum(isinstance(c, LanguageSelector) for c in walk(view.control)), 1
        )
        self.assertNotIn(view.notice, list(walk(view.control)))
        self.assertFalse(view.notice.visible)
        self.assertEqual(view.notice.value, "Synthetic protection status")
        view.pin_field.value = "0123"
        assert shield.on_click is not None
        handler = cast(Callable[[ft.Event], Awaitable[None]], shield.on_click)
        await handler(ft.Event(name="click", control=shield))
        show_details.assert_awaited_once()
        login.assert_not_awaited()
        self.assertEqual(view.pin_field.value, "0123")

    async def test_neutral_lock_message_is_deduplicated_but_real_error_remains(self):
        view = PinLoginView(AsyncMock())
        view.show_message(tr("service.app_locked"))
        self.assertFalse(view.message.visible)
        view.show_message(tr("protection.access_closed"))
        self.assertFalse(view.message.visible)
        view.show_message(tr("auth.pin_mismatch"))
        self.assertTrue(view.message.visible)
        view.set_locked(35)
        self.assertTrue(view.message.visible)
        self.assertIn("00:35", str(view.message.value))
        self.assertTrue(view.submit_button.disabled)

    async def test_protection_route_prompt_has_own_cancel_and_keeps_pin_error(self):
        cancel = AsyncMock()
        login = AsyncMock()
        view = PinLoginView(login)
        view.pin_field.value = "0123"
        view.show_message(tr("auth.pin_mismatch"))
        view.set_protection_prompt("Synthetic selected check", cancel)
        message = view.message.value
        with patch.object(view.pin_field, "focus", AsyncMock()) as focus:
            await view.focus_pin()
        focus.assert_awaited_once()
        self.assertEqual(view.pin_field.value, "0123")
        self.assertEqual(view.message.value, message)
        self.assertTrue(view.message.visible)
        await view._cancel_protection(
            ft.Event(name="click", control=view.cancel_protection_button)
        )
        cancel.assert_awaited_once()
        self.assertFalse(view.protection_prompt.visible)
        login.assert_not_awaited()
        self.assertEqual(view.pin_field.value, "0123")
        await view._cancel_protection(
            ft.Event(name="click", control=view.cancel_protection_button)
        )
        cancel.assert_awaited_once()

    async def test_language_change_and_locked_status_preserve_control_identity(self):
        view = PinLoginView(
            AsyncMock(), protection_shield=ft.IconButton(icon=ft.Icons.SHIELD)
        )
        field, header, control = view.pin_field, view.header, view.control
        view.pin_field.value = "01"
        view.set_locked(50)
        set_language("en")
        localize_tree(view.control)
        self.assertIs(view.pin_field, field)
        self.assertIs(view.header, header)
        self.assertIs(view.control, control)
        self.assertEqual(field.value, "01")
        self.assertTrue(field.disabled)
        self.assertTrue(view.submit_button.disabled)
        self.assertIn("00:50", str(view.message.value))

    async def test_auth_stages_keep_one_header_and_scroll_without_fixed_height(self):
        for view in (
            KeyEntryView(AsyncMock()),
            PinLoginView(AsyncMock()),
            PinSetupView("", AsyncMock(), lambda: "0123", AsyncMock()),
        ):
            with self.subTest(view=type(view).__name__):
                nodes = list(walk(view.control))
                self.assertEqual(sum(isinstance(c, AuthHeader) for c in nodes), 1)
                self.assertEqual(sum(isinstance(c, LanguageSelector) for c in nodes), 1)
                self.assertTrue(
                    any(isinstance(c, ft.ListView) and c.expand for c in nodes)
                )
                for field in (c for c in nodes if isinstance(c, ft.TextField)):
                    self.assertIsNone(field.height)

    async def test_profile_delete_requires_explicit_action_after_phrase(self):
        destroy = AsyncMock()
        dialog = ProfileDeletionDialog(destroy, lambda: None)
        dialog.phrase_field.value = dialog.phrase
        dialog._apply()
        self.assertFalse(dialog.confirm_button.disabled)
        self.assertIsNone(dialog.phrase_field.on_submit)
        self.assertTrue(dialog.cancel_button.autofocus)
        destroy.assert_not_awaited()
        await dialog._confirm(ft.Event(name="click", control=dialog.confirm_button))
        destroy.assert_awaited_once_with(dialog.phrase)
