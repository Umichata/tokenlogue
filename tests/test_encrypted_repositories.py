"""Реальные encrypted SQLite и прежние финансовые сценарии без сети."""

from __future__ import annotations

import dataclasses
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.drafts import ChatDraft  # noqa: E402
from chat.models import ChatMode, Message, MessageRole, MessageStatus  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.data_access import DataAccess, DataAccessError  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.encrypted_migration import (  # noqa: E402
    inspect_protection,
    migrate_database,
)
from storage.field_cipher import CiphertextError, FieldCipher  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests import test_message_sending as sending_tests  # noqa: E402


class EncryptedRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = AuthDatabase(self.temporary.name)
        self.cipher = FieldCipher(bytes(range(32)), "synthetic-db", "synthetic-key")
        migrate_database(self.database.path, self.cipher)
        self.access = DataAccess()
        self.access.open(self.cipher)
        self.chats = SqliteChatRepository(self.database.path, self.access)
        self.drafts = SqliteDraftRepository(self.database.path, self.access)
        self.chat = dataclasses.replace(
            sending_tests._chat("c", ChatMode.FREE, sending_tests.FREE_ROUTER_MODEL),
            title="TITLE_SENTINEL",
            title_origin="manual",
        )
        self.chats.create_chat(self.chat)

    def test_all_content_boundaries_roundtrip_without_plaintext_files(self) -> None:
        message = Message(
            id="m",
            chat_id="c",
            turn_id="t",
            role=MessageRole.USER,
            content="MESSAGE_SENTINEL",
            status=MessageStatus.SENT,
            requested_model_id=None,
            actual_model_id=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            created_at=sending_tests.NOW,
        )
        self.chats.create_message(message)
        self.assertEqual(self.chats.list_messages("c")[0].content, message.content)
        self.assertEqual(self.chats.get_chat("c"), self.chat)
        self.assertEqual(
            self.drafts.save_draft(ChatDraft("c", 1, "DRAFT_SENTINEL")),
            ChatDraft("c", 1, "DRAFT_SENTINEL"),
        )
        self.assertEqual(
            self.drafts.save_draft(ChatDraft("c", 2, "")), ChatDraft("c", 2, "")
        )
        self.assertEqual(self.drafts.get_draft("c"), ChatDraft("c", 2, ""))
        for file in Path(self.temporary.name).rglob("*"):
            if file.is_file():
                self.assertNotIn(b"_SENTINEL", file.read_bytes(), file.name)

    def test_manual_titles_remain_exact_and_do_not_change_with_locale(self) -> None:
        from i18n import set_language

        for title in ("Новый чат", "New chat"):
            self.chats.rename_chat("c", title, sending_tests.NOW)
            set_language("en")
            chat = self.chats.get_chat("c")
            assert chat is not None
            self.assertEqual(chat.title, title)
            self.assertEqual(chat.title_origin, "manual")
        set_language("ru")

    def test_none_access_and_closed_access_cannot_read_ciphertext_as_content(
        self,
    ) -> None:
        with self.assertRaises(CiphertextError):
            SqliteChatRepository(self.database.path).list_chats()
        self.access.lock()
        with self.assertRaises(DataAccessError):
            self.chats.list_chats()

    def test_corrupt_title_does_not_become_missing_or_empty_chat(self) -> None:
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("UPDATE chats SET title='not an envelope'")
        with self.assertRaises(CiphertextError):
            self.chats.get_chat("c")


class EncryptedMessageSendingTests(sending_tests.MessageSendingTests):
    """Повторяет прежние сетевые fake сценарии на защищённых SQL границах."""

    async def asyncSetUp(self) -> None:
        self.protected_access = DataAccess()
        self.protected_cipher = FieldCipher(bytes(range(32)), "send-db", "send-key")
        original_chat = sending_tests._chat

        def database(directory):
            database = AuthDatabase(directory)
            if inspect_protection(database.path) is None:
                migrate_database(database.path, self.protected_cipher)
                self.protected_access.open(self.protected_cipher)
            database.recover_interrupted_turns()
            return database

        replacements = {
            "AuthDatabase": database,
            "SqliteChatRepository": lambda path: SqliteChatRepository(
                path, self.protected_access
            ),
            "SqliteMessageRepository": lambda path: SqliteMessageRepository(
                path, self.protected_access
            ),
            "_chat": lambda *a, **kw: dataclasses.replace(
                original_chat(*a, **kw), title_origin="placeholder"
            ),
        }
        for name, replacement in replacements.items():
            active = patch.object(sending_tests, name, replacement)
            active.start()
            self.addCleanup(active.stop)
        await super().asyncSetUp()
