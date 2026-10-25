"""Закрытие отзывает доступ до ожидания, сохраняя последнюю правку через lease."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as application  # noqa: E402
from app import AppController  # noqa: E402
from auth.models import InitialRoute, KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.models import Chat, ChatMode  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.data_access import DataAccess, DataAccessError  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.encrypted_migration import migrate_database  # noqa: E402
from storage.field_cipher import FieldCipher  # noqa: E402
from tests.test_app import FakeAuthService, FakeKeyValidator, FakePage  # noqa: E402
from tests.test_secure_credentials import FakeSecureStorage  # noqa: E402


class ClosingPage(FakePage):
    platform = ft.PagePlatform.LINUX


class AppCloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_close_denies_reads_before_held_encrypted_draft_flush(self):
        with tempfile.TemporaryDirectory() as directory:
            database = AuthDatabase(directory)
            cipher = FieldCipher(os.urandom(32), "close-database", "close-key")
            migrate_database(database.path, cipher)
            access = DataAccess()
            access.open(cipher)
            now = datetime.now(UTC)
            repo = SqliteChatRepository(database.path, access=access)
            chat = Chat(
                "close-chat",
                "SYNTHETIC_CLOSE_TITLE",
                ChatMode.FREE,
                "openrouter/free",
                "fixture",
                Decimal(0),
                Decimal(0),
                now,
                now,
            )
            repo.create_chat_with_limits(
                chat,
                token_limit=100000,
                max_completion_tokens=10000,
                cost_limit_usd=Decimal(0),
            )
            page = ClosingPage()
            auth = FakeAuthService(initial_route=InitialRoute.PIN)
            created = []

            def make_controller(*args, **kwargs):
                controller = AppController(*args, **kwargs)
                created.append(controller)
                return controller

            with (
                patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": directory}),
                patch.object(
                    application,
                    "FletSecureCredentials",
                    return_value=SimpleNamespace(storage_backend=FakeSecureStorage()),
                ),
                patch.object(application, "DataAccess", return_value=access),
                patch.object(application, "AuthService", return_value=auth),
                patch.object(
                    application, "OpenRouterClient", return_value=FakeKeyValidator()
                ),
                patch.object(application, "ModelCatalogClient"),
                patch.object(application, "ChatCompletionsClient"),
                patch.object(application, "AppController", side_effect=make_controller),
                patch.object(ft.Control, "update"),
            ):
                await application.main(cast(ft.Page, page))
                controller = created[0]
                await controller._activate_session(
                    "synthetic-session-key",
                    KeyValidityState.VALID,
                    KeyLimitInfo.from_validated_remaining(None),
                )
                view = controller._chat_controller._workspace_view
                assert view is not None
                exact = "SYNTHETIC_LATEST_DRAFT_BEFORE_CLOSE — 🙂"
                view.restore_editor(exact)
                drafts = controller._chat_controller._drafts
                original_save = drafts._repository.save_draft
                entered, release = threading.Event(), threading.Event()

                def held_save(draft):
                    entered.set()
                    if not release.wait(5):
                        raise TimeoutError("Не освобождена запись fixture")
                    return original_save(draft)

                epoch = controller._security_epoch
                with patch.object(
                    drafts._repository, "save_draft", side_effect=held_save
                ):
                    closing = asyncio.create_task(getattr(page, "on_close")())
                    try:
                        self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                        self.assertFalse(access.unlocked)
                        self.assertNotEqual(controller._security_epoch, epoch)
                        self.assertFalse(controller._chat_controller.session_active)
                        self.assertFalse(controller._chat_controller.workspace_visible)
                        self.assertGreater(access.active_leases, 0)
                        with self.assertRaises(DataAccessError):
                            repo.list_chats()
                    finally:
                        release.set()
                        await closing
                self.assertTrue(controller._disposed)
                self.assertFalse(access.unlocked)
                self.assertEqual(access.active_leases, 0)
                access.open(cipher)
                stored = SqliteDraftRepository(database.path, access=access).get_draft(
                    chat.id
                )
                self.assertEqual(stored.text, exact)
                self.assertNotIn(exact.encode(), database.path.read_bytes())
                access.lock()


if __name__ == "__main__":
    unittest.main()
