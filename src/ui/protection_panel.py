"""One public device-protection panel for the PIN screen and the workspace."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

import flet as ft

from i18n import fresh_text, localize_tree, tr
from platform_security.local_protection import CheckState, ProtectionSnapshot
from ui.security_status import (
    mechanism_details,
    mechanism_label,
    mechanism_monitor_notice,
    mechanism_ready,
    previous_result_label,
    protection_label,
    protection_notice,
    protection_ready,
)
from ui.styles import (
    BORDER_COLOR,
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    PRIMARY_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
    primary_button_style,
    secondary_button_style,
)

Mechanism = Literal["screen", "sleep"]
DismissReason = Literal["user", "auth_handoff", "programmatic"]
TestCallback = Callable[[Mechanism], Awaitable[None]]


def update_protection_shield(
    button: ft.IconButton, snapshot: ProtectionSnapshot
) -> None:
    """Use the existing model's present readiness, never a second UI verdict."""
    ready = protection_ready(snapshot)
    button.icon = ft.Icons.GPP_GOOD_OUTLINED if ready else ft.Icons.GPP_MAYBE_OUTLINED
    button.icon_color = (
        ERROR_COLOR
        if snapshot.has_problem
        else SUCCESS_COLOR
        if ready
        else WARNING_COLOR
    )
    # Material IconButton exposes its tooltip to the accessibility tree too.
    button.tooltip = tr("session_watch.open_details", status=protection_label(snapshot))


def protection_shield(
    snapshot: ProtectionSnapshot,
    on_click: Callable[[ft.Event[ft.IconButton]], Awaitable[None]],
) -> ft.IconButton:
    button = ft.IconButton(
        width=48,
        height=48,
        icon_size=23,
        on_click=on_click,
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=12),
            side={
                ft.ControlState.DEFAULT: ft.BorderSide(1, ft.Colors.TRANSPARENT),
                ft.ControlState.FOCUSED: ft.BorderSide(2, PRIMARY_COLOR),
            },
            overlay_color={
                ft.ControlState.HOVERED: "#243F4A",
                ft.ControlState.FOCUSED: "#243F4A",
            },
        ),
    )
    update_protection_shield(button, snapshot)
    return button


class _MechanismCard:
    def __init__(self, mechanism: Mechanism, on_test: TestCallback) -> None:
        self.mechanism: Mechanism = mechanism
        self.result = ft.Text(weight=ft.FontWeight.W_600, no_wrap=False, expand=True)
        self.details = ft.Column(spacing=4, tight=True)
        self.monitor = ft.Text(size=12, no_wrap=False)
        self.explanation = ft.Text(
            tr(
                "local_protection.test_explanation"
                if mechanism == "screen"
                else "local_protection.sleep_test_explanation"
            ),
            size=12,
            color=MUTED_COLOR,
            no_wrap=False,
        )

        async def choose(_event: ft.Event[ft.TextButton]) -> None:
            if not self.button.disabled:
                await on_test(mechanism)

        self.button = ft.TextButton(
            tr(
                "local_protection.test_screen"
                if mechanism == "screen"
                else "local_protection.test_sleep"
            ),
            icon=ft.Icons.LOCK_OUTLINE
            if mechanism == "screen"
            else ft.Icons.BEDTIME_OUTLINED,
            height=48,
            style=secondary_button_style(),
            on_click=choose,
        )
        self.control = ft.Container(
            padding=16,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=12,
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=10,
                        controls=[
                            ft.Icon(
                                ft.Icons.LOCK_OUTLINE
                                if mechanism == "screen"
                                else ft.Icons.BEDTIME_OUTLINED,
                                size=20,
                                color=MUTED_COLOR,
                            ),
                            self.result,
                        ],
                    ),
                    self.details,
                    self.monitor,
                    self.explanation,
                    self.button,
                ],
            ),
        )

    def refresh(self, snapshot: ProtectionSnapshot, busy: bool) -> None:
        mechanism = self.mechanism
        result = snapshot.screen if mechanism == "screen" else snapshot.sleep
        history = (
            snapshot.screen_history if mechanism == "screen" else snapshot.sleep_history
        )
        self.result.value = mechanism_label(mechanism, result)
        # A saved success remains visible independently of a current warning.
        self.result.color = (
            ERROR_COLOR
            if result.state is CheckState.PROBLEM
            else SUCCESS_COLOR
            if result.state is CheckState.CONFIRMED
            else WARNING_COLOR
        )
        self.details.controls = [
            ft.Text(
                line,
                size=12,
                color=ERROR_COLOR
                if history is not None
                and history.state is CheckState.PROBLEM
                and line == previous_result_label(snapshot, mechanism)
                else MUTED_COLOR,
                no_wrap=False,
            )
            for line in mechanism_details(snapshot, mechanism)
        ]
        self.details.visible = bool(self.details.controls)
        self.monitor.value = mechanism_monitor_notice(snapshot, mechanism)
        self.monitor.color = (
            MUTED_COLOR if mechanism_ready(snapshot, mechanism) else WARNING_COLOR
        )
        self.button.disabled = busy or snapshot.test_running


