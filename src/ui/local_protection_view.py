"""Первый локальный тест Linux без доступа к ключам, PIN или переписке."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from i18n import fresh_text, tr
from platform_security.local_protection import CheckState, ProtectionSnapshot
from ui.branding import AuthHeader, BrandLoader
from ui.security_status import mechanism_ready, protection_notice
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    SUCCESS_COLOR,
    build_auth_screen,
    primary_button_style,
    secondary_button_style,
)


class LocalProtectionSetupView:
    """The screen is automatic, the operating-system lock always needs a click."""

    def __init__(
        self,
        snapshot: ProtectionSnapshot,
        on_start: Callable[[], Awaitable[None]],
        on_continue: Callable[[], Awaitable[None]],
    ) -> None:
        self._on_start = on_start
        self._on_continue = on_continue
        self._disposed = False
        self._requesting = False
        self._snapshot = snapshot
        self.progress = BrandLoader(size=26, active=False)
        self.status = ft.Text(no_wrap=False)
        self.message = ft.Text(visible=False, color=ERROR_COLOR, no_wrap=False)
        self.manual_notice = ft.Text(
            tr("protection_intro.manual_notice"), color=MUTED_COLOR, no_wrap=False
        )
        self.start_button = ft.Button(
            tr("protection_intro.start"),
            icon=ft.Icons.LOCK_OUTLINE,
            style=primary_button_style(),
            on_click=self._start,
        )
        self.continue_label = ft.Text(no_wrap=False, text_align=ft.TextAlign.CENTER)
        self.continue_button = ft.TextButton(
            self.continue_label, on_click=self._continue
        )
        self.continue_button.style = secondary_button_style()
        self.header = AuthHeader()
        self.control = build_auth_screen(
            [
                ft.Text(
                    tr("protection_intro.title"),
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                    no_wrap=False,
                ),
                ft.Text(
                    tr("protection_intro.instructions"),
                    color=MUTED_COLOR,
                    no_wrap=False,
                ),
                self.status,
                self.message,
                ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self.progress]),
                self.start_button,
                self.manual_notice,
                self.continue_button,
            ],
            header=self.header,
        )
        self.set_snapshot(snapshot)

    def set_snapshot(self, snapshot: ProtectionSnapshot) -> None:
        if self._disposed:
            return
        self._snapshot = snapshot
        running = self._requesting or snapshot.test_running
        confirmed = snapshot.screen.state is CheckState.CONFIRMED
        self.status.value = fresh_text(protection_notice(snapshot))
        self.status.color = (
            ERROR_COLOR
            if snapshot.has_problem
            else SUCCESS_COLOR
            if confirmed
            and mechanism_ready(snapshot, "screen")
            and not snapshot.persistence_error
            else MUTED_COLOR
        )
        self.progress.set_active(running)
        self.start_button.disabled = running
        self.continue_button.disabled = running
        self.start_button.content = (
            tr("protection_intro.repeat")
            if snapshot.screen.code not in {"not_checked", "observer_changed"}
            else tr("protection_intro.start")
        )
        self.continue_label.value = tr(
            "protection_intro.continue"
            if confirmed
            else "protection_intro.continue_manual"
        )
        self.manual_notice.visible = not confirmed

    def show_message(self, message: str) -> None:
        self.message.value = fresh_text(message)
        self.message.visible = bool(message)

    async def _start(self, _event: ft.Event) -> None:
        if self._disposed or self.start_button.disabled:
            return
        self._requesting = True
        self.show_message("")
        self.set_snapshot(self._snapshot)
        try:
            await self._on_start()
        finally:
            self._requesting = False
            self.set_snapshot(self._snapshot)
            if not self._disposed:
                try:
                    self.control.update()
                except (RuntimeError, AssertionError):
                    pass

    async def _continue(self, _event: ft.Event) -> None:
        if self._disposed or self.continue_button.disabled:
            return
        await self._on_continue()

    def dispose(self) -> None:
        self._disposed = True
        self.progress.dispose()
