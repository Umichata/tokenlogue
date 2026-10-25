"""Экраны первичной настройки и локального PIN-входа."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from auth.pin import is_valid_pin
from i18n import LocalizedText, fresh_text, tr
from ui.branding import BrandHeader, BrandLoader
from ui.language_selector import LanguageSelector
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    SUCCESS_COLOR,
    build_screen,
    primary_button_style,
)

AsyncTextCallback = Callable[[str], Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


class _SecretTextField(ft.TextField):
    """Поле, которое никогда не раскрывает значение через repr."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(value=<redacted>)"


class KeyEntryView:
    """Форма безопасного ввода и проверки OpenRouter API-ключа."""

    def __init__(
        self, on_submit: AsyncTextCallback, *, replacement: bool = False
    ) -> None:
        self._on_submit = on_submit
        self._busy = False
        self.key_field = _SecretTextField(
            label=tr("auth.api_key"),
            hint_text=tr("auth.key_hint"),
            password=True,
            can_reveal_password=True,
            autocorrect=False,
            enable_suggestions=False,
            enable_ime_personalized_learning=False,
            enable_stylus_handwriting=False,
            smart_dashes_type=False,
            smart_quotes_type=False,
            autofocus=True,
            on_change=self._key_changed,
            on_submit=self._handle_submit,
        )
        self.message = ft.Text(visible=False)
        self.progress = BrandLoader(size=26, active=False)
        self.submit_button = ft.Button(
            tr("auth.check_key"),
            icon=ft.Icons.VERIFIED_USER,
            style=primary_button_style(),
            disabled=True,
            on_click=self._handle_click,
        )
        self.control = build_screen(
            [
                BrandHeader(),
                LanguageSelector(),
                ft.Text(
                    tr("auth.replacement_instructions")
                    if replacement
                    else tr("auth.key_instructions"),
                    color=MUTED_COLOR,
                ),
                ft.Container(
                    bgcolor=PANEL_BACKGROUND,
                    border_radius=16,
                    padding=20,
                    content=ft.Column(
                        spacing=16,
                        controls=[
                            self.key_field,
                            self.message,
                            ft.Row(
                                alignment=ft.MainAxisAlignment.CENTER,
                                controls=[self.progress, self.submit_button],
                            ),
                        ],
                    ),
                ),
            ]
        )

    async def _handle_click(self, _event: ft.Event[ft.Button]) -> None:
        await self._submit_value()

    async def _handle_submit(self, _event: ft.Event[ft.TextField]) -> None:
        await self._submit_value()

    async def _submit_value(self) -> None:
        if self._busy or self.submit_button.disabled:
            return
        value = self.key_field.value
        if not isinstance(value, str) or not value.strip():
            return
        await self._on_submit(value)

    def _key_changed(self, _event: ft.Event[ft.TextField]) -> None:
        self._apply_key_state()
        self.submit_button.update()

    def _apply_key_state(self) -> None:
        value = self.key_field.value
        has_value = isinstance(value, str) and bool(value.strip())
        self.submit_button.disabled = self._busy or not has_value

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.key_field.disabled = busy
        self.progress.set_active(busy)
        self._apply_key_state()

    def show_message(self, text: str, *, success: bool = False) -> None:
        self.message.value = fresh_text(text)
        self.message.color = SUCCESS_COLOR if success else ERROR_COLOR
        self.message.visible = bool(text)

    def clear_key(self) -> None:
        self.key_field.value = ""
        self._apply_key_state()

    def dispose(self) -> None:
        self.clear_key()
        self._busy = True
        self.progress.dispose()


