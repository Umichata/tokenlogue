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


def ensure_provider_schema(connection: sqlite3.Connection) -> None:
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
