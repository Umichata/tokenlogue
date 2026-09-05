"""SQLite-хранилище verifier PIN и состояния блокировки."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from auth.models import LoginAttemptState, PinRecord, StoredAuthState

DATABASE_FILENAME = "tokenlogue.sqlite3"
SCHEMA_VERSION = 5


class UnsupportedSchemaVersion(RuntimeError):
    """База создана более новой, неизвестной приложению версией."""


class AuthDatabase:
    """Хранит только метаданные регистрации и производные данные PIN."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.path = _database_path(data_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def get_auth_state(self) -> StoredAuthState | None:
        """Возвращает связанную запись регистрации и состояние попыток."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    registration_id,
                    kdf_version,
                    kdf_algorithm,
                    kdf_iterations,
                    salt,
                    pin_verifier,
                    failed_attempts,
                    locked_until
                FROM auth_state
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return None

        return StoredAuthState(
            registration_id=str(row["registration_id"]),
            pin_record=PinRecord(
                version=int(row["kdf_version"]),
                algorithm=str(row["kdf_algorithm"]),
                iterations=int(row["kdf_iterations"]),
                salt=bytes(row["salt"]),
                verifier=bytes(row["pin_verifier"]),
            ),
            attempts=LoginAttemptState(
                failed_attempts=int(row["failed_attempts"]),
                locked_until=(
                    float(row["locked_until"])
                    if row["locked_until"] is not None
                    else None
                ),
            ),
        )

    def save_auth_state(self, registration_id: str, record: PinRecord) -> None:
        """Атомарно связывает PIN verifier с идентификатором регистрации."""
        if not registration_id:
            raise ValueError("Идентификатор регистрации не может быть пустым")
        with self._connection() as connection:
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
                VALUES (1, ?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    registration_id = excluded.registration_id,
                    kdf_version = excluded.kdf_version,
                    kdf_algorithm = excluded.kdf_algorithm,
                    kdf_iterations = excluded.kdf_iterations,
                    salt = excluded.salt,
                    pin_verifier = excluded.pin_verifier,
                    failed_attempts = 0,
                    locked_until = NULL
                """,
                (
                    registration_id,
                    record.version,
                    record.algorithm,
                    record.iterations,
                    sqlite3.Binary(record.salt),
                    sqlite3.Binary(record.verifier),
                ),
            )

    def clear_auth_data(self) -> None:
        """Удаляет только данные локальной аутентификации."""
        with self._connection() as connection:
            connection.execute("DELETE FROM auth_state WHERE singleton_id = 1")

    def reset_login_attempts(self) -> None:
        """Сбрасывает счётчик и блокировку после успешного входа."""
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE auth_state
                SET failed_attempts = 0, locked_until = NULL
                WHERE singleton_id = 1
                """
            )

    def register_failed_attempt(
        self,
        now: float,
        max_attempts: int,
        lock_seconds: int,
    ) -> LoginAttemptState:
        """Атомарно учитывает ошибку и при необходимости включает блокировку."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT failed_attempts, locked_until
                FROM auth_state
                WHERE singleton_id = 1
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("Данные PIN отсутствуют")

            locked_until = (
                float(row["locked_until"]) if row["locked_until"] is not None else None
            )
            if locked_until is not None and locked_until > now:
                return LoginAttemptState(
                    failed_attempts=int(row["failed_attempts"]),
                    locked_until=locked_until,
                )

            failed_attempts = int(row["failed_attempts"])
            if locked_until is not None and locked_until <= now:
                failed_attempts = 0
                locked_until = None

            failed_attempts += 1
            if failed_attempts >= max_attempts:
                failed_attempts = max_attempts
                locked_until = now + lock_seconds

            connection.execute(
                """
                UPDATE auth_state
                SET failed_attempts = ?, locked_until = ?
                WHERE singleton_id = 1
                """,
                (failed_attempts, locked_until),
            )
            return LoginAttemptState(failed_attempts, locked_until)

    def _initialize_schema(self) -> None:
        migrations: dict[int, Callable[[sqlite3.Connection], None]] = {
            0: _migrate_0_to_1,
            1: _migrate_1_to_2,
            2: _migrate_2_to_3,
            3: _migrate_3_to_4,
            4: _migrate_4_to_5,
        }
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            if current_version > SCHEMA_VERSION:
                raise UnsupportedSchemaVersion(
                    "Версия базы данных новее версии приложения"
                )

            while current_version < SCHEMA_VERSION:
                migration = migrations.get(current_version)
                if migration is None:
                    raise UnsupportedSchemaVersion(
                        "Для версии базы данных отсутствует миграция"
                    )
                migration(connection)
                current_version += 1
                connection.execute(f"PRAGMA user_version = {current_version}")
            _recover_interrupted_turns(connection)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _migrate_0_to_1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE auth_state (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
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


def _migrate_1_to_2(connection: sqlite3.Connection) -> None:
    # Старая запись не имеет связи с SecureStorage и безопасно не переносится.
    connection.execute("ALTER TABLE auth_state RENAME TO auth_state_v1")
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
    connection.execute("DROP TABLE auth_state_v1")


def _migrate_2_to_3(connection: sqlite3.Connection) -> None:
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
    connection.execute("CREATE INDEX idx_chats_updated_at ON chats(updated_at DESC)")
    connection.execute(
        """
        CREATE INDEX idx_messages_chat_created
        ON messages(chat_id, created_at)
        """
    )
    connection.execute("CREATE INDEX idx_messages_turn_id ON messages(turn_id)")


def _migrate_3_to_4(connection: sqlite3.Connection) -> None:
    for definition in (
        "request_price TEXT NOT NULL DEFAULT '0' CHECK (length(request_price) > 0)",
        "internal_reasoning_price_per_token TEXT NOT NULL DEFAULT '0' "
        "CHECK (length(internal_reasoning_price_per_token) > 0)",
        "input_cache_read_price_per_token TEXT NOT NULL DEFAULT '0' "
        "CHECK (length(input_cache_read_price_per_token) > 0)",
        "input_cache_write_price_per_token TEXT NOT NULL DEFAULT '0' "
        "CHECK (length(input_cache_write_price_per_token) > 0)",
        "pricing_overrides_json TEXT NOT NULL DEFAULT '[]' "
        "CHECK (length(pricing_overrides_json) > 0)",
        "pricing_snapshot_complete INTEGER NOT NULL DEFAULT 0 "
        "CHECK (pricing_snapshot_complete IN (0, 1))",
    ):
        connection.execute(f"ALTER TABLE chats ADD COLUMN {definition}")

    connection.execute("ALTER TABLE messages RENAME TO messages_v3")
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
            prompt_tokens INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
            completion_tokens INTEGER
                CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
            total_tokens INTEGER CHECK (total_tokens IS NULL OR total_tokens >= 0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO messages (
            id, chat_id, turn_id, role, content, status,
            requested_model_id, actual_model_id,
            prompt_tokens, completion_tokens, total_tokens,
            created_at, updated_at
        )
        SELECT
            id, chat_id, turn_id, role, content, status,
            requested_model_id, actual_model_id,
            prompt_tokens, completion_tokens, total_tokens,
            created_at, created_at
        FROM messages_v3
        """
    )
    connection.execute("DROP TABLE messages_v3")
    connection.execute(
        "CREATE INDEX idx_messages_chat_created ON messages(chat_id, created_at)"
    )
    connection.execute("CREATE INDEX idx_messages_turn_id ON messages(turn_id)")
    connection.execute(
        """
        CREATE UNIQUE INDEX idx_messages_one_user_per_turn
        ON messages(chat_id, turn_id) WHERE role = 'user'
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX idx_messages_one_assistant_per_turn
        ON messages(chat_id, turn_id) WHERE role = 'assistant'
        """
    )

    connection.execute(
        """
        CREATE TABLE chat_budgets (
            chat_id TEXT PRIMARY KEY,
            limits_configured INTEGER NOT NULL DEFAULT 0
                CHECK (limits_configured IN (0, 1)),
            token_limit INTEGER CHECK (token_limit IS NULL OR token_limit > 0),
            max_completion_tokens INTEGER
                CHECK (max_completion_tokens IS NULL OR max_completion_tokens >= 16),
            prompt_tokens_used INTEGER NOT NULL DEFAULT 0
                CHECK (prompt_tokens_used >= 0),
            completion_tokens_used INTEGER NOT NULL DEFAULT 0
                CHECK (completion_tokens_used >= 0),
            total_tokens_used INTEGER NOT NULL DEFAULT 0
                CHECK (total_tokens_used >= 0),
            reserved_tokens INTEGER NOT NULL DEFAULT 0
                CHECK (reserved_tokens >= 0),
            cost_limit_usd TEXT CHECK (
                cost_limit_usd IS NULL OR length(cost_limit_usd) > 0
            ),
            cost_used_usd TEXT NOT NULL DEFAULT '0'
                CHECK (length(cost_used_usd) > 0),
            cost_reserved_usd TEXT NOT NULL DEFAULT '0'
                CHECK (length(cost_reserved_usd) > 0),
            state TEXT NOT NULL DEFAULT 'unconfigured'
                CHECK (state IN (
                    'unconfigured', 'ready', 'exhausted', 'accounting_unknown'
                )),
            updated_at TEXT NOT NULL,
            CHECK (
                (limits_configured = 0
                    AND token_limit IS NULL
                    AND max_completion_tokens IS NULL)
                OR
                (limits_configured = 1
                    AND token_limit IS NOT NULL
                    AND max_completion_tokens IS NOT NULL
                    AND max_completion_tokens <= token_limit)
            ),
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO chat_budgets (
            chat_id, limits_configured, token_limit, max_completion_tokens,
            prompt_tokens_used, completion_tokens_used, total_tokens_used,
            reserved_tokens, cost_limit_usd, cost_used_usd,
            cost_reserved_usd, state, updated_at
        )
        SELECT
            id, 0, NULL, NULL, 0, 0, 0, 0,
            CASE WHEN mode = 'free' THEN '0' ELSE NULL END,
            '0', '0', 'unconfigured', updated_at
        FROM chats
        """
    )

    connection.execute(
        """
        CREATE TABLE turns (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
            requested_model_id TEXT NOT NULL,
            actual_model_id TEXT,
            generation_id TEXT,
            finish_reason TEXT,
            prompt_tokens INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
            completion_tokens INTEGER
                CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
            total_tokens INTEGER CHECK (total_tokens IS NULL OR total_tokens >= 0),
            cost_usd TEXT CHECK (cost_usd IS NULL OR length(cost_usd) > 0),
            reserved_tokens INTEGER NOT NULL DEFAULT 0
                CHECK (reserved_tokens >= 0),
            reserved_cost_usd TEXT NOT NULL DEFAULT '0'
                CHECK (length(reserved_cost_usd) > 0),
            accounting_status TEXT NOT NULL
                CHECK (accounting_status IN ('reserved', 'final', 'unknown', 'released')),
            error_type TEXT,
            request_sent INTEGER NOT NULL DEFAULT 0 CHECK (request_sent IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO turns (
            id, chat_id, status, requested_model_id, actual_model_id,
            prompt_tokens, completion_tokens, total_tokens,
            reserved_tokens, reserved_cost_usd, accounting_status,
            request_sent, created_at, updated_at
        )
        SELECT
            turn_id,
            chat_id,
            CASE
                WHEN SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) > 0
                    THEN 'pending'
                WHEN SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) > 0
                    THEN 'failed'
                ELSE 'sent'
            END,
            COALESCE(MAX(requested_model_id), ''),
            MAX(actual_model_id),
            MAX(prompt_tokens),
            MAX(completion_tokens),
            MAX(total_tokens),
            0,
            '0',
            'released',
            0,
            MIN(created_at),
            MAX(updated_at)
        FROM messages
        GROUP BY chat_id, turn_id
        """
    )
    connection.execute(
        "CREATE INDEX idx_turns_chat_created ON turns(chat_id, created_at)"
    )
    connection.execute(
        "CREATE INDEX idx_turns_accounting ON turns(chat_id, accounting_status)"
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX idx_turns_one_pending_per_chat
        ON turns(chat_id) WHERE status = 'pending'
        """
    )


def _migrate_4_to_5(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE chat_drafts (
            chat_id TEXT PRIMARY KEY NOT NULL,
            revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision >= 0),
            content TEXT NOT NULL CHECK (typeof(content) = 'text'),
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
        """
    )


def _recover_interrupted_turns(connection: sqlite3.Connection) -> None:
    timestamp = "strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')"
    connection.execute(
        f"""
        UPDATE turns
        SET status = 'failed',
            accounting_status = CASE
                WHEN reserved_tokens > 0 THEN 'unknown'
                ELSE 'released'
            END,
            error_type = 'interrupted',
            updated_at = {timestamp}
        WHERE status = 'pending'
        """
    )
    connection.execute(
        f"""
        UPDATE messages
        SET status = 'failed', updated_at = {timestamp}
        WHERE status = 'pending'
        """
    )
    connection.execute(
        f"""
        UPDATE chat_budgets
        SET state = 'accounting_unknown', updated_at = {timestamp}
        WHERE EXISTS (
            SELECT 1 FROM turns
            WHERE turns.chat_id = chat_budgets.chat_id
              AND turns.accounting_status = 'unknown'
        )
        """
    )


def _database_path(data_dir: str | Path | None) -> Path:
    """Строит путь только из внедрённого каталога или Flet app storage."""
    if data_dir is None:
        storage_data = os.environ.get("FLET_APP_STORAGE_DATA")
        if not storage_data:
            raise RuntimeError("FLET_APP_STORAGE_DATA не задан")
        base_dir = Path(storage_data)
    else:
        base_dir = Path(data_dir)
    return base_dir / DATABASE_FILENAME
