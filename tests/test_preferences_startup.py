"""Настройки читаются до базы, а открытые предупреждения меняют язык на месте."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, PropertyMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as application  # noqa: E402
from i18n import (  # noqa: E402
    LocalizedText,
    configure_localization,
    get_language,
    get_preferences,
    localize_tree,
    set_language,
)
from preferences import PreferencesStore  # noqa: E402
from tests import test_app as app_fixtures  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui.language_selector import LanguageSelector  # noqa: E402


@dataclass
class StartupPage:
    controls: list[ft.Control] = field(default_factory=list)
    update_calls: int = 0
    locale_configuration: ft.LocaleConfiguration | None = None

    def add(self, control: ft.Control) -> None:
        self.controls.append(control)

    def update(self) -> None:
        self.update_calls += 1


class PreferencesStartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    async def test_persisted_language_is_loaded_before_database_even_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokenlogue-preferences.json"
            preferences = PreferencesStore(path)
            preferences.set_language("en")
            preferences.set_wide_sidebar_visible(False)
            database_path = Path(directory) / "tokenlogue.sqlite3"
            database_path.write_bytes(b"SYNTHETIC_EXISTING_DATABASE_MARKER")
            page = StartupPage()
            observations = []

            def unavailable_database():
                observations.append(
                    (get_language(), get_preferences().wide_sidebar_visible)
                )
                raise OSError("SYNTHETIC_STORAGE_FAILURE_NOT_FOR_UI")

            with (
                patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}),
                patch.object(
                    application, "AuthDatabase", side_effect=unavailable_database
                ) as database,
                patch.object(application, "FletSecureCredentials") as secure,
                patch.object(application, "OpenRouterClient") as network,
            ):
                await application.main(cast(ft.Page, page))
                self.assertEqual(observations, [("en", False)])
                assert page.locale_configuration is not None
                assert page.locale_configuration.current_locale is not None
                self.assertEqual(
                    page.locale_configuration.current_locale.language_code, "en"
                )
                self.assertEqual(
                    [
                        locale.language_code
                        for locale in page.locale_configuration.supported_locales
                    ],
                    ["ru", "en"],
                )
                secure.assert_not_called()
                network.assert_not_called()
                texts = [
                    c.value for c in walk(page.controls[0]) if isinstance(c, ft.Text)
                ]
                self.assertIn("Storage unavailable", texts)
                self.assertIn(
                    "The application data directory could not be opened.", texts
                )
                self.assertFalse(
                    any("SYNTHETIC_STORAGE_FAILURE" in value for value in texts)
                )
                selector = next(
                    c for c in walk(page.controls[0]) if isinstance(c, LanguageSelector)
                )
                selector.value = "ru"
                selector._select(ft.Event(name="select", control=selector))
                self.assertEqual(database.call_count, 1)
                self.assertEqual(get_language(), "ru")
                assert page.locale_configuration is not None
                assert page.locale_configuration.current_locale is not None
                self.assertEqual(
                    page.locale_configuration.current_locale.language_code, "ru"
                )
                texts = [
                    c.value for c in walk(page.controls[0]) if isinstance(c, ft.Text)
                ]
                self.assertIn("Хранилище недоступно", texts)
                self.assertEqual(
                    json.loads(path.read_text()),
                    {"language": "ru", "wide_sidebar_visible": False},
                )
                self.assertEqual(
                    {p.name for p in Path(directory).iterdir()},
                    {path.name, database_path.name},
                )
                await application.main(cast(ft.Page, page))
                self.assertEqual(observations, [("en", False), ("ru", False)])

    async def test_missing_database_with_protected_alias_never_creates_empty_database(
        self,
    ):
        for key_present, binding_present in ((True, False), (False, True)):
            with self.subTest(key=key_present, binding=binding_present):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "tokenlogue-preferences.json"
                    preferences = PreferencesStore(path)
                    preferences.set_language("en")
                    reads = []

                    async def contains(alias):
                        reads.append((alias, get_language()))
                        return (
                            key_present
                            if alias == application.DATA_KEY_ALIAS
                            else binding_present
                        )

                    backend = SimpleNamespace(
                        contains_key=AsyncMock(side_effect=contains), get=AsyncMock()
                    )
                    credentials = SimpleNamespace(storage_backend=backend)
                    page = StartupPage()
                    with (
                        patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}),
                        patch.object(
                            application,
                            "FletSecureCredentials",
                            return_value=credentials,
                        ),
                        patch.object(application, "AuthDatabase") as database,
                    ):
                        await application.main(cast(ft.Page, page))
                    database.assert_not_called()
                    backend.get.assert_not_called()
                    self.assertTrue(all(language == "en" for _, language in reads))
                    self.assertFalse(
                        (Path(directory) / application.DATABASE_FILENAME).exists()
                    )
                    self.assertEqual(
                        {p.name for p in Path(directory).iterdir()}, {path.name}
                    )
                    texts = [
                        c.value
                        for c in walk(page.controls[0])
                        if isinstance(c, ft.Text)
                    ]
                    self.assertIn("Storage unavailable", texts)

    async def test_zero_length_protected_database_is_preserved_without_initialization(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / application.DATABASE_FILENAME
            database_path.write_bytes(b"")
            backend = SimpleNamespace(
                contains_key=AsyncMock(return_value=True), get=AsyncMock()
            )
            page = StartupPage()
            with (
                patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}),
                patch.object(
                    application,
                    "FletSecureCredentials",
                    return_value=SimpleNamespace(storage_backend=backend),
                ),
                patch.object(application, "AuthDatabase") as database,
            ):
                await application.main(cast(ft.Page, page))
            database.assert_not_called()
            backend.get.assert_not_called()
            self.assertEqual(database_path.read_bytes(), b"")
            self.assertEqual(
                {p.name for p in Path(directory).iterdir()}, {database_path.name}
            )

    async def test_composed_lock_warning_retranslates_without_replacing_pin_view(self):
        page = app_fixtures.FakePage()
        auth = app_fixtures.FakeAuthService()
        controller = app_fixtures._make_controller(page, auth)
        self.addCleanup(controller.dispose)

        def language_changed():
            localize_tree(page.controls)

        configure_localization(PreferencesStore(), language_changed)
        with patch.object(
            type(controller._chat_controller),
            "draft_save_failed",
            new_callable=PropertyMock,
            return_value=True,
        ):
            await controller._handle_chat_lock()
        view = controller._pin_login_view
        assert view is not None
        view.pin_field.value = "0123"
        self.assertIsInstance(view.message.value, LocalizedText)
        self.assertIn("Последний текст остаётся в памяти", view.message.value)
        set_language("en")
        self.assertIs(controller._pin_login_view, view)
        self.assertEqual(view.pin_field.value, "0123")
        self.assertTrue(view.message.value.startswith("The application is locked."))
        self.assertIn("The latest text remains in memory", view.message.value)
        self.assertFalse(any("А" <= char <= "я" for char in view.message.value))
        self.assertEqual(auth.key_calls, 0)
        self.assertEqual(auth.reset_calls, 0)


if __name__ == "__main__":
    unittest.main()
