"""Точные локальные бюджеты, резервы и ценовые preflight-расчёты."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from chat.errors import ChatErrorType
from chat.models import (
    CatalogModel,
    Chat,
    ChatMode,
    PriceComponents,
    ProviderPriceLimit,
    maximum_pricing,
)
from i18n import tr
from storage.access_context import repository_session

ZERO = Decimal("0")
DEFAULT_CHAT_TOKEN_LIMIT = 8192
DEFAULT_MAX_COMPLETION_TOKENS = 1024
SUGGESTED_PAID_COST_LIMIT_USD = Decimal("1.00")


class BudgetState(str, Enum):
    UNCONFIGURED = "unconfigured"
    READY = "ready"
    EXHAUSTED = "exhausted"
    ACCOUNTING_UNKNOWN = "accounting_unknown"


class AccountingStatus(str, Enum):
    RESERVED = "reserved"
    FINAL = "final"
    UNKNOWN = "unknown"
    RELEASED = "released"


class TurnStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class ChatBudget:
    chat_id: str
    limits_configured: bool
    token_limit: int | None
    max_completion_tokens: int | None
    prompt_tokens_used: int
    completion_tokens_used: int
    total_tokens_used: int
    reserved_tokens: int
    cost_limit_usd: Decimal | None
    cost_used_usd: Decimal
    cost_reserved_usd: Decimal
    state: BudgetState
    updated_at: datetime


@dataclass(frozen=True)
class RemainingBudget:
    tokens: int | None
    cost_usd: Decimal | None
    blocked_by_unknown_accounting: bool


@dataclass(frozen=True)
class TurnRecord:
    id: str
    chat_id: str
    status: TurnStatus
    requested_model_id: str
    actual_model_id: str | None
    generation_id: str | None = field(repr=False)
    finish_reason: str | None = field(repr=False)
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: Decimal | None
    reserved_tokens: int
    reserved_cost_usd: Decimal
    accounting_status: AccountingStatus
    error_type: ChatErrorType | None
    request_sent: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class BudgetReservation:
    turn_id: str
    user_message_id: str
    chat_id: str
    reserved_tokens: int
    reserved_cost_usd: Decimal
    created_at: datetime


@dataclass(frozen=True)
class ChatLimitConfiguration:
    token_limit: int
    max_completion_tokens: int
    cost_limit_usd: Decimal


@dataclass(frozen=True)
class ModelPriceChange:
    confirmed: PriceComponents
    current: PriceComponents


def parse_chat_limit_input(
    mode: ChatMode,
    token_limit: str,
    max_completion_tokens: str,
    cost_limit_usd: str | None,
) -> ChatLimitConfiguration:
    if not isinstance(mode, ChatMode):
        raise ValueError(tr("service.mode_unknown"))
    if not isinstance(token_limit, str) or not isinstance(
        max_completion_tokens,
        str,
    ):
        raise ValueError(tr("service.limit_tokens_text"))
    if cost_limit_usd is not None and not isinstance(cost_limit_usd, str):
        raise ValueError(tr("service.limit_money_text"))
    normalized_token_limit = _parse_ascii_positive_int(
        token_limit,
        tr("service.limit_total_label"),
    )
    normalized_completion_limit = _parse_ascii_positive_int(
        max_completion_tokens,
        tr("service.limit_completion_label"),
    )
    normalized_cost: Decimal | None = None
    if mode is ChatMode.PAID:
        if cost_limit_usd is None or not cost_limit_usd.strip():
            raise ValueError(tr("service.paid_limit_required"))
        try:
            normalized_cost = Decimal(cost_limit_usd.strip())
        except (ArithmeticError, ValueError) as error:
            raise ValueError(tr("service.money_number")) from error
    cost = validate_limit_configuration(
        mode,
        normalized_token_limit,
        normalized_completion_limit,
        normalized_cost,
    )
    return ChatLimitConfiguration(
        token_limit=normalized_token_limit,
        max_completion_tokens=normalized_completion_limit,
        cost_limit_usd=cost,
    )


def validate_limit_configuration(
    mode: ChatMode,
    token_limit: int,
    max_completion_tokens: int,
    cost_limit_usd: Decimal | None,
) -> Decimal:
    if not isinstance(mode, ChatMode):
        raise ValueError(tr("service.mode_unknown"))
    if isinstance(token_limit, bool) or not isinstance(token_limit, int):
        raise ValueError(tr("service.token_integer"))
    if token_limit <= 0:
        raise ValueError(tr("service.token_positive"))
    if isinstance(max_completion_tokens, bool) or not isinstance(
        max_completion_tokens, int
    ):
        raise ValueError(tr("service.completion_integer"))
    if max_completion_tokens < 16:
        raise ValueError(tr("service.completion_minimum"))
    if max_completion_tokens > token_limit:
        raise ValueError(tr("service.completion_budget"))

    if mode is ChatMode.FREE:
        if cost_limit_usd not in {None, ZERO}:
            raise ValueError(tr("service.free_money_zero"))
        return ZERO
    if cost_limit_usd is None:
        raise ValueError(tr("service.paid_budget_required"))
    if not isinstance(cost_limit_usd, Decimal):
        raise ValueError(tr("service.money_decimal"))
    if not cost_limit_usd.is_finite() or cost_limit_usd <= 0:
        raise ValueError(tr("service.money_positive"))
    return cost_limit_usd


def calculate_remaining_budget(budget: ChatBudget) -> RemainingBudget:
    if not budget.limits_configured or budget.token_limit is None:
        return RemainingBudget(None, None, False)
    token_remaining = max(
        0,
        budget.token_limit - budget.total_tokens_used - budget.reserved_tokens,
    )
    cost_remaining = (
        None
        if budget.cost_limit_usd is None
        else max(
            ZERO,
            budget.cost_limit_usd - budget.cost_used_usd - budget.cost_reserved_usd,
        )
    )
    return RemainingBudget(
        tokens=token_remaining,
        cost_usd=cost_remaining,
        blocked_by_unknown_accounting=(budget.state is BudgetState.ACCOUNTING_UNKNOWN),
    )


def format_decimal_usd(value: Decimal) -> str:
    """Форматирует точное денежное значение без промежуточного float."""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered if rendered else "0"


def estimate_max_cost(
    pricing: tuple[PriceComponents, ...],
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Не применяет скидки и выбирает худший из известных overrides."""
    if not pricing or prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError(tr("service.estimate_invalid"))
    estimates = []
    for item in pricing:
        if not item.valid:
            raise ValueError(tr("service.price_unsafe"))
        prompt_cost = (
            item.prompt + item.input_cache_read + item.input_cache_write
        ) * prompt_tokens
        completion_cost = (
            item.completion + item.internal_reasoning
        ) * completion_tokens
        estimates.append(item.request + prompt_cost + completion_cost)
    return max(estimates)


