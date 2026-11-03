"""Консервативная локальная оценка контекста без библиотеки токенизации."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field

from chat.models import Message, MessageRole, MessageStatus

FREE_ROUTER_CONTEXT_LENGTH = 8192
REQUEST_OVERHEAD_TOKENS = 32
MESSAGE_OVERHEAD_TOKENS = 8


class ContextWindowExceeded(ValueError):
    """Текущее сообщение не помещается даже без предыдущей истории."""


@dataclass(frozen=True)
class ContextMessage:
    role: MessageRole
    content: str = field(repr=False)


@dataclass(frozen=True)
class ContextWindow:
    messages: tuple[ContextMessage, ...]
    estimated_prompt_tokens: int
    history_truncated: bool = False


@dataclass(frozen=True)
class PreparedHistory:
    """Immutable successful pairs and their cached cumulative token estimates."""

    pairs: tuple[tuple[ContextMessage, ContextMessage], ...] = field(repr=False)
    cumulative_tokens: tuple[int, ...] = field(repr=False)

    @property
    def estimated_tokens(self) -> int:
        return self.cumulative_tokens[-1]


@dataclass(frozen=True)
class ContextSelection:
    """A cheap selection which materializes message tuples only for sending."""

    history: PreparedHistory = field(repr=False)
    current_user_text: str = field(repr=False)
    pair_start: int
    estimated_prompt_tokens: int

    @property
    def history_truncated(self) -> bool:
        return self.pair_start > 0

    def materialize(self) -> ContextWindow:
        messages = tuple(
            message
            for pair in self.history.pairs[self.pair_start :]
            for message in pair
        )
        return ContextWindow(
            (*messages, ContextMessage(MessageRole.USER, self.current_user_text)),
            self.estimated_prompt_tokens,
            self.history_truncated,
        )


def estimate_message_tokens(content: str) -> int:
    """
    Возвращает не точный подсчёт, а защитную оценку.

    Каждый UTF-8 байт считается отдельным токеном, затем добавляется постоянный
    служебный запас на роль и структуру сообщения.
    """
    return len(content.encode("utf-8")) + MESSAGE_OVERHEAD_TOKENS


def build_conversation_context(
    history: list[Message],
    current_user_text: str,
    *,
    context_length: int,
    completion_reserve: int,
    require_full_history: bool = False,
) -> ContextWindow:
    return select_conversation_context(
        prepare_history(history),
        current_user_text,
        context_length=context_length,
        completion_reserve=completion_reserve,
        require_full_history=require_full_history,
    ).materialize()


def prepare_history(history: Sequence[Message]) -> PreparedHistory:
    """Read an authorized history once, without holding repository handles."""
    pairs = tuple(_completed_pairs(history))
    cumulative = [0]
    for user, assistant in pairs:
        cumulative.append(
            cumulative[-1]
            + estimate_message_tokens(user.content)
            + estimate_message_tokens(assistant.content)
        )
    return PreparedHistory(pairs, tuple(cumulative))


def select_conversation_context(
    history: PreparedHistory,
    current_user_text: str,
    *,
    context_length: int,
    completion_reserve: int,
    require_full_history: bool = False,
) -> ContextSelection:
    if context_length <= 0 or completion_reserve < 16:
        raise ValueError("Некорректные ограничения контекста")
    available_prompt_tokens = context_length - completion_reserve
    current_cost = estimate_message_tokens(current_user_text)
    estimated = REQUEST_OVERHEAD_TOKENS + current_cost
    if estimated > available_prompt_tokens:
        raise ContextWindowExceeded("Текущее сообщение не помещается в контекст")

    # Prefix costs are positive. The first affordable suffix is exactly the
    # recent-pair selection used by the ordinary sending path.
    threshold = history.estimated_tokens - (available_prompt_tokens - estimated)
    pair_start = bisect_left(history.cumulative_tokens, max(0, threshold))
    if require_full_history and pair_start > 0:
        raise ContextWindowExceeded("Полная история не помещается в контекст")
    estimated += history.estimated_tokens - history.cumulative_tokens[pair_start]
    return ContextSelection(history, current_user_text, pair_start, estimated)


def _completed_pairs(
    history: Sequence[Message],
) -> list[tuple[ContextMessage, ContextMessage]]:
    turns: dict[str, dict[MessageRole, Message]] = {}
    order: list[str] = []
    for message in history:
        if message.status is not MessageStatus.SENT:
            continue
        if message.turn_id not in turns:
            turns[message.turn_id] = {}
            order.append(message.turn_id)
        turns[message.turn_id][message.role] = message

    pairs: list[tuple[ContextMessage, ContextMessage]] = []
    for turn_id in order:
        user = turns[turn_id].get(MessageRole.USER)
        assistant = turns[turn_id].get(MessageRole.ASSISTANT)
        if user is None or assistant is None:
            continue
        pairs.append(
            (
                ContextMessage(MessageRole.USER, user.content),
                ContextMessage(MessageRole.ASSISTANT, assistant.content),
            )
        )
    return pairs
