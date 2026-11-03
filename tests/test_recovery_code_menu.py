"""Настройки резервного кода используют существующее защищённое меню чата."""

from __future__ import annotations

import sys
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from i18n import configure_localization  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests.test_chat_view import FakePage, _chat, _state  # noqa: E402
from ui.chat_view import ChatWorkspaceView  # noqa: E402


class RecoveryCodeMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    def view(self, callback: AsyncMock | None) -> ChatWorkspaceView:
        chat = _chat()
        return ChatWorkspaceView(
            cast(ft.Page, FakePage(420)),
            [chat],
            chat,
            _state(chat),
            on_new_chat=AsyncMock(),
            on_select_chat=AsyncMock(),
            on_rename_chat=AsyncMock(),
            on_delete_chat=AsyncMock(),
            on_lock=AsyncMock(),
            on_send_message=AsyncMock(),
            on_retry_turn=AsyncMock(),
            on_configure_limits=AsyncMock(),
            on_edit_limits=AsyncMock(),
            on_release_unknown=AsyncMock(),
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.unknown(),
            key_validation_in_progress=False,
            on_retry_key=AsyncMock(),
            on_replace_key=AsyncMock(),
            on_security=callback,
        )

    async def click(self, button: ft.TextButton) -> None:
        assert button.on_click is not None
        callback = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
        await callback(ft.Event(name="click", control=button))

    async def test_explicit_security_action_preserves_editor_and_rejects_stale_click(
        self,
    ) -> None:
        callback = AsyncMock()
        view = self.view(callback)
        assert view.composer is not None
        view.composer.set_value("Несохранённый черновик\n🙂")
        editor = view.composer
        await view.open_menu()
        button = view.security_button
        assert button is not None
        await self.click(button)
        callback.assert_awaited_once()
        self.assertFalse(view.menu_open)
        self.assertIs(view.composer, editor)
        self.assertEqual(view.editor_value, "Несохранённый черновик\n🙂")
        await self.click(button)
        callback.assert_awaited_once()

    async def test_security_action_is_optional_and_disabled_during_send(self) -> None:
        ordinary = self.view(None)
        await ordinary.open_menu()
        self.assertIsNone(ordinary.security_button)
        callback = AsyncMock()
        view = self.view(callback)
        await view.open_menu()
        button = view.security_button
        assert button is not None
        view.set_sending(True)
        self.assertTrue(button.disabled)
        await self.click(button)
        callback.assert_not_called()
        self.assertTrue(view.menu_open)


if __name__ == "__main__":
    unittest.main()
