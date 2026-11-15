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
from providers.models import Currency, ProviderId

BUDGET_WARNING_FRACTION = Decimal("0.10")


@dataclass(frozen=True)
class BudgetWarning:
    limit_usd: Decimal | None
    remaining_usd: Decimal | None
    estimated_cost_usd: Decimal | None
    projected_remaining_usd: Decimal | None
    threshold_usd: Decimal | None
    currency: Currency = Currency.USD
    limit: Decimal | None = None
    remaining: Decimal | None = None
    estimated_cost: Decimal | None = None
    projected_remaining: Decimal | None = None
    threshold: Decimal | None = None
    unknown_pricing: bool = False

    def __post_init__(self) -> None:
        if self.currency is Currency.USD:
            for name in (
                "limit",
                "remaining",
                "estimated_cost",
                "projected_remaining",
                "threshold",
            ):
                if getattr(self, name) is None:
                    object.__setattr__(self, name, getattr(self, name + "_usd"))

    @property
    def exceeds_limit(self) -> bool:
        return self.projected_remaining is not None and self.projected_remaining < 0


def budget_warning(
    budget: ChatBudget, estimated_cost: Decimal | None
) -> BudgetWarning | None:
    limit = budget.cost_limit
    if limit is None or (estimated_cost is not None and estimated_cost <= 0):
        return None
    remaining = limit - budget.cost_used - budget.cost_reserved
    projected = None if estimated_cost is None else remaining - estimated_cost
    threshold = limit * BUDGET_WARNING_FRACTION
    if projected is not None and projected > threshold:
        return None
    usd = budget.currency is Currency.USD
    return BudgetWarning(
        limit if usd else None,
        remaining if usd else None,
        estimated_cost if usd else None,
        projected if usd else None,
        threshold if usd else None,
        currency=budget.currency,
        limit=limit,
        remaining=remaining,
        estimated_cost=estimated_cost,
        projected_remaining=projected,
        threshold=threshold,
        unknown_pricing=estimated_cost is None,
    )


def text_digest(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def budget_version(budget: ChatBudget) -> tuple[object, ...]:
    """Bind exact limits and their observed revision, including live reservations."""
    return (
        budget.limits_configured,
        budget.token_limit,
        budget.max_completion_tokens,
        budget.cost_limit,
        budget.total_tokens_used,
        budget.reserved_tokens,
        budget.cost_used,
        budget.cost_reserved,
        budget.state,
        budget.updated_at,
        budget.provider_id,
        budget.currency,
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
    estimated_cost_usd: Decimal | None
    projected_remaining_usd: Decimal | None
    reserved_tokens: int
    scope: object = field(repr=False)
    retry_turn_id: str | None = None
    provider_id: ProviderId = ProviderId.OPENROUTER
    currency: Currency = Currency.USD
    estimated_cost: Decimal | None = None
    projected_remaining: Decimal | None = None
    unknown_pricing: bool = False
    credential_sha256: str = field(default="", repr=False)
    credential_revision: object = field(default=None, repr=False)
    session_epoch: int | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.currency is Currency.USD:
            if self.estimated_cost is None:
                object.__setattr__(self, "estimated_cost", self.estimated_cost_usd)
            if self.projected_remaining is None:
                object.__setattr__(
                    self, "projected_remaining", self.projected_remaining_usd
                )


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


@dataclass(frozen=True)
class UnknownPriceConsent(BudgetConsent):
    """One explicit unknown-price dispatch, including unresolved prior money.

    The repository consumes this distinct permission only against its fresh
    transactional budget snapshot. It never releases an earlier reservation.
    """
