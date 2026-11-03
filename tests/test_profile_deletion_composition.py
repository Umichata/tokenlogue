"""Startup и новая композиция не открывают остатки удаляемой регистрации."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as composition  # noqa: E402
from app import AppController  # noqa: E402
from auth.models import AuthStatus  # noqa: E402
from storage.data_protection import DATA_KEY_ALIAS  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.profile_deletion import PROFILE_ALIASES, ProfileDeletion  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests import test_encryption_initialization as fixtures  # noqa: E402
from tests.test_app_lifecycle import AndroidPage  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
)


class ProfileDeletionCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.EncryptionInitializationTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        protection = self.fx.protection()
        await protection.unlock("0123", self.fx.stored())
        protection.lock()
        self.storage = self.fx.storage
        self.path = self.fx.database.path
        self.controllers = []
        self.databases = []
        self.order = []
        self.page = AndroidPage()
        self.bridge = SimpleNamespace(
            supports_recovery=AsyncMock(return_value=False),
            sync_secure_storage=AsyncMock(),
        )
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for manager in (
            patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": str(self.path.parent)}),
            patch.object(ft.Control, "update"),
            patch.object(
                composition,
                "FletSecureCredentials",
                return_value=FletSecureCredentials(self.storage),
            ),
            patch.object(composition, "DeviceRecovery", return_value=self.bridge),
            patch.object(
                composition, "OpenRouterClient", return_value=FakeKeyValidator()
            ),
            patch.object(
                composition, "ModelCatalogClient", return_value=FakeCatalogClient(())
            ),
            patch.object(
                composition,
                "ChatCompletionsClient",
                return_value=FakeCompletionClient([]),
            ),
            patch.object(
                composition, "AppController", side_effect=self.capture_controller
            ),
            patch.object(composition, "AuthDatabase", side_effect=self.create_database),
        ):
            self.stack.enter_context(manager)
        self.storage.read_keys.clear()

    def capture_controller(self, *args, **kwargs):
        controller = AppController(*args, **kwargs)
        self.controllers.append(controller)
        self.addCleanup(controller.dispose)
        return controller

    def create_database(self):
        self.order.append("database")
        database = AuthDatabase(self.path.parent)
        self.databases.append(database)
        return database

    async def accepted_intent(self):
        deletion = ProfileDeletion(self.path, self.storage)
        scope = await deletion.capture()
        await deletion.accept(scope)
        return deletion

    async def test_pending_deletion_finishes_before_database_and_new_setup(self):
        await self.accepted_intent()
        original = ProfileDeletion.finish

        async def finish(deletion):
            await original(deletion)
            self.order.append("deletion_finished")

        with patch.object(ProfileDeletion, "finish", finish):
            await composition.main(cast(ft.Page, self.page))
        self.assertLess(
            self.order.index("deletion_finished"), self.order.index("database")
        )
        self.assertIsNotNone(self.controllers[-1]._key_view)
        self.assertIsNone(self.databases[-1].get_auth_state())
        self.assertTrue(all(key not in self.storage.values for key in PROFILE_ALIASES))
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertGreater(self.bridge.sync_secure_storage.await_count, 0)

    async def test_pending_error_blocks_database_until_real_retry(self):
        deletion = await self.accepted_intent()
        with patch.object(
            self.storage, "remove", side_effect=OSError("synthetic-remove-failure")
        ):
            await composition.main(cast(ft.Page, self.page))
        self.assertTrue(deletion.pending())
        self.assertFalse(self.databases)
        self.assertFalse(self.controllers)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await composition.main(cast(ft.Page, self.page))
        self.assertFalse(deletion.pending())
        self.assertIsNotNone(self.controllers[-1]._key_view)

    async def test_gui_delete_recomposes_then_new_registration_survives_restart(self):
        old_registration = self.fx.stored().registration_id
        old_key = self.storage.values[DATA_KEY_ALIAS]
        await composition.main(cast(ft.Page, self.page))
        old = self.controllers[-1]
        await old.request_profile_deletion()
        dialog = old._profile_deletion_view
        assert dialog is not None
        dialog.phrase_field.value = dialog.phrase
        await dialog._confirm(None)
        current = self.controllers[-1]
        self.assertIsNot(current, old)
        self.assertTrue(old._disposed)
        self.assertIsNotNone(current._key_view)
        self.assertIsNone(self.databases[-1].get_auth_state())
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await current.submit_key("synthetic-new-registration-no-network")
        token = current._pending_setup_token
        assert token is not None
        await current.confirm_pin_setup("4567", token)
        self.assertTrue(current._chat_controller.session_active)
        stored = self.databases[-1].get_auth_state()
        assert stored is not None
        self.assertNotEqual(stored.registration_id, old_registration)
        self.assertNotEqual(self.storage.values[DATA_KEY_ALIAS], old_key)
        self.assertIsNone(current._chat_controller.selected_chat_id)
        await getattr(self.page, "on_close")()
        await composition.main(cast(ft.Page, self.page))
        restarted = self.controllers[-1]
        self.assertEqual(
            (await restarted._auth_service.login("0123")).status, AuthStatus.INVALID_PIN
        )
        await restarted.submit_pin("4567")
        self.assertTrue(restarted._chat_controller.session_active)
        self.assertIsNone(restarted._chat_controller.selected_chat_id)
        self.assertIsNone(restarted._code_pin_view)


class ProfileStartupPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_own_775_profile_keeps_startup_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "legacy-profile"
            profile.mkdir()
            profile.chmod(0o775)
            database_path = profile / "tokenlogue.sqlite3"
            database_path.write_bytes(b"synthetic-existing-database")
            page = AndroidPage()
            with (
                patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": str(profile)}),
                patch.object(composition, "FletSecureCredentials") as secure,
                patch.object(
                    composition,
                    "AuthDatabase",
                    side_effect=OSError("synthetic-storage-failure"),
                ) as database,
            ):
                await composition.main(cast(ft.Page, page))
            database.assert_called_once()
            secure.assert_not_called()
            self.assertEqual(profile.stat().st_mode & 0o777, 0o775)
            self.assertEqual(database_path.read_bytes(), b"synthetic-existing-database")

    async def test_symlink_cannot_create_lock_or_read_foreign_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            foreign = base / "foreign"
            foreign.mkdir()
            (foreign / "tokenlogue-preferences.json").write_text(
                "synthetic-foreign-data"
            )
            link = base / "profile-link"
            link.symlink_to(foreign, target_is_directory=True)
            page = AndroidPage()
            with (
                patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": str(link)}),
                patch.object(composition, "PreferencesStore") as preferences,
                patch.object(composition, "FletSecureCredentials") as secure,
                patch.object(composition, "AuthDatabase") as database,
            ):
                await composition.main(cast(ft.Page, page))
            preferences.assert_not_called()
            secure.assert_not_called()
            database.assert_not_called()
            self.assertEqual(
                {item.name for item in foreign.iterdir()},
                {"tokenlogue-preferences.json"},
            )
