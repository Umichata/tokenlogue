"""Безопасное plain-text представление локальной истории чата."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from chat.accounting import AccountingStatus, TurnRecord, format_decimal_usd
from chat.errors import safe_error_message
from chat.models import Message, MessageRole, MessageStatus
from ui.styles import ERROR_COLOR, MUTED_COLOR, PANEL_BACKGROUND

RetryCallback = Callable[[str], Awaitable[None]]


class MessageHistoryView:
    def __init__(
        self,
        messages: tuple[Message, ...],
        turns: tuple[TurnRecord, ...],
        *,
        on_retry: RetryCallback,
    ) -> None:
        self._on_retry = on_retry
        self._turns: dict[str, TurnRecord] = {}
        self.control = ft.ListView(
            expand=True,
            spacing=10,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            scroll=ft.ScrollMode.AUTO,
            auto_scroll=False,
            build_controls_on_demand=False,
        )
        self.set_messages(messages, turns)

    def set_messages(
        self,
        messages: tuple[Message, ...],
        turns: tuple[TurnRecord, ...],
    ) -> None:
        self._turns = {turn.id: turn for turn in turns}
        if not messages:
            self.control.controls = [
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text(
                        "Сообщений пока нет",
                        color=MUTED_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                )
            ]
            return
        self.control.controls = [self._build_message(message) for message in messages]

    async def scroll_to_end(self) -> None:
        try:
            await self.control.scroll_to(offset=-1, duration=160)
        except (RuntimeError, AssertionError):
            return

    def _build_message(self, message: Message) -> ft.Control:
        turn = self._turns.get(message.turn_id)
        is_user = message.role is MessageRole.USER
        details: list[ft.Control] = [
            ft.Text(message.content, selectable=True),
        ]
        metadata = _message_metadata(message, turn)
        if metadata:
            details.append(ft.Text(metadata, size=11, color=MUTED_COLOR))

        if message.status is MessageStatus.PENDING:
            details.append(ft.Text("Отправляется…", size=11, color=MUTED_COLOR))
        elif message.status is MessageStatus.FAILED:
            if not is_user:
                details.append(
                    ft.Text(
                        "Ответ получен не полностью",
                        size=11,
                        color=ERROR_COLOR,
                    )
                )
            if turn is not None and turn.error_type is not None:
                details.append(
                    ft.Text(
                        safe_error_message(turn.error_type),
                        size=11,
                        color=ERROR_COLOR,
                    )
                )
            if (
                is_user
                and turn is not None
                and turn.accounting_status is AccountingStatus.RELEASED
            ):
                details.append(
                    ft.TextButton(
                        "Повторить",
                        icon=ft.Icons.REFRESH,
                        on_click=self._retry_handler(message.turn_id),
                    )
                )

        bubble = ft.Container(
            bgcolor=(ft.Colors.BLUE_700 if is_user else PANEL_BACKGROUND),
            border_radius=14,
            padding=12,
            content=ft.Column(tight=True, spacing=5, controls=details),
        )
        return ft.Row(
            alignment=(
                ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START
            ),
            controls=[bubble],
        )

    def _retry_handler(
        self,
        turn_id: str,
    ) -> Callable[[ft.Event[ft.TextButton]], Awaitable[None]]:
        async def handle_click(_event: ft.Event[ft.TextButton]) -> None:
            await self._on_retry(turn_id)

        return handle_click


def _message_metadata(message: Message, turn: TurnRecord | None) -> str:
    parts: list[str] = []
    if message.role is MessageRole.ASSISTANT:
        model = message.actual_model_id or (
            turn.actual_model_id if turn is not None else None
        )
        if model:
            parts.append(f"Модель: {model}")
    if turn is not None and turn.accounting_status is AccountingStatus.FINAL:
        if turn.prompt_tokens is not None:
            parts.append(f"prompt: {turn.prompt_tokens}")
        if turn.completion_tokens is not None:
            parts.append(f"completion: {turn.completion_tokens}")
        if turn.total_tokens is not None:
            parts.append(f"всего: {turn.total_tokens}")
        if turn.cost_usd is not None:
            parts.append(f"стоимость: ${format_decimal_usd(turn.cost_usd)}")
    return " · ".join(parts)
