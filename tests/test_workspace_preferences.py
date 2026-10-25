"""Предпочтения раскладки не меняют чат и не хранят его содержимое."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import flet as ft

from tests import test_chat_menu as menu_fixture
from tests.test_chat_menu import walk


class WorkspacePreferencesTests(unittest.IsolatedAsyncioTestCase):
    page: menu_fixture.FakePage
    calls: list[tuple[str, tuple[str, ...]]]
    view = menu_fixture.ChatMenuTests.view
    click = menu_fixture.ChatMenuTests.click

    def setUp(self):
        from i18n import configure_localization
        from preferences import PreferencesStore

        menu_fixture.ChatMenuTests.setUp(cast(menu_fixture.ChatMenuTests, self))
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_wide_toggle_preserves_editor_and_history_and_reclaims_width(self):
        self.page.width = 760
        view = self.view()
        history, composer = view.message_history, view.composer
        assert composer is not None
        composer.set_value("  Новый чат\nNew chat 🙂  ")
        view.set_sending(True)
        await view.open_menu()
        original_dialog, original_list = view._menu_dialog, view._menu_list
        assert view._menu_container is not None
        self.assertEqual(view._menu_container.width, 360)
        self.assertTrue(hasattr(view, "sidebar_button"))
        with patch.object(ft.Control, "update"):
            await self.click(view.sidebar_button)
        self.assertFalse(view.sidebar_visible)
        self.assertIs(view.message_history, history)
        self.assertIs(view.composer, composer)
        self.assertEqual(view.editor_value, "  Новый чат\nNew chat 🙂  ")
        self.assertTrue(composer.busy)
        self.assertIs(view._menu_dialog, original_dialog)
        self.assertIs(view._menu_list, original_list)
        self.assertFalse(
            any(
                isinstance(c, ft.VerticalDivider) and c.visible
                for c in walk(view.control)
            )
        )
        self.assertEqual(self.calls, [])

    async def test_narrow_editor_scrolls_without_replacing_draft_or_inflight_controls(
        self,
    ):
        self.page.width = 1280
        view = self.view()
        composer, history = view.composer, view.message_history
        assert composer is not None
        draft = "  Новый чат\nNew chat 🙂\nthird\nfourth\nfifth\nsixth  "
        composer.set_value(draft)
        view.set_sending(True)
        with patch.object(ft.Control, "update"):
            view._handle_size_change(
                cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=420, height=300))
            )
            self.assertEqual(composer.message_field.max_lines, 2)
            self.assertIs(view.composer, composer)
            self.assertIs(view.message_history, history)
            self.assertEqual(view.editor_value, draft)
            self.assertTrue(composer.busy)
            self.assertTrue(composer.send_button.disabled)
            view._handle_size_change(
                cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=1280, height=750))
            )
        self.assertEqual(composer.message_field.max_lines, 5)
        self.assertIs(view.composer, composer)
        self.assertEqual(view.editor_value, draft)
        self.assertEqual(self.calls, [])

    async def test_narrow_drawer_does_not_overwrite_wide_preference(self):
        from preferences import PreferencesStore

        with tempfile.TemporaryDirectory() as directory:
            prefs = PreferencesStore(Path(directory) / "preferences.json")
            self.page.width = 1280
            view = self.view(preferences=prefs)
            with patch.object(ft.Control, "update"):
                await self.click(view.sidebar_button)
                view._handle_size_change(
                    cast(
                        ft.LayoutSizeChangeEvent, SimpleNamespace(width=420, height=700)
                    )
                )
                await self.click(view.sidebar_button)
                view._handle_size_change(
                    cast(
                        ft.LayoutSizeChangeEvent,
                        SimpleNamespace(width=1280, height=750),
                    )
                )
            self.assertFalse(view.sidebar_visible)
            view.dispose()
            restored = self.view(preferences=PreferencesStore(prefs.path))
            self.assertFalse(restored.sidebar_visible)
            assert prefs.path is not None
            self.assertEqual(
                json.loads(prefs.path.read_text()),
                {"language": "ru", "wide_sidebar_visible": False},
            )


if __name__ == "__main__":
    unittest.main()
