"""Additive provider accounting metadata, independent of the encryption format.

Only authorized repository writes invoke this migration. The content cipher,
registration and PIN records remain untouched. Every alteration and backfill is
performed in the caller's transaction and is safe to repeat after interruption.
"""

from __future__ import annotations

import sqlite3


def has_provider_schema(connection: sqlite3.Connection) -> bool:
    return "provider_id" in _columns(connection, "chats")


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def ensure_provider_schema(
    connection: sqlite3.Connection, *, chat_connections: bool = True
) -> None:
    definitions = {
        "chats": (
            "provider_id TEXT NOT NULL DEFAULT 'openrouter' CHECK(provider_id IN ('openrouter','vsegpt'))",
            "currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency IN ('USD','RUB'))",
        ),
        "chat_budgets": (
            "provider_id TEXT NOT NULL DEFAULT 'openrouter' CHECK(provider_id IN ('openrouter','vsegpt'))",
            "currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency IN ('USD','RUB'))",
            "cost_limit TEXT",
            "cost_used TEXT NOT NULL DEFAULT '0'",
            "cost_reserved TEXT NOT NULL DEFAULT '0'",
        ),
        "turns": (
            "provider_id TEXT NOT NULL DEFAULT 'openrouter' CHECK(provider_id IN ('openrouter','vsegpt'))",
            "currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency IN ('USD','RUB'))",
            "cost TEXT",
            "reserved_cost TEXT NOT NULL DEFAULT '0'",
            "usage_source TEXT NOT NULL DEFAULT 'unknown' CHECK(usage_source IN ('api','estimated','unknown'))",
            "cost_source TEXT NOT NULL DEFAULT 'unknown' CHECK(cost_source IN ('api','estimated','unknown'))",
            "cached_tokens INTEGER CHECK(cached_tokens IS NULL OR cached_tokens>=0)",
            "reasoning_tokens INTEGER CHECK(reasoning_tokens IS NULL OR reasoning_tokens>=0)",
        ),
    }
    for table, fields in definitions.items():
        columns = _columns(connection, table)
        added: set[str] = set()
        for definition in fields:
            name = definition.split()[0]
            if name not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
                added.add(name)
        if table == "chat_budgets":
            for name in ("cost_limit", "cost_used", "cost_reserved"):
                if name in added:
                    connection.execute(f"UPDATE {table} SET {name}={name}_usd")
        if table == "turns":
            if "cost" in added:
                connection.execute("UPDATE turns SET cost=cost_usd")
            if "reserved_cost" in added:
                connection.execute("UPDATE turns SET reserved_cost=reserved_cost_usd")
            if "usage_source" in added:
                connection.execute(
                    "UPDATE turns SET usage_source='api' WHERE prompt_tokens IS NOT NULL "
                    "OR completion_tokens IS NOT NULL OR total_tokens IS NOT NULL"
                )
            if "cost_source" in added:
                connection.execute(
                    "UPDATE turns SET cost_source='api' WHERE cost_usd IS NOT NULL"
                )

    if chat_connections:
        ensure_chat_connection_schema(connection)


MONETARY_TABLE = "chat_monetary_budgets"


def has_chat_connection_schema(connection: sqlite3.Connection) -> bool:
    return "connection_revision" in _columns(connection, "chats")


def ensure_chat_connection_schema(connection: sqlite3.Connection) -> None:
    """Backfill each old aggregate once, inside the caller's transaction.

    The old budget, not a sum of mutable messages or turns, is authoritative for
    migration. Existing target rows are never overwritten on a repeated call.
    """
    for table, definitions in {
        "chats": (
            "connection_revision INTEGER NOT NULL DEFAULT 0 CHECK(connection_revision>=0)",
        ),
        "turns": (
            "connection_revision INTEGER NOT NULL DEFAULT 0 CHECK(connection_revision>=0)",
            "retry_of_turn_id TEXT REFERENCES turns(id)",
        ),
    }.items():
        for definition in definitions:
            if definition.split()[0] not in _columns(connection, table):
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
    create_monetary_schema(connection)
    validate_monetary_schema(connection)
    connection.execute(
        "INSERT OR IGNORE INTO chat_monetary_budgets "
        "(chat_id,provider_id,currency,cost_limit,cost_used,cost_reserved,updated_at) "
        "SELECT chat_id,provider_id,currency,cost_limit,cost_used,cost_reserved,updated_at "
        "FROM chat_budgets"
    )


def create_monetary_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS chat_monetary_budgets ("
        "chat_id TEXT NOT NULL,provider_id TEXT NOT NULL CHECK(provider_id IN ('openrouter','vsegpt')),"
        "currency TEXT NOT NULL CHECK(currency IN ('USD','RUB')),"
        "cost_limit TEXT,cost_used TEXT NOT NULL DEFAULT '0',"
        "cost_reserved TEXT NOT NULL DEFAULT '0',updated_at TEXT NOT NULL,"
        "PRIMARY KEY(chat_id,provider_id,currency),"
        "CHECK((provider_id='openrouter' AND currency='USD') OR (provider_id='vsegpt' AND currency='RUB')),"
        "FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE)"
    )


def validate_monetary_schema(connection: sqlite3.Connection) -> None:
    expected = sqlite3.connect(":memory:")
    try:
        create_monetary_schema(expected)
        for pragma in ("table_info", "foreign_key_list", "index_list"):
            actual = [
                tuple(row)
                for row in connection.execute(f"PRAGMA {pragma}({MONETARY_TABLE})")
            ]
            wanted = [
                tuple(row)
                for row in expected.execute(f"PRAGMA {pragma}({MONETARY_TABLE})")
            ]
            if actual != wanted:
                raise ValueError("monetary_schema_invalid")
        actual = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name=?", (MONETARY_TABLE,)
        ).fetchone()
        wanted = expected.execute(
            "SELECT sql FROM sqlite_master WHERE name=?", (MONETARY_TABLE,)
        ).fetchone()
        if actual is None or wanted is None or actual[0] != wanted[0]:
            raise ValueError("monetary_schema_invalid")
    finally:
        expected.close()