class PinSetupView:
    """Редактируемый выбранный PIN и независимое подтверждение перед сохранением."""

    def __init__(
        self,
        notice: str,
        on_confirm: AsyncTextCallback,
        on_suggest: Callable[[], str],
        on_cancel: AsyncCallback,
        *,
        title: str | None = None,
        instructions: str | None = None,
        confirm_label: str | None = None,
    ) -> None:
        self._on_confirm = on_confirm
        self._on_suggest = on_suggest
        self._on_cancel = on_cancel
        self._busy = False
        self._disposed = False
        self.pin_field = self._pin_field("PIN", self._pin_changed)
        self.repeat_field = self._pin_field(tr("auth.repeat_pin"), self._repeat_changed)
        self.repeat_field.on_submit = self._confirm
        self.message = ft.Text(visible=False, color=ERROR_COLOR)
        self.progress = BrandLoader(size=26, active=False)
        self.suggest_button = ft.TextButton(
            tr("auth.suggest_pin"), icon=ft.Icons.CASINO, on_click=self._suggest
        )
        self.confirm_button = ft.Button(
            fresh_text(confirm_label)
            if confirm_label is not None
            else tr("auth.save_pin"),
            icon=ft.Icons.CHECK,
            style=primary_button_style(),
            disabled=True,
            on_click=self._confirm,
        )
        self.cancel_button = ft.TextButton(tr("common.back"), on_click=self._cancel)
        self.control = build_screen(
            [
                BrandHeader(),
                LanguageSelector(),
                ft.Text(
                    fresh_text(title) if title is not None else tr("auth.choose_pin"),
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                ),
                ft.Text(
                    fresh_text(instructions)
                    if instructions is not None
                    else tr("auth.pin_instructions"),
                    color=MUTED_COLOR,
                ),
                ft.Container(
                    bgcolor=PANEL_BACKGROUND,
                    border_radius=16,
                    padding=20,
                    content=ft.Column(
                        spacing=16,
                        controls=[
                            ft.Text(
                                fresh_text(notice),
                                color=SUCCESS_COLOR,
                                visible=bool(notice),
                            ),
                            self.pin_field,
                            self.suggest_button,
                            self.repeat_field,
                            self.message,
                            ft.Row(controls=[self.progress, self.confirm_button]),
                            self.cancel_button,
                        ],
                    ),
                ),
            ]
        )

    @staticmethod
    def _pin_field(label: str, on_change: Callable) -> _SecretTextField:
        return _SecretTextField(
            label=label,
            password=True,
            can_reveal_password=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=4,
            autocorrect=False,
            enable_suggestions=False,
            enable_ime_personalized_learning=False,
            enable_stylus_handwriting=False,
            smart_dashes_type=False,
            smart_quotes_type=False,
            on_change=on_change,
        )

    def _values_match(self) -> bool:
        pin = self.pin_field.value
        return (
            isinstance(pin, str)
            and is_valid_pin(pin)
            and pin == self.repeat_field.value
        )

    def _apply_pin_state(self) -> None:
        self.confirm_button.disabled = (
            self._busy or self._disposed or not self._values_match()
        )
        self.pin_field.disabled = self._busy
        self.repeat_field.disabled = self._busy
        self.suggest_button.disabled = self._busy
        self.cancel_button.disabled = self._busy

    def _pin_changed(self, _event: ft.Event[ft.TextField]) -> None:
        if self._busy or self._disposed:
            return
        self.repeat_field.value = ""
        self.show_message("")
        self._apply_pin_state()
        self.repeat_field.update()
        self.confirm_button.update()
        self.message.update()

    def _repeat_changed(self, _event: ft.Event[ft.TextField]) -> None:
        if self._busy or self._disposed:
            return
        if self.repeat_field.value and not self._values_match():
            self.show_message(tr("auth.pin_mismatch"))
        else:
            self.show_message("")
        self._apply_pin_state()
        self.confirm_button.update()
        self.message.update()

    def _suggest(self, _event: ft.Event[ft.TextButton]) -> None:
        if self._busy or self._disposed:
            return
        self.pin_field.value = self._on_suggest()
        self.repeat_field.value = ""
        self.show_message("")
        self._apply_pin_state()
        self.pin_field.update()
        self.repeat_field.update()
        self.message.update()
        self.confirm_button.update()

    async def _confirm(self, _event: ft.Event) -> None:
        await self._submit_value()

    async def _submit_value(self) -> None:
        if self._busy or self._disposed or not self._values_match():
            return
        pin = self.pin_field.value
        assert isinstance(pin, str)
        self.set_busy(True)
        try:
            await self._on_confirm(pin)
        finally:
            if not self._disposed:
                self.set_busy(False)

    async def _cancel(self, _event: ft.Event) -> None:
        if self._busy or self._disposed:
            return
        self.clear_pin()
        await self._on_cancel()

    def show_message(self, message: str) -> None:
        self.message.value = fresh_text(message)
        self.message.visible = bool(message)

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.set_active(busy)
        self._apply_pin_state()

    def clear_pin(self) -> None:
        self.pin_field.value = ""
        self.repeat_field.value = ""
        self._apply_pin_state()

    def dispose(self) -> None:
        self._disposed = True
        self.clear_pin()
        self.progress.dispose()


