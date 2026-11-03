"""Явная выдача и ввод резервного кода без системного пароля."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from auth.pin import is_valid_pin
from i18n import fresh_text, tr
from ui.branding import AuthHeader, BrandLoader
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    WARNING_COLOR,
    build_auth_screen,
    input_style,
    primary_button_style,
    secondary_button_style,
)

AsyncTextCallback = Callable[[str], Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


class _SecretTextField(ft.TextField):
    """Скрывает введённое значение в обычном диагностическом представлении."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(value=<redacted>)"


class _SecretText(ft.Text):
    def __repr__(self) -> str:
        return f"{type(self).__name__}(value=<redacted>)"


class _SecretInputView:
    def __init__(
        self,
        on_submit: AsyncTextCallback,
        on_cancel: AsyncCallback,
        *,
        title: str,
        instructions: str,
        label: str,
        submit_label: str,
        max_length: int = 128,
        enabled: bool = True,
        valid: Callable[[str], bool] = bool,
        before_field: list[ft.Control] | None = None,
        after_field: list[ft.Control] | None = None,
        protection_notice: str = "",
    ) -> None:
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._enabled = enabled
        self._valid = valid
        self._busy = False
        self._locked = False
        self._disposed = False
        self._cancel_pending = False
        self._field = _SecretTextField(
            **input_style(),
            label=label,
            password=True,
            can_reveal_password=True,
            max_length=max_length,
            autocorrect=False,
            enable_suggestions=False,
            enable_ime_personalized_learning=False,
            enable_stylus_handwriting=False,
            smart_dashes_type=False,
            smart_quotes_type=False,
            visible=enabled,
            disabled=not enabled,
            on_change=self._changed,
            on_submit=self._submit,
        )
        self.message = ft.Text(visible=False, color=ERROR_COLOR)
        self.progress = BrandLoader(size=26, active=False)
        self.submit_button = ft.Button(
            submit_label,
            disabled=True,
            style=primary_button_style(),
            on_click=self._submit,
        )
        self.cancel_button = ft.TextButton(tr("common.back"), on_click=self._cancel)
        self.protection_notice = ft.Text(
            fresh_text(protection_notice),
            color=WARNING_COLOR,
            visible=bool(protection_notice),
        )
        self.cancel_button.style = secondary_button_style()
        self.header = AuthHeader()
        self.control = build_auth_screen(
            [
                ft.Text(title, theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                ft.Text(instructions, color=MUTED_COLOR),
                self.protection_notice,
                *(before_field or []),
                self._field,
                self.message,
                ft.Row(alignment=ft.MainAxisAlignment.CENTER, controls=[self.progress]),
                self.submit_button,
                *(after_field or []),
                self.cancel_button,
            ],
            header=self.header,
        )

    def _apply_state(self) -> None:
        value = self._field.value
        unavailable = (
            self._busy or self._locked or self._disposed or self._cancel_pending
        )
        self._field.disabled = unavailable or not self._enabled
        self.submit_button.disabled = (
            unavailable
            or not self._enabled
            or not isinstance(value, str)
            or not self._valid(value)
        )

    def _changed(self, _event: ft.Event) -> None:
        self._apply_state()
        self.submit_button.update()

    async def _submit(self, _event: ft.Event) -> None:
        await self._submit_value()

    async def _submit_value(self) -> None:
        self._apply_state()
        if self.submit_button.disabled:
            return
        value = self._field.value
        if not isinstance(value, str):
            return
        self.set_busy(True)
        try:
            await self._on_submit(value)
        finally:
            if not self._disposed:
                self.set_busy(False)

    async def _cancel(self, _event: ft.Event) -> None:
        if self._disposed or self._cancel_pending:
            return
        self._cancel_pending = True
        self.clear_secret()
        self.cancel_button.disabled = True
        self._apply_state()
        try:
            await self._on_cancel()
        finally:
            if not self._disposed:
                self._cancel_pending = False
                self.cancel_button.disabled = False
                self._apply_state()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.set_active(busy and not self._disposed)
        self._apply_state()

    def show_message(self, message: str) -> None:
        self.message.value = fresh_text(message)
        self.message.visible = bool(message)

    def set_protection_notice(self, notice: str) -> None:
        self.protection_notice.value = fresh_text(notice)
        self.protection_notice.visible = bool(notice)

    def clear_secret(self) -> None:
        self._field.value = ""
        self._apply_state()

    def dispose(self) -> None:
        self._disposed = True
        self.clear_secret()
        self.cancel_button.disabled = True
        self.progress.dispose()


class RecoveryCodeEntryView(_SecretInputView):
    """Основной Linux-путь с отдельным явно выбранным системным способом."""

    def __init__(
        self,
        on_submit: AsyncTextCallback,
        on_cancel: AsyncCallback,
        *,
        enrolled: bool,
        on_system_recovery: AsyncCallback | None = None,
        message: str = "",
    ) -> None:
        self._on_system_recovery = on_system_recovery
        self.system_button = (
            ft.TextButton(
                tr("recovery_code.system_optional"),
                on_click=self._system_recovery,
                style=secondary_button_style(),
            )
            if on_system_recovery is not None
            else None
        )
        super().__init__(
            on_submit,
            on_cancel,
            title=tr("recovery_code.enter_title"),
            instructions=tr(
                "recovery_code.enter_instructions"
                if enrolled
                else "recovery_code.not_enrolled"
            ),
            label=tr("recovery_code.code_label"),
            submit_label=tr("recovery_code.verify"),
            enabled=enrolled,
            after_field=[self.system_button] if self.system_button is not None else [],
        )
        self.code_field = self._field
        self.show_message(message)

    async def _system_recovery(self, _event: ft.Event) -> None:
        if (
            self._disposed
            or self._busy
            or self._cancel_pending
            or self._on_system_recovery is None
        ):
            return
        self.clear_secret()
        self.set_busy(True)
        try:
            await self._on_system_recovery()
        finally:
            if not self._disposed:
                self.set_busy(False)

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        if self.system_button is not None:
            self.system_button.disabled = busy or self._disposed or self._cancel_pending

    def dispose(self) -> None:
        super().dispose()
        if self.system_button is not None:
            self.system_button.disabled = True


class RecoveryCodePinView(_SecretInputView):
    """Повторный ввод действующего PIN перед выдачей или перевыпуском."""

    def __init__(
        self,
        on_confirm: AsyncTextCallback,
        on_cancel: AsyncCallback,
        *,
        protection_notice: str = "",
    ) -> None:
        super().__init__(
            on_confirm,
            on_cancel,
            title=tr("recovery_code.settings"),
            instructions=tr("recovery_code.confirm_pin_instructions"),
            label="PIN",
            submit_label=tr("recovery_code.generate"),
            max_length=4,
            valid=is_valid_pin,
            protection_notice=protection_notice,
        )
        self.pin_field = self._field
        self.pin_field.keyboard_type = ft.KeyboardType.NUMBER
        self.pin_field.input_filter = ft.NumbersOnlyInputFilter()
        self.confirm_button = self.submit_button

    def set_locked(self, seconds: int) -> None:
        was_locked = self._locked
        self._locked = seconds > 0
        self._apply_state()
        if self._locked:
            self.show_message(
                tr(
                    "auth.lock_countdown",
                    time=f"{seconds // 60:02d}:{seconds % 60:02d}",
                )
            )
        elif was_locked:
            self.show_message(tr("auth.lock_expired"))


class RecoveryCodeDisplayView(_SecretInputView):
    """Однократный показ с подтверждением сохранения повторным вводом."""

    def __init__(
        self,
        code: str,
        on_confirm: AsyncTextCallback,
        on_cancel: AsyncCallback,
        *,
        on_copy: AsyncTextCallback | None = None,
        protection_notice: str = "",
    ) -> None:
        self._code = code
        self._on_copy = on_copy
        self._copy_pending = False
        self.code_text = _SecretText(
            code.replace("-", " "),
            font_family="monospace",
            size=24,
            selectable=True,
            no_wrap=False,
        )
        self.copy_button = (
            ft.TextButton(
                tr("recovery_code.copy"),
                on_click=self._copy,
                style=secondary_button_style(),
            )
            if on_copy is not None
            else None
        )
        before: list[ft.Control] = [self.code_text]
        if self.copy_button is not None:
            before.append(self.copy_button)
            before.append(
                ft.Text(tr("recovery_code.clipboard_notice"), color=MUTED_COLOR)
            )
        super().__init__(
            on_confirm,
            on_cancel,
            title=tr("recovery_code.save_title"),
            instructions=tr("recovery_code.save_instructions"),
            label=tr("recovery_code.repeat_label"),
            submit_label=tr("recovery_code.confirm_saved"),
            before_field=before,
            protection_notice=protection_notice,
        )
        self.repeat_field = self._field
        self.confirm_button = self.submit_button

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code=<redacted>)"

    async def _copy(self, _event: ft.Event) -> None:
        if (
            self._disposed
            or self._busy
            or self._cancel_pending
            or self._copy_pending
            or self._on_copy is None
            or not self._code
        ):
            return
        self._copy_pending = True
        assert self.copy_button is not None
        self.copy_button.disabled = True
        try:
            await self._on_copy(self._code)
        finally:
            self._copy_pending = False
            if not self._disposed:
                self.copy_button.disabled = self._busy or self._cancel_pending

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        if self.copy_button is not None:
            self.copy_button.disabled = (
                busy or self._disposed or self._cancel_pending or self._copy_pending
            )

    def clear_secret(self) -> None:
        super().clear_secret()
        self._code = ""
        self.code_text.value = ""

    def dispose(self) -> None:
        super().dispose()
        if self.copy_button is not None:
            self.copy_button.disabled = True