def model_price_increased(chat: Chat, current: CatalogModel) -> bool:
    return (
        not chat.pricing_snapshot_complete
        or not current.pricing_is_complete
        or model_price_change(chat, current) is not None
    )


def model_price_change(chat: Chat, current: CatalogModel) -> ModelPriceChange | None:
    if not chat.pricing_snapshot_complete or not current.pricing_is_complete:
        return None
    confirmed = _maximum_components((chat.price_snapshot, *chat.pricing_overrides))
    live = maximum_pricing(current)
    increased = any(
        live_value > confirmed_value
        for live_value, confirmed_value in zip(
            live.values(),
            confirmed.values(),
            strict=True,
        )
    )
    return ModelPriceChange(confirmed, live) if increased else None


def confirmed_pricing(chat: Chat) -> tuple[PriceComponents, ...]:
    if not chat.pricing_snapshot_complete:
        raise ValueError(tr("service.price_confirmation"))
    return (chat.price_snapshot, *chat.pricing_overrides)


def confirmed_provider_price_limit(chat: Chat) -> ProviderPriceLimit:
    """Оставляет внутренние token-компоненты в единицах USD за токен."""
    confirmed = _maximum_components(confirmed_pricing(chat))
    return ProviderPriceLimit(
        prompt_per_token=confirmed.prompt,
        completion_per_token=confirmed.completion,
        request=confirmed.request,
    )


def _maximum_components(pricing: tuple[PriceComponents, ...]) -> PriceComponents:
    if not pricing or not all(item.valid for item in pricing):
        raise ValueError(tr("service.price_snapshot_invalid"))
    return PriceComponents(
        prompt=max(item.prompt for item in pricing),
        completion=max(item.completion for item in pricing),
        request=max(item.request for item in pricing),
        internal_reasoning=max(item.internal_reasoning for item in pricing),
        input_cache_read=max(item.input_cache_read for item in pricing),
        input_cache_write=max(item.input_cache_write for item in pricing),
    )