class PinLoginView:
    """Форма четырёхзначного PIN и подтверждаемого сброса ключа."""

    def __init__(
        self,
        on_submit: AsyncTextCallback,
        on_reset_requested: AsyncCallback,
        *,
        on_forgot_pin: AsyncCallback | None = None,
        notice: str = "",
    ) -> None:
        self._on_submit = on_submit
        self._on_forgot_pin = on_forgot_pin
        self._disposed = False
        self._on_reset_requested = on_reset_requested
        self._busy = False
        self._locked = False
        self.pin_field = _SecretTextField(
            label="PIN",
            password=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
            max_length=4,
            text_align=ft.TextAlign.CENTER,
            autofocus=True,
            autocorrect=False,
            enable_suggestions=False,
            enable_ime_personalized_learning=False,
            on_change=self._pin_changed,
            on_submit=self._handle_submit,
        )
        self.message = ft.Text(visible=False)
        self.submit_button = ft.Button(
            tr("auth.sign_in"),
            icon=ft.Icons.LOCK_OPEN,
            style=primary_button_style(),
            disabled=True,
            on_click=self._handle_click,
        )
        self.reset_button = ft.TextButton(
            tr("auth.reset_key"),
            icon=ft.Icons.RESTART_ALT,
            on_click=self._request_reset,
        )
        self.forgot_pin_button = (
            ft.TextButton(tr("recovery.forgot_pin"), on_click=self._request_recovery)
            if on_forgot_pin is not None
            else None
        )
        self.progress = BrandLoader(size=26, active=False)
        self.control = build_screen(
            [
                BrandHeader(),
                LanguageSelector(),
                ft.Text(tr("auth.enter_pin"), color=MUTED_COLOR),
                *([ft.Text(fresh_text(notice), color=MUTED_COLOR)] if notice else []),
                ft.Container(
                    bgcolor=PANEL_BACKGROUND,
                    border_radius=16,
                    padding=20,
                    content=ft.Column(
                        spacing=16,
                        controls=[
                            self.pin_field,
                            self.message,
                            self.progress,
                            self.submit_button,
                            self.reset_button,
                            *(
                                [self.forgot_pin_button]
                                if self.forgot_pin_button is not None
                                else []
                            ),
                        ],
                    ),
                ),
            ]
        )

    async def _handle_click(self, _event: ft.Event[ft.Button]) -> None:
        await self._submit_value()

    async def _handle_submit(self, _event: ft.Event[ft.TextField]) -> None:
        await self._submit_value()

    async def _submit_value(self) -> None:
        if self._busy or self._locked or self.submit_button.disabled:
            return
        value = self.pin_field.value
        if not isinstance(value, str):
            return
        await self._on_submit(value)

    def _pin_changed(self, _event: ft.Event[ft.TextField]) -> None:
        self._apply_pin_state()
        self.submit_button.update()

    def _apply_pin_state(self) -> None:
        pin = self.pin_field.value
        is_complete = (
            isinstance(pin, str) and len(pin) == 4 and pin.isascii() and pin.isdigit()
        )
        self.pin_field.disabled = self._busy or self._locked
        self.submit_button.disabled = self._busy or self._locked or not is_complete

    async def _request_recovery(self, _event: ft.Event) -> None:
        if self._disposed or self._busy or self._on_forgot_pin is None:
            return
        self.set_busy(True)
        try:
            await self._on_forgot_pin()
        finally:
            if not self._disposed:
                self.set_busy(False)

    async def _request_reset(self, _event: ft.Event[ft.TextButton]) -> None:
        await self._on_reset_requested()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.set_active(busy)
        self.reset_button.disabled = busy
        if self.forgot_pin_button is not None:
            self.forgot_pin_button.disabled = busy
        self._apply_pin_state()

    def set_locked(self, seconds: int) -> None:
        self._locked = seconds > 0
        self._apply_pin_state()
        if self._locked:
            self.show_message(tr("auth.lock_seconds", seconds=seconds))
        elif (
            isinstance(self.message.value, LocalizedText)
            and self.message.value.key == "auth.lock_seconds"
        ):
            self.show_message(tr("auth.lock_expired"), success=True)

    def show_message(self, text: str, *, success: bool = False) -> None:
        self.message.value = fresh_text(text)
        self.message.color = SUCCESS_COLOR if success else ERROR_COLOR
        self.message.visible = bool(text)

    def clear_pin(self) -> None:
        self.pin_field.value = ""
        self._apply_pin_state()

    def dispose(self) -> None:
        self._disposed = True
        self.clear_pin()
        self._busy = True
        self.progress.dispose()


