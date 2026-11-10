"""Immutable, local chat metrics without credentials or transport access."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from auth.models import KeyLimitInfo
from chat.account_balance import AccountBalanceSnapshot
from chat.accounting import ChatBudget, RemainingBudget, calculate_remaining_budget
from chat.models import Chat, ChatMode


class LastRequestState(str, Enum):
    NONE = "none"
    PENDING = "pending"
    FINAL = "final"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LastRequestMetrics:
    state: LastRequestState
    turn_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: Decimal | None = None
    sent_at: datetime | None = None
    chronology_known: bool = True
    attempt_sequence: int | None = None


@dataclass(frozen=True)
class ChatMetricsSnapshot:
    chat_id: str
    mode: ChatMode
    remaining: RemainingBudget
    last_request: LastRequestMetrics
    pending: bool = False
    key_limit: KeyLimitInfo = field(default_factory=KeyLimitInfo.unknown)
    metadata_updated_at: datetime | None = None
    account_balance_usd: Decimal | None = None
    account_balance: AccountBalanceSnapshot = field(
        default_factory=AccountBalanceSnapshot
    )


def build_chat_metrics(
    chat: Chat,
    budget: ChatBudget,
    last_request: LastRequestMetrics,
    *,
    pending: bool = False,
    key_limit: KeyLimitInfo | None = None,
    metadata_updated_at: datetime | None = None,
    account_balance: AccountBalanceSnapshot | None = None,
) -> ChatMetricsSnapshot:
    """Keep account API snapshots separate from chat and key budgets."""
    if chat.id != budget.chat_id:
        raise ValueError("chat_metrics_snapshot_mismatch")
    return ChatMetricsSnapshot(
        chat_id=chat.id,
        mode=chat.mode,
        remaining=calculate_remaining_budget(budget),
        last_request=last_request,
        pending=pending,
        key_limit=key_limit or KeyLimitInfo.unknown(),
        metadata_updated_at=metadata_updated_at,
        account_balance_usd=(
            account_balance.balance_usd if account_balance is not None else None
        ),
        account_balance=account_balance or AccountBalanceSnapshot(),
    )
