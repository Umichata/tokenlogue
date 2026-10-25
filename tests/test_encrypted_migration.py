"""Миграция синтетической schema 6 без открытой резервной копии."""

from __future__ import annotations

import errno
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.database import AuthDatabase  # noqa: E402
from storage.encrypted_migration import (  # noqa: E402
    inspect_protection,
    migrate_database,
)
from storage.field_cipher import CiphertextError, FieldCipher  # noqa: E402


class EncryptedMigrationTests(unittest.TestCase):
    def fixture(self, directory: str) -> Path:
        path = AuthDatabase(directory).path
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO chats (rowid,id,title,mode,requested_model_id,requested_model_name,prompt_price_per_token,completion_price_per_token,created_at,updated_at,title_is_manual) VALUES (99,'c','TITLE_SENTINEL','paid','model','model','0.0000','0.0001','same','same',1)"
            )
            connection.execute(
                "INSERT INTO chat_budgets (chat_id,cost_used_usd,cost_reserved_usd,reserved_tokens,state,updated_at) VALUES ('c','0.0000','0.0001',17,'accounting_unknown','same')"
            )
            connection.execute(
                "INSERT INTO turns (rowid,id,chat_id,status,requested_model_id,generation_id,finish_reason,reserved_tokens,reserved_cost_usd,accounting_status,error_type,request_sent,created_at,updated_at) VALUES (77,'t','c','failed','model','GENERATION_SENTINEL','REASON_SENTINEL',17,'0.0001','unknown','network_error',1,'same','same')"
            )
            connection.execute(
                "INSERT INTO messages (rowid,id,chat_id,turn_id,role,content,status,created_at,updated_at) VALUES (51,'m','c','t','user','MESSAGE_SENTINEL','failed','same','same')"
            )
            connection.execute(
                "INSERT INTO chat_drafts (chat_id,revision,content) VALUES ('c',37,'DRAFT_SENTINEL')"
            )
        return path

    def test_roundtrip_preserves_rowids_metadata_and_no_open_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")
            migrate_database(path, cipher)
            metadata = inspect_protection(path)
            assert metadata is not None
            self.assertEqual(metadata.database_id, "db-a")
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0], 7
                )
                title = connection.execute(
                    "SELECT rowid,title,title_is_manual,title_origin FROM chats"
                ).fetchone()
                self.assertEqual(title[0], 99)
                self.assertEqual(title[2:], (1, "manual"))
                self.assertEqual(
                    cipher.decrypt(
                        title[1], table="chats", field="title", record_id="c"
                    ),
                    "TITLE_SENTINEL",
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT rowid,accounting_status,reserved_tokens,reserved_cost_usd FROM turns"
                    ).fetchone(),
                    (77, "unknown", 17, "0.0001"),
                )
                self.assertEqual(
                    connection.execute("SELECT rowid FROM messages").fetchone()[0], 51
                )
                self.assertEqual(
                    connection.execute("SELECT revision FROM chat_drafts").fetchone()[
                        0
                    ],
                    37,
                )
            before = path.read_bytes()
            migrate_database(path, cipher)
            self.assertEqual(path.read_bytes(), before)
            for file in Path(directory).rglob("*"):
                if file.is_file():
                    self.assertNotIn(b"_SENTINEL", file.read_bytes(), file.name)

    def test_each_interruption_is_retryable_with_same_key(self) -> None:
        for stage in ("after_key_saved", "mid_copy", "before_replace", "after_replace"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                path = self.fixture(directory)
                cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")

                def failpoint(point: str) -> None:
                    if point == stage:
                        raise OSError("synthetic interruption")

                with self.assertRaises(OSError):
                    migrate_database(path, cipher, failpoint=failpoint)
                self.assertTrue(path.is_file())
                migrate_database(path, cipher)
                metadata = inspect_protection(path)
                assert metadata is not None
                self.assertEqual(metadata.key_id, "key-a")

    def test_wrong_key_does_not_replace_encrypted_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            migrate_database(path, FieldCipher(bytes(range(32)), "db-a", "key-a"))
            original = path.read_bytes()
            with self.assertRaises(CiphertextError):
                migrate_database(path, FieldCipher(bytes(32), "db-a", "key-a"))
            self.assertEqual(original, path.read_bytes())

    def test_corruption_never_creates_a_new_empty_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokenlogue.sqlite3"
            path.write_bytes(b"synthetic corrupt database")
            with self.assertRaises(CiphertextError):
                migrate_database(path, FieldCipher(bytes(32), "db-a", "key-a"))
            self.assertEqual(path.read_bytes(), b"synthetic corrupt database")

    def test_committed_wal_after_process_exit_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            code = "import sqlite3,sys,os;c=sqlite3.connect(sys.argv[1]);c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA wal_autocheckpoint=0');c.execute(\"UPDATE chat_drafts SET content='WAL_SENTINEL'\");c.commit();os._exit(0)"
            subprocess.run(
                [sys.executable, "-c", code, str(path)], check=True, capture_output=True
            )
            self.assertTrue(path.with_name(path.name + "-wal").is_file())
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")
            migrate_database(path, cipher)
            with sqlite3.connect(path) as connection:
                content = connection.execute(
                    "SELECT content FROM chat_drafts"
                ).fetchone()[0]
            self.assertEqual(
                cipher.decrypt(
                    content,
                    table="chat_drafts",
                    field="content",
                    record_id="c",
                    chat_id="c",
                    revision=37,
                ),
                "WAL_SENTINEL",
            )
            for file in Path(directory).rglob("*"):
                if file.is_file():
                    self.assertNotIn(b"_SENTINEL", file.read_bytes())

    def test_disk_full_before_replace_preserves_original_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")
            original_replace = os.replace

            def replace(source, destination):
                if Path(destination) == path:
                    raise OSError(errno.ENOSPC, "synthetic full disk")
                return original_replace(source, destination)

            with patch("storage.encrypted_migration.os.replace", replace):
                with self.assertRaises(OSError):
                    migrate_database(path, cipher)
            self.assertIsNone(inspect_protection(path))
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute("SELECT title FROM chats").fetchone()[0],
                    "TITLE_SENTINEL",
                )
            migrate_database(path, cipher)
            self.assertIsNotNone(inspect_protection(path))

    def test_busy_reader_blocks_replace_without_losing_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            reader = sqlite3.connect(path)
            reader.execute("PRAGMA journal_mode=WAL")
            reader.execute("BEGIN")
            reader.execute("SELECT title FROM chats").fetchone()
            with sqlite3.connect(path) as writer:
                writer.execute("UPDATE chat_drafts SET content='BUSY_SENTINEL'")
            writer.close()
            original_connect = sqlite3.connect

            def connect(*args, **kwargs):
                kwargs["timeout"] = 0.02
                return original_connect(*args, **kwargs)

            try:
                with patch("storage.encrypted_migration.sqlite3.connect", connect):
                    with self.assertRaises(CiphertextError):
                        migrate_database(
                            path, FieldCipher(bytes(range(32)), "db-a", "key-a")
                        )
                self.assertIsNone(inspect_protection(path))
            finally:
                reader.close()
            migrate_database(path, FieldCipher(bytes(range(32)), "db-a", "key-a"))

    def test_unknown_journal_stage_preserves_all_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")

            def interrupt(stage: str) -> None:
                if stage == "mid_copy":
                    raise OSError("synthetic interruption")

            with self.assertRaises(OSError):
                migrate_database(path, cipher, failpoint=interrupt)
            journal = path.with_name(path.name + ".protection-migration.json")
            state = json.loads(journal.read_text())
            for invalid in (None, "unrecognised"):
                state["stage"] = invalid
                journal.write_text(json.dumps(state))
                before = {
                    f.name: f.read_bytes()
                    for f in Path(directory).iterdir()
                    if f.is_file()
                }
                with self.assertRaises(CiphertextError):
                    migrate_database(path, cipher)
                self.assertEqual(
                    before,
                    {
                        f.name: f.read_bytes()
                        for f in Path(directory).iterdir()
                        if f.is_file()
                    },
                )

    def test_corrupted_protected_field_prevents_reopen_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")
            migrate_database(path, cipher)
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE messages SET content='broken-envelope'")
            original = path.read_bytes()
            with self.assertRaises(CiphertextError):
                migrate_database(path, cipher)
            self.assertEqual(path.read_bytes(), original)

    def test_metadata_disk_full_before_copy_keeps_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")
            with patch(
                "storage.encrypted_migration._journal",
                side_effect=OSError(errno.ENOSPC, "synthetic full disk"),
            ):
                with self.assertRaises(OSError):
                    migrate_database(path, cipher)
            self.assertIsNone(inspect_protection(path))
            self.assertFalse(list(Path(directory).glob(".*.protected-*")))
            migrate_database(path, cipher)

    def test_tampered_journal_cannot_delete_an_unrelated_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            cipher = FieldCipher(bytes(range(32)), "db-a", "key-a")

            def interrupt(stage: str) -> None:
                if stage == "mid_copy":
                    raise OSError("synthetic interruption")

            with self.assertRaises(OSError):
                migrate_database(path, cipher, failpoint=interrupt)
            unrelated = path.with_name("." + path.name + ".protected-unrelated")
            with sqlite3.connect(unrelated) as connection:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
                connection.execute("INSERT INTO unrelated VALUES ('KEEP_THIS_FIXTURE')")
            before = unrelated.read_bytes()
            journal = path.with_name(path.name + ".protection-migration.json")
            state = json.loads(journal.read_text())
            state["temporary"] = unrelated.name
            journal.write_text(json.dumps(state))
            with self.assertRaises(CiphertextError):
                migrate_database(path, cipher)
            self.assertEqual(unrelated.read_bytes(), before)

    def test_auth_read_never_recreates_a_database_deleted_after_startup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = AuthDatabase(directory)
            database.path.unlink()
            with self.assertRaises((sqlite3.Error, CiphertextError)):
                database.get_auth_state()
            self.assertFalse(database.path.exists())

    def test_already_unknown_accounting_metadata_is_unchanged_on_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = AuthDatabase(directory)
            path = self.fixture(directory)
            with sqlite3.connect(path) as connection:
                before = connection.execute(
                    "SELECT * FROM chat_budgets WHERE chat_id='c'"
                ).fetchone()
            database.recover_interrupted_turns()
            database.recover_interrupted_turns()
            AuthDatabase(directory)
            with sqlite3.connect(path) as connection:
                after = connection.execute(
                    "SELECT * FROM chat_budgets WHERE chat_id='c'"
                ).fetchone()
            self.assertEqual(after, before)
