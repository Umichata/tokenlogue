"""Content-free snapshots of actual dispatches, ordered independently of turns.

A retry reuses its turn. Recording a separate dispatch sequence preserves the
previous actual attempt when that retry is later cancelled before HTTP. The
extension is created only inside an authorized dispatch transaction, never on
PIN startup, draft edits or read-only metrics queries. Schema versions 6 and 7
and the existing encrypted fields retain their original format.
"""

from __future__ import annotations

import sqlite3

TABLE = "chat_request_attempts"


def has_request_attempts(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone()
        is not None
    )


def create_request_attempts_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE chat_request_attempts (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            sent_at TEXT,
            chronology_known INTEGER NOT NULL CHECK (chronology_known IN (0,1)),
            status TEXT NOT NULL CHECK (status IN ('pending','sent','failed')),
            accounting_status TEXT NOT NULL CHECK (
                accounting_status IN ('reserved','final','unknown','released')
            ),
            prompt_tokens INTEGER CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
            completion_tokens INTEGER CHECK (
                completion_tokens IS NULL OR completion_tokens >= 0
            ),
            total_tokens INTEGER CHECK (total_tokens IS NULL OR total_tokens >= 0),
            cost_usd TEXT CHECK (cost_usd IS NULL OR length(cost_usd) > 0),
            FOREIGN KEY (turn_id) REFERENCES turns(id) ON DELETE CASCADE,
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        "CREATE INDEX idx_chat_request_attempts_chat ON chat_request_attempts(chat_id,sequence)"
    )
    connection.execute(
        "CREATE INDEX idx_chat_request_attempts_turn ON chat_request_attempts(turn_id,sequence)"
    )


def validate_request_attempts_schema(connection: sqlite3.Connection) -> None:
    """Accept only the known extension, including its foreign-key boundaries."""
    expected = sqlite3.connect(":memory:")
    try:
        create_request_attempts_schema(expected)
        for pragma in ("table_info", "foreign_key_list", "index_list"):
            actual = [
                tuple(row) for row in connection.execute(f"PRAGMA {pragma}({TABLE})")
            ]
            wanted = [
                tuple(row) for row in expected.execute(f"PRAGMA {pragma}({TABLE})")
            ]
            if actual != wanted:
                raise ValueError("request_attempts_schema_invalid")
        for name in (
            TABLE,
            "idx_chat_request_attempts_chat",
            "idx_chat_request_attempts_turn",
        ):
            actual = connection.execute(
                "SELECT sql FROM sqlite_master WHERE name=?", (name,)
            ).fetchone()
            wanted = expected.execute(
                "SELECT sql FROM sqlite_master WHERE name=?", (name,)
            ).fetchone()
            if actual is None or wanted is None or actual[0] != wanted[0]:
                raise ValueError("request_attempts_schema_invalid")
    finally:
        expected.close()


def ensure_request_attempts(connection: sqlite3.Connection) -> None:
    if has_request_attempts(connection):
        return
    create_request_attempts_schema(connection)
    # Older turns have no immutable send chronology. Their created_at may
    # predate a retry and updated_at may be a late reconciliation. Retain the
    # known values, but never present this storage order as a factual last send.
    connection.execute(
        """
        INSERT INTO chat_request_attempts (
            turn_id,chat_id,sent_at,chronology_known,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd
        )
        SELECT id,chat_id,NULL,0,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd
        FROM turns WHERE request_sent=1 ORDER BY rowid
        """
    )


def record_request_attempt(
    connection: sqlite3.Connection, turn_id: str, sent_at: str
) -> None:
    connection.execute(
        """
        INSERT INTO chat_request_attempts (
            turn_id,chat_id,sent_at,chronology_known,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd
        )
        SELECT id,chat_id,?,1,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd
        FROM turns WHERE id=? AND request_sent=1
        """,
        (sent_at, turn_id),
    )


def synchronize_request_attempt(connection: sqlite3.Connection, turn_id: str) -> None:
    if not has_request_attempts(connection):
        return
    # Only a dispatched current attempt can update its snapshot. An unsent
    # retry must not overwrite the previous attempt with its cleared fields.
    connection.execute(
        """
        UPDATE chat_request_attempts
        SET (status,accounting_status,prompt_tokens,completion_tokens,total_tokens,cost_usd) = (
            SELECT status,accounting_status,prompt_tokens,completion_tokens,total_tokens,cost_usd
            FROM turns WHERE id=?
        )
        WHERE sequence=(SELECT MAX(sequence) FROM chat_request_attempts WHERE turn_id=?)
          AND EXISTS (SELECT 1 FROM turns WHERE id=? AND request_sent=1)
        """,
        (turn_id, turn_id, turn_id),
    )


def recover_request_attempts(connection: sqlite3.Connection) -> None:
    if not has_request_attempts(connection):
        return
    for row in connection.execute(
        """
        SELECT DISTINCT a.turn_id FROM chat_request_attempts AS a
        JOIN turns AS t ON t.id=a.turn_id
        WHERE a.status='pending' AND t.status!='pending' AND t.request_sent=1
        """
    ).fetchall():
        synchronize_request_attempt(connection, str(row[0]))
