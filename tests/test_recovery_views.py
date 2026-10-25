"""Восстановление запускается явно и не повторяется при смене языка."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization, localize_tree, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui import auth_view  # noqa: E402
from ui.language_selector import LanguageSelector  # noqa: E402


class RecoveryViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_login_recovery_is_optional_and_has_singleflight(self):
        ordinary = auth_view.PinLoginView(AsyncMock(), AsyncMock())
        self.assertIsNone(ordinary.forgot_pin_button)
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def recover():
            calls.append("challenge")
            entered.set()
            await release.wait()

        view = auth_view.PinLoginView(AsyncMock(), AsyncMock(), on_forgot_pin=recover)
        view.set_locked(30)
        button = view.forgot_pin_button
        assert button is not None
        event = ft.Event(name="click", control=button)
        pending = asyncio.create_task(view._request_recovery(event))
        await entered.wait()
        self.assertTrue(button.disabled)
        await view._request_recovery(event)
        view.pin_field.value = "0123"
        set_language("en")
        localize_tree(view.control)
        self.assertEqual(view.pin_field.value, "0123")
        self.assertEqual(button.content, "Forgot PIN?")
        self.assertEqual(calls, ["challenge"])
        view.dispose()
        release.set()
        await pending
        self.assertTrue(button.disabled)

    async def test_protected_key_replacement_dialog_translates_without_old_reset_claim(
        self,
    ):
        confirm = AsyncMock()
        dialog = auth_view.build_reset_dialog(
            confirm,
            lambda: None,
            title=tr("recovery.replace_key_title"),
            message=tr("recovery.replace_key_notice"),
            confirm_label=tr("recovery.replace_key_confirm"),
        )
        set_language("en")
        localize_tree(dialog)
        assert isinstance(dialog.title, ft.Text)
        assert isinstance(dialog.content, ft.Text)
        self.assertEqual(dialog.title.value, "Replace OpenRouter key?")
        self.assertIn(
            "Your app PIN, conversation encryption key, history and drafts are kept.",
            dialog.content.value,
        )
        self.assertNotIn("will be removed", dialog.content.value)
        confirm.assert_not_called()

    async def test_waiting_recovery_keeps_prompt_and_allows_cancel(self):
        retry, cancel = AsyncMock(), AsyncMock()
        view = auth_view.DeviceRecoveryView(retry, cancel, busy=True)
        control = view.control
        set_language("en")
        localize_tree(view.control)
        self.assertIs(view.control, control)
        self.assertTrue(view.retry_button.disabled)
        self.assertFalse(view.cancel_button.disabled)
        self.assertTrue(
            any(isinstance(c, LanguageSelector) for c in walk(view.control))
        )
        await view._retry(ft.Event(name="click", control=view.retry_button))
        retry.assert_not_called()
        await view._cancel(ft.Event(name="click", control=view.cancel_button))
        cancel.assert_awaited_once()
        retry.assert_not_called()

    async def test_recovery_pin_choice_reuses_fields_and_requires_repeat(self):
        confirm = AsyncMock()
        view = auth_view.PinSetupView(
            tr("recovery.verified_notice"),
            confirm,
            lambda: "0123",
            AsyncMock(),
            title=tr("recovery.choose_new_pin"),
            instructions=tr("recovery.choose_instructions"),
            confirm_label=tr("recovery.save_new_pin"),
        )
        first, repeat = view.pin_field, view.repeat_field
        first.value = "0123"
        repeat.value = "0124"
        await view._submit_value()
        confirm.assert_not_called()
        repeat.value = "0123"
        set_language("en")
        localize_tree(view.control)
        self.assertIs(view.pin_field, first)
        self.assertIs(view.repeat_field, repeat)
        self.assertEqual(first.value, "0123")
        self.assertEqual(repeat.value, "0123")
        self.assertEqual(view.confirm_button.content, "Save new PIN")
        texts = [c.value for c in walk(view.control) if isinstance(c, ft.Text)]
        self.assertIn("Choose a new PIN", texts)
        self.assertIn(tr("recovery.choose_instructions"), texts)
        import ui

        self.assertIs(ui.DeviceRecoveryView, auth_view.DeviceRecoveryView)
        await view._submit_value()
        confirm.assert_awaited_once_with("0123")


if __name__ == "__main__":
    unittest.main()