class BudgetRepository(Protocol):
    def get_chat_mode(self, chat_id: str) -> ChatMode | None: ...

    def get_chat_budget(self, chat_id: str) -> ChatBudget | None: ...

    def set_chat_limits(
        self,
        chat_id: str,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal,
        *,
        cost_increase_confirmed: bool,
        updated_at: datetime,
    ) -> ChatBudget: ...

    def release_unknown_reservation(
        self,
        turn_id: str,
        updated_at: datetime,
    ) -> None: ...

    def list_turns(self, chat_id: str) -> list[TurnRecord]: ...


class ChatBudgetService:
    def __init__(
        self,
        repository: BudgetRepository,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._now = now or (lambda: datetime.now(UTC))

    @repository_session("_repository")
    async def configure_chat_limits(
        self,
        chat_id: str,
        *,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal | None,
        cost_increase_confirmed: bool = False,
        updated_at: datetime | None = None,
    ) -> ChatBudget:
        _require_identifier(chat_id, tr("service.label.chat"))
        if not isinstance(cost_increase_confirmed, bool):
            raise ValueError(tr("service.money_confirmation_invalid"))
        mode = await asyncio.to_thread(self._repository.get_chat_mode, chat_id)
        if mode is None:
            raise KeyError(tr("service.chat_missing"))
        current = await self.get_chat_budget(chat_id)
        if current.limits_configured:
            raise ValueError(tr("service.limits_exist"))
        normalized_cost = validate_limit_configuration(
            mode,
            token_limit,
            max_completion_tokens,
            cost_limit_usd,
        )
        if mode is ChatMode.PAID and not cost_increase_confirmed:
            raise ValueError(tr("service.money_confirmation_required"))
        return await asyncio.to_thread(
            self._repository.set_chat_limits,
            chat_id,
            token_limit,
            max_completion_tokens,
            normalized_cost,
            cost_increase_confirmed=cost_increase_confirmed,
            updated_at=_as_utc(updated_at or self._now()),
        )

    @repository_session("_repository")
    async def update_chat_limits(
        self,
        chat_id: str,
        *,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal | None,
        cost_increase_confirmed: bool = False,
        updated_at: datetime | None = None,
    ) -> ChatBudget:
        _require_identifier(chat_id, tr("service.label.chat"))
        if not isinstance(cost_increase_confirmed, bool):
            raise ValueError(tr("service.money_confirmation_invalid"))
        mode = await asyncio.to_thread(self._repository.get_chat_mode, chat_id)
        if mode is None:
            raise KeyError(tr("service.chat_missing"))
        current = await self.get_chat_budget(chat_id)
        if not current.limits_configured:
            raise ValueError(tr("service.limits_missing"))
        normalized_cost = validate_limit_configuration(
            mode,
            token_limit,
            max_completion_tokens,
            cost_limit_usd,
        )
        return await asyncio.to_thread(
            self._repository.set_chat_limits,
            chat_id,
            token_limit,
            max_completion_tokens,
            normalized_cost,
            cost_increase_confirmed=cost_increase_confirmed,
            updated_at=_as_utc(updated_at or self._now()),
        )

    @repository_session("_repository")
    async def get_chat_budget(self, chat_id: str) -> ChatBudget:
        _require_identifier(chat_id, tr("service.label.chat"))
        budget = await asyncio.to_thread(self._repository.get_chat_budget, chat_id)
        if budget is None:
            raise KeyError(tr("service.chat_missing"))
        return budget

    @repository_session("_repository")
    async def calculate_remaining_budget(self, chat_id: str) -> RemainingBudget:
        return calculate_remaining_budget(await self.get_chat_budget(chat_id))

    @repository_session("_repository")
    async def list_chat_turns(self, chat_id: str) -> list[TurnRecord]:
        _require_identifier(chat_id, tr("service.label.chat"))
        return await asyncio.to_thread(self._repository.list_turns, chat_id)

    @repository_session("_repository")
    async def release_unknown_reservation(
        self,
        turn_id: str,
        *,
        confirmed: bool,
        updated_at: datetime | None = None,
    ) -> None:
        _require_identifier(turn_id, tr("service.label.turn"))
        if confirmed is not True:
            raise ValueError(tr("service.release_confirmation"))
        await asyncio.to_thread(
            self._repository.release_unknown_reservation,
            turn_id,
            _as_utc(updated_at or self._now()),
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_ascii_positive_int(value: str, label: str) -> int:
    normalized = value.strip()
    if not normalized or not normalized.isascii() or not normalized.isdecimal():
        raise ValueError(tr("service.positive_integer", field=label))
    return int(normalized)


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("service.identifier_invalid", field=label))
