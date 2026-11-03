"""Общий PIN экран сохраняет порядок и раздельные действия при блокировке."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui.auth_view import PinLoginView  # noqa: E402


class PinActionsOrderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_visual_and_default_focus_order_in_both_languages(self):
        for language in ("en", "ru"):
            set_language(language)
            with self.subTest(language=language):
                view = PinLoginView(
                    AsyncMock(),
                    on_forgot_pin=AsyncMock(),
                    on_delete_profile=AsyncMock(),
                )
                actions = [
                    control
                    for control in walk(view.control)
                    if isinstance(control, (ft.Button, ft.TextButton))
                    and control.visible
                ]
                self.assertEqual(
                    actions,
                    [
                        view.submit_button,
                        view.delete_profile_button,
                        view.forgot_pin_button,
                    ],
                )
                self.assertEqual(
                    [str(button.content) for button in actions],
                    [
                        str(tr("auth.sign_in")),
                        str(tr("profile_deletion.entry")),
                        str(tr("recovery.forgot_pin")),
                    ],
                )
                self.assertTrue(view.control.expand)
                self.assertFalse(hasattr(view, "reset_button"))
                self.assertFalse(hasattr(view, "_on_reset_requested"))
                self.assertTrue(
                    any(isinstance(c, ft.ListView) for c in walk(view.control))
                )

    async def test_each_action_keeps_its_handler_and_throttle_busy_disposal_guards(
        self,
    ):
        login, recover, delete = (AsyncMock() for _ in range(3))
        view = PinLoginView(login, on_forgot_pin=recover, on_delete_profile=delete)
        view.pin_field.value = "0123"
        view._apply_pin_state()
        await view._handle_click(ft.Event(name="click", control=view.submit_button))
        login.assert_awaited_once_with("0123")
        view.set_locked(30)
        self.assertTrue(view.submit_button.disabled)
        assert view.delete_profile_button is not None
        assert view.forgot_pin_button is not None
        self.assertFalse(view.delete_profile_button.disabled)
        self.assertFalse(view.forgot_pin_button.disabled)
        await view._request_profile_deletion(
            ft.Event(name="click", control=view.delete_profile_button)
        )
        delete.assert_awaited_once_with()
        recover.assert_not_called()
        await view._request_recovery(
            ft.Event(name="click", control=view.forgot_pin_button)
        )
        recover.assert_awaited_once_with()
        view.set_busy(True)
        self.assertTrue(view.delete_profile_button.disabled)
        self.assertTrue(view.forgot_pin_button.disabled)
        await view._request_profile_deletion(
            ft.Event(name="click", control=view.delete_profile_button)
        )
        await view._request_recovery(
            ft.Event(name="click", control=view.forgot_pin_button)
        )
        view.dispose()
        await view._request_profile_deletion(
            ft.Event(name="click", control=view.delete_profile_button)
        )
        await view._request_recovery(
            ft.Event(name="click", control=view.forgot_pin_button)
        )
        self.assertEqual(delete.await_count, 1)
        self.assertEqual(recover.await_count, 1)

    async def test_missing_optional_action_does_not_rebind_the_remaining_action(self):
        for option in ("delete", "recover"):
            with self.subTest(option=option):
                action = AsyncMock()
                view = PinLoginView(
                    AsyncMock(),
                    on_delete_profile=action if option == "delete" else None,
                    on_forgot_pin=action if option == "recover" else None,
                )
                if option == "delete":
                    self.assertIsNone(view.forgot_pin_button)
                    assert view.delete_profile_button is not None
                    await view._request_profile_deletion(
                        ft.Event(name="click", control=view.delete_profile_button)
                    )
                else:
                    self.assertIsNone(view.delete_profile_button)
                    assert view.forgot_pin_button is not None
                    await view._request_recovery(
                        ft.Event(name="click", control=view.forgot_pin_button)
                    )
                action.assert_awaited_once_with()
