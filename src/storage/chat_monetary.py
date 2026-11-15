"""Canonical per-provider money with a legacy active-budget projection.

Only token counters belong to the whole chat. The old monetary columns remain
readable for compatibility, but all new accounting writes name their provider.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any

from providers.models import Currency, ProviderId, provider_spec
from storage.provider_schema import MONETARY_TABLE, has_chat_connection_schema


def budget_row(
    connection: sqlite3.Connection,
    chat_id: str,
    provider_id: ProviderId | None = None,
) -> dict[str, Any] | None:
    row = (
        connection.execute(
            "SELECT b.*,c.mode AS chat_mode,c.provider_id AS active_provider,"
            "c.currency AS active_currency FROM chat_budgets b JOIN chats c ON c.id=b.chat_id WHERE b.chat_id=?",
            (chat_id,),
        ).fetchone()
        if has_provider_columns(connection)
        else connection.execute(
            "SELECT b.*,c.mode AS chat_mode FROM chat_budgets b JOIN chats c ON c.id=b.chat_id WHERE b.chat_id=?",
            (chat_id,),
        ).fetchone()
    )
    if row is None:
        return None
    values = dict(row)
    active = ProviderId(values.get("active_provider", "openrouter"))
    selected = active if provider_id is None else ProviderId(provider_id)
    currency = provider_spec(selected).currency
    if has_chat_connection_schema(connection):
        money = connection.execute(
            f"SELECT * FROM {MONETARY_TABLE} WHERE chat_id=? AND provider_id=? AND currency=?",
            (chat_id, selected.value, currency.value),
        ).fetchone()
        values.update(
            cost_limit=money["cost_limit"] if money else None,
            cost_used=money["cost_used"] if money else "0",
            cost_reserved=money["cost_reserved"] if money else "0",
        )
    elif selected != active:
        values.update(cost_limit=None, cost_used="0", cost_reserved="0")
    values["provider_id"] = selected.value
    values["currency"] = currency.value
    for name in ("cost_limit", "cost_used", "cost_reserved"):
        value = values.get(name, values.get(name + "_usd"))
        values[name] = value
        values[name + "_usd"] = (
            value if currency is Currency.USD else None if name == "cost_limit" else "0"
        )
    return values


def has_provider_columns(connection: sqlite3.Connection) -> bool:
    return any(
        row[1] == "provider_id"
        for row in connection.execute("PRAGMA table_info(chats)")
    )


def write_money(
    connection: sqlite3.Connection,
    chat_id: str,
    provider_id: ProviderId,
    currency: Currency,
    *,
    cost_limit: Decimal | None,
    cost_used: Decimal,
    cost_reserved: Decimal,
    updated_at: str,
) -> None:
    if provider_spec(provider_id).currency is not currency:
        raise ValueError("provider_currency_mismatch")
    connection.execute(
        f"INSERT INTO {MONETARY_TABLE} (chat_id,provider_id,currency,cost_limit,cost_used,cost_reserved,updated_at) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(chat_id,provider_id,currency) DO UPDATE SET cost_limit=excluded.cost_limit,cost_used=excluded.cost_used,cost_reserved=excluded.cost_reserved,updated_at=excluded.updated_at",
        (
            chat_id,
            provider_id.value,
            currency.value,
            str(cost_limit) if cost_limit is not None else None,
            str(cost_used),
            str(cost_reserved),
            updated_at,
        ),
    )


def refresh_active_projection(connection: sqlite3.Connection, chat_id: str) -> None:
    row = budget_row(connection, chat_id)
    if row is None:
        return
    unknown = (
        connection.execute(
            "SELECT 1 FROM turns WHERE chat_id=? AND accounting_status='unknown' LIMIT 1",
            (chat_id,),
        ).fetchone()
        is not None
    )
    token_limit = row["token_limit"]
    used = Decimal(row["cost_used"])
    reserved = Decimal(row["cost_reserved"])
    limit = Decimal(row["cost_limit"]) if row["cost_limit"] is not None else None
    if unknown:
        state = "accounting_unknown"
    elif token_limit is None:
        state = "unconfigured"
    elif row["total_tokens_used"] + row["reserved_tokens"] >= token_limit:
        state = "exhausted"
    elif row["chat_mode"] == "paid" and limit is not None and used + reserved >= limit:
        state = "exhausted"
    else:
        state = "ready"
    # A historic paid charge does not make a newly selected free model paid.
    # An unexpected known charge in this actual free connection remains blocked.
    if row["chat_mode"] == "free" and any(
        Decimal(str(cost[0])) > 0
        for cost in connection.execute(
            "SELECT t.cost FROM turns t JOIN chats c ON c.id=t.chat_id WHERE t.chat_id=? AND t.connection_revision=c.connection_revision AND t.cost IS NOT NULL",
            (chat_id,),
        )
    ):
        state = "exhausted"
    connection.execute(
        "UPDATE chat_budgets SET provider_id=?,currency=?,cost_limit=?,cost_used=?,cost_reserved=?,cost_limit_usd=?,cost_used_usd=?,cost_reserved_usd=?,state=? WHERE chat_id=?",
        (
            row["provider_id"],
            row["currency"],
            row["cost_limit"],
            row["cost_used"],
            row["cost_reserved"],
            row["cost_limit_usd"],
            row["cost_used_usd"],
            row["cost_reserved_usd"],
            state,
            chat_id,
        ),
    )
