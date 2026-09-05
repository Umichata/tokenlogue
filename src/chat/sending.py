"""Внутренний механизм preflight, отправки, retry и точного учёта."""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from api.chat_completions import ChatCompletionResult
from api.openrouter import KeyValidationResult
from auth.access import free_mode_allowed, paid_mode_allowed
from auth.contracts import KeyValidator
from auth.key_validation import interpret_key_validation
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.accounting import (
    AccountingStatus,
    BudgetReservation,
    BudgetState,
    ChatBudget,
    ModelPriceChange,
    TurnRecord,
    confirmed_pricing,
    confirmed_provider_price_limit,
    estimate_max_cost,
    model_price_change,
    model_price_increased,
)
from chat.context import (
    FREE_ROUTER_CONTEXT_LENGTH,
    REQUEST_OVERHEAD_TOKENS,
    ContextMessage,
    ContextWindowExceeded,
    build_conversation_context,
    estimate_message_tokens,
)
from chat.errors import ChatErrorType, safe_error_message
from chat.models import (
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    Message,
    PriceComponents,
    ProviderPriceLimit,
    is_free_model,
)
from chat.service import ChatService

MIN_COMPLETION_TOKENS = 16
TITLE_MAX_LENGTH = 60
ReservationCallback = Callable[[str], Awaitable[None] | None]


class CompletionClient(Protocol):
    async def complete(
        self,
        api_key: str,
        requested_model_id: str,
        messages: tuple[ContextMessage, ...],
        max_completion_tokens: int,
        provider_price_limit: ProviderPriceLimit,
    ) -> ChatCompletionResult: ...


class CatalogClient(Protocol):
    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...] | None: ...


class MessageRepository(Protocol):
    def get_chat_budget(self, chat_id: str) -> ChatBudget | None: ...

    def reserve_turn(
        self,
        reservation: BudgetReservation,
        *,
        content: str,
        requested_model_id: str,
        retry: bool,
        draft_revision: int | None = None,
    ) -> None: ...

    def mark_request_sent(self, turn_id: str, updated_at: datetime) -> None: ...

    def finalize_known_turn(
        self,
        turn_id: str,
        *,
        assistant_message_id: str,
        content: str | None,
        successful: bool,
        requested_model_id: str,
        actual_model_id: str | None,
        generation_id: str | None,
        finish_reason: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: Decimal,
        error_type: ChatErrorType | None,
        generated_title: str | None,
        updated_at: datetime,
    ) -> None: ...

    def release_local_failure(
        self,
        turn_id: str,
        error_type: ChatErrorType,
        updated_at: datetime,
    ) -> None: ...

    def release_known_failure(
        self,
        turn_id: str,
        error_type: ChatErrorType,
        updated_at: datetime,
    ) -> None: ...

    def mark_unknown_outcome(
        self,
        turn_id: str,
        *,
        assistant_message_id: str,
        partial_content: str | None,
        requested_model_id: str,
        actual_model_id: str | None,
        generation_id: str | None,
        finish_reason: str | None,
        error_type: ChatErrorType,
        updated_at: datetime,
    ) -> None: ...

    def get_turn(self, turn_id: str) -> TurnRecord | None: ...

    def get_user_message_for_turn(self, turn_id: str) -> Message | None: ...

    def update_price_snapshot(
        self,
        chat_id: str,
        *,
        prompt_price: Decimal,
        completion_price: Decimal,
        request_price: Decimal,
        internal_reasoning_price: Decimal,
        cache_read_price: Decimal,
        cache_write_price: Decimal,
        overrides_json: str,
        updated_at: datetime,
    ) -> None: ...


@dataclass(frozen=True)
class ChatPreflight:
    chat: Chat
    model: CatalogModel
    messages: tuple[ContextMessage, ...]
    estimated_prompt_tokens: int
    effective_max_completion_tokens: int
    reserved_tokens: int
    reserved_cost_usd: Decimal
    provider_price_limit: ProviderPriceLimit
    fresh_key_validity: KeyValidityState
    fresh_key_limit: KeyLimitInfo
    remaining_tokens_after_reservation: int
    remaining_cost_after_reservation: Decimal | None


@dataclass(frozen=True)
class MessageSendPreview:
    chat_id: str
    turn_id: str | None
    model_id: str | None
    model_name: str | None
    estimated_prompt_tokens: int | None
    max_completion_tokens: int | None
    reserved_tokens: int | None
    reserved_cost_usd: Decimal | None
    remaining_tokens_after_reservation: int | None
    remaining_cost_after_reservation: Decimal | None
    error_type: ChatErrorType | None
    safe_message: str | None
    price_change: ModelPriceChange | None = None
    key_validity_update: KeyValidityState | None = None
    key_limit_update: KeyLimitInfo | None = None

    @property
    def allowed(self) -> bool:
        return self.error_type is None


@dataclass(frozen=True)
class SendMessageResult:
    turn_id: str | None
    successful: bool
    truncated: bool
    content: str | None = field(repr=False)
    error_type: ChatErrorType | None
    safe_message: str | None
    retry_after: int | None = None
    accounting_unknown: bool = False
    key_validity_update: KeyValidityState | None = None
    key_limit_update: KeyLimitInfo | None = None
    price_change: ModelPriceChange | None = None


class _PreflightFailure(Exception):
    def __init__(
        self,
        error_type: ChatErrorType,
        *,
        price_change: ModelPriceChange | None = None,
        key_validity: KeyValidityState | None = None,
        key_limit: KeyLimitInfo | None = None,
    ) -> None:
        super().__init__(error_type.value)
        self.error_type = error_type
        self.price_change = price_change
        self.key_validity = key_validity
        self.key_limit = key_limit


class MessageSendingService:
    def __init__(
        self,
        chat_service: ChatService,
        message_repository: MessageRepository,
        completion_client: CompletionClient,
        catalog_client: CatalogClient,
        key_validator: KeyValidator,
        *,
        on_key_validity_changed: Callable[[KeyValidityState], None] | None = None,
        now: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self._chat_service = chat_service
        self._messages = message_repository
        self._completion_client = completion_client
        self._catalog_client = catalog_client
        self._key_validator = key_validator
        self._on_key_validity_changed = on_key_validity_changed
        self._now = now or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory
        self._chat_locks: dict[str, asyncio.Lock] = {}

    async def preview_message(
        self,
        chat_id: str,
        text: str,
        *,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
    ) -> MessageSendPreview:
        if not _valid_identifier(chat_id) or not isinstance(text, str):
            return _preview_failure(
                chat_id if isinstance(chat_id, str) else "",
                ChatErrorType.INVALID_REQUEST,
            )
        if not isinstance(api_key, str):
            return _preview_failure(chat_id, ChatErrorType.KEY_NOT_VALID)
        normalized = text.strip()
        if not normalized:
            return _preview_failure(chat_id, ChatErrorType.INVALID_REQUEST)
        if not api_key.strip():
            return _preview_failure(chat_id, ChatErrorType.KEY_NOT_VALID)
        lock = self._chat_locks.setdefault(chat_id, asyncio.Lock())
        if lock.locked():
            return _preview_failure(chat_id, ChatErrorType.TURN_ALREADY_ACTIVE)
        try:
            preflight = await self._preflight(
                chat_id,
                normalized,
                api_key=api_key,
                key_validity=key_validity,
                key_limit=key_limit,
                paid_confirmed=True,
            )
        except _PreflightFailure as error:
            return _preview_failure(
                chat_id,
                error.error_type,
                price_change=error.price_change,
                key_validity=error.key_validity,
                key_limit=error.key_limit,
            )
        return _preview_from_preflight(preflight)

    async def preview_failed_turn(
        self,
        turn_id: str,
        *,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
    ) -> MessageSendPreview:
        if not _valid_identifier(turn_id):
            return _preview_failure(
                "",
                ChatErrorType.TURN_NOT_RETRYABLE,
                turn_id=turn_id if isinstance(turn_id, str) else None,
            )
        turn = await asyncio.to_thread(self._messages.get_turn, turn_id)
        user_message = await asyncio.to_thread(
            self._messages.get_user_message_for_turn,
            turn_id,
        )
        if (
            turn is None
            or user_message is None
            or turn.status.value != "failed"
            or turn.accounting_status is not AccountingStatus.RELEASED
        ):
            return _preview_failure(
                turn.chat_id if turn is not None else "",
                ChatErrorType.TURN_NOT_RETRYABLE,
                turn_id=turn_id,
            )
        preview = await self.preview_message(
            turn.chat_id,
            user_message.content,
            api_key=api_key,
            key_validity=key_validity,
            key_limit=key_limit,
        )
        return MessageSendPreview(
            chat_id=preview.chat_id,
            turn_id=turn_id,
            model_id=preview.model_id,
            model_name=preview.model_name,
            estimated_prompt_tokens=preview.estimated_prompt_tokens,
            max_completion_tokens=preview.max_completion_tokens,
            reserved_tokens=preview.reserved_tokens,
            reserved_cost_usd=preview.reserved_cost_usd,
            remaining_tokens_after_reservation=(
                preview.remaining_tokens_after_reservation
            ),
            remaining_cost_after_reservation=preview.remaining_cost_after_reservation,
            error_type=preview.error_type,
            safe_message=preview.safe_message,
            price_change=preview.price_change,
            key_validity_update=preview.key_validity_update,
            key_limit_update=preview.key_limit_update,
        )

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        paid_confirmed: bool = False,
        on_reserved: ReservationCallback | None = None,
        draft_revision: int | None = None,
    ) -> SendMessageResult:
        if (
            not _valid_identifier(chat_id)
            or not isinstance(text, str)
            or not isinstance(paid_confirmed, bool)
            or (
                draft_revision is not None
                and (
                    isinstance(draft_revision, bool)
                    or not isinstance(draft_revision, int)
                    or draft_revision < 0
                )
            )
        ):
            return _local_failure(ChatErrorType.INVALID_REQUEST)
        if not isinstance(api_key, str):
            return _local_failure(ChatErrorType.KEY_NOT_VALID)
        normalized = text.strip()
        if not normalized:
            return _local_failure(ChatErrorType.INVALID_REQUEST)
        if not api_key.strip():
            return _local_failure(ChatErrorType.KEY_NOT_VALID)
        lock = self._chat_locks.setdefault(chat_id, asyncio.Lock())
        if lock.locked():
            return _local_failure(ChatErrorType.TURN_ALREADY_ACTIVE)
        async with lock:
            return await self._send_locked(
                chat_id,
                normalized,
                api_key=api_key,
                key_validity=key_validity,
                key_limit=key_limit,
                turn_id=str(self._uuid_factory()),
                user_message_id=str(self._uuid_factory()),
                retry=False,
                paid_confirmed=paid_confirmed,
                on_reserved=on_reserved,
                draft_revision=draft_revision,
            )

    async def retry_failed_turn(
        self,
        turn_id: str,
        *,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        paid_confirmed: bool = False,
        on_reserved: ReservationCallback | None = None,
    ) -> SendMessageResult:
        if not _valid_identifier(turn_id) or not isinstance(paid_confirmed, bool):
            return _local_failure(ChatErrorType.TURN_NOT_RETRYABLE)
        if not isinstance(api_key, str):
            return _local_failure(ChatErrorType.KEY_NOT_VALID, turn_id=turn_id)
        if not api_key.strip():
            return _local_failure(ChatErrorType.KEY_NOT_VALID, turn_id=turn_id)
        turn = await asyncio.to_thread(self._messages.get_turn, turn_id)
        user_message = await asyncio.to_thread(
            self._messages.get_user_message_for_turn,
            turn_id,
        )
        if (
            turn is None
            or user_message is None
            or turn.status.value != "failed"
            or turn.accounting_status is not AccountingStatus.RELEASED
        ):
            return _local_failure(ChatErrorType.TURN_NOT_RETRYABLE, turn_id=turn_id)
        lock = self._chat_locks.setdefault(turn.chat_id, asyncio.Lock())
        if lock.locked():
            return _local_failure(
                ChatErrorType.TURN_ALREADY_ACTIVE,
                turn_id=turn_id,
            )
        async with lock:
            return await self._send_locked(
                turn.chat_id,
                user_message.content,
                api_key=api_key,
                key_validity=key_validity,
                key_limit=key_limit,
                turn_id=turn_id,
                user_message_id=user_message.id,
                retry=True,
                paid_confirmed=paid_confirmed,
                on_reserved=on_reserved,
            )

    async def reconfirm_model_price(
        self,
        chat_id: str,
        *,
        api_key: str,
        confirmed: bool,
    ) -> None:
        if not _valid_identifier(chat_id):
            raise ValueError("Некорректный идентификатор чата")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Ключ сессии отсутствует")
        if confirmed is not True:
            raise ValueError("Изменение цены требует явного подтверждения")
        chat = await self._chat_service.get_chat(chat_id)
        if chat is None:
            raise KeyError("Чат не найден")
        models = await self._catalog_client.fetch_models(api_key)
        current = _find_model(models, chat.requested_model_id)
        if current is None:
            raise ValueError("Модель отсутствует в текущем каталоге")
        if not current.pricing_is_complete:
            raise ValueError("Цена модели не может быть безопасно подтверждена")
        await asyncio.to_thread(
            self._messages.update_price_snapshot,
            chat_id,
            prompt_price=current.prompt_price_per_token,
            completion_price=current.completion_price_per_token,
            request_price=current.request_price,
            internal_reasoning_price=current.internal_reasoning_price_per_token,
            cache_read_price=current.input_cache_read_price_per_token,
            cache_write_price=current.input_cache_write_price_per_token,
            overrides_json=_pricing_overrides_json(current.pricing_overrides),
            updated_at=_as_utc(self._now()),
        )

    async def _send_locked(
        self,
        chat_id: str,
        text: str,
        *,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        turn_id: str,
        user_message_id: str,
        retry: bool,
        paid_confirmed: bool,
        on_reserved: ReservationCallback | None,
        draft_revision: int | None = None,
    ) -> SendMessageResult:
        try:
            preflight = await self._preflight(
                chat_id,
                text,
                api_key=api_key,
                key_validity=key_validity,
                key_limit=key_limit,
                paid_confirmed=paid_confirmed,
            )
        except _PreflightFailure as error:
            return _local_failure(
                error.error_type,
                turn_id=turn_id if retry else None,
                price_change=error.price_change,
                key_validity=error.key_validity,
                key_limit=error.key_limit,
            )

        timestamp = _as_utc(self._now())
        reservation = BudgetReservation(
            turn_id=turn_id,
            user_message_id=user_message_id,
            chat_id=chat_id,
            reserved_tokens=preflight.reserved_tokens,
            reserved_cost_usd=preflight.reserved_cost_usd,
            created_at=timestamp,
        )
        reservation_task = asyncio.create_task(
            asyncio.to_thread(
                self._messages.reserve_turn,
                reservation,
                content=text,
                requested_model_id=preflight.chat.requested_model_id,
                retry=retry,
                draft_revision=draft_revision,
            )
        )
        try:
            await asyncio.shield(reservation_task)
        except asyncio.CancelledError:
            reserved = False
            try:
                await reservation_task
                reserved = True
            except Exception:
                pass
            if reserved:
                await self._release_before_send(turn_id, ChatErrorType.INTERRUPTED)
            raise
        except Exception:
            return _local_failure(
                ChatErrorType.TURN_ALREADY_ACTIVE,
                turn_id=turn_id if retry else None,
            )

        mark_sent_task = asyncio.create_task(
            asyncio.to_thread(
                self._messages.mark_request_sent,
                turn_id,
                _as_utc(self._now()),
            )
        )
        try:
            await asyncio.shield(mark_sent_task)
        except asyncio.CancelledError:
            marked_sent = False
            try:
                await mark_sent_task
                marked_sent = True
            except Exception:
                pass
            await self._release_without_http(
                turn_id,
                ChatErrorType.INTERRUPTED,
                request_marked=marked_sent,
            )
            raise
        except Exception:
            await self._release_before_send(turn_id, ChatErrorType.INVALID_REQUEST)
            return _local_failure(ChatErrorType.INVALID_REQUEST, turn_id=turn_id)

        if on_reserved is not None:
            try:
                callback_result = on_reserved(turn_id)
                if inspect.isawaitable(callback_result):
                    await callback_result
            except asyncio.CancelledError:
                await self._release_without_http(
                    turn_id,
                    ChatErrorType.INTERRUPTED,
                    request_marked=True,
                )
                raise
            except Exception:
                pass

        try:
            result = await self._completion_client.complete(
                api_key,
                preflight.chat.requested_model_id,
                preflight.messages,
                preflight.effective_max_completion_tokens,
                preflight.provider_price_limit,
            )
        except asyncio.CancelledError:
            await self._mark_cancelled_unknown(turn_id, preflight)
            raise
        except Exception:
            result = ChatCompletionResult(
                content=None,
                generation_id=None,
                requested_model_id=preflight.chat.requested_model_id,
                actual_model_id=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                cost_usd=None,
                error_type=ChatErrorType.NETWORK_ERROR,
                accounting_unknown=True,
            )
        try:
            return await self._record_result(turn_id, text, preflight, result)
        except Exception:
            await self._mark_cancelled_unknown(turn_id, preflight)
            return SendMessageResult(
                turn_id=turn_id,
                successful=False,
                truncated=False,
                content=None,
                error_type=ChatErrorType.ACCOUNTING_UNKNOWN,
                safe_message=safe_error_message(ChatErrorType.ACCOUNTING_UNKNOWN),
                accounting_unknown=True,
            )

    async def _preflight(
        self,
        chat_id: str,
        text: str,
        *,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        paid_confirmed: bool,
    ) -> ChatPreflight:
        chat = await self._chat_service.get_chat(chat_id)
        if chat is None:
            raise _PreflightFailure(ChatErrorType.INVALID_REQUEST)
        budget = await asyncio.to_thread(self._messages.get_chat_budget, chat_id)
        if budget is None or not budget.limits_configured:
            raise _PreflightFailure(ChatErrorType.LIMITS_NOT_CONFIGURED)
        if budget.state is BudgetState.ACCOUNTING_UNKNOWN:
            raise _PreflightFailure(ChatErrorType.ACCOUNTING_UNKNOWN)
        if budget.token_limit is None or budget.max_completion_tokens is None:
            raise _PreflightFailure(ChatErrorType.LIMITS_NOT_CONFIGURED)
        if budget.state is BudgetState.EXHAUSTED:
            if budget.total_tokens_used + budget.reserved_tokens >= budget.token_limit:
                raise _PreflightFailure(ChatErrorType.TOKEN_LIMIT_EXCEEDED)
            raise _PreflightFailure(ChatErrorType.COST_LIMIT_EXCEEDED)

        if chat.mode is ChatMode.PAID and not paid_confirmed:
            raise _PreflightFailure(ChatErrorType.PAID_CONFIRMATION_REQUIRED)

        current_key_validity = key_validity
        current_key_limit = key_limit
        if chat.mode is ChatMode.PAID:
            if not paid_mode_allowed(current_key_validity, current_key_limit):
                raise _PreflightFailure(ChatErrorType.KEY_NOT_VALID)
            validation: KeyValidationResult
            try:
                validation = await self._key_validator.validate_key(api_key)
            except Exception:
                raise _PreflightFailure(ChatErrorType.KEY_NOT_VALID) from None
            current_key_validity, current_key_limit = interpret_key_validation(
                validation
            )
            self._publish_key_validity(current_key_validity)
            if not paid_mode_allowed(current_key_validity, current_key_limit):
                raise _PreflightFailure(
                    ChatErrorType.KEY_NOT_VALID,
                    key_validity=current_key_validity,
                    key_limit=current_key_limit,
                )
        elif not free_mode_allowed(current_key_validity):
            raise _PreflightFailure(ChatErrorType.KEY_NOT_VALID)

        model = await self._resolve_current_model(chat, api_key)
        pricing: tuple[PriceComponents, ...]
        if chat.requested_model_id == FREE_ROUTER_MODEL.id:
            pricing = (PriceComponents(),)
            price_limit = ProviderPriceLimit.zero()
        elif chat.mode is ChatMode.FREE:
            if not is_free_model(model):
                raise _PreflightFailure(ChatErrorType.MODEL_PRICE_UNSAFE)
            pricing = model.all_pricing
            price_limit = ProviderPriceLimit.zero()
        else:
            if not model.pricing_is_complete:
                raise _PreflightFailure(ChatErrorType.MODEL_PRICE_UNSAFE)
            if model_price_increased(chat, model):
                raise _PreflightFailure(
                    ChatErrorType.PRICE_RECONFIRMATION_REQUIRED,
                    price_change=model_price_change(chat, model),
                    key_validity=current_key_validity,
                    key_limit=current_key_limit,
                )
            try:
                pricing = confirmed_pricing(chat)
                price_limit = confirmed_provider_price_limit(chat)
            except ValueError:
                raise _PreflightFailure(
                    ChatErrorType.PRICE_RECONFIRMATION_REQUIRED
                ) from None

        context_length = (
            FREE_ROUTER_CONTEXT_LENGTH
            if chat.requested_model_id == FREE_ROUTER_MODEL.id
            else model.context_length
        )
        if context_length is None or context_length <= MIN_COMPLETION_TOKENS:
            raise _PreflightFailure(ChatErrorType.CONTEXT_LENGTH_EXCEEDED)
        provider_completion_limit = (
            model.provider_max_completion_tokens or budget.max_completion_tokens
        )
        completion_cap = min(
            budget.max_completion_tokens,
            provider_completion_limit,
        )
        if completion_cap < MIN_COMPLETION_TOKENS:
            raise _PreflightFailure(ChatErrorType.MAX_TOKENS_EXCEEDED)
        token_remaining = (
            budget.token_limit - budget.total_tokens_used - budget.reserved_tokens
        )
        minimum_prompt = REQUEST_OVERHEAD_TOKENS + estimate_message_tokens(text)
        completion_cap = min(completion_cap, token_remaining - minimum_prompt)
        if completion_cap < MIN_COMPLETION_TOKENS:
            raise _PreflightFailure(ChatErrorType.TOKEN_LIMIT_EXCEEDED)
        history = await self._chat_service.list_messages(chat_id)
        try:
            context = build_conversation_context(
                history,
                text,
                context_length=context_length,
                completion_reserve=completion_cap,
                require_full_history=True,
            )
        except ContextWindowExceeded:
            raise _PreflightFailure(ChatErrorType.CONTEXT_LENGTH_EXCEEDED) from None
        effective_completion = min(
            completion_cap,
            token_remaining - context.estimated_prompt_tokens,
            context_length - context.estimated_prompt_tokens,
        )
        if effective_completion < MIN_COMPLETION_TOKENS:
            raise _PreflightFailure(ChatErrorType.TOKEN_LIMIT_EXCEEDED)
        reserved_tokens = context.estimated_prompt_tokens + effective_completion
        reserved_cost = (
            Decimal("0")
            if chat.mode is ChatMode.FREE
            else estimate_max_cost(
                pricing,
                context.estimated_prompt_tokens,
                effective_completion,
            )
        )
        if chat.mode is ChatMode.PAID:
            if budget.cost_limit_usd is None:
                raise _PreflightFailure(ChatErrorType.LIMITS_NOT_CONFIGURED)
            cost_remaining = (
                budget.cost_limit_usd - budget.cost_used_usd - budget.cost_reserved_usd
            )
            if reserved_cost > cost_remaining:
                raise _PreflightFailure(ChatErrorType.COST_LIMIT_EXCEEDED)
            if (
                current_key_limit.state is KeyLimitState.AVAILABLE
                and current_key_limit.remaining is not None
                and reserved_cost > current_key_limit.remaining
            ):
                raise _PreflightFailure(ChatErrorType.KEY_LIMIT_EXCEEDED)
        remaining_cost = (
            None
            if chat.mode is ChatMode.FREE or budget.cost_limit_usd is None
            else budget.cost_limit_usd
            - budget.cost_used_usd
            - budget.cost_reserved_usd
            - reserved_cost
        )
        return ChatPreflight(
            chat=chat,
            model=model,
            messages=context.messages,
            estimated_prompt_tokens=context.estimated_prompt_tokens,
            effective_max_completion_tokens=effective_completion,
            reserved_tokens=reserved_tokens,
            reserved_cost_usd=reserved_cost,
            provider_price_limit=price_limit,
            fresh_key_validity=current_key_validity,
            fresh_key_limit=current_key_limit,
            remaining_tokens_after_reservation=token_remaining - reserved_tokens,
            remaining_cost_after_reservation=remaining_cost,
        )

    async def _resolve_current_model(
        self,
        chat: Chat,
        api_key: str,
    ) -> CatalogModel:
        if chat.requested_model_id == FREE_ROUTER_MODEL.id:
            return FREE_ROUTER_MODEL
        models = await self._catalog_client.fetch_models(api_key)
        model = _find_model(models, chat.requested_model_id)
        if model is None:
            raise _PreflightFailure(ChatErrorType.MODEL_UNAVAILABLE)
        return model

    async def _record_result(
        self,
        turn_id: str,
        user_text: str,
        preflight: ChatPreflight,
        result: ChatCompletionResult,
    ) -> SendMessageResult:
        timestamp = _as_utc(self._now())
        if result.error_type is ChatErrorType.AUTHENTICATION:
            self._publish_key_validity(KeyValidityState.INVALID)
        if result.has_complete_usage:
            assert result.prompt_tokens is not None
            assert result.completion_tokens is not None
            assert result.total_tokens is not None
            assert result.cost_usd is not None
            await asyncio.to_thread(
                self._messages.finalize_known_turn,
                turn_id,
                assistant_message_id=str(self._uuid_factory()),
                content=result.content,
                successful=result.successful,
                requested_model_id=preflight.chat.requested_model_id,
                actual_model_id=result.actual_model_id,
                generation_id=result.generation_id,
                finish_reason=result.finish_reason,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                cost_usd=result.cost_usd,
                error_type=result.error_type,
                generated_title=(
                    _title_from_message(user_text) if result.successful else None
                ),
                updated_at=timestamp,
            )
        elif result.accounting_unknown:
            await asyncio.to_thread(
                self._messages.mark_unknown_outcome,
                turn_id,
                assistant_message_id=str(self._uuid_factory()),
                partial_content=result.content,
                requested_model_id=preflight.chat.requested_model_id,
                actual_model_id=result.actual_model_id,
                generation_id=result.generation_id,
                finish_reason=result.finish_reason,
                error_type=result.error_type or ChatErrorType.ACCOUNTING_UNKNOWN,
                updated_at=timestamp,
            )
        else:
            await asyncio.to_thread(
                self._messages.release_known_failure,
                turn_id,
                result.error_type or ChatErrorType.MALFORMED_RESPONSE,
                timestamp,
            )
        return SendMessageResult(
            turn_id=turn_id,
            successful=result.successful and result.has_complete_usage,
            truncated=result.truncated,
            content=result.content,
            error_type=result.error_type,
            safe_message=(
                safe_error_message(result.error_type)
                if result.error_type is not None
                else (
                    safe_error_message(ChatErrorType.ACCOUNTING_UNKNOWN)
                    if result.accounting_unknown
                    else None
                )
            ),
            retry_after=result.retry_after,
            accounting_unknown=result.accounting_unknown,
            key_validity_update=(
                KeyValidityState.INVALID
                if result.error_type is ChatErrorType.AUTHENTICATION
                else preflight.fresh_key_validity
            ),
            key_limit_update=(
                KeyLimitInfo.unknown()
                if result.error_type is ChatErrorType.AUTHENTICATION
                else preflight.fresh_key_limit
            ),
        )

    async def _release_before_send(
        self,
        turn_id: str,
        error_type: ChatErrorType,
    ) -> None:
        try:
            await asyncio.shield(
                asyncio.to_thread(
                    self._messages.release_local_failure,
                    turn_id,
                    error_type,
                    _as_utc(self._now()),
                )
            )
        except Exception:
            return

    async def _release_without_http(
        self,
        turn_id: str,
        error_type: ChatErrorType,
        *,
        request_marked: bool,
    ) -> None:
        operation = (
            self._messages.release_known_failure
            if request_marked
            else self._messages.release_local_failure
        )
        try:
            await asyncio.shield(
                asyncio.to_thread(
                    operation,
                    turn_id,
                    error_type,
                    _as_utc(self._now()),
                )
            )
        except Exception:
            return

    async def _mark_cancelled_unknown(
        self,
        turn_id: str,
        preflight: ChatPreflight,
    ) -> None:
        try:
            await asyncio.shield(
                asyncio.to_thread(
                    self._messages.mark_unknown_outcome,
                    turn_id,
                    assistant_message_id=str(self._uuid_factory()),
                    partial_content=None,
                    requested_model_id=preflight.chat.requested_model_id,
                    actual_model_id=None,
                    generation_id=None,
                    finish_reason=None,
                    error_type=ChatErrorType.ACCOUNTING_UNKNOWN,
                    updated_at=_as_utc(self._now()),
                )
            )
        except Exception:
            return

    def _publish_key_validity(self, validity: KeyValidityState) -> None:
        if self._on_key_validity_changed is not None:
            self._on_key_validity_changed(validity)


def _find_model(
    models: tuple[CatalogModel, ...] | None,
    model_id: str,
) -> CatalogModel | None:
    if models is None:
        return None
    return next((model for model in models if model.id == model_id), None)


def _title_from_message(message: str) -> str:
    normalized = " ".join(message.split())
    return normalized[:TITLE_MAX_LENGTH].rstrip()


def _pricing_overrides_json(overrides: tuple[PriceComponents, ...]) -> str:
    return json.dumps(
        [
            {
                "prompt": str(item.prompt),
                "completion": str(item.completion),
                "request": str(item.request),
                "internal_reasoning": str(item.internal_reasoning),
                "input_cache_read": str(item.input_cache_read),
                "input_cache_write": str(item.input_cache_write),
            }
            for item in overrides
        ],
        separators=(",", ":"),
        sort_keys=True,
    )


def _local_failure(
    error_type: ChatErrorType,
    *,
    turn_id: str | None = None,
    price_change: ModelPriceChange | None = None,
    key_validity: KeyValidityState | None = None,
    key_limit: KeyLimitInfo | None = None,
) -> SendMessageResult:
    return SendMessageResult(
        turn_id=turn_id,
        successful=False,
        truncated=False,
        content=None,
        error_type=error_type,
        safe_message=safe_error_message(error_type),
        key_validity_update=key_validity,
        key_limit_update=key_limit,
        price_change=price_change,
    )


def _preview_from_preflight(preflight: ChatPreflight) -> MessageSendPreview:
    return MessageSendPreview(
        chat_id=preflight.chat.id,
        turn_id=None,
        model_id=preflight.chat.requested_model_id,
        model_name=preflight.chat.requested_model_name,
        estimated_prompt_tokens=preflight.estimated_prompt_tokens,
        max_completion_tokens=preflight.effective_max_completion_tokens,
        reserved_tokens=preflight.reserved_tokens,
        reserved_cost_usd=preflight.reserved_cost_usd,
        remaining_tokens_after_reservation=(
            preflight.remaining_tokens_after_reservation
        ),
        remaining_cost_after_reservation=(preflight.remaining_cost_after_reservation),
        error_type=None,
        safe_message=None,
        key_validity_update=preflight.fresh_key_validity,
        key_limit_update=preflight.fresh_key_limit,
    )


def _preview_failure(
    chat_id: str,
    error_type: ChatErrorType,
    *,
    turn_id: str | None = None,
    price_change: ModelPriceChange | None = None,
    key_validity: KeyValidityState | None = None,
    key_limit: KeyLimitInfo | None = None,
) -> MessageSendPreview:
    return MessageSendPreview(
        chat_id=chat_id,
        turn_id=turn_id,
        model_id=None,
        model_name=None,
        estimated_prompt_tokens=None,
        max_completion_tokens=None,
        reserved_tokens=None,
        reserved_cost_usd=None,
        remaining_tokens_after_reservation=None,
        remaining_cost_after_reservation=None,
        error_type=error_type,
        safe_message=safe_error_message(error_type),
        price_change=price_change,
        key_validity_update=key_validity,
        key_limit_update=key_limit,
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
