"""Мобильный редактор обычного текстового сообщения."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from chat.estimates import DraftEstimate, EstimateState
from i18n import fresh_text, tr
from ui.branding import BrandLoader
from ui.chat_metrics import DraftEstimateLine
from ui.styles import (
    BORDER_COLOR,
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    input_style,
    primary_button_style,
)

MessageSubmitCallback = Callable[[str], Awaitable[None]]


class MessageComposer:
    def __init__(
        self,
        on_submit: MessageSubmitCallback,
        *,
        enabled: bool = True,
        on_change: MessageSubmitCallback | None = None,
    ) -> None:
        self._on_submit = on_submit
        self._on_change = on_change
        self._disposed = False
        self._enabled = enabled
        self._busy = False
        self.message_field = ft.TextField(
            label=tr("composer.message"),
            hint_text=tr("composer.hint"),
            multiline=True,
            min_lines=1,
            max_lines=5,
            shift_enter=True,
            expand=True,
            on_change=self._handle_change,
            on_submit=self._handle_submit,
            **input_style(),
        )
        self.send_button = ft.Button(
            tr("composer.send"),
            icon=ft.Icons.SEND,
            style=primary_button_style(),
            height=52,
            disabled=True,
            on_click=self._handle_click,
        )
        self.progress = BrandLoader(size=26, active=False)
        self.status = ft.Text("", color=MUTED_COLOR, visible=False, selectable=True)
        self.estimate = DraftEstimateLine()
        self.progress_row = ft.Row(
            visible=False,
            controls=[self.progress, ft.Text(tr("composer.waiting"), expand=True)],
        )
        self.control = ft.Container(
            bgcolor=PANEL_BACKGROUND,
            border=ft.Border(top=ft.BorderSide(1, BORDER_COLOR)),
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
                    self.estimate.control,
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
            or self._disposed
            or self._busy
            or not isinstance(value, str)
            or not value.strip()
        ):
            return
        await self._on_submit(value)

    async def _handle_change(self, _event: ft.Event[ft.TextField]) -> None:
        if self._disposed:
            return
        value = self.message_field.value
        self.set_estimate(
            DraftEstimate(EstimateState.EMPTY)
            if not isinstance(value, str) or not value.strip()
            else None
        )
        self._apply_state()
        self.send_button.update()
        if self._on_change is not None and isinstance(value, str):
            await self._on_change(value)

    def set_value(self, text: str) -> None:
        if self.message_field.value != text:
            self.message_field.value = text
            self.estimate.set_estimate(
                DraftEstimate(EstimateState.EMPTY) if not text.strip() else None
            )
        self._apply_state()

    def set_estimate(self, estimate: DraftEstimate | None) -> None:
        if self._disposed:
            return
        self.estimate.set_estimate(estimate)
        try:
            self.estimate.control.update()
        except (RuntimeError, AssertionError):
            pass

    def refresh_language(self) -> None:
        self.estimate.sync_language()

    def dispose(self) -> None:
        self._disposed = True
        self.progress.dispose()
        self.message_field.value = ""
        self.estimate.clear()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._apply_state()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._apply_state()

    def clear_if_matches(self, expected: str) -> None:
        if self.message_field.value == expected:
            self.message_field.value = ""
            self.estimate.set_estimate(DraftEstimate(EstimateState.EMPTY))
            self._apply_state()

    def show_message(self, message: str, *, error: bool = True) -> None:
        self.status.value = fresh_text(message)
        self.status.color = ERROR_COLOR if error else MUTED_COLOR
        self.status.visible = bool(message)

    def _apply_state(self) -> None:
        value = self.message_field.value
        has_text = isinstance(value, str) and bool(value.strip())
        self.message_field.disabled = not self._enabled or self._busy
        self.send_button.disabled = not self._enabled or self._busy or not has_text
        self.progress.set_active(self._busy)
        self.progress_row.visible = self._busy
