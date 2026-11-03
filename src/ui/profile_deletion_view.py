"""Отдельное подтверждение уничтожения и возобновляемое состояние выполнения."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from i18n import fresh_text, tr
from ui.branding import AuthHeader, BrandLoader
from ui.language_selector import LanguageSelector
from ui.styles import (
    CARD_RADIUS,
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    build_auth_screen,
    danger_button_style,
    input_style,
    primary_button_style,
    secondary_button_style,
)


class ProfileDeletionDialog:
    """Фраза подтверждает намерение, не открывает доступ и не проверяет PIN."""

    def __init__(
        self,
        on_confirm: Callable[[str], Awaitable[None]],
        on_cancel: Callable[[], None],
        *,
        preparation_required: bool = False,
    ) -> None:
        self.phrase = str(tr("profile_deletion.phrase"))
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._disposed = False
        self._busy = False
        self.phrase_field = ft.TextField(
            **input_style(),
            label=tr("profile_deletion.phrase_prompt"),
            max_length=64,
            autocorrect=False,
            enable_suggestions=False,
            on_change=self._changed,
        )
        self.confirm_button = ft.TextButton(
            tr("profile_deletion.confirm"),
            disabled=True,
            on_click=self._confirm,
            style=danger_button_style(),
        )
        self.cancel_button = ft.TextButton(
            tr("profile_deletion.cancel"),
            on_click=self._cancel,
            style=secondary_button_style(),
            autofocus=True,
        )
        self.dialog = ft.AlertDialog(
            modal=True,
            bgcolor=PANEL_BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS),
            scrollable=True,
            title=ft.Text(tr("profile_deletion.title")),
            content=ft.Column(
                tight=True,
                width=420,
                spacing=16,
                controls=[
                    ft.Text(tr("profile_deletion.description")),
                    ft.Text(tr("profile_deletion.remote_notice"), color=MUTED_COLOR),
                    ft.Text(tr("profile_deletion.local_notice"), color=MUTED_COLOR),
                    ft.Text(tr("profile_deletion.backup_notice"), color=MUTED_COLOR),
                    *(
                        [ft.Text(tr("profile_deletion.preparation_notice"))]
                        if preparation_required
                        else []
                    ),
                    ft.Text(self.phrase, weight=ft.FontWeight.BOLD, selectable=True),
                    self.phrase_field,
                ],
            ),
            actions=[self.cancel_button, self.confirm_button],
            actions_alignment=ft.MainAxisAlignment.END,
            on_dismiss=self._dismissed,
        )

    def _apply(self) -> None:
        self.confirm_button.disabled = (
            self._disposed or self._busy or self.phrase_field.value != self.phrase
        )
        self.cancel_button.disabled = self._disposed or self._busy
        self.phrase_field.disabled = self._disposed or self._busy

    def _changed(self, _event: object) -> None:
        self._apply()
        self.confirm_button.update()

    async def _confirm(self, _event: object) -> None:
        self._apply()
        if self.confirm_button.disabled:
            return
        value = self.phrase_field.value
        if not isinstance(value, str):
            return
        self._busy = True
        self._apply()
        try:
            await self._on_confirm(value)
        finally:
            if not self._disposed:
                self._busy = False
                self._apply()

    def _cancel(self, _event: object) -> None:
        if not self._disposed and not self._busy:
            self._on_cancel()

    def _dismissed(self, _event: object) -> None:
        self._cancel(_event)

    def dispose(self) -> None:
        self._disposed = True
        self.phrase_field.value = ""
        self.dialog.open = False
        self._apply()


class ProfileDeletionProgressView:
    def __init__(self, on_retry: Callable[[], Awaitable[None]]) -> None:
        self.progress = BrandLoader(size=26, active=True)
        self.message = ft.Text(visible=False, color=ERROR_COLOR)
        self.retry_button = ft.Button(
            tr("profile_deletion.retry"),
            visible=False,
            on_click=self._retry,
            style=primary_button_style(),
        )
        self._on_retry = on_retry
        self._busy = True
        self._disposed = False
        language = LanguageSelector(compact=True)
        language.disabled = True
        self.header = AuthHeader(language_selector=language)
        self.control = build_auth_screen(
            [
                ft.Text(
                    tr("profile_deletion.progress"),
                    theme_style=ft.TextThemeStyle.TITLE_LARGE,
                ),
                ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self.progress]),
                self.message,
                self.retry_button,
            ],
            header=self.header,
        )

    async def _retry(self, _event: object) -> None:
        if self._disposed or self._busy:
            return
        self.set_busy()
        await self._on_retry()

    def set_busy(self) -> None:
        self._busy = True
        self.progress.set_active(True)
        self.message.visible = False
        self.retry_button.visible = False

    def show_error(self, message: str, *, retry_label: str | None = None) -> None:
        self._busy = False
        self.progress.set_active(False)
        self.message.value = fresh_text(message)
        self.message.visible = True
        self.retry_button.visible = True
        if retry_label is not None:
            self.retry_button.content = fresh_text(retry_label)

    def dispose(self) -> None:
        self._disposed = True
        self.progress.dispose()
