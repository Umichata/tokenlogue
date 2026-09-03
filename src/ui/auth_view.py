"""Экраны первичной настройки и локального PIN-входа."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

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


class _SecretText(ft.Text):
    """Текст, который никогда не раскрывает значение через repr."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}(value=<redacted>)"


class KeyEntryView:
    """Форма безопасного ввода и проверки OpenRouter API-ключа."""

    def __init__(self, on_submit: AsyncTextCallback) -> None:
        self._on_submit = on_submit
        self._busy = False
        self.key_field = _SecretTextField(
            label="OpenRouter API-ключ",
            hint_text="Введите ключ",
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
        self.progress = ft.ProgressRing(visible=False)
        self.submit_button = ft.Button(
            "Проверить ключ",
            icon=ft.Icons.VERIFIED_USER,
            style=primary_button_style(),
            disabled=True,
            on_click=self._handle_click,
        )
        self.control = build_screen(
            [
                ft.Text("Tokenlogue", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                ft.Text(
                    "Введите OpenRouter API-ключ. Он будет сохранён "
                    "только после подтверждения созданного PIN.",
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
        self.progress.visible = busy
        self._apply_key_state()

    def show_message(self, text: str, *, success: bool = False) -> None:
        self.message.value = text
        self.message.color = SUCCESS_COLOR if success else ERROR_COLOR
        self.message.visible = bool(text)

    def clear_key(self) -> None:
        self.key_field.value = ""
        self._apply_key_state()


class PinDisplayView:
    """Показывает сгенерированный PIN до единственного подтверждения."""

    def __init__(
        self,
        pin: str,
        notice: str,
        on_confirm: AsyncCallback,
    ) -> None:
        self._on_confirm = on_confirm
        self.pin_text = _SecretText(
            pin,
            size=42,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )
        self.message = ft.Text(notice, color=SUCCESS_COLOR)
        self.progress = ft.ProgressRing(visible=False)
        self.confirm_button = ft.Button(
            "Я сохранил PIN",
            icon=ft.Icons.CHECK,
            style=primary_button_style(),
            on_click=self._confirm,
        )
        self.control = build_screen(
            [
                ft.Text("Сохраните PIN", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
                ft.Text(
                    "PIN показывается один раз. Он понадобится при следующем запуске.",
                    color=MUTED_COLOR,
                ),
                ft.Container(
                    bgcolor=PANEL_BACKGROUND,
                    border_radius=16,
                    padding=20,
                    content=ft.Column(
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=18,
                        controls=[
                            self.pin_text,
                            self.message,
                            self.progress,
                            self.confirm_button,
                        ],
                    ),
                ),
            ]
        )

    async def _confirm(self, _event: ft.Event[ft.Button]) -> None:
        await self._on_confirm()

    def hide_pin(self) -> None:
        self.pin_text.value = "••••"

    def set_busy(self, busy: bool) -> None:
        self.confirm_button.disabled = busy
        self.progress.visible = busy


class PinLoginView:
    """Форма четырёхзначного PIN и подтверждаемого сброса ключа."""

    def __init__(
        self,
        on_submit: AsyncTextCallback,
        on_reset_requested: AsyncCallback,
    ) -> None:
        self._on_submit = on_submit
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
            "Войти",
            icon=ft.Icons.LOCK_OPEN,
            style=primary_button_style(),
            disabled=True,
            on_click=self._handle_click,
        )
        self.reset_button = ft.TextButton(
            "Сбросить ключ",
            icon=ft.Icons.RESTART_ALT,
            on_click=self._request_reset,
        )
        self.progress = ft.ProgressRing(visible=False)
        self.control = build_screen(
            [
                ft.Text(
                    "Вход в Tokenlogue",
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                ),
                ft.Text("Введите сохранённый четырёхзначный PIN.", color=MUTED_COLOR),
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

    async def _request_reset(self, _event: ft.Event[ft.TextButton]) -> None:
        await self._on_reset_requested()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.progress.visible = busy
        self.reset_button.disabled = busy
        self._apply_pin_state()

    def set_locked(self, seconds: int) -> None:
        self._locked = seconds > 0
        self._apply_pin_state()
        if self._locked:
            self.show_message(f"Слишком много попыток. Повторите через {seconds} сек.")
        elif self.message.value.startswith("Слишком много попыток"):
            self.show_message("Блокировка снята. Введите PIN.", success=True)

    def show_message(self, text: str, *, success: bool = False) -> None:
        self.message.value = text
        self.message.color = SUCCESS_COLOR if success else ERROR_COLOR
        self.message.visible = bool(text)

    def clear_pin(self) -> None:
        self.pin_field.value = ""
        self._apply_pin_state()


class StorageErrorView:
    """Блокирующий экран при недоступности локального хранилища."""

    def __init__(self, message: str, on_retry: AsyncCallback) -> None:
        self._on_retry = on_retry
        self.retry_button = ft.Button("Повторить", on_click=self._retry)
        self.control = build_screen(
            [
                ft.Text(
                    "Хранилище недоступно",
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                ),
                ft.Text(message, color=ERROR_COLOR),
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
) -> ft.AlertDialog:
    """Создаёт явное подтверждение удаления данных аутентификации."""

    async def handle_confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm()

    def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    actions: list[ft.Control] = [
        ft.TextButton("Отмена", on_click=handle_cancel),
        ft.Button("Сбросить", bgcolor=ERROR_COLOR, on_click=handle_confirm),
    ]
    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Сбросить ключ?"),
        content=ft.Text(
            "Будут удалены сохранённый API-ключ, PIN и состояние блокировки."
        ),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )
