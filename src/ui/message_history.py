"""Безопасное plain-text представление локальной истории чата."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

import flet as ft

from chat.accounting import AccountingStatus, TurnRecord
from chat.errors import safe_error_message
from chat.models import Message, MessageRole, MessageStatus
from i18n import money, number, tr
from ui.styles import (
    BORDER_COLOR,
    ELEVATED_BACKGROUND,
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    secondary_button_style,
)

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
            spacing=16,
            padding=ft.Padding.symmetric(horizontal=16, vertical=16),
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
                        tr("history.empty"),
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
            ft.Row(
                controls=[
                    ft.Text(
                        tr("protection_panel.you") if is_user else "Tokenlogue",
                        size=12,
                        color=MUTED_COLOR,
                        weight=ft.FontWeight.W_600,
                        expand=True,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CONTENT_COPY_OUTLINED,
                        tooltip=tr("protection_panel.copy_message"),
                        width=44,
                        height=44,
                        icon_size=18,
                        style=secondary_button_style(),
                        on_click=self._copy_handler(message.content),
                    ),
                ]
            ),
            *_message_content(message.content),
        ]
        metadata = _message_metadata(message, turn)
        if metadata:
            spans = []
            for index, (label, value) in enumerate(metadata):
                if index:
                    spans.append(ft.TextSpan(" · "))
                spans.extend(
                    [ft.TextSpan(tr("meta.label", label=label)), ft.TextSpan(value)]
                )
            details.append(ft.Text(spans=spans, size=11, color=MUTED_COLOR))

        if message.status is MessageStatus.PENDING:
            details.append(ft.Text(tr("history.sending"), size=11, color=MUTED_COLOR))
        elif message.status is MessageStatus.FAILED:
            if not is_user:
                details.append(
                    ft.Text(
                        tr("history.partial"),
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
                        tr("common.retry"),
                        icon=ft.Icons.REFRESH,
                        on_click=self._retry_handler(message.turn_id),
                    )
                )

        bubble = ft.Container(
            width=760,
            bgcolor=ELEVATED_BACKGROUND if is_user else PANEL_BACKGROUND,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=16,
            padding=ft.Padding(16, 4, 16, 16),
            content=ft.Column(tight=True, spacing=8, controls=details),
        )
        return ft.Row(
            controls=[
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment.CENTER_RIGHT
                    if is_user
                    else ft.Alignment.CENTER_LEFT,
                    padding=ft.Padding.only(left=16)
                    if is_user
                    else ft.Padding.only(right=16),
                    content=bubble,
                )
            ],
        )

    @staticmethod
    def _copy_handler(content: str):
        async def copy(_event: ft.Event[ft.IconButton]) -> None:
            await ft.Clipboard().set(content)

        return copy

    def _retry_handler(
        self,
        turn_id: str,
    ) -> Callable[[ft.Event[ft.TextButton]], Awaitable[None]]:
        async def handle_click(_event: ft.Event[ft.TextButton]) -> None:
            await self._on_retry(turn_id)

        return handle_click


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([A-Za-z0-9_+.-]*)[ \t]*$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+)$")
_LIST = re.compile(r"^([ \t]*)([-+*]|[0-9]{1,9}[.)])[ \t]+(.+)$")
_INLINE = re.compile(r"(?<!\\)(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`)")


def _inline_spans(text: str) -> list[ft.TextSpan]:
    """Small local emphasis only. URL and image syntax stays inert text."""
    spans = []
    offset = 0
    for match in _INLINE.finditer(text):
        if match.start() > offset:
            spans.append(ft.TextSpan(text[offset : match.start()]))
        token = match.group()
        code = token.startswith("`")
        spans.append(
            ft.TextSpan(
                token[1:-1] if code else token[2:-2],
                style=ft.TextStyle(
                    font_family="monospace" if code else None,
                    bgcolor=ELEVATED_BACKGROUND if code else None,
                    weight=None if code else ft.FontWeight.W_600,
                ),
            )
        )
        offset = match.end()
    if offset < len(text) or not spans:
        spans.append(ft.TextSpan(text[offset:]))
    return spans


def _code_block(code: str, language: str) -> ft.Container:
    async def copy(_event: ft.Event[ft.IconButton]) -> None:
        await ft.Clipboard().set(code)

    return ft.Container(
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=10,
        bgcolor="#101923",
        padding=ft.Padding(12, 0, 12, 12),
        content=ft.Column(
            tight=True,
            spacing=0,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(language, size=11, color=MUTED_COLOR, expand=True),
                        ft.IconButton(
                            icon=ft.Icons.CONTENT_COPY_OUTLINED,
                            tooltip=tr("protection_panel.copy_code"),
                            width=44,
                            height=44,
                            icon_size=18,
                            style=secondary_button_style(),
                            on_click=copy,
                        ),
                    ]
                ),
                ft.Row(
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        ft.Text(code, selectable=True, font_family="monospace", size=14)
                    ],
                ),
            ],
        ),
    )


def _message_content(content: str) -> list[ft.Control]:
    """Render a bounded set of familiar formatting without a web renderer.

    This deliberately is not a CommonMark parser. All content remains local
    selectable Text/TextSpan controls. No link, image, HTML or URI is executed.
    A code copy keeps the original fenced contents, including line endings.
    """
    result: list[ft.Control] = []
    lines = content.splitlines(keepends=True)
    index = 0
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            result.append(
                ft.Text(
                    spans=_inline_spans("".join(paragraph)), selectable=True, size=15
                )
            )
            paragraph.clear()

    while index < len(lines):
        raw = lines[index]
        text = raw.rstrip("\r\n")
        fence = _FENCE.fullmatch(text)
        if fence is not None:
            closing = re.compile(
                r"^ {0,3}"
                + re.escape(fence[1][0])
                + "{"
                + str(len(fence[1]))
                + r",}[ \t]*$"
            )
            end = next(
                (
                    n
                    for n in range(index + 1, len(lines))
                    if closing.fullmatch(lines[n].rstrip("\r\n"))
                ),
                None,
            )
            if end is not None:
                flush()
                result.append(_code_block("".join(lines[index + 1 : end]), fence[2]))
                index = end + 1
                continue
            # A partial response may end inside a fence. Treat its remainder
            # as one code block and consume it once, avoiding repeated scans.
            flush()
            result.append(_code_block("".join(lines[index + 1 :]), fence[2]))
            break
        heading = _HEADING.fullmatch(text)
        item = _LIST.fullmatch(text)
        if heading is not None:
            flush()
            result.append(
                ft.Text(
                    spans=_inline_spans(heading[2]),
                    size=20
                    if len(heading[1]) == 1
                    else 18
                    if len(heading[1]) == 2
                    else 16,
                    weight=ft.FontWeight.W_600,
                    selectable=True,
                )
            )
        elif text.startswith("> "):
            flush()
            result.append(
                ft.Container(
                    border=ft.Border(left=ft.BorderSide(2, MUTED_COLOR)),
                    padding=ft.Padding.only(left=12),
                    content=ft.Text(
                        spans=_inline_spans(text[2:]), selectable=True, size=15
                    ),
                )
            )
        elif item is not None:
            flush()
            marker = "•" if item[2] in ("-", "+", "*") else item[2]
            result.append(
                ft.Text(
                    spans=[
                        ft.TextSpan(item[1] + marker + " "),
                        *_inline_spans(item[3]),
                    ],
                    selectable=True,
                    size=15,
                )
            )
        else:
            paragraph.append(raw)
        index += 1
    flush()
    return result or [ft.Text("", selectable=True, size=15)]


def _message_metadata(
    message: Message, turn: TurnRecord | None
) -> list[tuple[str, str]]:
    parts: list[tuple[str, str]] = []
    if message.role is MessageRole.ASSISTANT:
        model = message.actual_model_id or (
            turn.actual_model_id if turn is not None else None
        )
        if model:
            parts.append((tr("meta.model"), model))
    if turn is not None and turn.accounting_status is AccountingStatus.FINAL:
        if turn.prompt_tokens is not None:
            parts.append((tr("meta.prompt_tokens"), number(turn.prompt_tokens)))
        if turn.completion_tokens is not None:
            parts.append((tr("meta.completion_tokens"), number(turn.completion_tokens)))
        if turn.total_tokens is not None:
            parts.append((tr("meta.total"), number(turn.total_tokens)))
        if turn.cost_usd is not None:
            parts.append((tr("meta.cost"), money(turn.cost_usd)))
    return parts
