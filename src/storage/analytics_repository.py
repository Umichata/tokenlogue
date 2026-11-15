"""Read the saved-chat dispatch journal without modifying legacy profiles."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from chat.analytics import RequestAttempt
from providers.models import Currency, ProviderId
from storage.database_connections import ContentAccess, connection
from storage.request_attempts import has_request_attempts


class SqliteAnalyticsRepository:
    def __init__(
        self, database_path: str | Path, access: ContentAccess | None = None
    ) -> None:
        self.path = Path(database_path)
        self.access = access

    def list_attempts(self) -> list[RequestAttempt]:
        with connection(self.path, self.access, "read") as database:
            if has_request_attempts(database):
                rows = database.execute(
                    "SELECT a.* FROM chat_request_attempts a JOIN chats c ON c.id=a.chat_id ORDER BY a.sequence"
                ).fetchall()
                return [_attempt(row) for row in rows]
            # No dispatch chronology was saved in older profiles. A turn may
            # have been retried and mutated; do not infer send time or model.
            rows = database.execute(
                "SELECT rowid AS sequence,* FROM turns WHERE request_sent=1 ORDER BY rowid"
            ).fetchall()
            return [_attempt(row, legacy_turn=True) for row in rows]


def _attempt(row: sqlite3.Row, *, legacy_turn: bool = False) -> RequestAttempt:
    columns = row.keys()
    sent_at = None
    known = not legacy_turn and bool(row["chronology_known"])
    if known and row["sent_at"]:
        try:
            sent_at = datetime.fromisoformat(str(row["sent_at"]))
            if sent_at.tzinfo is None:
                sent_at = None
        except ValueError:
            pass
    tokens = (row["prompt_tokens"], row["completion_tokens"], row["total_tokens"])
    cost_value = row["cost"] if "cost" in columns else row["cost_usd"]
    return RequestAttempt(
        sequence=int(row["sequence"]),
        turn_id=str(row["id"] if legacy_turn else row["turn_id"]),
        chat_id=str(row["chat_id"]),
        provider_id=ProviderId(str(row["provider_id"]))
        if "provider_id" in columns
        else ProviderId.OPENROUTER,
        currency=Currency(str(row["currency"]))
        if "currency" in columns
        else Currency.USD,
        requested_model_id=str(row["requested_model_id"])
        if not legacy_turn
        and "requested_model_id" in columns
        and row["requested_model_id"] is not None
        else None,
        actual_model_id=str(row["actual_model_id"])
        if not legacy_turn
        and "actual_model_id" in columns
        and row["actual_model_id"] is not None
        else None,
        sent_at=sent_at,
        chronology_known=known and sent_at is not None,
        prompt_tokens=int(tokens[0]) if tokens[0] is not None else None,
        completion_tokens=int(tokens[1]) if tokens[1] is not None else None,
        total_tokens=int(tokens[2]) if tokens[2] is not None else None,
        usage_source=str(row["usage_source"])
        if "usage_source" in columns
        else "api"
        if any(value is not None for value in tokens)
        else "unknown",
        cost=Decimal(str(cost_value)) if cost_value is not None else None,
        cost_source=str(row["cost_source"])
        if "cost_source" in columns
        else "api"
        if cost_value is not None
        else "unknown",
        accounting_status=str(row["accounting_status"]),
        cached_tokens=int(row["cached_tokens"])
        if "cached_tokens" in columns and row["cached_tokens"] is not None
        else None,
        reserved_cost=Decimal(str(row["reserved_cost"]))
        if not legacy_turn
        and "reserved_cost" in columns
        and row["reserved_cost"] is not None
        else None,
        reserved_tokens=int(row["reserved_tokens"])
        if not legacy_turn
        and "reserved_tokens" in columns
        and row["reserved_tokens"] is not None
        else None,
        reasoning_tokens=int(row["reasoning_tokens"])
        if "reasoning_tokens" in columns and row["reasoning_tokens"] is not None
        else None,
    )
