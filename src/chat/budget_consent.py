"""Exact request-scoped permission for a local chat spending warning.

This permission never authorizes a key, provider, token or unknown-accounting
exception. It is consumed under the repository's reservation transaction.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from decimal import Decimal

from chat.accounting import ChatBudget
from chat.models import Chat, PriceComponents

BUDGET_WARNING_FRACTION = Decimal("0.10")


@dataclass(frozen=True)
class BudgetWarning:
    limit_usd: Decimal
    remaining_usd: Decimal
    estimated_cost_usd: Decimal
    projected_remaining_usd: Decimal
    threshold_usd: Decimal

    @property
    def exceeds_limit(self) -> bool:
        return self.projected_remaining_usd < 0


def budget_warning(budget: ChatBudget, estimated_cost: Decimal) -> BudgetWarning | None:
    limit = budget.cost_limit_usd
    if limit is None or estimated_cost <= 0:
        return None
    remaining = limit - budget.cost_used_usd - budget.cost_reserved_usd
    projected = remaining - estimated_cost
    threshold = limit * BUDGET_WARNING_FRACTION
    if projected > threshold:
        return None
    return BudgetWarning(limit, remaining, estimated_cost, projected, threshold)


def text_digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def budget_version(budget: ChatBudget) -> tuple[object, ...]:
    """Bind exact limits and their observed revision, including live reservations."""
    return (
        budget.limits_configured,
        budget.token_limit,
        budget.max_completion_tokens,
        budget.cost_limit_usd,
        budget.total_tokens_used,
        budget.reserved_tokens,
        budget.cost_used_usd,
        budget.cost_reserved_usd,
        budget.state,
        budget.updated_at,
    )


def chat_prices(chat: Chat) -> tuple[PriceComponents, ...]:
    return (chat.price_snapshot, *chat.pricing_overrides)


@dataclass(frozen=True)
class BudgetConsentBasis:
    chat_id: str
    model_id: str
    text_sha256: str = field(repr=False)
    draft_revision: int | None
    limits_version: tuple[object, ...] = field(repr=False)
    pricing: tuple[PriceComponents, ...]
    request_sha256: str = field(repr=False)
    estimated_cost_usd: Decimal
    projected_remaining_usd: Decimal
    reserved_tokens: int
    scope: object = field(repr=False)
    retry_turn_id: str | None = None


class BudgetConsentRevoked(RuntimeError):
    """A fresh warning is required before this request can reserve money."""


@dataclass(frozen=True)
class BudgetConsent:
    basis: BudgetConsentBasis = field(repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _used: list[bool] = field(default_factory=lambda: [False], repr=False)

    def matches(self, basis: BudgetConsentBasis) -> bool:
        with self._lock:
            return not self._used[0] and self.basis == basis

    def consume(self, basis: BudgetConsentBasis) -> None:
        """Fail closed even if a later insert rolls back after this one use."""
        with self._lock:
            if self._used[0] or self.basis != basis:
                raise BudgetConsentRevoked()
            self._used[0] = True