class DeviceRecoveryView:
    """Ожидание отдельной системной проверки без доступа к сохранённым чатам."""

    def __init__(
        self,
        on_retry: AsyncCallback,
        on_cancel: AsyncCallback,
        *,
        message: str = "",
        busy: bool = False,
    ) -> None:
        self._on_retry = on_retry
        self._on_cancel = on_cancel
        self._busy = busy
        self._disposed = False
        self._cancel_pending = False
        self.message = ft.Text(
            fresh_text(message), visible=bool(message), color=ERROR_COLOR
        )
        self.progress = BrandLoader(size=26, active=busy)
        self.waiting = ft.Text(tr("recovery.waiting"), visible=busy, color=MUTED_COLOR)
        self.retry_button = ft.Button(
            tr("recovery.confirm_device"),
            icon=ft.Icons.VERIFIED_USER,
            disabled=busy,
            on_click=self._retry,
            style=primary_button_style(),
        )
        self.cancel_button = ft.TextButton(tr("recovery.cancel"), on_click=self._cancel)
        self.control = build_screen(
            [
                BrandHeader(),
                LanguageSelector(),
                ft.Text(
                    tr("recovery.title"), theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM
                ),
                ft.Text(tr("recovery.explanation"), color=MUTED_COLOR),
                self.message,
                ft.Row(controls=[self.progress]),
                self.waiting,
                self.retry_button,
                self.cancel_button,
                ft.Text(tr("recovery.cancel_notice"), color=MUTED_COLOR),
            ]
        )

    async def _retry(self, _event: ft.Event) -> None:
        if self._disposed or self._busy or self._cancel_pending:
            return
        self.set_busy(True)
        try:
            await self._on_retry()
        finally:
            if not self._disposed:
                self.set_busy(False)

    async def _cancel(self, _event: ft.Event) -> None:
        if self._disposed or self._cancel_pending:
            return
        self._cancel_pending = True
        self.cancel_button.disabled = True
        try:
            await self._on_cancel()
        finally:
            if not self._disposed:
                self._cancel_pending = False
                self.cancel_button.disabled = False

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.retry_button.disabled = busy or self._disposed or self._cancel_pending
        self.progress.set_active(busy and not self._disposed)
        self.waiting.visible = busy

    def show_message(self, message: str) -> None:
        self.message.value = fresh_text(message)
        self.message.visible = bool(message)

    def dispose(self) -> None:
        self._disposed = True
        self.retry_button.disabled = True
        self.cancel_button.disabled = True
        self.progress.dispose()


class StorageErrorView:
    """Блокирующий экран при недоступности локального хранилища."""

    def __init__(self, message: str, on_retry: AsyncCallback) -> None:
        self._on_retry = on_retry
        self.retry_button = ft.Button(tr("common.retry"), on_click=self._retry)
        self.control = build_screen(
            [
                BrandHeader(),
                LanguageSelector(),
                ft.Text(
                    tr("auth.storage_unavailable"),
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                ),
                ft.Text(fresh_text(message), color=ERROR_COLOR),
                self.retry_button,
            ]
        )

    async def _retry(self, _event: ft.Event[ft.Button]) -> None:
        if self.retry_button.disabled:
            return
        self.retry_button.disabled = True
        self.retry_button.update()
        await self._on_retry()


def build_reset_dialog(
    on_confirm: AsyncCallback,
    on_cancel: Callable[[], None],
    *,
    title: str | None = None,
    message: str | None = None,
    confirm_label: str | None = None,
) -> ft.AlertDialog:
    """Создаёт явное подтверждение удаления данных аутентификации."""

    async def handle_confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm()

    def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    actions: list[ft.Control] = [
        ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
        ft.Button(
            fresh_text(confirm_label)
            if confirm_label is not None
            else tr("auth.reset"),
            bgcolor=ERROR_COLOR,
            on_click=handle_confirm,
        ),
    ]
    return ft.AlertDialog(
        modal=True,
        title=ft.Text(
            fresh_text(title) if title is not None else tr("auth.reset_title")
        ),
        content=ft.Text(
            fresh_text(message) if message is not None else tr("auth.reset_body")
        ),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )
