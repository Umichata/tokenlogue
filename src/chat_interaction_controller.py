"""Состояние и сценарии активного чата без зависимости от Flet."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from auth.models import KeyLimitInfo, KeyValidityState
from chat.accounting import (
    ChatBudget,
    ChatBudgetService,
    ChatLimitConfiguration,
    RemainingBudget,
    TurnRecord,
    calculate_remaining_budget,
)
from chat.errors import ChatErrorType, safe_error_message
from chat.models import Chat, Message
from chat.sending import MessageSendingService, MessageSendPreview, SendMessageResult
from chat.service import ChatService


@dataclass(frozen=True)
class ChatSessionContext:
    api_key: str = field(repr=False)
    key_validity: KeyValidityState
    key_limit: KeyLimitInfo


@dataclass(frozen=True)
class ActiveChatState:
    chat: Chat
    messages: tuple[Message, ...]
    turns: tuple[TurnRecord, ...]
    budget: ChatBudget
    remaining: RemainingBudget
    sending: bool = False


@dataclass(frozen=True)
class InteractionOutcome:
    applied: bool
    result: SendMessageResult
    state: ActiveChatState | None


SessionProvider = Callable[[], ChatSessionContext | None]
KeyStateCallback = Callable[[KeyValidityState, KeyLimitInfo], None]
ReservationCallback = Callable[[str], Awaitable[None]]


class ChatInteractionController:
    """Координирует один активный сетевой запрос на всё приложение."""

    def __init__(
        self,
        chat_service: ChatService,
        budget_service: ChatBudgetService,
        sending_service: MessageSendingService,
        *,
        session_provider: SessionProvider,
        on_key_state_changed: KeyStateCallback,
    ) -> None:
        self._chat_service = chat_service
        self._budget_service = budget_service
        self._sending_service = sending_service
        self._session_provider = session_provider
        self._on_key_state_changed = on_key_state_changed
        self._operation_lock = asyncio.Lock()
        self._active_chat_id: str | None = None
        self._generation = 0
        self._session_generation = 0
        self._active = False

    @property
    def busy(self) -> bool:
        return self._operation_lock.locked()

    @property
    def active_chat_id(self) -> str | None:
        return self._active_chat_id

    def activate(self) -> None:
        self._generation += 1
        self._session_generation += 1
        self._active = True
        self._active_chat_id = None

    def deactivate(self) -> None:
        self._generation += 1
        self._session_generation += 1
        self._active = False
        self._active_chat_id = None

    async def select_chat(self, chat_id: str) -> ActiveChatState:
        _require_identifier(chat_id, "чата")
        if not self._active:
            raise RuntimeError("Чат-сессия неактивна")
        self._generation += 1
        self._active_chat_id = chat_id
        return await self.load_state(chat_id)

    async def load_state(self, chat_id: str) -> ActiveChatState:
        _require_identifier(chat_id, "чата")
        chat, messages, budget, turns = await asyncio.gather(
            self._chat_service.get_chat(chat_id),
            self._chat_service.list_messages(chat_id),
            self._budget_service.get_chat_budget(chat_id),
            self._budget_service.list_chat_turns(chat_id),
        )
        if chat is None:
            raise KeyError("Чат не найден")
        return ActiveChatState(
            chat=chat,
            messages=tuple(messages),
            turns=tuple(turns),
            budget=budget,
            remaining=calculate_remaining_budget(budget),
            sending=self.busy,
        )

    async def preview_message(self, chat_id: str, text: str) -> MessageSendPreview:
        if not _is_identifier(chat_id) or not isinstance(text, str):
            return _invalid_preview(chat_id if isinstance(chat_id, str) else "")
        if self._operation_lock.locked():
            return _busy_preview(chat_id)
        session = self._session_provider()
        if session is None:
            return _missing_session_preview(chat_id)
        generation = self._generation
        async with self._operation_lock:
            preview = await self._sending_service.preview_message(
                chat_id,
                text,
                api_key=session.api_key,
                key_validity=session.key_validity,
                key_limit=session.key_limit,
            )
        if not self._matches(chat_id, generation):
            return _stale_preview(chat_id)
        self._apply_key_state(preview.key_validity_update, preview.key_limit_update)
        return preview

    async def preview_retry(self, turn_id: str) -> MessageSendPreview:
        if not _is_identifier(turn_id):
            return _invalid_preview("", turn_id=None)
        if self._operation_lock.locked():
            return _busy_preview(self._active_chat_id or "", turn_id=turn_id)
        session = self._session_provider()
        if session is None:
            return _missing_session_preview(self._active_chat_id or "", turn_id=turn_id)
        generation = self._generation
        chat_id = self._active_chat_id
        async with self._operation_lock:
            preview = await self._sending_service.preview_failed_turn(
                turn_id,
                api_key=session.api_key,
                key_validity=session.key_validity,
                key_limit=session.key_limit,
            )
        if chat_id is None or not self._matches(chat_id, generation):
            return _stale_preview(preview.chat_id, turn_id=turn_id)
        self._apply_key_state(preview.key_validity_update, preview.key_limit_update)
        return preview

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        paid_confirmed: bool,
        on_reserved: ReservationCallback | None = None,
        draft_revision: int | None = None,
    ) -> InteractionOutcome:
        if (
            not _is_identifier(chat_id)
            or not isinstance(text, str)
            or not isinstance(paid_confirmed, bool)
        ):
            return InteractionOutcome(False, _invalid_result(), None)
        if self._operation_lock.locked():
            return InteractionOutcome(False, _busy_result(), None)
        session = self._session_provider()
        if session is None:
            return InteractionOutcome(False, _missing_session_result(), None)
        generation = self._generation
        session_generation = self._session_generation

        async def reserved(turn_id: str) -> None:
            # Reservation state belongs to the originating chat, even after
            # navigation; only an ended authentication session invalidates it.
            if (
                on_reserved is not None
                and self._active
                and self._session_generation == session_generation
                and self._session_provider() is not None
            ):
                await on_reserved(turn_id)

        async with self._operation_lock:
            result = await self._sending_service.send_message(
                chat_id,
                text,
                api_key=session.api_key,
                key_validity=session.key_validity,
                key_limit=session.key_limit,
                paid_confirmed=paid_confirmed,
                on_reserved=reserved,
                draft_revision=draft_revision,
            )
        if not self._matches(chat_id, generation):
            return InteractionOutcome(False, result, None)
        self._apply_key_state(result.key_validity_update, result.key_limit_update)
        return InteractionOutcome(True, result, await self.load_state(chat_id))

    async def retry_turn(
        self,
        chat_id: str,
        turn_id: str,
        *,
        paid_confirmed: bool,
        on_reserved: ReservationCallback | None = None,
    ) -> InteractionOutcome:
        if (
            not _is_identifier(chat_id)
            or not _is_identifier(turn_id)
            or not isinstance(paid_confirmed, bool)
        ):
            return InteractionOutcome(False, _invalid_result(), None)
        if self._operation_lock.locked():
            return InteractionOutcome(False, _busy_result(turn_id), None)
        session = self._session_provider()
        if session is None:
            return InteractionOutcome(False, _missing_session_result(turn_id), None)
        generation = self._generation

        async def reserved(reserved_turn_id: str) -> None:
            if on_reserved is not None and self._matches(chat_id, generation):
                await on_reserved(reserved_turn_id)

        async with self._operation_lock:
            result = await self._sending_service.retry_failed_turn(
                turn_id,
                api_key=session.api_key,
                key_validity=session.key_validity,
                key_limit=session.key_limit,
                paid_confirmed=paid_confirmed,
                on_reserved=reserved,
            )
        if not self._matches(chat_id, generation):
            return InteractionOutcome(False, result, None)
        self._apply_key_state(result.key_validity_update, result.key_limit_update)
        return InteractionOutcome(True, result, await self.load_state(chat_id))

    async def save_limits(
        self,
        chat_id: str,
        configuration: ChatLimitConfiguration,
        *,
        cost_increase_confirmed: bool,
    ) -> ActiveChatState:
        _require_identifier(chat_id, "чата")
        if not isinstance(configuration, ChatLimitConfiguration):
            raise ValueError("Некорректная конфигурация лимитов")
        if not isinstance(cost_increase_confirmed, bool):
            raise ValueError("Некорректное подтверждение денежного лимита")
        if self._operation_lock.locked():
            raise RuntimeError("Нельзя менять лимиты во время отправки")
        generation = self._generation
        async with self._operation_lock:
            current = await self._budget_service.get_chat_budget(chat_id)
            operation = (
                self._budget_service.update_chat_limits
                if current.limits_configured
                else self._budget_service.configure_chat_limits
            )
            await operation(
                chat_id,
                token_limit=configuration.token_limit,
                max_completion_tokens=configuration.max_completion_tokens,
                cost_limit_usd=configuration.cost_limit_usd,
                cost_increase_confirmed=cost_increase_confirmed,
            )
        if not self._matches(chat_id, generation):
            raise RuntimeError("Активный чат изменился")
        return await self.load_state(chat_id)

    async def release_unknown(
        self,
        chat_id: str,
        turn_id: str,
        *,
        confirmed: bool,
    ) -> ActiveChatState:
        _require_identifier(chat_id, "чата")
        _require_identifier(turn_id, "попытки")
        if confirmed is not True:
            raise ValueError("Снятие неизвестного резерва требует подтверждения")
        if self._operation_lock.locked():
            raise RuntimeError("Другая операция ещё выполняется")
        generation = self._generation
        async with self._operation_lock:
            await self._budget_service.release_unknown_reservation(
                turn_id,
                confirmed=confirmed,
            )
        if not self._matches(chat_id, generation):
            raise RuntimeError("Активный чат изменился")
        return await self.load_state(chat_id)

    async def reconfirm_price(self, chat_id: str, *, confirmed: bool) -> None:
        _require_identifier(chat_id, "чата")
        if confirmed is not True:
            raise ValueError("Изменение цены требует явного подтверждения")
        if self._operation_lock.locked():
            raise RuntimeError("Другая операция ещё выполняется")
        session = self._session_provider()
        if session is None:
            raise RuntimeError("Чат-сессия неактивна")
        generation = self._generation
        async with self._operation_lock:
            await self._sending_service.reconfirm_model_price(
                chat_id,
                api_key=session.api_key,
                confirmed=confirmed,
            )
        if not self._matches(chat_id, generation):
            raise RuntimeError("Активный чат изменился")

    def _matches(self, chat_id: str, generation: int) -> bool:
        return (
            self._active
            and self._active_chat_id == chat_id
            and self._generation == generation
            and self._session_provider() is not None
        )

    def _apply_key_state(
        self,
        validity: KeyValidityState | None,
        limit: KeyLimitInfo | None,
    ) -> None:
        if validity is not None and limit is not None and self._active:
            self._on_key_state_changed(validity, limit)


def _busy_result(turn_id: str | None = None) -> SendMessageResult:
    error_type = ChatErrorType.TURN_ALREADY_ACTIVE
    return SendMessageResult(
        turn_id=turn_id,
        successful=False,
        truncated=False,
        content=None,
        error_type=error_type,
        safe_message=safe_error_message(error_type),
    )


def _missing_session_result(turn_id: str | None = None) -> SendMessageResult:
    error_type = ChatErrorType.KEY_NOT_VALID
    return SendMessageResult(
        turn_id=turn_id,
        successful=False,
        truncated=False,
        content=None,
        error_type=error_type,
        safe_message=safe_error_message(error_type),
    )


def _invalid_result() -> SendMessageResult:
    error_type = ChatErrorType.INVALID_REQUEST
    return SendMessageResult(
        turn_id=None,
        successful=False,
        truncated=False,
        content=None,
        error_type=error_type,
        safe_message=safe_error_message(error_type),
    )


def _busy_preview(chat_id: str, *, turn_id: str | None = None) -> MessageSendPreview:
    return _preview_error(chat_id, ChatErrorType.TURN_ALREADY_ACTIVE, turn_id=turn_id)


def _missing_session_preview(
    chat_id: str,
    *,
    turn_id: str | None = None,
) -> MessageSendPreview:
    return _preview_error(chat_id, ChatErrorType.KEY_NOT_VALID, turn_id=turn_id)


def _stale_preview(chat_id: str, *, turn_id: str | None = None) -> MessageSendPreview:
    return _preview_error(chat_id, ChatErrorType.INTERRUPTED, turn_id=turn_id)


def _invalid_preview(
    chat_id: str,
    *,
    turn_id: str | None = None,
) -> MessageSendPreview:
    return _preview_error(chat_id, ChatErrorType.INVALID_REQUEST, turn_id=turn_id)


def _preview_error(
    chat_id: str,
    error_type: ChatErrorType,
    *,
    turn_id: str | None,
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
    )


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_identifier(value: object, label: str) -> None:
    if not _is_identifier(value):
        raise ValueError(f"Некорректный идентификатор {label}")
