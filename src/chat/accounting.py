"""Точные локальные бюджеты, резервы и ценовые preflight-расчёты."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
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
    generation_id: str | None
    finish_reason: str | None
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
        raise ValueError("Неизвестный режим чата")
    if not isinstance(token_limit, str) or not isinstance(
        max_completion_tokens,
        str,
    ):
        raise ValueError("Токеновые лимиты должны быть текстовыми значениями")
    if cost_limit_usd is not None and not isinstance(cost_limit_usd, str):
        raise ValueError("Денежный лимит должен быть текстовым значением")
    normalized_token_limit = _parse_ascii_positive_int(
        token_limit,
        "Общий лимит токенов",
    )
    normalized_completion_limit = _parse_ascii_positive_int(
        max_completion_tokens,
        "Максимум токенов ответа",
    )
    normalized_cost: Decimal | None = None
    if mode is ChatMode.PAID:
        if cost_limit_usd is None or not cost_limit_usd.strip():
            raise ValueError("Для платного чата укажите денежный лимит")
        try:
            normalized_cost = Decimal(cost_limit_usd.strip())
        except (ArithmeticError, ValueError) as error:
            raise ValueError("Денежный лимит должен быть числом") from error
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
        raise ValueError("Неизвестный режим чата")
    if isinstance(token_limit, bool) or not isinstance(token_limit, int):
        raise ValueError("Токен-бюджет должен быть целым числом")
    if token_limit <= 0:
        raise ValueError("Токен-бюджет должен быть положительным")
    if isinstance(max_completion_tokens, bool) or not isinstance(
        max_completion_tokens, int
    ):
        raise ValueError("Максимальная длина ответа должна быть целым числом")
    if max_completion_tokens < 16:
        raise ValueError("Максимальная длина ответа не может быть меньше 16")
    if max_completion_tokens > token_limit:
        raise ValueError("Максимальная длина ответа превышает токен-бюджет")

    if mode is ChatMode.FREE:
        if cost_limit_usd not in {None, ZERO}:
            raise ValueError("Денежный лимит бесплатного чата всегда равен нулю")
        return ZERO
    if cost_limit_usd is None:
        raise ValueError("Для платного чата требуется денежный бюджет")
    if not isinstance(cost_limit_usd, Decimal):
        raise ValueError("Денежный бюджет должен использовать Decimal")
    if not cost_limit_usd.is_finite() or cost_limit_usd <= 0:
        raise ValueError("Денежный бюджет должен быть положительным и конечным")
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
        raise ValueError("Некорректные данные оценки стоимости")
    estimates = []
    for item in pricing:
        if not item.valid:
            raise ValueError("Цена не может быть безопасно оценена")
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
        raise ValueError("Снимок цены требует подтверждения")
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
        raise ValueError("Некорректный снимок цены")
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
        _require_identifier(chat_id, "чата")
        if not isinstance(cost_increase_confirmed, bool):
            raise ValueError("Некорректное подтверждение денежного лимита")
        mode = await asyncio.to_thread(self._repository.get_chat_mode, chat_id)
        if mode is None:
            raise KeyError("Чат не найден")
        current = await self.get_chat_budget(chat_id)
        if current.limits_configured:
            raise ValueError("Лимиты чата уже настроены")
        normalized_cost = validate_limit_configuration(
            mode,
            token_limit,
            max_completion_tokens,
            cost_limit_usd,
        )
        if mode is ChatMode.PAID and not cost_increase_confirmed:
            raise ValueError("Денежный бюджет требует явного подтверждения")
        return await asyncio.to_thread(
            self._repository.set_chat_limits,
            chat_id,
            token_limit,
            max_completion_tokens,
            normalized_cost,
            cost_increase_confirmed=cost_increase_confirmed,
            updated_at=_as_utc(updated_at or self._now()),
        )

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
        _require_identifier(chat_id, "чата")
        if not isinstance(cost_increase_confirmed, bool):
            raise ValueError("Некорректное подтверждение денежного лимита")
        mode = await asyncio.to_thread(self._repository.get_chat_mode, chat_id)
        if mode is None:
            raise KeyError("Чат не найден")
        current = await self.get_chat_budget(chat_id)
        if not current.limits_configured:
            raise ValueError("Лимиты чата ещё не настроены")
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

    async def get_chat_budget(self, chat_id: str) -> ChatBudget:
        _require_identifier(chat_id, "чата")
        budget = await asyncio.to_thread(self._repository.get_chat_budget, chat_id)
        if budget is None:
            raise KeyError("Чат не найден")
        return budget

    async def calculate_remaining_budget(self, chat_id: str) -> RemainingBudget:
        return calculate_remaining_budget(await self.get_chat_budget(chat_id))

    async def list_chat_turns(self, chat_id: str) -> list[TurnRecord]:
        _require_identifier(chat_id, "чата")
        return await asyncio.to_thread(self._repository.list_turns, chat_id)

    async def release_unknown_reservation(
        self,
        turn_id: str,
        *,
        confirmed: bool,
        updated_at: datetime | None = None,
    ) -> None:
        _require_identifier(turn_id, "попытки")
        if confirmed is not True:
            raise ValueError("Снятие неизвестного резерва требует подтверждения")
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
        raise ValueError(f"{label} должен быть положительным целым числом")
    return int(normalized)


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Некорректный идентификатор {label}")
