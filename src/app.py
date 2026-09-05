"""Контроллер аутентификации и жизненного цикла приложения."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future

import flet as ft

from api.models import ModelCatalogService
from auth.contracts import KeyValidator
from auth.models import (
    AuthResult,
    AuthStatus,
    InitialRoute,
    KeyLimitInfo,
    KeyValidityState,
)
from auth.service import AuthService
from chat.accounting import ChatBudgetService
from chat.drafts import ChatDraftService
from chat.sending import MessageSendingService
from chat.service import ChatService
from chat_controller import ChatSessionController
from ui import (
    KeyEntryView,
    PinDisplayView,
    PinLoginView,
    StorageErrorView,
    build_reset_dialog,
)


class AppController:
    """Управляет аутентификацией и передаёт разблокированную сессию чатам."""

    def __init__(
        self,
        page: ft.Page,
        auth_service: AuthService,
        key_validator: KeyValidator,
        chat_service: ChatService,
        catalog_service: ModelCatalogService,
        budget_service: ChatBudgetService,
        sending_service: MessageSendingService,
        drafts: ChatDraftService,
    ) -> None:
        self._page = page
        self._auth_service = auth_service
        self._chat_controller = ChatSessionController(
            page,
            key_validator,
            chat_service,
            catalog_service,
            budget_service,
            sending_service,
            drafts,
            on_lock=self._handle_chat_lock,
            on_replace_key=self.request_reset,
            on_storage_error=self._show_storage_error,
        )
        self._key_view: KeyEntryView | None = None
        self._pin_display_view: PinDisplayView | None = None
        self._pin_login_view: PinLoginView | None = None
        self._lock_task: Future[None] | None = None
        self._operation_lock = asyncio.Lock()
        self._reset_dialog_open = False
        self._disposed = False

    async def start(self) -> None:
        if self._disposed or self._operation_lock.locked():
            return
        async with self._operation_lock:
            result = await self._auth_service.initialize()
            if self._disposed:
                return
            if result.initial_route is InitialRoute.SETUP:
                self._show_key_entry(result.message)
            elif result.initial_route is InitialRoute.PIN:
                self._show_pin_login(result.message, result.lock_seconds_remaining)
            else:
                self._show_storage_error(result.message)

    async def submit_key(self, api_key: str) -> None:
        view = self._key_view
        if self._disposed or view is None or self._operation_lock.locked():
            return
        async with self._operation_lock:
            if self._key_view is not view:
                return
            view.set_busy(True)
            view.show_message("")
            self._page.update()

            result = await self._auth_service.start_setup(api_key)
            if self._disposed or self._key_view is not view:
                self._auth_service.cancel_pending_setup()
                return
            view.set_busy(False)
            if result.pin is not None:
                view.clear_key()
                self._show_pin_display(result)
                return
            view.show_message(result.message)
            self._page.update()

    async def confirm_pin_saved(self) -> None:
        view = self._pin_display_view
        if self._disposed or view is None or self._operation_lock.locked():
            return
        async with self._operation_lock:
            if self._pin_display_view is not view:
                return
            view.hide_pin()
            view.set_busy(True)
            self._page.update()

            result = await self._auth_service.complete_setup()
            if self._disposed or self._pin_display_view is not view:
                return
            if result.status is AuthStatus.AUTHENTICATED and result.api_key is not None:
                await self._activate_session(
                    result.api_key,
                    result.key_validity,
                    result.key_limit,
                )
                return
            self._show_key_entry(result.message)

    async def submit_pin(self, pin: str) -> None:
        view = self._pin_login_view
        if self._disposed or view is None or self._operation_lock.locked():
            return
        async with self._operation_lock:
            if self._pin_login_view is not view:
                return
            view.set_busy(True)
            view.show_message("")
            self._page.update()

            result = await self._auth_service.login(pin)
            if self._disposed or self._pin_login_view is not view:
                return
            view.set_busy(False)
            view.clear_pin()
            if result.status is AuthStatus.AUTHENTICATED and result.api_key is not None:
                await self._activate_session(
                    result.api_key,
                    result.key_validity,
                    result.key_limit,
                )
                return
            if result.status is AuthStatus.SETUP_REQUIRED:
                self._show_key_entry(result.message)
                return
            view.show_message(result.message)
            if result.status is AuthStatus.LOCKED:
                self._start_lock_countdown(view, result.lock_seconds_remaining)
            self._page.update()

    async def request_reset(self) -> None:
        if (
            self._disposed
            or self._reset_dialog_open
            or self._operation_lock.locked()
            or (
                self._pin_login_view is None
                and not self._chat_controller.session_active
            )
        ):
            return
        self._reset_dialog_open = True
        dialog = build_reset_dialog(
            on_confirm=self.confirm_reset,
            on_cancel=self.cancel_reset,
        )
        self._page.show_dialog(dialog)

    async def confirm_reset(self) -> None:
        if self._disposed or not self._reset_dialog_open:
            return
        self._reset_dialog_open = False
        self._page.pop_dialog()
        if self._operation_lock.locked():
            return

        view = self._pin_login_view
        chat_was_active = self._chat_controller.session_active
        if view is None and not chat_was_active:
            return
        if chat_was_active:
            self._chat_controller.deactivate()
        async with self._operation_lock:
            if view is not None:
                if self._pin_login_view is not view:
                    return
                view.set_busy(True)
                self._page.update()
            result = await self._auth_service.reset_authentication()
            if self._disposed:
                return
            if result.status is AuthStatus.SETUP_REQUIRED:
                self._show_key_entry(result.message, success=True)
            elif view is not None and self._pin_login_view is view:
                view.set_busy(False)
                view.show_message(result.message)
                self._page.update()
            else:
                self._show_storage_error(result.message)

    def cancel_reset(self) -> None:
        if not self._reset_dialog_open:
            return
        self._reset_dialog_open = False
        self._page.pop_dialog()

    async def lock_application(self) -> None:
        """Делегирует безопасную блокировку активной чат-сессии."""
        await self._chat_controller.lock_application()

    def dispose(self) -> None:
        """Удаляет секретные значения и останавливает фоновые UI-задачи."""
        if self._disposed:
            return
        self._disposed = True
        self._cancel_lock_task()
        self._auth_service.cancel_pending_setup()
        self._clear_secret_controls()
        self._chat_controller.dispose()

    async def flush_drafts(self) -> bool:
        return await self._chat_controller.flush_drafts()

    async def _activate_session(
        self,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
    ) -> None:
        self._cancel_lock_task()
        self._clear_secret_controls()
        self._key_view = None
        self._pin_display_view = None
        self._pin_login_view = None
        await self._chat_controller.activate(api_key, key_validity, key_limit)

    async def _handle_chat_lock(self) -> None:
        if not self._disposed:
            self._show_pin_login("Приложение заблокировано. Введите PIN.")

    def _show_key_entry(self, message: str = "", *, success: bool = False) -> None:
        self._cancel_lock_task()
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._pin_login_view = None
        self._pin_display_view = None
        self._key_view = KeyEntryView(self.submit_key)
        if message:
            self._key_view.show_message(message, success=success)
        self._replace_page(self._key_view.control)

    def _show_pin_display(self, result: AuthResult) -> None:
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = None
        self._pin_login_view = None
        self._pin_display_view = PinDisplayView(
            result.pin or "",
            result.message,
            self.confirm_pin_saved,
        )
        self._replace_page(self._pin_display_view.control)

    def _show_pin_login(self, message: str = "", lock_seconds: int = 0) -> None:
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = None
        self._pin_display_view = None
        view = PinLoginView(self.submit_pin, self.request_reset)
        self._pin_login_view = view
        if message:
            view.show_message(message)
        self._replace_page(view.control)
        if lock_seconds > 0:
            self._start_lock_countdown(view, lock_seconds)

    def _show_storage_error(self, message: str) -> None:
        self._chat_controller.deactivate()
        view = StorageErrorView(
            message or "Не удалось открыть локальное хранилище.",
            self.start,
        )
        self._replace_page(view.control)

    def _replace_page(self, control: ft.Control) -> None:
        if self._disposed:
            return
        self._page.controls.clear()
        self._page.add(control)

    def _clear_secret_controls(self) -> None:
        if self._key_view is not None:
            self._key_view.clear_key()
        if self._pin_display_view is not None:
            self._pin_display_view.hide_pin()
        if self._pin_login_view is not None:
            self._pin_login_view.clear_pin()

    def _start_lock_countdown(self, view: PinLoginView, seconds: int) -> None:
        self._cancel_lock_task()
        self._lock_task = self._page.run_task(self._lock_countdown, view, seconds)

    async def _lock_countdown(self, view: PinLoginView, seconds: int) -> None:
        for remaining in range(seconds, 0, -1):
            if self._disposed or self._pin_login_view is not view:
                return
            view.set_locked(remaining)
            self._page.update()
            await asyncio.sleep(1)
        if not self._disposed and self._pin_login_view is view:
            view.set_locked(0)
            self._page.update()

    def _cancel_lock_task(self) -> None:
        if self._lock_task is not None and not self._lock_task.done():
            self._lock_task.cancel()
        self._lock_task = None
