"""Консервативная локальная оценка контекста без библиотеки токенизации."""

from __future__ import annotations

from dataclasses import dataclass

from chat.models import Message, MessageRole, MessageStatus

FREE_ROUTER_CONTEXT_LENGTH = 8192
REQUEST_OVERHEAD_TOKENS = 32
MESSAGE_OVERHEAD_TOKENS = 8


class ContextWindowExceeded(ValueError):
    """Текущее сообщение не помещается даже без предыдущей истории."""


@dataclass(frozen=True)
class ContextMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class ContextWindow:
    messages: tuple[ContextMessage, ...]
    estimated_prompt_tokens: int
    history_truncated: bool = False


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
    if context_length <= 0 or completion_reserve < 16:
        raise ValueError("Некорректные ограничения контекста")
    available_prompt_tokens = context_length - completion_reserve
    current_cost = estimate_message_tokens(current_user_text)
    estimated = REQUEST_OVERHEAD_TOKENS + current_cost
    if estimated > available_prompt_tokens:
        raise ContextWindowExceeded("Текущее сообщение не помещается в контекст")

    selected_pairs: list[tuple[ContextMessage, ContextMessage]] = []
    history_truncated = False
    for user, assistant in reversed(_completed_pairs(history)):
        pair_cost = estimate_message_tokens(user.content) + estimate_message_tokens(
            assistant.content
        )
        if estimated + pair_cost > available_prompt_tokens:
            history_truncated = True
            break
        selected_pairs.append((user, assistant))
        estimated += pair_cost

    messages: list[ContextMessage] = []
    for user, assistant in reversed(selected_pairs):
        messages.extend((user, assistant))
    messages.append(ContextMessage(MessageRole.USER, current_user_text))
    if require_full_history and history_truncated:
        raise ContextWindowExceeded("Полная история не помещается в контекст")
    return ContextWindow(tuple(messages), estimated, history_truncated)


def _completed_pairs(
    history: list[Message],
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
