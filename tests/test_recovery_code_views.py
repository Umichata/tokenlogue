"""Экран резервного кода не подтверждает владение и не сохраняет секрет сам."""

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
from ui.recovery_code_view import (  # noqa: E402
    RecoveryCodeDisplayView,
    RecoveryCodeEntryView,
    RecoveryCodePinView,
)

# Это заведомо публичное тестовое значение, а не выданный приложением секрет.
SYNTHETIC_CODE = "ABCD-EFGH-IJKL-MNOP-QRST-UVWX-YZ23-4567"


class RecoveryCodeViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_unenrolled_profile_does_not_offer_generation_or_read_a_key(self):
        submit, system = AsyncMock(), AsyncMock()
        view = RecoveryCodeEntryView(
            submit, AsyncMock(), enrolled=False, on_system_recovery=system
        )
        self.assertFalse(view.code_field.visible)
        self.assertTrue(view.code_field.disabled)
        view.code_field.value = SYNTHETIC_CODE
        await view._submit_value()
        submit.assert_not_called()
        system.assert_not_called()
        assert view.system_button is not None
        await view._system_recovery(ft.Event(name="click", control=view.system_button))
        system.assert_awaited_once()
        self.assertEqual(view.code_field.value, "")
        set_language("en")
        localize_tree(view.control)
        texts = [c.value for c in walk(view.control) if isinstance(c, ft.Text)]
        self.assertIn(tr("recovery_code.not_enrolled"), texts)

    async def test_entry_is_singleflight_and_localization_never_submits(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def submit(_value: str) -> None:
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()

        view = RecoveryCodeEntryView(submit, AsyncMock(), enrolled=True)
        view.code_field.value = SYNTHETIC_CODE.lower()
        pending = asyncio.create_task(view._submit_value())
        await entered.wait()
        await view._submit_value()
        set_language("en")
        localize_tree(view.control)
        self.assertEqual(calls, 1)
        self.assertTrue(view.code_field.disabled)
        self.assertTrue(view.code_field.password)
        self.assertEqual(view.code_field.max_length, 128)
        self.assertEqual(view.code_field.value, SYNTHETIC_CODE.lower())
        view.dispose()
        release.set()
        await pending
        self.assertEqual(view.code_field.value, "")
        self.assertTrue(view.submit_button.disabled)

    async def test_current_pin_requires_four_ascii_digits_and_is_cleared(self):
        confirm = AsyncMock()
        view = RecoveryCodePinView(confirm, AsyncMock())
        for invalid in ("", "123", "12345", "１２３４", "1a34"):
            view.pin_field.value = invalid
            await view._submit_value()
        confirm.assert_not_called()
        view.pin_field.value = "0123"
        await view._submit_value()
        confirm.assert_awaited_once_with("0123")
        view.dispose()
        self.assertEqual(view.pin_field.value, "")
        await view._submit_value()
        confirm.assert_awaited_once()

    async def test_one_time_display_copies_only_after_explicit_action(self):
        copy, confirm = AsyncMock(), AsyncMock()
        view = RecoveryCodeDisplayView(
            SYNTHETIC_CODE, confirm, AsyncMock(), on_copy=copy
        )
        copy.assert_not_called()
        confirm.assert_not_called()
        self.assertEqual(view.repeat_field.value, "")
        self.assertFalse(view.code_text.no_wrap)
        self.assertIsNone(view.code_text.width)
        self.assertTrue(any(isinstance(c, ft.ListView) for c in walk(view.control)))
        self.assertNotIn(SYNTHETIC_CODE, repr(view))
        self.assertNotIn(SYNTHETIC_CODE, repr(view.code_text))
        self.assertNotIn(SYNTHETIC_CODE, repr(view.repeat_field))
        assert view.copy_button is not None
        event = ft.Event(name="click", control=view.copy_button)
        await view._copy(event)
        copy.assert_awaited_once_with(SYNTHETIC_CODE)
        view.repeat_field.value = SYNTHETIC_CODE
        await view._submit_value()
        confirm.assert_awaited_once_with(SYNTHETIC_CODE)
        view.dispose()
        self.assertEqual(view.code_text.value, "")
        self.assertEqual(view.repeat_field.value, "")
        self.assertEqual(view._code, "")
        await view._copy(event)
        await view._submit_value()
        copy.assert_awaited_once()
        confirm.assert_awaited_once()

    async def test_cancel_clears_display_before_callback_and_rejects_old_events(self):
        called = []
        view: RecoveryCodeDisplayView

        async def cancel() -> None:
            called.append("cancel")
            self.assertEqual(view.code_text.value, "")
            self.assertEqual(view.repeat_field.value, "")
            view.dispose()

        view = RecoveryCodeDisplayView(SYNTHETIC_CODE, AsyncMock(), cancel)
        view.repeat_field.value = SYNTHETIC_CODE
        event = ft.Event(name="click", control=view.cancel_button)
        await view._cancel(event)
        await view._cancel(event)
        self.assertEqual(called, ["cancel"])
        self.assertTrue(view.cancel_button.disabled)

    async def test_display_translation_keeps_controls_and_does_not_copy(self):
        copy = AsyncMock()
        view = RecoveryCodeDisplayView(
            SYNTHETIC_CODE, AsyncMock(), AsyncMock(), on_copy=copy
        )
        original = view.code_text
        for language in ("en", "ru"):
            set_language(language)
            localize_tree(view.control)
            self.assertIs(view.code_text, original)
            self.assertEqual(view.code_text.value, SYNTHETIC_CODE.replace("-", " "))
            self.assertEqual(view.repeat_field.value, "")
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
