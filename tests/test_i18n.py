"""Переводит только явные ресурсы, сохраняя пользовательские данные и controls."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.models import ChatMode  # noqa: E402
from i18n import (  # noqa: E402
    CATALOGUES,
    configure_localization,
    display_chat_title,
    fresh_text,
    get_language,
    localize_tree,
    money,
    set_language,
    tr,
)
from preferences import PreferencesStore  # noqa: E402
from tests import test_chat_menu as menu_fixture  # noqa: E402
from tests.test_chat_view import _chat  # noqa: E402
from ui.auth_view import (  # noqa: E402
    KeyEntryView,
    PinLoginView,
    PinSetupView,
    StorageErrorView,
)
from ui.chat_limits_view import ChatLimitsForm  # noqa: E402
from ui.chat_view import RenameChatDialog  # noqa: E402
from ui.language_selector import LanguageSelector  # noqa: E402


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    def test_catalogues_have_identical_keys_and_parameters(self):
        self.assertEqual(CATALOGUES["ru"].keys(), CATALOGUES["en"].keys())
        self.assertGreater(len(CATALOGUES["ru"]), 150)
        for key in CATALOGUES["ru"]:

            def names(value):
                return {n for _, n, _, _ in Formatter().parse(value) if n}

            self.assertEqual(
                names(CATALOGUES["ru"][key]), names(CATALOGUES["en"][key]), key
            )

    def test_actual_flet_page_dialog_stack_updates_in_place(self):
        from flet.controls.base_page import BasePage

        page = BasePage()
        dialog = ft.AlertDialog(
            title=ft.Text(tr("chat.rename_title")),
            content=ft.TextField(value="Новый чат"),
        )
        page._dialogs.controls.append(dialog)
        set_language("en")
        localize_tree(page)
        self.assertIs(page._dialogs.controls[0], dialog)
        assert isinstance(dialog.title, ft.Text)
        assert isinstance(dialog.content, ft.TextField)
        self.assertEqual(dialog.title.value, "Rename chat")
        self.assertEqual(dialog.content.value, "Новый чат")

    def test_plain_user_strings_and_nested_translations_are_distinct(self):
        user_title = "Новый чат"
        translated = tr("chat.delete_body", title=user_title)
        nested = tr(
            "chat.subtitle", mode=tr("chat.free"), model="provider/Русская-model"
        )
        user = ft.Text(user_title)
        app = ft.Text(translated)
        mode = ft.Text(nested)
        editor = ft.TextField(value="New chat\nНовый чат\n0123")
        root = ft.Column([user, app, mode, editor])
        set_language("en")
        localize_tree(root)
        self.assertEqual(user.value, user_title)
        self.assertEqual(editor.value, "New chat\nНовый чат\n0123")
        self.assertIn(user_title, app.value)
        self.assertTrue(app.value.startswith("The chat"))
        self.assertEqual(mode.value, "Free · provider/Русская-model")
        self.assertNotIn(user_title, repr(translated))
        self.assertEqual(fresh_text(translated), app.value)
        self.assertEqual(copy.deepcopy(translated).key, "chat.delete_body")

    def test_language_selector_and_builtin_model_search_use_current_locale(self):
        from chat.models import FREE_ROUTER_MODEL
        from ui.model_selection_view import filter_models

        calls = []
        configure_localization(PreferencesStore(), lambda: calls.append("language"))
        selector = LanguageSelector()
        selector.value = "en"
        selector._select(ft.Event(name="select", control=selector))
        self.assertEqual(get_language(), "en")
        self.assertEqual(calls, ["language"])
        self.assertEqual(
            filter_models((FREE_ROUTER_MODEL,), "Automatic"), (FREE_ROUTER_MODEL,)
        )
        self.assertEqual(
            FREE_ROUTER_MODEL.name, "Автоматический выбор бесплатной модели"
        )

    def test_rename_placeholder_hint_translates_but_typed_or_legacy_titles_do_not(self):
        placeholder = replace(_chat(), title="Новый чат", title_origin="placeholder")
        dialog = RenameChatDialog(placeholder, AsyncMock(), lambda: None)
        self.assertEqual(dialog.title_field.value, "")
        self.assertEqual(dialog.title_field.hint_text, "Новый чат")
        dialog.title_field.value = "Новый чат / New chat"
        set_language("en")
        localize_tree(dialog.control)
        self.assertEqual(dialog.title_field.value, "Новый чат / New chat")
        self.assertEqual(dialog.title_field.hint_text, "New chat")
        for origin in ("legacy", "manual", "message"):
            for title in ("Новый чат", "New chat"):
                view = RenameChatDialog(
                    replace(_chat(), title=title, title_origin=origin),
                    AsyncMock(),
                    lambda: None,
                )
                self.assertEqual(view.title_field.value, title)
                self.assertIsNone(view.title_field.hint_text)

    def test_only_explicit_placeholder_titles_change(self):
        for title in ("Новый чат", "New chat", "  Пользовательский заголовок  "):
            for origin in ("legacy", "manual", "message"):
                self.assertEqual(
                    display_chat_title(
                        SimpleNamespace(title=title, title_origin=origin)
                    ),
                    title,
                )
        placeholder = SimpleNamespace(title="", title_origin="placeholder")
        self.assertEqual(display_chat_title(placeholder), "Новый чат")
        set_language("en")
        self.assertEqual(display_chat_title(placeholder), "New chat")

    def test_auth_switch_preserves_typed_values_and_pending_state(self):
        callback = AsyncMock()
        setup = PinSetupView(tr("auth.choose_pin"), callback, lambda: "1234", callback)
        setup.pin_field.value = setup.repeat_field.value = "0123"
        setup.set_busy(True)
        views = [
            setup,
            KeyEntryView(callback),
            PinLoginView(callback, callback),
            StorageErrorView(tr("auth.storage_unavailable"), callback),
        ]
        set_language("en")
        for view in views:
            localize_tree(view.control)
            self.assertTrue(
                any(
                    isinstance(c, LanguageSelector)
                    for c in view.control.content.controls
                )
            )
        self.assertEqual(setup.pin_field.value, "0123")
        self.assertEqual(setup.repeat_field.value, "0123")
        self.assertTrue(setup.confirm_button.disabled)
        self.assertEqual(setup.confirm_button.content, "Save PIN")
        callback.assert_not_called()

    def test_open_dialog_values_and_locale_decimal_presentation(self):
        callback = AsyncMock()
        dialog = RenameChatDialog(_chat(), callback, lambda: None)
        dialog.title_field.value = "New chat"
        form = ChatLimitsForm(ChatMode.PAID, callback)
        form.token_limit.value = "100000"
        assert form.cost_limit is not None
        form.cost_limit.value = "0.005"
        amount = ft.Text(money(Decimal("0.005")))
        self.assertEqual(amount.value, "0,005 USD")
        set_language("en")
        for control in (dialog.control, form.control, amount):
            localize_tree(control)
        self.assertEqual(dialog.title_field.value, "New chat")
        self.assertEqual(form.token_limit.value, "100000")
        self.assertEqual(form.cost_limit.value, "0.005")
        self.assertEqual(amount.value, "$0.005")
        callback.assert_not_called()

    def test_preferences_are_separate_and_reopen_before_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            preferences = PreferencesStore(path)
            configure_localization(preferences)
            set_language("en")
            preferences.set_wide_sidebar_visible(False)
            self.assertEqual(
                set(json.loads(path.read_text())), {"language", "wide_sidebar_visible"}
            )
            configure_localization(PreferencesStore(path))
            self.assertEqual(get_language(), "en")
            self.assertEqual(tr("auth.sign_in"), "Sign in")
            self.assertFalse(PreferencesStore(path).wide_sidebar_visible)


class WorkspaceLanguageTests(unittest.IsolatedAsyncioTestCase):
    page: menu_fixture.FakePage
    calls: list[tuple[str, tuple[str, ...]]]
    view = menu_fixture.ChatMenuTests.view
    click = menu_fixture.ChatMenuTests.click

    def setUp(self):
        menu_fixture.ChatMenuTests.setUp(cast(menu_fixture.ChatMenuTests, self))
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_language_keeps_open_menu_drawer_and_sending(self):
        view = self.view()
        assert view.composer is not None
        view.composer.set_value("Новый чат\nNew chat")
        view.set_sending(True)
        await view.open_menu()
        drawer = self.page.drawer
        assert drawer is not None
        setattr(drawer, "_test_drawer_open", True)
        dialog, menu, history, composer = (
            view._menu_dialog,
            view._menu_list,
            view.message_history,
            view.composer,
        )
        set_language("en")
        for control in (view.control, drawer, dialog):
            localize_tree(control)
        self.assertIs(view._menu_dialog, dialog)
        self.assertIs(view._menu_list, menu)
        self.assertIs(view.message_history, history)
        self.assertIs(view.composer, composer)
        self.assertTrue(getattr(drawer, "_test_drawer_open"))
        self.assertTrue(composer.busy)
        self.assertEqual(view.editor_value, "Новый чат\nNew chat")
        assert view.rename_button is not None and view.delete_button is not None
        self.assertEqual(view.rename_button.content, "Rename")
        self.assertEqual(view.delete_button.content, "Delete chat")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
