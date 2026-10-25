"""Контроллер аутентификации и жизненного цикла приложения."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from typing import cast

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
from i18n import localize_tree, tr
from storage.data_access import DataAccess
from ui import (
    DeviceRecoveryView,
    KeyEntryView,
    PinLoginView,
    PinSetupView,
    StorageErrorView,
    build_reset_dialog,
)
from ui.branding import set_page_animations_active


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
        *,
        data_access: DataAccess | None = None,
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
            **({"data_access": data_access} if data_access is not None else {}),
        )
        self._key_view: KeyEntryView | None = None
        self._pin_setup_view: PinSetupView | None = None
        self._pending_setup_token: str | None = None
        self._pending_recovery_token: str | None = None
        self._recovery_view: DeviceRecoveryView | None = None
        self._pin_login_view: PinLoginView | None = None
        self._lock_task: Future[None] | None = None
        self._operation_lock = asyncio.Lock()
        self._reset_dialog_open = False
        self._reset_dialog: ft.AlertDialog | None = None
        self._reset_dialog_context: tuple[int, int] | None = None
        self._disposed = False
        self._closing = False
        self._security_epoch = 0
        self._suspending = False
        self._in_background = False

    async def start(self) -> None:
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            result = await self._auth_service.initialize()
            if self._disposed or epoch != self._security_epoch:
                return
            if result.initial_route is InitialRoute.SETUP:
                self._show_key_entry(result.message)
            elif result.initial_route is InitialRoute.PIN:
                self._show_pin_login(result.message, result.lock_seconds_remaining)
            else:
                self._show_storage_error(result.message)

    async def submit_key(self, api_key: str) -> None:
        view = self._key_view
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or view is None
            or self._operation_lock.locked()
        ):
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
            if result.status is AuthStatus.AUTHENTICATED and result.api_key is not None:
                await self._activate_session(
                    result.api_key, result.key_validity, result.key_limit
                )
                return
            if (
                result.status is AuthStatus.PIN_CHOICE_REQUIRED
                and result.pending_setup_token
            ):
                view.clear_key()
                self._show_pin_setup(result)
                return
            if result.status is AuthStatus.PIN_REQUIRED:
                self._show_pin_login(result.message)
                return
            view.show_message(result.message)
            self._page.update()

    async def confirm_pin_setup(self, pin: str, pending_setup_token: str) -> None:
        view = self._pin_setup_view
        if pending_setup_token != self._pending_setup_token:
            return
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or view is None
            or self._operation_lock.locked()
        ):
            return
        async with self._operation_lock:
            if self._pin_setup_view is not view:
                return
            view.clear_pin()
            view.set_busy(True)
            self._page.update()

            result = await self._auth_service.complete_setup(pin, pending_setup_token)
            if self._disposed or self._pin_setup_view is not view:
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
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or view is None
            or self._operation_lock.locked()
        ):
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

    def _recovery_available(self) -> bool:
        return getattr(
            self._page, "platform", None
        ) is ft.PagePlatform.ANDROID and bool(
            getattr(self._auth_service, "recovery_available", False)
        )

    def _protection_notice(self) -> str:
        if not bool(getattr(self._auth_service, "data_protection_enabled", False)):
            return ""
        if getattr(self._page, "platform", None) is ft.PagePlatform.ANDROID:
            return tr(
                "recovery.protection_notice_android"
                if self._recovery_available()
                else "recovery.protection_notice_android_unavailable"
            )
        return tr("recovery.protection_notice_other")

    def _lock_auth_access(self) -> None:
        lock = getattr(self._auth_service, "lock_access", None)
        if callable(lock):
            lock()
        else:
            self._auth_service.cancel_pending_setup()

    async def _cancel_native_recovery(self) -> None:
        cancel = getattr(self._auth_service, "cancel_recovery", None)
        if callable(cancel):
            try:
                await cast(Callable[[], Awaitable[None]], cancel)()
            except Exception:
                # Эпоха уже отозвана, позднее подтверждение не даёт доступа.
                pass

    async def request_recovery(self) -> None:
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or not self._recovery_available()
            or (self._pin_login_view is None and self._recovery_view is None)
        ):
            return
        self._security_epoch += 1
        epoch = self._security_epoch
        async with self._operation_lock:
            self._show_recovery_view(busy=True)
            view = self._recovery_view
            result = await self._auth_service.recover_pin()
            if (
                self._disposed
                or epoch != self._security_epoch
                or self._recovery_view is not view
            ):
                return
            if (
                result.status is AuthStatus.PIN_CHOICE_REQUIRED
                and result.pending_setup_token
            ):
                self._show_recovery_pin(result.pending_setup_token)
            else:
                assert view is not None
                view.set_busy(False)
                view.show_message(result.message or tr("recovery.failed"))
                self._page.update()

    async def cancel_recovery(self) -> None:
        if (
            self._disposed
            or (self._recovery_view is None and self._pending_recovery_token is None)
            or (
                self._pending_recovery_token is not None
                and self._operation_lock.locked()
            )
        ):
            return
        self._security_epoch += 1
        self._lock_auth_access()
        self._show_pin_login(tr("recovery.cancelled"))
        await self._cancel_native_recovery()

    async def confirm_recovery(self, pin: str, token: str) -> None:
        view = self._pin_setup_view
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or view is None
            or token != self._pending_recovery_token
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            view.clear_pin()
            view.set_busy(True)
            self._page.update()
            result = await self._auth_service.complete_recovery(pin, token)
            if (
                self._disposed
                or epoch != self._security_epoch
                or self._pin_setup_view is not view
            ):
                return
            if result.status is AuthStatus.AUTHENTICATED and result.api_key is not None:
                await self._activate_session(
                    result.api_key, result.key_validity, result.key_limit
                )
            else:
                self._show_recovery_view(
                    message=result.message or tr("recovery.failed")
                )

    def _show_recovery_view(self, *, message: str = "", busy: bool = False) -> None:
        self._cancel_lock_task()
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = self._pin_login_view = self._pin_setup_view = None
        self._recovery_view = DeviceRecoveryView(
            self.request_recovery, self.cancel_recovery, message=message, busy=busy
        )
        self._replace_page(self._recovery_view.control)

    def _show_recovery_pin(self, token: str) -> None:
        self._clear_secret_controls()
        self._key_view = self._pin_login_view = None
        self._pending_recovery_token = token

        async def confirm(pin: str) -> None:
            await self.confirm_recovery(pin, token)

        self._pin_setup_view = PinSetupView(
            tr("recovery.verified_notice"),
            confirm,
            self._auth_service.suggest_pin,
            self.cancel_recovery,
            title=tr("recovery.choose_new_pin"),
            instructions=tr("recovery.choose_instructions"),
            confirm_label=tr("recovery.save_new_pin"),
        )
        self._replace_page(self._pin_setup_view.control)

    async def request_reset(self) -> None:
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._reset_dialog_open
            or self._operation_lock.locked()
            or (
                self._pin_login_view is None
                and not self._chat_controller.session_active
            )
        ):
            return
        protected = bool(getattr(self._auth_service, "data_protection_enabled", False))
        if protected and not self._chat_controller.session_active:
            if self._pin_login_view is not None:
                self._pin_login_view.show_message(tr("protection.sign_in_first"))
                self._page.update()
            return
        context = (
            self._security_epoch,
            self._chat_controller.session_generation,
        )

        async def confirm() -> None:
            if self._reset_dialog is dialog and self._reset_context_current(context):
                await self.confirm_reset()

        def cancel() -> None:
            if self._reset_dialog is dialog:
                self.cancel_reset()

        dialog = build_reset_dialog(
            on_confirm=confirm,
            on_cancel=cancel,
            title=tr("recovery.replace_key_title") if protected else None,
            message=tr("recovery.replace_key_notice") if protected else None,
            confirm_label=tr("recovery.replace_key_confirm") if protected else None,
        )
        self._reset_dialog_open = True
        self._reset_dialog = dialog
        self._reset_dialog_context = context
        self._page.show_dialog(dialog)

    def _reset_context_current(self, context: tuple[int, int] | None) -> bool:
        return context is not None and context == (
            self._security_epoch,
            self._chat_controller.session_generation,
        )

    def _close_reset_dialog(self) -> None:
        """Закрывает только собственное подтверждение, не чужое окно поверх него."""
        dialog = self._reset_dialog
        self._reset_dialog_open = False
        self._reset_dialog = None
        self._reset_dialog_context = None
        if dialog is not None:
            dialog.open = False
            try:
                dialog.update()
            except (RuntimeError, AssertionError):
                pass

    async def confirm_reset(self) -> None:
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or not self._reset_dialog_open
        ):
            return
        context = self._reset_dialog_context
        if not self._reset_context_current(context):
            self.cancel_reset()
            return
        assert context is not None
        self._close_reset_dialog()
        if self._operation_lock.locked():
            return

        epoch = self._security_epoch
        view = self._pin_login_view
        chat_was_active = self._chat_controller.session_active
        if view is None and not chat_was_active:
            return
        async with self._operation_lock:
            if chat_was_active:
                if bool(getattr(self._auth_service, "data_protection_enabled", False)):
                    if not await self._chat_controller.flush_drafts():
                        return
                    if (
                        self._disposed
                        or epoch != self._security_epoch
                        or context[1] != self._chat_controller.session_generation
                        or not self._chat_controller.session_active
                    ):
                        return
                self._chat_controller.deactivate()
                self._replace_page(ft.Container())
            if view is not None:
                if self._pin_login_view is not view:
                    return
                view.set_busy(True)
                self._page.update()
            result = await self._auth_service.reset_authentication()
            if self._disposed or epoch != self._security_epoch:
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
        self._close_reset_dialog()

    async def handle_lifecycle_change(
        self, event: ft.AppLifecycleStateChangeEvent
    ) -> None:
        """Блокирует Android при уходе в фон, не разблокирует на RESUME."""
        if event.state in (
            ft.AppLifecycleState.HIDE,
            ft.AppLifecycleState.PAUSE,
            ft.AppLifecycleState.DETACH,
        ):
            set_page_animations_active(self._page, False)
        elif event.state in (
            ft.AppLifecycleState.SHOW,
            ft.AppLifecycleState.RESUME,
            ft.AppLifecycleState.RESTART,
        ):
            set_page_animations_active(self._page, True)
        if (
            self._disposed
            or self._closing
            or self._page.platform is not ft.PagePlatform.ANDROID
        ):
            return
        if event.state is ft.AppLifecycleState.RESUME:
            self._in_background = False
            return
        if event.state not in (ft.AppLifecycleState.HIDE, ft.AppLifecycleState.PAUSE):
            return
        if self._in_background or self._suspending:
            return
        self._in_background = True
        self._suspending = True
        self._security_epoch += 1
        epoch = self._security_epoch
        # Отзываем доступ, callbacks и transient секреты до любой записи и await.
        self._cancel_lock_task()
        recovery_active = (
            self._recovery_view is not None or self._pending_recovery_token is not None
        )
        self._chat_controller.begin_lock()
        self._lock_auth_access()
        self.cancel_reset()
        self._clear_secret_controls()
        self._key_view = None
        self._pin_setup_view = None
        self._pin_login_view = None
        self._replace_page(ft.Container())
        try:
            if recovery_active:
                await self._cancel_native_recovery()
            saved = await self._chat_controller.flush_drafts()
            async with self._operation_lock:
                result = await self._auth_service.initialize()
                if self._disposed or epoch != self._security_epoch:
                    return
                message = result.message
                if not saved:
                    message = self._draft_lock_warning()
                if result.initial_route is InitialRoute.SETUP:
                    self._show_key_entry(message)
                elif result.initial_route is InitialRoute.PIN:
                    self._show_pin_login(message, result.lock_seconds_remaining)
                else:
                    self._show_storage_error(message)
        finally:
            self._suspending = False

    async def lock_application(self) -> None:
        """Делегирует безопасную блокировку активной чат-сессии."""
        await self._chat_controller.lock_application()

    def prepare_close(self) -> None:
        """Отзывает новые операции до ожидания native cancel и записи черновиков."""
        if self._disposed or self._closing:
            return
        self._closing = True
        self._suspending = True
        self._in_background = True
        self._security_epoch += 1
        self._cancel_lock_task()
        try:
            # Сначала захватываем последнюю правку и её узкое разрешение записи.
            self._chat_controller.begin_lock()
        finally:
            self._lock_auth_access()
            try:
                self.cancel_reset()
            except (RuntimeError, AssertionError):
                self._reset_dialog_open = False
            self._clear_secret_controls()
            self._key_view = self._pin_setup_view = self._pin_login_view = None
            self._page.controls.clear()
            try:
                self._page.add(ft.Container())
            except (RuntimeError, AssertionError):
                # Отключённому клиенту нельзя отправить пустой экран, доступ уже закрыт.
                pass

    async def cancel_system_recovery(self) -> None:
        """Закрывает собственный prompt после синхронного отзыва разрешения."""
        await self._cancel_native_recovery()

    def dispose(self) -> None:
        """Удаляет секретные значения и останавливает фоновые UI-задачи."""
        if self._disposed:
            return
        self.prepare_close()
        self._disposed = True
        self._security_epoch += 1
        self._cancel_lock_task()
        self._chat_controller.begin_lock()
        self._lock_auth_access()
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
        self._pin_setup_view = None
        self._pin_login_view = None
        await self._chat_controller.activate(api_key, key_validity, key_limit)

    async def _handle_chat_lock(self) -> None:
        self._lock_auth_access()
        if not self._disposed and not self._closing:
            message = tr("service.app_locked")
            if self._chat_controller.draft_save_failed:
                message = tr(
                    "app.lock_with_warning",
                    locked=message,
                    warning=self._draft_lock_warning(),
                )
            self._show_pin_login(message)

    @staticmethod
    def _draft_lock_warning() -> str:
        return tr("service.draft_lock_failed")

    def _show_key_entry(self, message: str = "", *, success: bool = False) -> None:
        self._cancel_lock_task()
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._pin_login_view = None
        self._pin_setup_view = None
        self._key_view = KeyEntryView(
            self.submit_key,
            replacement=bool(
                getattr(self._auth_service, "key_replacement_pending", False)
            ),
        )
        if message:
            self._key_view.show_message(message, success=success)
        self._replace_page(self._key_view.control)

    async def cancel_pin_setup(self) -> None:
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
        ):
            return
        self._auth_service.cancel_pending_setup()
        self._show_key_entry()

    def _show_pin_setup(self, result: AuthResult) -> None:
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = None
        self._pin_login_view = None
        token = result.pending_setup_token
        if token is None:
            self._show_key_entry(tr("service.setup_expired"))
            return
        self._pending_setup_token = token

        async def confirm(pin: str) -> None:
            await self.confirm_pin_setup(pin, token)

        self._pin_setup_view = PinSetupView(
            result.message,
            confirm,
            self._auth_service.suggest_pin,
            self.cancel_pin_setup,
            instructions=(
                tr(
                    "recovery.setup_with_notice",
                    instructions=tr("auth.pin_instructions"),
                    notice=self._protection_notice(),
                )
                if self._protection_notice()
                else None
            ),
        )
        self._replace_page(self._pin_setup_view.control)

    def _show_pin_login(self, message: str = "", lock_seconds: int = 0) -> None:
        self.cancel_reset()
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = None
        self._pin_setup_view = None
        view = PinLoginView(
            self.submit_pin,
            self.request_reset,
            on_forgot_pin=self.request_recovery if self._recovery_available() else None,
            notice=self._protection_notice(),
        )
        self._pin_login_view = view
        if bool(getattr(self._auth_service, "data_protection_enabled", False)):
            view.reset_button.content = tr("recovery.replace_key_confirm")
        if message:
            view.show_message(message)
        self._replace_page(view.control)
        if lock_seconds > 0:
            self._start_lock_countdown(view, lock_seconds)

    def _show_storage_error(self, message: str) -> None:
        self._chat_controller.deactivate()
        view = StorageErrorView(
            message or tr("service.local_storage_open"),
            self.start,
        )
        self._replace_page(view.control)

    def _replace_page(self, control: ft.Control) -> None:
        if self._disposed or self._closing:
            return
        localize_tree(control)
        self._page.controls.clear()
        self._page.add(control)

    def _clear_secret_controls(self) -> None:
        self._pending_setup_token = None
        self._pending_recovery_token = None
        if self._recovery_view is not None:
            self._recovery_view.dispose()
        self._recovery_view = None
        if self._key_view is not None:
            self._key_view.dispose()
        if self._pin_setup_view is not None:
            self._pin_setup_view.dispose()
        if self._pin_login_view is not None:
            self._pin_login_view.dispose()

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
