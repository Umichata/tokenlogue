"""Pure local request planning shared by sending and the live composer estimate.

No API key, repository, consent or transport is accepted here. The UTF-8 token
estimate is deliberately conservative and is not model-specific tokenization.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum

from auth.models import KeyLimitInfo, KeyLimitState
from chat.accounting import (
    BudgetState,
    ChatBudget,
    confirmed_pricing,
    estimate_max_cost,
    model_price_increased,
)
from chat.context import (
    FREE_ROUTER_CONTEXT_LENGTH,
    REQUEST_OVERHEAD_TOKENS,
    ContextSelection,
    ContextWindowExceeded,
    PreparedHistory,
    estimate_message_tokens,
    select_conversation_context,
)
from chat.errors import ChatErrorType
from chat.models import (
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    PriceComponents,
    is_free_model,
)
from providers.models import Currency, PriceUnit, ProviderId

MIN_COMPLETION_TOKENS = 16
ZERO = Decimal("0")


class EstimateState(str, Enum):
    EMPTY = "empty"
    READY = "ready"
    UNAVAILABLE = "unavailable"
    OVER_LIMIT = "over_limit"


@dataclass(frozen=True)
class DraftEstimate:
    state: EstimateState
    prompt_tokens: int | None = None
    max_completion_tokens: int | None = None
    cost_upper_usd: Decimal | None = None
    error: ChatErrorType | None = None
    free_router: bool = False
    cost_upper: Decimal | None = None
    currency: Currency = Currency.USD
    provider_id: ProviderId = ProviderId.OPENROUTER

    def __post_init__(self) -> None:
        if self.currency is Currency.USD and self.cost_upper is None:
            object.__setattr__(self, "cost_upper", self.cost_upper_usd)


@dataclass(frozen=True)
class PreparedEstimateSnapshot:
    """Authorized immutable inputs whose lifetime is owned by the controller."""

    chat: Chat
    budget: ChatBudget | None
    model: CatalogModel | None
    history: PreparedHistory = field(repr=False)
    key_limit: KeyLimitInfo = field(default_factory=KeyLimitInfo.unknown)


@dataclass(frozen=True)
class RequestPlan:
    context: ContextSelection = field(repr=False)
    effective_max_completion_tokens: int
    reserved_tokens: int
    reserved_cost_usd: Decimal | None
    remaining_tokens_after_reservation: int
    remaining_cost_after_reservation: Decimal | None
    reserved_cost: Decimal | None = None
    currency: Currency = Currency.USD

    def __post_init__(self) -> None:
        if self.currency is Currency.USD and self.reserved_cost is None:
            object.__setattr__(self, "reserved_cost", self.reserved_cost_usd)


class RequestPlanError(ValueError):
    def __init__(self, error_type: ChatErrorType) -> None:
        super().__init__(error_type.value)
        self.error_type = error_type


def calculate_request_plan(
    *,
    chat: Chat,
    budget: ChatBudget,
    model: CatalogModel,
    history: PreparedHistory,
    text: str,
    pricing: tuple[PriceComponents, ...] | None,
    key_limit: KeyLimitInfo,
    apply_chat_cost_limit: bool = True,
    allow_unknown_accounting: bool = False,
) -> RequestPlan:
    """Plan the exact local context and caps without authorizing a send.

    Unknown pricing preserves the token/context bound but deliberately leaves
    money and the price-limited response cap unknown. Real preflight only calls
    this function after its existing complete-price and authorization guards.
    """
    normalized = text.strip()
    if not normalized:
        raise RequestPlanError(ChatErrorType.INVALID_REQUEST)
    if not budget.limits_configured:
        raise RequestPlanError(ChatErrorType.LIMITS_NOT_CONFIGURED)
    if budget.state is BudgetState.ACCOUNTING_UNKNOWN and not allow_unknown_accounting:
        raise RequestPlanError(ChatErrorType.ACCOUNTING_UNKNOWN)
    if budget.token_limit is None or budget.max_completion_tokens is None:
        raise RequestPlanError(ChatErrorType.LIMITS_NOT_CONFIGURED)
    if budget.state is BudgetState.EXHAUSTED:
        if budget.total_tokens_used + budget.reserved_tokens >= budget.token_limit:
            raise RequestPlanError(ChatErrorType.TOKEN_LIMIT_EXCEEDED)
        if apply_chat_cost_limit:
            raise RequestPlanError(ChatErrorType.COST_LIMIT_EXCEEDED)
    context_length = (
        FREE_ROUTER_CONTEXT_LENGTH
        if chat.provider_id is ProviderId.OPENROUTER
        and chat.requested_model_id == FREE_ROUTER_MODEL.id
        else model.context_length
    )
    if context_length is None or context_length <= MIN_COMPLETION_TOKENS:
        raise RequestPlanError(ChatErrorType.CONTEXT_LENGTH_EXCEEDED)
    completion_cap = budget.max_completion_tokens
    if model.provider_max_completion_tokens is not None:
        completion_cap = min(completion_cap, model.provider_max_completion_tokens)
    if completion_cap < MIN_COMPLETION_TOKENS:
        raise RequestPlanError(ChatErrorType.MAX_TOKENS_EXCEEDED)
    token_remaining = (
        budget.token_limit - budget.total_tokens_used - budget.reserved_tokens
    )
    try:
        context = select_conversation_context(
            history,
            normalized,
            context_length=context_length,
            completion_reserve=MIN_COMPLETION_TOKENS,
            require_full_history=True,
        )
    except ContextWindowExceeded:
        raise RequestPlanError(ChatErrorType.CONTEXT_LENGTH_EXCEEDED) from None
    effective_completion = min(
        completion_cap,
        token_remaining - context.estimated_prompt_tokens,
        context_length - context.estimated_prompt_tokens,
    )
    if effective_completion < MIN_COMPLETION_TOKENS:
        raise RequestPlanError(ChatErrorType.TOKEN_LIMIT_EXCEEDED)
    if chat.mode is ChatMode.PAID:
        if budget.cost_limit is None:
            raise RequestPlanError(ChatErrorType.LIMITS_NOT_CONFIGURED)
        if pricing is not None:
            if not pricing or not all(item.valid for item in pricing):
                raise RequestPlanError(ChatErrorType.MODEL_PRICE_UNSAFE)
            cost_remaining = budget.cost_limit - budget.cost_used - budget.cost_reserved
            if apply_chat_cost_limit:
                effective_completion = _cap_completion_by_cost(
                    effective_completion,
                    pricing,
                    context.estimated_prompt_tokens,
                    cost_remaining,
                    ChatErrorType.COST_LIMIT_EXCEEDED,
                )
            if (
                key_limit.state is KeyLimitState.AVAILABLE
                and key_limit.remaining is not None
            ):
                effective_completion = _cap_completion_by_cost(
                    effective_completion,
                    pricing,
                    context.estimated_prompt_tokens,
                    key_limit.remaining,
                    ChatErrorType.KEY_LIMIT_EXCEEDED,
                )
    reserved_tokens = context.estimated_prompt_tokens + effective_completion
    reserved_cost = (
        ZERO
        if chat.mode is ChatMode.FREE
        else (
            None
            if pricing is None
            else estimate_max_cost(
                pricing, context.estimated_prompt_tokens, effective_completion
            )
        )
    )
    remaining_cost = (
        None
        if chat.mode is ChatMode.FREE
        or budget.cost_limit is None
        or reserved_cost is None
        else budget.cost_limit - budget.cost_used - budget.cost_reserved - reserved_cost
    )
    return RequestPlan(
        context,
        effective_completion,
        reserved_tokens,
        reserved_cost if chat.currency is Currency.USD else None,
        token_remaining - reserved_tokens,
        remaining_cost,
        reserved_cost=reserved_cost,
        currency=chat.currency,
    )


def estimate_draft(snapshot: PreparedEstimateSnapshot, text: str) -> DraftEstimate:
    """Calculate immediately from an already authorized local snapshot."""
    result = _estimate_draft(snapshot, text)
    return replace(
        result, currency=snapshot.chat.currency, provider_id=snapshot.chat.provider_id
    )


def _estimate_draft(snapshot: PreparedEstimateSnapshot, text: str) -> DraftEstimate:
    free_router = (
        snapshot.chat.provider_id is ProviderId.OPENROUTER
        and snapshot.chat.requested_model_id == FREE_ROUTER_MODEL.id
    )
    if not text.strip():
        return DraftEstimate(EstimateState.EMPTY, free_router=free_router)
    try:
        prompt_tokens = (
            REQUEST_OVERHEAD_TOKENS
            + snapshot.history.estimated_tokens
            + estimate_message_tokens(text.strip())
        )
    except UnicodeError:
        return DraftEstimate(
            EstimateState.UNAVAILABLE,
            error=ChatErrorType.INVALID_REQUEST,
            free_router=free_router,
        )
    model = FREE_ROUTER_MODEL if free_router else snapshot.model
    if (
        model is None
        or model.id != snapshot.chat.requested_model_id
        or model.provider_id != snapshot.chat.provider_id
        or model.currency != snapshot.chat.currency
    ):
        return DraftEstimate(
            EstimateState.UNAVAILABLE,
            prompt_tokens=prompt_tokens,
            error=ChatErrorType.MODEL_UNAVAILABLE,
            free_router=free_router,
        )
    if snapshot.budget is None:
        return DraftEstimate(
            EstimateState.UNAVAILABLE,
            prompt_tokens=prompt_tokens,
            error=ChatErrorType.LIMITS_NOT_CONFIGURED,
            free_router=free_router,
        )
    pricing = _estimate_pricing(snapshot.chat, model)
    try:
        plan = calculate_request_plan(
            chat=snapshot.chat,
            budget=snapshot.budget,
            model=model,
            history=snapshot.history,
            text=text,
            pricing=pricing,
            key_limit=snapshot.key_limit,
            apply_chat_cost_limit=False,
            allow_unknown_accounting=(
                snapshot.chat.provider_id is ProviderId.VSEGPT and pricing is None
            ),
        )
    except RequestPlanError as error:
        unavailable = error.error_type in {
            ChatErrorType.LIMITS_NOT_CONFIGURED,
            ChatErrorType.ACCOUNTING_UNKNOWN,
            ChatErrorType.MODEL_PRICE_UNSAFE,
        }
        return DraftEstimate(
            EstimateState.UNAVAILABLE if unavailable else EstimateState.OVER_LIMIT,
            prompt_tokens=prompt_tokens,
            error=error.error_type,
            free_router=free_router,
        )
    known_price = pricing is not None
    return DraftEstimate(
        EstimateState.READY if known_price else EstimateState.UNAVAILABLE,
        prompt_tokens=plan.context.estimated_prompt_tokens,
        max_completion_tokens=(
            plan.effective_max_completion_tokens if known_price else None
        ),
        cost_upper_usd=plan.reserved_cost_usd if known_price else None,
        cost_upper=plan.reserved_cost if known_price else None,
        error=None if known_price else ChatErrorType.MODEL_PRICE_UNSAFE,
        free_router=free_router,
    )


def _estimate_pricing(
    chat: Chat, model: CatalogModel
) -> tuple[PriceComponents, ...] | None:
    if (
        chat.provider_id is ProviderId.OPENROUTER
        and chat.requested_model_id == FREE_ROUTER_MODEL.id
    ):
        return (PriceComponents(),)
    if chat.mode is ChatMode.FREE:
        return model.all_pricing if is_free_model(model) else None
    if (
        model.pricing_unit is not PriceUnit.TOKEN
        or not model.pricing_is_complete
        or not all(item.valid for item in model.all_pricing)
    ):
        return None
    # Opt-in sends use the current price. A manual price-increase confirmation
    # also adopts that price. Otherwise preflight retains the confirmed schedule.
    if chat.paid_without_confirmation or model_price_increased(chat, model):
        return model.all_pricing
    try:
        return confirmed_pricing(chat)
    except ValueError:
        return None


def _cap_completion_by_cost(
    maximum: int,
    pricing: tuple[PriceComponents, ...],
    prompt_tokens: int,
    remaining_cost: Decimal,
    error_type: ChatErrorType,
) -> int:
    if estimate_max_cost(pricing, prompt_tokens, maximum) <= remaining_cost:
        return maximum
    if (
        estimate_max_cost(pricing, prompt_tokens, MIN_COMPLETION_TOKENS)
        > remaining_cost
    ):
        raise RequestPlanError(error_type)
    lower = MIN_COMPLETION_TOKENS
    upper = maximum - 1
    while lower < upper:
        candidate = (lower + upper + 1) // 2
        if estimate_max_cost(pricing, prompt_tokens, candidate) <= remaining_cost:
            lower = candidate
        else:
            upper = candidate - 1
    return lower
