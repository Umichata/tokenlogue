"""Проверки мобильных компонентов редактора, истории и лимитов."""

from __future__ import annotations

import inspect
import sys
import unittest
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import (  # noqa: E402
    AccountingStatus,
    BudgetState,
    ChatBudget,
    TurnRecord,
    TurnStatus,
    calculate_remaining_budget,
)
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    Chat,
    ChatMode,
    Message,
    MessageRole,
    MessageStatus,
)
from chat.sending import SendMessageResult  # noqa: E402
from chat_interaction_controller import ActiveChatState  # noqa: E402
from chat_workspace_controller import _result_message  # noqa: E402
from ui.chat_limits_view import ChatLimitsForm  # noqa: E402
from ui.chat_view import ChatWorkspaceView  # noqa: E402
from ui.message_composer import MessageComposer  # noqa: E402
from ui.message_history import MessageHistoryView  # noqa: E402

NOW = datetime(2026, 7, 1, tzinfo=UTC)


class FakePage:
    def __init__(self, width: int = 400) -> None:
        self.width = width
        self.drawer: ft.NavigationDrawer | None = None

    async def show_drawer(self) -> None:
        return None

    async def close_drawer(self) -> None:
        return None


class ChatComponentTests(unittest.IsolatedAsyncioTestCase):
    async def test_composer_supports_enter_shift_enter_and_android_button(self) -> None:
        submitted: list[object] = []

        async def submit(text: str) -> None:
            submitted.append(text)

        composer = MessageComposer(submit)

        self.assertTrue(composer.message_field.multiline)
        self.assertEqual(composer.message_field.min_lines, 1)
        self.assertEqual(composer.message_field.max_lines, 5)
        self.assertTrue(composer.message_field.shift_enter)
        self.assertTrue(composer.send_button.disabled)
        self.assertTrue(inspect.iscoroutinefunction(composer.send_button.on_click))

        composer.message_field.value = "hello\nworld"
        composer._apply_state()
        self.assertFalse(composer.send_button.disabled)
        click_handler = cast(
            Callable[[ft.Event[ft.Button]], Awaitable[None]],
            composer.send_button.on_click,
        )
        await click_handler(ft.Event(name="click", control=composer.send_button))
        self.assertEqual(submitted, ["hello\nworld"])
        self.assertNotIsInstance(submitted[0], ft.Event)

        submitted.clear()
        submit_handler = cast(
            Callable[[ft.Event[ft.TextField]], Awaitable[None]],
            composer.message_field.on_submit,
        )
        await submit_handler(ft.Event(name="submit", control=composer.message_field))
        self.assertEqual(submitted, ["hello\nworld"])

        submitted.clear()
        self.assertTrue(composer.message_field.shift_enter)
        self.assertEqual(submitted, [])

        composer.message_field.value = "  \n  "
        composer._apply_state()
        await click_handler(ft.Event(name="click", control=composer.send_button))
        self.assertEqual(submitted, [])

        composer.set_busy(True)
        self.assertTrue(composer.message_field.disabled)
        self.assertTrue(composer.send_button.disabled)
        self.assertTrue(composer.progress.visible)

    def test_free_limits_hide_money_and_paid_limits_keep_decimal_text(self) -> None:
        async def submit(_tokens: str, _completion: str, _cost: str | None) -> None:
            return None

        free = ChatLimitsForm(ChatMode.FREE, submit)
        paid = ChatLimitsForm(ChatMode.PAID, submit)

        self.assertIsNone(free.cost_limit)
        self.assertIsNotNone(paid.cost_limit)
        assert paid.cost_limit is not None
        self.assertEqual(paid.cost_limit.value, "1")
        self.assertNotIsInstance(paid.cost_limit.value, float)

    def test_rate_limit_message_includes_safe_retry_after(self) -> None:
        result = SendMessageResult(
            turn_id="turn",
            successful=False,
            truncated=False,
            content=None,
            error_type=ChatErrorType.RATE_LIMIT_EXCEEDED,
            safe_message="OpenRouter временно ограничил частоту запросов.",
            retry_after=17,
        )

        message = _result_message(result)

        self.assertIn("17 с", message)
        self.assertNotIn("Authorization", message)

    async def test_history_preserves_order_and_exposes_only_safe_retry(self) -> None:
        retried: list[str] = []

        async def retry(turn_id: str) -> None:
            retried.append(turn_id)

        messages = (
            _message("user", MessageRole.USER, MessageStatus.FAILED, "question"),
            _message(
                "assistant", MessageRole.ASSISTANT, MessageStatus.FAILED, "partial"
            ),
        )
        turn = _turn(
            accounting_status=AccountingStatus.RELEASED,
            error_type=ChatErrorType.PROVIDER_UNAVAILABLE,
        )
        history = MessageHistoryView(messages, (turn,), on_retry=retry)

        self.assertEqual(len(history.control.controls), 2)
        first_row = cast(ft.Row, history.control.controls[0])
        first_bubble = cast(ft.Container, first_row.controls[0])
        first_column = cast(ft.Column, first_bubble.content)
        displayed = [
            control.value
            for control in first_column.controls
            if isinstance(control, ft.Text)
        ]
        self.assertIn("question", displayed)
        retry_button = next(
            control
            for control in first_column.controls
            if isinstance(control, ft.TextButton)
        )
        handler = cast(
            Callable[[ft.Event[ft.TextButton]], Awaitable[None]],
            retry_button.on_click,
        )
        await handler(ft.Event(name="click", control=retry_button))
        self.assertEqual(retried, ["turn"])

    def test_unconfigured_chat_is_readable_and_sending_is_disabled(self) -> None:
        chat = _chat()
        state = _state(chat, configured=False)

        async def callback(*_args: str) -> None:
            return None

        view = ChatWorkspaceView(
            cast(ft.Page, FakePage()),
            [chat],
            chat,
            state,
            on_new_chat=callback,
            on_select_chat=callback,
            on_rename_chat=callback,
            on_delete_chat=callback,
            on_lock=callback,
            on_send_message=callback,
            on_retry_turn=callback,
            on_configure_limits=callback,
            on_edit_limits=callback,
            on_release_unknown=callback,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            key_validation_in_progress=False,
            on_retry_key=callback,
            on_replace_key=callback,
        )

        self.assertIsNotNone(view.limits_button)
        self.assertIsNotNone(view.composer)
        assert view.composer is not None
        self.assertTrue(view.composer.send_button.disabled)
        assert view.message_history is not None
        empty = cast(ft.Container, view.message_history.control.controls[0])
        empty_text = cast(ft.Text, empty.content)
        self.assertEqual(empty_text.value, "Сообщений пока нет")

    def test_unknown_state_shows_reserved_values_and_release_action(self) -> None:
        chat = _chat()
        budget = _budget(chat.id, configured=True, unknown=True)
        state = ActiveChatState(
            chat=chat,
            messages=(),
            turns=(
                _turn(
                    accounting_status=AccountingStatus.UNKNOWN,
                    error_type=ChatErrorType.TIMEOUT,
                ),
            ),
            budget=budget,
            remaining=calculate_remaining_budget(budget),
        )

        async def callback(*_args: str) -> None:
            return None

        view = ChatWorkspaceView(
            cast(ft.Page, FakePage()),
            [chat],
            chat,
            state,
            on_new_chat=callback,
            on_select_chat=callback,
            on_rename_chat=callback,
            on_delete_chat=callback,
            on_lock=callback,
            on_send_message=callback,
            on_retry_turn=callback,
            on_configure_limits=callback,
            on_edit_limits=callback,
            on_release_unknown=callback,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            key_validation_in_progress=False,
            on_retry_key=callback,
            on_replace_key=callback,
        )

        self.assertIsNotNone(view.release_unknown_button)
        assert view.composer is not None
        self.assertTrue(view.composer.send_button.disabled)


def _chat() -> Chat:
    return Chat(
        id="chat",
        title="Новый чат",
        mode=ChatMode.FREE,
        requested_model_id=FREE_ROUTER_MODEL.id,
        requested_model_name=FREE_ROUTER_MODEL.name,
        prompt_price_per_token=Decimal("0"),
        completion_price_per_token=Decimal("0"),
        created_at=NOW,
        updated_at=NOW,
    )


def _budget(
    chat_id: str,
    *,
    configured: bool,
    unknown: bool = False,
) -> ChatBudget:
    return ChatBudget(
        chat_id=chat_id,
        limits_configured=configured,
        token_limit=1000 if configured else None,
        max_completion_tokens=64 if configured else None,
        prompt_tokens_used=20,
        completion_tokens_used=10,
        total_tokens_used=30,
        reserved_tokens=50 if unknown else 0,
        cost_limit_usd=Decimal("0"),
        cost_used_usd=Decimal("0"),
        cost_reserved_usd=Decimal("0"),
        state=(
            BudgetState.ACCOUNTING_UNKNOWN
            if unknown
            else BudgetState.READY
            if configured
            else BudgetState.UNCONFIGURED
        ),
        updated_at=NOW,
    )


def _state(chat: Chat, *, configured: bool) -> ActiveChatState:
    budget = _budget(chat.id, configured=configured)
    return ActiveChatState(
        chat=chat,
        messages=(),
        turns=(),
        budget=budget,
        remaining=calculate_remaining_budget(budget),
    )


def _message(
    message_id: str,
    role: MessageRole,
    status: MessageStatus,
    content: str,
) -> Message:
    return Message(
        id=message_id,
        chat_id="chat",
        turn_id="turn",
        role=role,
        content=content,
        status=status,
        requested_model_id=FREE_ROUTER_MODEL.id,
        actual_model_id=FREE_ROUTER_MODEL.id if role is MessageRole.ASSISTANT else None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        created_at=NOW,
    )


def _turn(
    *,
    accounting_status: AccountingStatus,
    error_type: ChatErrorType | None,
) -> TurnRecord:
    return TurnRecord(
        id="turn",
        chat_id="chat",
        status=TurnStatus.FAILED,
        requested_model_id=FREE_ROUTER_MODEL.id,
        actual_model_id=None,
        generation_id=None,
        finish_reason=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        cost_usd=None,
        reserved_tokens=50,
        reserved_cost_usd=Decimal("0"),
        accounting_status=accounting_status,
        error_type=error_type,
        request_sent=True,
        created_at=NOW,
        updated_at=NOW,
    )


if __name__ == "__main__":
    unittest.main()
