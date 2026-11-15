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


def create_request_attempts_schema(
    connection: sqlite3.Connection,
    *,
    legacy: bool = False,
    connection_revision: bool = True,
) -> None:
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

    if not legacy:
        extend_request_attempts_schema(
            connection, connection_revision=connection_revision
        )


def extend_request_attempts_schema(
    connection: sqlite3.Connection, *, connection_revision: bool = True
) -> None:
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({TABLE})")}
    for definition in (
        "provider_id TEXT NOT NULL DEFAULT 'openrouter' CHECK(provider_id IN ('openrouter','vsegpt'))",
        "currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency IN ('USD','RUB'))",
        "requested_model_id TEXT",
        "actual_model_id TEXT",
        "usage_source TEXT NOT NULL DEFAULT 'unknown' CHECK(usage_source IN ('api','estimated','unknown'))",
        "cost_source TEXT NOT NULL DEFAULT 'unknown' CHECK(cost_source IN ('api','estimated','unknown'))",
        "cost TEXT",
        "cached_tokens INTEGER CHECK(cached_tokens IS NULL OR cached_tokens>=0)",
        "reasoning_tokens INTEGER CHECK(reasoning_tokens IS NULL OR reasoning_tokens>=0)",
        "reserved_cost TEXT",
        "reserved_tokens INTEGER CHECK(reserved_tokens IS NULL OR reserved_tokens>=0)",
    ):
        name = definition.split()[0]
        if name in columns:
            continue
        connection.execute(f"ALTER TABLE {TABLE} ADD COLUMN {definition}")
        if name == "cost":
            connection.execute(f"UPDATE {TABLE} SET cost=cost_usd")
        elif name == "cost_source":
            connection.execute(
                f"UPDATE {TABLE} SET cost_source='api' WHERE cost_usd IS NOT NULL"
            )
        elif name == "usage_source":
            connection.execute(
                f"UPDATE {TABLE} SET usage_source='api' WHERE prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL OR total_tokens IS NOT NULL"
            )
    if connection_revision and "connection_revision" not in columns:
        connection.execute(
            f"ALTER TABLE {TABLE} ADD COLUMN connection_revision INTEGER NOT NULL DEFAULT 0 CHECK(connection_revision>=0)"
        )
    # Existing mutable turns cannot prove a historical requested or actual model.
    # Do not backfill either identifier from the current chat or reused turn.


def request_attempts_are_extended(connection: sqlite3.Connection) -> bool:
    return any(
        row[1] == "provider_id"
        for row in connection.execute(f"PRAGMA table_info({TABLE})")
    )


def validate_request_attempts_schema(connection: sqlite3.Connection) -> None:
    """Accept only the known extension, including its foreign-key boundaries."""
    expected = sqlite3.connect(":memory:")
    try:
        create_request_attempts_schema(
            expected,
            legacy=not request_attempts_are_extended(connection),
            connection_revision=any(
                row[1] == "connection_revision"
                for row in connection.execute(f"PRAGMA table_info({TABLE})")
            ),
        )
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
        extend_request_attempts_schema(connection)
        return
    create_request_attempts_schema(connection)
    # Chronology and requested model cannot be recovered from a mutable old
    # turn, but its recorded provider/currency must never come from today's chat.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(turns)")}
    provider = "provider_id" if "provider_id" in columns else "'openrouter'"
    currency = "currency" if "currency" in columns else "'USD'"
    cost = "cost" if "cost" in columns else "cost_usd"
    revision = "connection_revision" if "connection_revision" in columns else "0"
    connection.execute(
        f"""
        INSERT INTO chat_request_attempts (
            turn_id,chat_id,sent_at,chronology_known,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd,cost,usage_source,cost_source,
            provider_id,currency,connection_revision
        )
        SELECT id,chat_id,NULL,0,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd,{cost},
            CASE WHEN prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL OR total_tokens IS NOT NULL THEN 'api' ELSE 'unknown' END,
            CASE WHEN {cost} IS NOT NULL THEN 'api' ELSE 'unknown' END,
            {provider},{currency},{revision}
        FROM turns WHERE request_sent=1 ORDER BY rowid
        """
    )


def record_request_attempt(
    connection: sqlite3.Connection, turn_id: str, sent_at: str
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO chat_request_attempts (
            turn_id,chat_id,sent_at,chronology_known,status,accounting_status,
            prompt_tokens,completion_tokens,total_tokens,cost_usd,
            provider_id,currency,requested_model_id,actual_model_id,
            cost,usage_source,cost_source,cached_tokens,reasoning_tokens,reserved_cost,reserved_tokens,connection_revision
        )
        SELECT t.id,t.chat_id,?,1,t.status,t.accounting_status,
            t.prompt_tokens,t.completion_tokens,t.total_tokens,t.cost_usd,
            t.provider_id,t.currency,t.requested_model_id,t.actual_model_id,
            t.cost,t.usage_source,t.cost_source,t.cached_tokens,t.reasoning_tokens,t.reserved_cost,t.reserved_tokens,t.connection_revision
        FROM turns AS t WHERE t.id=? AND t.request_sent=1
        """,
        (sent_at, turn_id),
    )
    if cursor.lastrowid is None:
        raise ValueError("request_attempt_not_recorded")
    return cursor.lastrowid


def synchronize_request_attempt(connection: sqlite3.Connection, turn_id: str) -> None:
    if not has_request_attempts(connection):
        return
    extended = request_attempts_are_extended(connection) and any(
        row[1] == "cost" for row in connection.execute("PRAGMA table_info(turns)")
    )
    fields = (
        "status,accounting_status,prompt_tokens,completion_tokens,total_tokens,cost_usd"
    )
    if extended:
        fields += ",actual_model_id,cost,usage_source,cost_source,cached_tokens,reasoning_tokens"
    # Immutable dispatch identity, requested model, provider, currency and time
    # are deliberately absent from the update list.
    connection.execute(
        f"UPDATE {TABLE} SET ({fields})=(SELECT {fields} FROM turns WHERE id=?) "
        f"WHERE sequence=(SELECT MAX(sequence) FROM {TABLE} WHERE turn_id=?) "
        "AND EXISTS (SELECT 1 FROM turns WHERE id=? AND request_sent=1)",
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
