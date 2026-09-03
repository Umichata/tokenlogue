"""Доменные модели чатов и централизованная классификация моделей."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

PRICE_PER_MILLION = Decimal("1000000")


class ChatMode(str, Enum):
    FREE = "free"
    PAID = "paid"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


@dataclass(frozen=True)
class PriceComponents:
    """Полный набор цен, потенциально применимый к текстовому запросу."""

    prompt: Decimal = Decimal("0")
    completion: Decimal = Decimal("0")
    request: Decimal = Decimal("0")
    internal_reasoning: Decimal = Decimal("0")
    input_cache_read: Decimal = Decimal("0")
    input_cache_write: Decimal = Decimal("0")

    def values(self) -> tuple[Decimal, ...]:
        return (
            self.prompt,
            self.completion,
            self.request,
            self.internal_reasoning,
            self.input_cache_read,
            self.input_cache_write,
        )

    @property
    def valid(self) -> bool:
        return all(
            isinstance(value, Decimal) and _valid_price(value)
            for value in self.values()
        )

    @property
    def is_zero(self) -> bool:
        return self.valid and all(value == 0 for value in self.values())


@dataclass(frozen=True)
class ProviderPriceLimit:
    """Внутренний лимит: токеновые цены за токен, request — за запрос."""

    prompt_per_token: Decimal
    completion_per_token: Decimal
    request: Decimal

    @property
    def valid(self) -> bool:
        return all(
            isinstance(value, Decimal) and value.is_finite() and value >= 0
            for value in (
                self.prompt_per_token,
                self.completion_per_token,
                self.request,
            )
        )

    @classmethod
    def zero(cls) -> ProviderPriceLimit:
        return cls(Decimal("0"), Decimal("0"), Decimal("0"))


@dataclass(frozen=True)
class CatalogModel:
    id: str
    name: str
    prompt_price_per_token: Decimal
    completion_price_per_token: Decimal
    input_modalities: tuple[str, ...] = ("text",)
    output_modalities: tuple[str, ...] = ("text",)
    recommended: bool = False
    request_price: Decimal = Decimal("0")
    internal_reasoning_price_per_token: Decimal = Decimal("0")
    input_cache_read_price_per_token: Decimal = Decimal("0")
    input_cache_write_price_per_token: Decimal = Decimal("0")
    pricing_overrides: tuple[PriceComponents, ...] = ()
    pricing_is_complete: bool = True
    context_length: int | None = None
    provider_max_completion_tokens: int | None = None

    @property
    def base_pricing(self) -> PriceComponents:
        return PriceComponents(
            prompt=self.prompt_price_per_token,
            completion=self.completion_price_per_token,
            request=self.request_price,
            internal_reasoning=self.internal_reasoning_price_per_token,
            input_cache_read=self.input_cache_read_price_per_token,
            input_cache_write=self.input_cache_write_price_per_token,
        )

    @property
    def all_pricing(self) -> tuple[PriceComponents, ...]:
        return (self.base_pricing, *self.pricing_overrides)

    @property
    def prompt_price_per_million(self) -> Decimal:
        return self.prompt_price_per_token * PRICE_PER_MILLION

    @property
    def completion_price_per_million(self) -> Decimal:
        return self.completion_price_per_token * PRICE_PER_MILLION


FREE_ROUTER_MODEL = CatalogModel(
    id="openrouter/free",
    name="Автоматический выбор бесплатной модели",
    prompt_price_per_token=Decimal("0"),
    completion_price_per_token=Decimal("0"),
    recommended=True,
    context_length=8192,
)


@dataclass(frozen=True)
class ModelCatalog:
    free_models: tuple[CatalogModel, ...]
    paid_models: tuple[CatalogModel, ...]
    available: bool
    warning: str | None = None


@dataclass(frozen=True)
class Chat:
    id: str
    title: str
    mode: ChatMode
    requested_model_id: str
    requested_model_name: str
    prompt_price_per_token: Decimal
    completion_price_per_token: Decimal
    created_at: datetime
    updated_at: datetime
    request_price: Decimal = Decimal("0")
    internal_reasoning_price_per_token: Decimal = Decimal("0")
    input_cache_read_price_per_token: Decimal = Decimal("0")
    input_cache_write_price_per_token: Decimal = Decimal("0")
    pricing_overrides: tuple[PriceComponents, ...] = ()
    pricing_snapshot_complete: bool = True

    @property
    def price_snapshot(self) -> PriceComponents:
        return PriceComponents(
            prompt=self.prompt_price_per_token,
            completion=self.completion_price_per_token,
            request=self.request_price,
            internal_reasoning=self.internal_reasoning_price_per_token,
            input_cache_read=self.input_cache_read_price_per_token,
            input_cache_write=self.input_cache_write_price_per_token,
        )


@dataclass(frozen=True)
class Message:
    id: str
    chat_id: str
    turn_id: str
    role: MessageRole
    content: str = field(repr=False)
    status: MessageStatus
    requested_model_id: str | None
    actual_model_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    created_at: datetime


def is_standard_text_chat_model(model: CatalogModel) -> bool:
    """Проверяет обычную text-to-text модель и валидные цены."""
    if "text" not in model.input_modalities or "text" not in model.output_modalities:
        return False
    if not all(pricing.valid for pricing in model.all_pricing):
        return False
    if model.id == FREE_ROUTER_MODEL.id:
        return True
    if model.id.startswith("openrouter/"):
        return False

    lowered_id = model.id.lower()
    if ":" in lowered_id and not lowered_id.endswith(":free"):
        return False
    slug_tokens = (
        lowered_id.replace("/", "-").replace(":", "-").replace("_", "-").split("-")
    )
    return not {"batch", "online"}.intersection(slug_tokens)


def is_free_model(model: CatalogModel) -> bool:
    return (
        is_standard_text_chat_model(model)
        and model.pricing_is_complete
        and all(pricing.is_zero for pricing in model.all_pricing)
    )


def is_paid_model(model: CatalogModel) -> bool:
    return (
        is_standard_text_chat_model(model)
        and model.pricing_is_complete
        and any(
            value > 0 for pricing in model.all_pricing for value in pricing.values()
        )
    )


def maximum_pricing(model: CatalogModel) -> PriceComponents:
    """Возвращает покомпонентный максимум без применения возможных скидок."""
    schedules = model.all_pricing
    return PriceComponents(
        prompt=max(item.prompt for item in schedules),
        completion=max(item.completion for item in schedules),
        request=max(item.request for item in schedules),
        internal_reasoning=max(item.internal_reasoning for item in schedules),
        input_cache_read=max(item.input_cache_read for item in schedules),
        input_cache_write=max(item.input_cache_write for item in schedules),
    )


def format_price_per_million(price: Decimal) -> str:
    """Форматирует USD за миллион токенов без float-преобразования."""
    value = price * PRICE_PER_MILLION
    rendered = f"{value:,.6f}".rstrip("0").rstrip(".")
    return rendered if rendered else "0"


def _valid_price(price: Decimal) -> bool:
    return price.is_finite() and price >= 0
