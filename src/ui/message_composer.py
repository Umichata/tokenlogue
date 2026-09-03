"""Мобильный редактор обычного текстового сообщения."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from ui.styles import ERROR_COLOR, MUTED_COLOR, PANEL_BACKGROUND, primary_button_style

MessageSubmitCallback = Callable[[str], Awaitable[None]]


class MessageComposer:
    def __init__(
        self,
        on_submit: MessageSubmitCallback,
        *,
        enabled: bool = True,
    ) -> None:
        self._on_submit = on_submit
        self._enabled = enabled
        self._busy = False
        self.message_field = ft.TextField(
            label="Сообщение",
            hint_text="Введите сообщение",
            multiline=True,
            min_lines=1,
            max_lines=5,
            shift_enter=True,
            expand=True,
            on_change=self._handle_change,
            on_submit=self._handle_submit,
        )
        self.send_button = ft.Button(
            "Отправить",
            icon=ft.Icons.SEND,
            style=primary_button_style(),
            disabled=True,
            on_click=self._handle_click,
        )
        self.progress = ft.ProgressRing(
            width=18,
            height=18,
            stroke_width=2,
            visible=False,
        )
        self.status = ft.Text("", color=MUTED_COLOR, visible=False, selectable=True)
        self.progress_row = ft.Row(
            visible=False,
            controls=[self.progress, ft.Text("Ожидание ответа…")],
        )
        self.control = ft.Container(
            bgcolor=PANEL_BACKGROUND,
            padding=12,
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    self.status,
                    ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.END,
                        controls=[self.message_field, self.send_button],
                    ),
                    self.progress_row,
                ],
            ),
        )
        self._apply_state()

    @property
    def value(self) -> str:
        return self.message_field.value

    @property
    def busy(self) -> bool:
        return self._busy

    async def _handle_click(self, _event: ft.Event[ft.Button]) -> None:
        await self._submit_current_text()

    async def _handle_submit(self, _event: ft.Event[ft.TextField]) -> None:
        await self._submit_current_text()

    async def _submit_current_text(self) -> None:
        value = self.message_field.value
        if (
            self.send_button.disabled
            or self._busy
            or not isinstance(value, str)
            or not value.strip()
        ):
            return
        await self._on_submit(value)

    def _handle_change(self, _event: ft.Event[ft.TextField]) -> None:
        self._apply_state()
        self.send_button.update()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._apply_state()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._apply_state()

    def clear_if_matches(self, expected: str) -> None:
        if self.message_field.value == expected:
            self.message_field.value = ""
            self._apply_state()

    def show_message(self, message: str, *, error: bool = True) -> None:
        self.status.value = message
        self.status.color = ERROR_COLOR if error else MUTED_COLOR
        self.status.visible = bool(message)

    def _apply_state(self) -> None:
        value = self.message_field.value
        has_text = isinstance(value, str) and bool(value.strip())
        self.message_field.disabled = not self._enabled or self._busy
        self.send_button.disabled = not self._enabled or self._busy or not has_text
        self.progress.visible = self._busy
        self.progress_row.visible = self._busy