class ProtectionPanel:
    """A non-secret view. Choosing and starting tests belongs to its caller.

    The panel never opens an authenticated session or requests an OS action.
    Its closure reason keeps an explicit handoff to the ordinary PIN distinct
    from Escape, an outside click and the visible Cancel/Close controls.
    """

    def __init__(
        self,
        page: ft.Page,
        *,
        on_test: TestCallback,
        on_start: TestCallback | None = None,
        on_close: Callable[[DismissReason], None] | None = None,
        locked: bool = False,
        desktop_tests: bool = True,
        platform_notice: str | None = None,
    ) -> None:
        self._page = page
        self._on_test = on_test
        self._on_start = on_start or on_test
        self._on_close = on_close
        self._locked = locked
        self._desktop_tests = desktop_tests
        self._snapshot: ProtectionSnapshot | None = None
        self._busy = False
        self._action_pending = False
        self._shield: ft.IconButton | None = None
        self._dialog: ft.AlertDialog | None = None
        self._notice: str | None = None
        self.selected_test: Mechanism | None = None
        self._confirm_test = False
        self._cards = {
            mechanism: _MechanismCard(mechanism, self._choose)
            for mechanism in ("screen", "sleep")
        }
        for card in self._cards.values():
            card.control.visible = desktop_tests
        self.screen_test_button = self._cards["screen"].button
        self.sleep_test_button = self._cards["sleep"].button
        self.subtitle = ft.Text(
            tr("protection_panel.subtitle"),
            size=12,
            color=MUTED_COLOR,
            visible=desktop_tests,
        )
        self.platform_notice = ft.Text(
            platform_notice or tr("protection_panel.android_policy"),
            no_wrap=False,
            visible=not desktop_tests,
        )
        self.locked_notice = ft.Text(
            tr("protection_panel.sign_in_explanation"),
            size=12,
            color=MUTED_COLOR,
            visible=locked and desktop_tests,
        )
        self.notice = ft.Text(size=12, color=WARNING_COLOR, visible=False)
        self.problem = ft.Text(color=ERROR_COLOR, visible=False)
        self.save_warning = ft.Text(
            tr("local_protection.save_failed"),
            size=12,
            color=WARNING_COLOR,
            visible=False,
        )
        self.selection_label = ft.Text(weight=ft.FontWeight.W_600)
        self.start_button = ft.Button(
            tr("protection_panel.start_test"),
            height=48,
            style=primary_button_style(),
            on_click=self._start,
        )
        self.cancel_button = ft.TextButton(
            tr("common.cancel"), height=48, on_click=self._dismiss_user
        )
        self.selection = ft.Container(
            padding=16,
            border_radius=12,
            bgcolor="#243F4A",
            visible=False,
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    self.selection_label,
                    ft.Text(tr("protection_panel.start_explanation"), size=12),
                    self.start_button,
                    self.cancel_button,
                ],
            ),
        )
        self.content = ft.ListView(
            spacing=12,
            padding=0,
            auto_scroll=False,
            controls=[
                self.subtitle,
                self.platform_notice,
                self.locked_notice,
                self.notice,
                self.problem,
                self.save_warning,
                self.selection,
                self._cards["screen"].control,
                self._cards["sleep"].control,
            ]
            if desktop_tests
            else [self.platform_notice],
        )
        self._container = ft.Container(content=self.content)
        self.close_button = ft.IconButton(
            icon=ft.Icons.CLOSE,
            tooltip=tr("protection_panel.close"),
            width=48,
            height=48,
            autofocus=True,
            on_click=self._dismiss_user,
        )

    @property
    def is_open(self) -> bool:
        return self._dialog is not None

    def open(
        self,
        snapshot: ProtectionSnapshot,
        *,
        shield: ft.IconButton | None = None,
        selected_test: Mechanism | None = None,
        confirm_test: bool = False,
        notice: str | None = None,
        busy: bool = False,
    ) -> None:
        self._shield = shield or self._shield
        self.set_context(
            selected_test=selected_test, confirm_test=confirm_test, notice=notice
        )
        self.refresh(snapshot, busy=busy)
        if self._dialog is not None:
            return
        dialog = ft.AlertDialog(
            modal=False,
            alignment=ft.Alignment.TOP_RIGHT,
            bgcolor=PANEL_BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=16),
            inset_padding=ft.Padding(12, 64, 12, 12),
            title_padding=ft.Padding(20, 4, 4, 4),
            content_padding=ft.Padding(20, 0, 20, 20),
            semantics_label=tr("session_watch.menu_title"),
            title=ft.Row(
                controls=[
                    ft.Text(
                        tr("session_watch.menu_title"),
                        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                        expand=True,
                    ),
                    self.close_button,
                ]
            ),
            content=self._container,
            on_dismiss=self._native_dismissed,
        )
        self._dialog = dialog
        self.resize()
        self._page.show_dialog(dialog)

    def set_context(
        self,
        *,
        locked: bool | None = None,
        selected_test: Mechanism | None = None,
        confirm_test: bool = False,
        notice: str | None = None,
    ) -> None:
        if locked is not None:
            self._locked = locked
        self.selected_test = selected_test
        self._confirm_test = (
            self._desktop_tests and confirm_test and selected_test is not None
        )
        self._notice = notice
        self.locked_notice.visible = self._locked and self._desktop_tests
        self.notice.value = fresh_text(notice) if notice else ""
        self.notice.visible = bool(notice)
        self.selection.visible = self._confirm_test
        self.selection_label.value = tr(
            "protection_panel.selected_screen"
            if selected_test == "screen"
            else "protection_panel.selected_sleep"
        )
        self._update()

    def refresh(self, snapshot: ProtectionSnapshot, *, busy: bool = False) -> None:
        self._snapshot = snapshot
        self._busy = busy
        localize_tree(self._dialog or self.content)
        for card in self._cards.values():
            card.refresh(snapshot, busy or self._action_pending)
        self.problem.value = protection_notice(snapshot) if snapshot.has_problem else ""
        self.problem.visible = snapshot.has_problem
        self.save_warning.visible = snapshot.persistence_error
        self.start_button.disabled = (
            busy or self._action_pending or snapshot.test_running or self._locked
        )
        self._update()

    def resize(self, width: float | None = None, height: float | None = None) -> None:
        available_width = width or getattr(self._page, "width", None) or 420
        available_height = height or getattr(self._page, "height", None) or 700
        self._container.width = max(160, min(400, available_width - 64))
        self._container.height = max(96, min(580, available_height - 172))
        self._update()

    def close(self, reason: DismissReason = "programmatic") -> None:
        dialog = self._dialog
        if dialog is None:
            return
        self._dialog = None
        dialog.open = False
        try:
            dialog.update()
        except (RuntimeError, AssertionError):
            pass
        if self._on_close is not None:
            self._on_close(reason)

    async def dismiss(self, reason: DismissReason = "user") -> None:
        self.close(reason)
        if reason == "user" and self._shield is not None:
            try:
                await self._shield.focus()
            except (RuntimeError, AssertionError):
                pass

    async def _dismiss_user(self, _event: ft.Event) -> None:
        await self.dismiss("user")

    async def _native_dismissed(self, event: ft.Event[ft.DialogControl]) -> None:
        if event.control is self._dialog:
            await self.dismiss("user")

    async def _choose(self, mechanism: Mechanism) -> None:
        snapshot = self._snapshot
        if (
            self._dialog is not None
            and self._desktop_tests
            and not self._busy
            and not self._action_pending
            and not (snapshot and snapshot.test_running)
        ):
            self._action_pending = True
            if snapshot is not None:
                self.refresh(snapshot, busy=self._busy)
            try:
                await self._on_test(mechanism)
            finally:
                self._action_pending = False
                if self._snapshot is not None:
                    self.refresh(self._snapshot, busy=self._busy)

    async def _start(self, _event: ft.Event[ft.Button]) -> None:
        if (
            self._dialog is not None
            and self._confirm_test
            and self.selected_test is not None
            and not self.start_button.disabled
        ):
            mechanism = self.selected_test
            self._action_pending = True
            if self._snapshot is not None:
                self.refresh(self._snapshot, busy=self._busy)
            try:
                await self._on_start(mechanism)
            finally:
                self._action_pending = False
                if self._snapshot is not None:
                    self.refresh(self._snapshot, busy=self._busy)

    def _update(self) -> None:
        if self._dialog is not None:
            try:
                self._dialog.update()
            except (RuntimeError, AssertionError):
                pass
