"""Тесты SQLite-хранилища данных PIN и блокировки."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import PinRecord  # noqa: E402
from storage.database import (  # noqa: E402
    DATABASE_FILENAME,
    SCHEMA_VERSION,
    AuthDatabase,
    UnsupportedSchemaVersion,
)

REGISTRATION_ID = "registration-test-id"


class AuthDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = AuthDatabase(self.temp_dir.name)
        self.record = PinRecord(
            version=1,
            algorithm="pbkdf2_hmac_sha256",
            iterations=1_000,
            salt=b"s" * 16,
            verifier=b"v" * 32,
        )

    def test_uses_injected_directory(self) -> None:
        self.assertEqual(
            self.database.path,
            Path(self.temp_dir.name) / DATABASE_FILENAME,
        )
        self.assertTrue(self.database.path.exists())

    def test_uses_flet_storage_environment(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            with patch.dict(os.environ, {"FLET_APP_STORAGE_DATA": data_dir}):
                database = AuthDatabase()

            self.assertEqual(database.path, Path(data_dir) / DATABASE_FILENAME)

    def test_uses_new_database_identity_without_opening_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            legacy_path = Path(data_dir) / "ai_chat.sqlite3"
            legacy_marker = b"not-a-sqlite-database"
            legacy_path.write_bytes(legacy_marker)

            database = AuthDatabase(data_dir)

            self.assertEqual(DATABASE_FILENAME, "tokenlogue.sqlite3")
            self.assertEqual(database.path, Path(data_dir) / "tokenlogue.sqlite3")
            self.assertTrue(database.path.exists())
            self.assertEqual(legacy_path.read_bytes(), legacy_marker)

    def test_auth_state_persists_across_repository_restart(self) -> None:
        self.database.save_auth_state(REGISTRATION_ID, self.record)

        reopened = AuthDatabase(self.temp_dir.name)
        stored = reopened.get_auth_state()

        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.registration_id, REGISTRATION_ID)
        self.assertEqual(stored.pin_record, self.record)
        self.assertEqual(stored.attempts.failed_attempts, 0)
        self.assertIsNone(stored.attempts.locked_until)

    def test_failed_attempts_and_lock_are_persisted(self) -> None:
        self.database.save_auth_state(REGISTRATION_ID, self.record)

        state = None
        for _ in range(5):
            state = self.database.register_failed_attempt(100.0, 5, 30)

        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.failed_attempts, 5)
        self.assertEqual(state.locked_until, 130.0)
        reopened = AuthDatabase(self.temp_dir.name)
        stored = reopened.get_auth_state()
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.attempts.failed_attempts, 5)
        self.assertEqual(stored.attempts.locked_until, 130.0)

    def test_clear_removes_auth_record(self) -> None:
        self.database.save_auth_state(REGISTRATION_ID, self.record)

        self.database.clear_auth_data()

        self.assertIsNone(self.database.get_auth_state())

    def test_schema_has_no_api_key_or_plain_pin_column(self) -> None:
        with closing(sqlite3.connect(self.database.path)) as connection:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(auth_state)")
            }

        self.assertNotIn("api_key", columns)
        self.assertNotIn("pin", columns)
        self.assertIn("pin_verifier", columns)
        self.assertIn("registration_id", columns)

    def test_migrates_version_one_without_reusing_unlinked_pin(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database_path = Path(data_dir) / DATABASE_FILENAME
            _create_version_one_database(database_path)

            migrated = AuthDatabase(data_dir)

            self.assertIsNone(migrated.get_auth_state())
            with closing(sqlite3.connect(database_path)) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)

    def test_migrates_version_two_without_losing_auth_state(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database_path = Path(data_dir) / DATABASE_FILENAME
            _create_version_two_database(database_path)

            migrated = AuthDatabase(data_dir)
            state = migrated.get_auth_state()

            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state.registration_id, REGISTRATION_ID)
            self.assertEqual(state.pin_record, self.record)
            self.assertEqual(state.attempts.failed_attempts, 2)
            self.assertEqual(state.attempts.locked_until, 1234.0)
            with closing(sqlite3.connect(database_path)) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    )
                }
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("chats", tables)
            self.assertIn("messages", tables)
            self.assertTrue(
                {
                    "idx_chats_updated_at",
                    "idx_messages_chat_created",
                    "idx_messages_turn_id",
                }.issubset(indexes)
            )

    def test_migrates_version_three_with_auth_chats_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database_path = Path(data_dir) / DATABASE_FILENAME
            _create_version_three_database(database_path)

            migrated = AuthDatabase(data_dir)

            state = migrated.get_auth_state()
            self.assertIsNotNone(state)
            assert state is not None
            self.assertEqual(state.registration_id, REGISTRATION_ID)
            with closing(sqlite3.connect(database_path)) as connection:
                connection.row_factory = sqlite3.Row
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                chat = connection.execute(
                    "SELECT * FROM chats WHERE id = 'existing-chat'"
                ).fetchone()
                messages = connection.execute(
                    """
                    SELECT role, content FROM messages
                    WHERE chat_id = 'existing-chat' ORDER BY created_at
                    """
                ).fetchall()
                budget = connection.execute(
                    "SELECT * FROM chat_budgets WHERE chat_id = 'existing-chat'"
                ).fetchone()
                turn = connection.execute(
                    "SELECT * FROM turns WHERE id = 'existing-turn'"
                ).fetchone()
            self.assertEqual(version, SCHEMA_VERSION)
            assert chat is not None and budget is not None and turn is not None
            self.assertEqual(chat["requested_model_id"], "vendor/existing")
            self.assertEqual(chat["pricing_snapshot_complete"], 0)
            self.assertEqual(
                [(row["role"], row["content"]) for row in messages],
                [("user", "old question"), ("assistant", "old answer")],
            )
            self.assertEqual(budget["limits_configured"], 0)
            self.assertIsNone(budget["token_limit"])
            self.assertIsNone(budget["cost_limit_usd"])
            self.assertEqual(turn["status"], "sent")

    def test_rejects_unknown_newer_schema(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database_path = Path(data_dir) / DATABASE_FILENAME
            with closing(sqlite3.connect(database_path)) as connection:
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

            with self.assertRaises(UnsupportedSchemaVersion):
                AuthDatabase(data_dir)

    def test_schema_uses_text_for_money_and_integer_for_tokens(self) -> None:
        with closing(sqlite3.connect(self.database.path)) as connection:
            budget_columns = {
                row[1]: row[2]
                for row in connection.execute("PRAGMA table_info(chat_budgets)")
            }
            turn_columns = {
                row[1]: row[2] for row in connection.execute("PRAGMA table_info(turns)")
            }

        for name in ("cost_limit_usd", "cost_used_usd", "cost_reserved_usd"):
            self.assertEqual(budget_columns[name], "TEXT")
        self.assertEqual(turn_columns["cost_usd"], "TEXT")
        self.assertEqual(turn_columns["reserved_cost_usd"], "TEXT")
        for name in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "reserved_tokens",
        ):
            self.assertEqual(turn_columns[name], "INTEGER")


def _create_version_one_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            """
            CREATE TABLE auth_state (
                singleton_id INTEGER PRIMARY KEY,
                kdf_version INTEGER NOT NULL,
                kdf_algorithm TEXT NOT NULL,
                kdf_iterations INTEGER NOT NULL,
                salt BLOB NOT NULL,
                pin_verifier BLOB NOT NULL,
                failed_attempts INTEGER NOT NULL,
                locked_until REAL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO auth_state VALUES (1, 1, ?, 1000, ?, ?, 0, NULL)
            """,
            ("pbkdf2_hmac_sha256", b"s" * 16, b"v" * 32),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()


def _create_version_two_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            """
            CREATE TABLE auth_state (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                registration_id TEXT NOT NULL,
                kdf_version INTEGER NOT NULL CHECK (kdf_version > 0),
                kdf_algorithm TEXT NOT NULL,
                kdf_iterations INTEGER NOT NULL CHECK (kdf_iterations > 0),
                salt BLOB NOT NULL,
                pin_verifier BLOB NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0
                    CHECK (failed_attempts >= 0),
                locked_until REAL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO auth_state (
                singleton_id,
                registration_id,
                kdf_version,
                kdf_algorithm,
                kdf_iterations,
                salt,
                pin_verifier,
                failed_attempts,
                locked_until
            )
            VALUES (1, ?, 1, ?, 1000, ?, ?, 2, 1234.0)
            """,
            (
                REGISTRATION_ID,
                "pbkdf2_hmac_sha256",
                b"s" * 16,
                b"v" * 32,
            ),
        )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()


def _create_version_three_database(path: Path) -> None:
    _create_version_two_database(path)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            """
            CREATE TABLE chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                mode TEXT NOT NULL CHECK (mode IN ('free', 'paid')),
                requested_model_id TEXT NOT NULL,
                requested_model_name TEXT NOT NULL,
                prompt_price_per_token TEXT NOT NULL,
                completion_price_per_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
                requested_model_id TEXT,
                actual_model_id TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX idx_chats_updated_at ON chats(updated_at DESC)"
        )
        connection.execute(
            "CREATE INDEX idx_messages_chat_created ON messages(chat_id, created_at)"
        )
        connection.execute("CREATE INDEX idx_messages_turn_id ON messages(turn_id)")
        timestamp = "2026-01-01T00:00:00.000000+00:00"
        connection.execute(
            """
            INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "existing-chat",
                "Existing",
                "paid",
                "vendor/existing",
                "Existing model",
                "0.000001",
                "0.000002",
                timestamp,
                timestamp,
            ),
        )
        connection.executemany(
            """
            INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "old-user",
                    "existing-chat",
                    "existing-turn",
                    "user",
                    "old question",
                    "sent",
                    "vendor/existing",
                    None,
                    None,
                    None,
                    None,
                    timestamp,
                ),
                (
                    "old-assistant",
                    "existing-chat",
                    "existing-turn",
                    "assistant",
                    "old answer",
                    "sent",
                    "vendor/existing",
                    "vendor/actual",
                    10,
                    5,
                    15,
                    "2026-01-01T00:00:01.000000+00:00",
                ),
            ),
        )
        connection.execute("PRAGMA user_version = 3")
        connection.commit()


if __name__ == "__main__":
    unittest.main()
