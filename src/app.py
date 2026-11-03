"""Контроллер аутентификации и жизненного цикла приложения."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Literal, cast

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
from auth.service import AuthService, deletion_error_message
from chat.accounting import ChatBudgetService
from chat.drafts import ChatDraftService
from chat.sending import MessageSendingService
from chat.service import ChatService
from chat_controller import ChatSessionController, WorkspaceDeletionOrigin
from i18n import fresh_text, get_preferences, localize_tree, tr
from platform_security.local_protection import (
    SCREEN_CONTRACT,
    AppLockState,
    CheckState,
    DeviceCheckRecord,
    DeviceProtectionHistory,
    LocalProtectionChecks,
    ObserverContext,
    ProtectionSnapshot,
    ScreenLockAdapter,
    SleepAdapter,
)
from storage.access_context import finish_worker
from storage.data_access import DataAccess
from storage.profile_deletion import DeletionScope
from ui import (
    DeviceRecoveryView,
    KeyEntryView,
    PinLoginView,
    PinSetupView,
    RecoveryCodeDisplayView,
    RecoveryCodeEntryView,
    RecoveryCodePinView,
    StorageErrorView,
    build_reset_dialog,
)
from ui.branding import set_page_animations_active
from ui.local_protection_view import LocalProtectionSetupView
from ui.profile_deletion_view import ProfileDeletionDialog, ProfileDeletionProgressView
from ui.protection_panel import (
    DismissReason,
    Mechanism,
    ProtectionPanel,
    protection_shield,
    update_protection_shield,
)
from ui.security_status import (
    protection_notice,
    protection_ready,
    session_watch_details,
    untested_protection,
)

_APP_TRACE_EVENTS = {
    "app_started",
    "key_submit_started",
    "key_result",
    "pin_setup_build",
    "pin_setup_shown",
    "pin_setup_failed",
    "key_entry_build",
    "key_entry_shown",
    "system_event",
}
_APP_TRACE_SYSTEM_REASONS = {
    "screen_lock",
    "sleep",
    "session_change",
    "shutdown",
    "trust_lost",
    "protection_emergency",
    "language_change",
}


@dataclass(frozen=True)
class _ProfileDeletionOrigin:
    source: PinLoginView | WorkspaceDeletionOrigin
    epoch: int


@dataclass(eq=False)
class _ProtectionTestIntent:
    """An expiring UI choice, never a credential or an authorization grant."""

    mechanism: Mechanism
    origin: PinLoginView
    composition: object
    epoch: int
    expires_at: float
    authorized_session: int | None = None
    authorized_control: ft.BaseControl | None = None


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
        on_profile_deleted: Callable[[], Awaitable[None]] | None = None,
        on_profile_reload: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._page = page
        self._data_access = data_access
        self._auth_service = auth_service
        self._on_profile_deleted = on_profile_deleted
        self._on_profile_reload = on_profile_reload
        self._profile_deletion_view: ProfileDeletionDialog | None = None
        self._profile_deletion_scope: DeletionScope | None = None
        self._profile_deletion_origin: _ProfileDeletionOrigin | None = None
        self._profile_deletion_progress: ProfileDeletionProgressView | None = None
        self._deletion_started = False
        self._deletion_cancelled = False
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
            on_delete_profile=self._request_workspace_profile_deletion,
            on_test_screen_lock=(
                self.request_screen_lock_test
                if getattr(page, "platform", None)
                in (ft.PagePlatform.LINUX, ft.PagePlatform.WINDOWS)
                else None
            ),
            on_test_sleep=(
                self.request_sleep_test
                if getattr(page, "platform", None) is ft.PagePlatform.LINUX
                else None
            ),
            on_security=(
                self.request_recovery_code_settings
                if getattr(page, "platform", None) is ft.PagePlatform.LINUX
                else None
            ),
            on_storage_error=self._show_storage_error,
            **({"data_access": data_access} if data_access is not None else {}),
        )
        self._key_view: KeyEntryView | None = None
        self._pin_setup_view: PinSetupView | None = None
        self._pending_setup_token: str | None = None
        self._pending_recovery_token: str | None = None
        self._recovery_view: DeviceRecoveryView | None = None
        self._code_entry_view: RecoveryCodeEntryView | None = None
        self._code_pin_view: RecoveryCodePinView | None = None
        self._code_display_view: RecoveryCodeDisplayView | None = None
        self._pending_code_issue_id: str | None = None
        self._recovery_source = "system"
        self._pin_login_view: PinLoginView | None = None
        self._protection_setup_view: LocalProtectionSetupView | None = None
        self._preferences = get_preferences()
        self._onboarding_handled_in_process = False
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
        self._system_lock_task: asyncio.Task[None] | None = None
        self._linux_watch_ready = False
        self._linux_watch_system = False
        self._linux_watch_screen = False
        self._screen_lock_adapter: ScreenLockAdapter | None = None
        self._sleep_adapter: SleepAdapter | None = None
        self._protection_trace: Callable[[dict[str, object]], None] | None = None
        self._history_writer: (
            Callable[[Literal["screen", "sleep"], DeviceCheckRecord], object] | None
        ) = None
        self._history_save_tasks: set[asyncio.Task[None]] = set()
        self._history_save_lock = asyncio.Lock()
        self._history_save_revision = 0
        self._history_save_versions: dict[str, int] = {}
        self._history_save_failures: set[str] = set()
        self._pin_protection_panel: ProtectionPanel | None = None
        self._pin_protection_shield: ft.IconButton | None = None
        self._protection_test_intent: _ProtectionTestIntent | None = None
        self._protection_intent_expiry: asyncio.Task[None] | None = None
        self._protection_intent_clock = time.monotonic
        self._protection_intent_lifetime = 120.0
        self._local_protection = (
            LocalProtectionChecks(
                self.protection_app_state,
                lambda: self.prepare_system_lock("protection_emergency"),
                self._protection_changed,
            )
            if getattr(page, "platform", None)
            in (ft.PagePlatform.LINUX, ft.PagePlatform.WINDOWS)
            else None
        )
        if self._local_protection is not None:
            self._protection_changed(self._local_protection.snapshot)

    async def start(self) -> None:
        self._trace_app("app_started")
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or self._deletion_started
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
            or self._profile_deletion_view is not None
        ):
            return
        async with self._operation_lock:
            if self._key_view is not view:
                return
            self._trace_app("key_submit_started", same_key_view=True)
            view.set_busy(True)
            view.show_message("")
            self._page.update()

            result = await self._auth_service.start_setup(api_key)
            self._trace_app(
                "key_result",
                same_key_view=self._key_view is view,
                auth_status=result.status,
                setup_token_present=bool(result.pending_setup_token),
            )
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
        authenticated = False
        onboarding = self._portable_route() and bool(
            getattr(self._auth_service, "data_protection_enabled", False)
        )
        async with self._operation_lock:
            if self._pin_setup_view is not view:
                return
            view.clear_pin()
            view.set_busy(True)
            self._page.update()
            if onboarding:
                try:
                    # Save the resumable step before the registration can commit.
                    await finish_worker(
                        asyncio.to_thread(
                            self._preferences.set_local_protection_onboarding,
                            "pending",
                        )
                    )
                except OSError:
                    view.set_busy(False)
                    view.show_message(tr("protection_intro.preferences_failed"))
                    self._page.update()
                    return
                if self._disposed or self._pin_setup_view is not view:
                    return
            result = await self._auth_service.complete_setup(pin, pending_setup_token)
            if self._disposed or self._pin_setup_view is not view:
                return
            if result.status is AuthStatus.AUTHENTICATED and result.api_key is not None:
                await self._activate_session(
                    result.api_key,
                    result.key_validity,
                    result.key_limit,
                    present_workspace=not onboarding,
                )
                authenticated = True
            else:
                self._show_key_entry(result.message)
        if authenticated:
            if onboarding:
                await self._resume_protection_setup()
            else:
                await self._offer_code_settings()

    async def submit_pin(self, pin: str) -> None:
        view = self._pin_login_view
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or view is None
            or self._operation_lock.locked()
            or self._profile_deletion_view is not None
        ):
            return
        onboarding = self._protection_setup_pending()
        authenticated = False
        pending_protection = None
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
                if self._protection_test_intent is not None:
                    pending_protection = self._current_protection_intent(
                        authenticated=False
                    )
                await self._activate_session(
                    result.api_key,
                    result.key_validity,
                    result.key_limit,
                    present_workspace=not onboarding,
                    preserve_protection_intent=pending_protection is not None,
                )
                authenticated = True
            elif result.status is AuthStatus.SETUP_REQUIRED:
                self._show_key_entry(result.message)
            else:
                view.show_message(result.message)
                if result.status is AuthStatus.LOCKED:
                    self._start_lock_countdown(view, result.lock_seconds_remaining)
                self._page.update()
        if authenticated and onboarding:
            await self._resume_protection_setup()
        if authenticated and pending_protection is not None:
            await self._present_pin_protection_test()

    def _protection_setup_pending(self) -> bool:
        return (
            self._portable_route()
            and not self._onboarding_handled_in_process
            and bool(getattr(self._auth_service, "data_protection_enabled", False))
            and self._preferences.local_protection_onboarding == "pending"
        )

    async def _resume_protection_setup(self) -> None:
        checks = self._local_protection
        if (
            checks is None
            or not self._protection_setup_pending()
            or self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or not self.protection_app_state().opened
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            if (
                self._disposed
                or self._closing
                or epoch != self._security_epoch
                or not self.protection_app_state().opened
            ):
                return
            message = ""
            if checks.snapshot.screen.state is CheckState.CONFIRMED:
                try:
                    await finish_worker(
                        asyncio.to_thread(
                            self._preferences.set_local_protection_onboarding,
                            "done",
                        )
                    )
                except OSError:
                    message = tr("protection_intro.preferences_failed")
                if (
                    self._disposed
                    or self._closing
                    or epoch != self._security_epoch
                    or not self.protection_app_state().opened
                ):
                    return
            self._show_protection_setup_step(checks.snapshot, message)

    def _show_protection_setup_step(
        self, snapshot: ProtectionSnapshot, message: str = ""
    ) -> None:
        old = self._protection_setup_view
        if old is not None:
            old.dispose()

        async def continue_setup() -> None:
            await self._continue_protection_setup(view)

        view = LocalProtectionSetupView(
            snapshot, self.request_screen_lock_test, continue_setup
        )
        self._protection_setup_view = view
        if message:
            view.show_message(message)
        self._replace_page(view.control)

    async def _continue_protection_setup(self, view: LocalProtectionSetupView) -> None:
        checks = self._local_protection
        if (
            self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or self._protection_setup_view is not view
            or checks is None
            or checks.snapshot.screen_test_running
            or checks.snapshot.sleep_test_running
            or not self.protection_app_state().opened
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            try:
                await finish_worker(
                    asyncio.to_thread(
                        self._preferences.set_local_protection_onboarding, "done"
                    )
                )
            except OSError:
                # This acknowledgement is not an access or security boundary.
                # The durable pending marker will offer the step after restart.
                pass
            if (
                self._disposed
                or self._closing
                or epoch != self._security_epoch
                or self._protection_setup_view is not view
                or not self.protection_app_state().opened
            ):
                return
            self._onboarding_handled_in_process = True
            self._protection_setup_view = None
            view.dispose()
            await self._chat_controller.present_workspace()
        await self._offer_code_settings()

    def _recovery_available(self) -> bool:
        return bool(getattr(self._auth_service, "recovery_available", False))

    def _offer_recovery(self) -> bool:
        return (
            getattr(self._page, "platform", None) is ft.PagePlatform.LINUX
            or self._recovery_available()
        )

    def _protection_snapshot(self) -> ProtectionSnapshot:
        return (
            self._local_protection.snapshot
            if self._local_protection is not None
            else untested_protection(False, False)
        )

    def _cancel_protection_intent(self, *, close_panel: bool = True) -> None:
        self._protection_test_intent = None
        timer = self._protection_intent_expiry
        self._protection_intent_expiry = None
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if timer is not None and timer is not current:
            timer.cancel()
        view = self._pin_login_view
        if view is not None and not view._disposed:
            view.set_protection_prompt("")
        if close_panel and self._pin_protection_panel is not None:
            self._pin_protection_panel.close("programmatic")

    async def cancel_pin_protection_test(self) -> None:
        self._cancel_protection_intent()
        if not self._disposed and not self._closing:
            self._page.update()

    def _protection_panel_closed(self, reason: DismissReason) -> None:
        if reason == "user":
            self._cancel_protection_intent(close_panel=False)
            if not self._disposed and not self._closing:
                self._page.update()

    def _current_protection_intent(
        self, *, authenticated: bool
    ) -> _ProtectionTestIntent | None:
        intent = self._protection_test_intent
        valid = (
            intent is not None
            and not self._disposed
            and not self._closing
            and not self._suspending
            and not self._in_background
            and not self._deletion_started
            and intent.composition is self._auth_service
            and intent.epoch == self._security_epoch
            and self._protection_intent_clock() < intent.expires_at
        )
        if valid and intent is not None:
            if authenticated:
                valid = (
                    intent.authorized_session is not None
                    and intent.authorized_session
                    == self._chat_controller.session_generation
                    and self.protection_app_state().opened
                    and any(c is intent.authorized_control for c in self._page.controls)
                )
            else:
                valid = (
                    self._pin_login_view is intent.origin
                    and not intent.origin._disposed
                    and any(c is intent.origin.control for c in self._page.controls)
                )
        if not valid:
            self._cancel_protection_intent()
            return None
        return intent

    def _start_protection_intent_expiry(self, intent: _ProtectionTestIntent) -> None:
        async def expire() -> None:
            try:
                await asyncio.sleep(
                    max(0, intent.expires_at - self._protection_intent_clock())
                )
                if self._protection_test_intent is intent:
                    self._cancel_protection_intent()
                    if not self._disposed and not self._closing:
                        self._page.update()
            except asyncio.CancelledError:
                return

        self._protection_intent_expiry = asyncio.create_task(expire())

    async def show_pin_protection(self, origin: PinLoginView) -> None:
        if (
            self._disposed
            or self._closing
            or self._pin_login_view is not origin
            or origin._disposed
            or not any(c is origin.control for c in self._page.controls)
        ):
            return
        panel = self._pin_protection_panel
        if panel is None:
            panel = ProtectionPanel(
                self._page,
                on_test=self._choose_pin_protection_test,
                on_start=self._start_pin_protection_test,
                on_close=self._protection_panel_closed,
                locked=True,
                desktop_tests=getattr(self._page, "platform", None)
                is ft.PagePlatform.LINUX,
                platform_notice=self._protection_notice()
                if getattr(self._page, "platform", None) is not ft.PagePlatform.LINUX
                else None,
            )
            self._pin_protection_panel = panel
        intent = self._protection_test_intent
        if intent is not None:
            intent = self._current_protection_intent(authenticated=False)
        panel.set_context(locked=True)
        panel.open(
            self._protection_snapshot(),
            shield=self._pin_protection_shield,
            selected_test=intent.mechanism if intent is not None else None,
        )

    async def _choose_pin_protection_test(self, mechanism: Mechanism) -> None:
        if (
            mechanism not in ("screen", "sleep")
            or getattr(self._page, "platform", None) is not ft.PagePlatform.LINUX
            or self._local_protection is None
            or self._local_protection.snapshot.test_running
            or self._operation_lock.locked()
            or self._profile_deletion_view is not None
        ):
            return
        panel = self._pin_protection_panel
        if panel is None or not panel.is_open:
            return
        if self.protection_app_state().opened:
            intent = self._current_protection_intent(authenticated=True)
            if intent is not None:
                intent.mechanism = mechanism
                panel.set_context(
                    locked=False, selected_test=mechanism, confirm_test=True
                )
            return
        view = self._pin_login_view
        if (
            view is None
            or view._disposed
            or self._disposed
            or self._closing
            or self._suspending
            or not any(c is view.control for c in self._page.controls)
        ):
            return
        self._cancel_protection_intent(close_panel=False)
        intent = _ProtectionTestIntent(
            mechanism,
            view,
            self._auth_service,
            self._security_epoch,
            self._protection_intent_clock() + self._protection_intent_lifetime,
        )
        self._protection_test_intent = intent
        self._start_protection_intent_expiry(intent)
        view.set_protection_prompt(
            tr(
                "protection_route.wait_for_pin"
                if view._locked
                else "protection_route.enter_pin"
            ),
            self.cancel_pin_protection_test,
        )
        panel.close("auth_handoff")
        self._page.update()
        await view.focus_pin()

    async def _present_pin_protection_test(self) -> None:
        intent = self._protection_test_intent
        if intent is None:
            return
        intent.authorized_session = self._chat_controller.session_generation
        intent.authorized_control = (
            self._page.controls[-1] if self._page.controls else None
        )
        if self._current_protection_intent(authenticated=True) is not intent:
            return
        panel = self._pin_protection_panel
        if panel is None:
            self._cancel_protection_intent()
            return
        panel.set_context(locked=False)
        panel.open(
            self._protection_snapshot(),
            shield=self._chat_controller.protection_anchor,
            selected_test=intent.mechanism,
            confirm_test=True,
        )

    async def _start_pin_protection_test(self, mechanism: Mechanism) -> None:
        intent = self._current_protection_intent(authenticated=True)
        panel = self._pin_protection_panel
        if (
            intent is None
            or mechanism != intent.mechanism
            or panel is None
            or not panel.is_open
            or self._operation_lock.locked()
        ):
            return
        # Consume before the first await. The existing protected entry point
        # performs its own active-session/draft/epoch checks before any OS call.
        self._cancel_protection_intent()
        if mechanism == "screen":
            await self.request_screen_lock_test()
        else:
            await self.request_sleep_test()

    def _protection_notice(self) -> str:
        if not bool(getattr(self._auth_service, "data_protection_enabled", False)):
            return ""
        if getattr(self._page, "platform", None) is ft.PagePlatform.ANDROID:
            return tr(
                "recovery.protection_notice_android"
                if self._recovery_available()
                else "recovery.protection_notice_android_unavailable"
            )
        if self._local_protection is not None:
            return protection_notice(self._local_protection.snapshot)
        if getattr(self._page, "platform", None) is ft.PagePlatform.LINUX:
            return tr(
                "recovery_code.protection_notice",
                watcher=session_watch_details(
                    self._linux_watch_system, self._linux_watch_screen
                ),
            )
        return tr("recovery.protection_notice_other")

    def set_session_watch_status(
        self, *, system_events: bool, screen_events: bool
    ) -> None:
        """Предупреждение отражает реально работающие подписки, не платформу."""
        self._linux_watch_ready = system_events and screen_events
        self._linux_watch_system = system_events
        self._linux_watch_screen = screen_events
        if self._local_protection is not None:
            self._protection_changed(self._local_protection.snapshot)
            return
        self._chat_controller.set_session_watch_status(
            system_events=system_events, screen_events=screen_events
        )
        self._update_protection_controls()

    def protection_app_state(self) -> AppLockState:
        view = self._pin_login_view
        return AppLockState(
            self._chat_controller.session_generation,
            self._chat_controller.session_active,
            self._data_access is not None and self._data_access.unlocked,
            view is not None
            and not self._disposed
            and not self._closing
            and not view._disposed
            and any(control is view.control for control in self._page.controls),
        )

    def set_screen_lock_adapter(
        self,
        adapter: ScreenLockAdapter | None,
        sleep_context: ObserverContext | None = None,
    ) -> None:
        self._screen_lock_adapter = adapter
        if self._local_protection is not None:
            self._local_protection.update_observers(
                adapter.screen_context if adapter is not None else None,
                sleep_context,
                screen_compatible=getattr(adapter, "screen_history_compatible", True),
                sleep_compatible=getattr(adapter, "sleep_history_compatible", True),
            )

    def set_sleep_adapter(self, adapter: SleepAdapter | None) -> None:
        self._sleep_adapter = adapter

    def record_normal_protection(
        self,
        mechanism: Literal["screen", "sleep"],
        context: ObserverContext | None,
        before: AppLockState,
    ) -> None:
        if self._local_protection is not None and mechanism in ("screen", "sleep"):
            self._local_protection.normal_reaction(
                mechanism,
                context,
                before.application_session,
                before.opened,
            )

    def record_sleep_resume(
        self,
        context: ObserverContext,
        actual_suspend: bool,
        test_id: int | None = None,
    ) -> None:
        if self._local_protection is not None:
            self._local_protection.observe_sleep_resume(
                context, actual_suspend, test_id=test_id
            )

    def record_screen_transition(
        self, context: ObserverContext, locked: bool, test_id: int | None = None
    ) -> None:
        if self._local_protection is not None:
            self._local_protection.observe_screen_transition(
                context, locked, test_id=test_id
            )

    def set_protection_trace(
        self, trace: Callable[[dict[str, object]], None] | None
    ) -> None:
        self._protection_trace = trace
        if self._local_protection is not None:
            self._local_protection.set_trace(trace)

    def _trace_app(
        self,
        event: str,
        *,
        same_key_view: bool | None = None,
        auth_status: AuthStatus | None = None,
        setup_token_present: bool | None = None,
        error: Exception | None = None,
        system_reason: str | None = None,
    ) -> None:
        sink = self._protection_trace
        if sink is None or event not in _APP_TRACE_EVENTS:
            return
        try:
            state = self.protection_app_state()
            pin_setup = self._pin_setup_view
            record: dict[str, object] = {
                "event": event,
                "page_linux": getattr(self._page, "platform", None)
                is ft.PagePlatform.LINUX,
                "key_view": self._key_view is not None,
                "pin_setup_view": pin_setup is not None,
                "pin_setup_visible": pin_setup is not None
                and any(c is pin_setup.control for c in self._page.controls),
                "disposed": self._disposed,
                "suspending": self._suspending,
                "in_background": self._in_background,
                "session_open": state.session_open,
                "data_open": state.data_open,
                "pin_visible": state.pin_visible,
            }
            if type(same_key_view) is bool:
                record["same_key_view"] = same_key_view
            if isinstance(auth_status, AuthStatus):
                record["auth_status"] = auth_status.value
            if type(setup_token_present) is bool:
                record["setup_token_present"] = setup_token_present
            if error is not None:
                record["exception_class"] = type(error).__name__
            if (
                isinstance(system_reason, str)
                and system_reason in _APP_TRACE_SYSTEM_REASONS
            ):
                record["system_reason"] = str(system_reason)
            sink(record)
        except Exception:
            # Opt-in diagnostics must never become an authentication dependency.
            pass

    def _protection_changed(self, snapshot: ProtectionSnapshot) -> None:
        if self._disposed or self._closing:
            return
        self._chat_controller.set_protection_status(snapshot)
        if self._protection_setup_view is not None:
            self._protection_setup_view.set_snapshot(snapshot)
        if self._pin_protection_shield is not None:
            update_protection_shield(self._pin_protection_shield, snapshot)
        if self._pin_protection_panel is not None:
            self._pin_protection_panel.refresh(
                snapshot, busy=self._operation_lock.locked()
            )
        self._update_protection_controls()

    def _update_protection_controls(self) -> None:
        for view in (self._code_pin_view, self._code_display_view):
            if view is not None:
                view.set_protection_notice(self._code_protection_notice())
        if self._pin_login_view is not None and not self._disposed:
            notice = self._pin_login_view.notice
            notice.value = fresh_text(self._protection_notice())
            notice.visible = False
            if self._local_protection is not None:
                snapshot = self._local_protection.snapshot
                notice.color = (
                    ft.Colors.RED_300
                    if snapshot.has_problem
                    else ft.Colors.GREEN_300
                    if protection_ready(snapshot)
                    else ft.Colors.AMBER_200
                )
            self._page.update()
        elif not self._disposed and not self._closing:
            self._page.update()

    def _code_protection_notice(self) -> str:
        if not self._portable_route():
            return ""
        if self._local_protection is not None:
            return protection_notice(self._local_protection.snapshot)
        return session_watch_details(self._linux_watch_system, self._linux_watch_screen)

    async def request_screen_lock_test(self) -> None:
        checks, adapter = self._local_protection, self._screen_lock_adapter
        if (
            checks is None
            or self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or self._deletion_started
            or checks.snapshot.test_running
            or not self._chat_controller.session_active
        ):
            return
        if (
            self._profile_deletion_origin is not None
            or self._reset_dialog_open
            or self._operation_lock.locked()
        ):
            self._report_screen_lock_test_busy()
            return
        if adapter is None:
            checks.preparation_unavailable()
            return
        epoch = self._security_epoch
        generation = self._chat_controller.session_generation
        async with self._operation_lock:
            if not await self._chat_controller.prepare_screen_lock_test():
                self._report_screen_lock_test_busy()
                return
            if (
                self._disposed
                or self._closing
                or self._suspending
                or epoch != self._security_epoch
                or generation != self._chat_controller.session_generation
                or not self.protection_app_state().opened
            ):
                return
        # The ordinary OS-event handler must be able to finish its PIN route
        # while the asynchronous lock request is still awaiting its reply.
        if (
            self._disposed
            or self._closing
            or self._suspending
            or epoch != self._security_epoch
            or generation != self._chat_controller.session_generation
            or not self.protection_app_state().opened
        ):
            return
        await checks.start_screen_test(adapter, generation)

    async def request_sleep_test(self) -> None:
        """Only an explicit desktop action requests sleep after the normal draft flush."""
        checks, adapter = self._local_protection, self._sleep_adapter
        if (
            checks is None
            or getattr(self._page, "platform", None) is not ft.PagePlatform.LINUX
            or self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or self._deletion_started
            or checks.snapshot.screen_test_running
            or checks.snapshot.sleep_test_running
            or not self._chat_controller.session_active
        ):
            return
        if (
            self._profile_deletion_origin is not None
            or self._reset_dialog_open
            or self._operation_lock.locked()
        ):
            self._report_screen_lock_test_busy()
            return
        if adapter is None:
            checks.sleep_preparation_unavailable()
            return
        epoch = self._security_epoch
        generation = self._chat_controller.session_generation
        async with self._operation_lock:
            if not await self._chat_controller.prepare_screen_lock_test():
                self._report_screen_lock_test_busy()
                return
            if (
                self._disposed
                or self._closing
                or self._suspending
                or epoch != self._security_epoch
                or generation != self._chat_controller.session_generation
                or not self.protection_app_state().opened
            ):
                return
        # Never keep the registration/UI lock across sleep or the manual unlock.
        # The trusted ordinary sleep handler must synchronously revoke real access.
        if (
            self._disposed
            or self._closing
            or self._suspending
            or epoch != self._security_epoch
            or generation != self._chat_controller.session_generation
            or not self.protection_app_state().opened
        ):
            return
        await checks.start_sleep_test(adapter, generation)

    def _report_screen_lock_test_busy(self) -> None:
        if self._protection_setup_view is not None:
            self._protection_setup_view.show_message(tr("service.operation_pending"))
            self._page.update()
        else:
            self._chat_controller.report_screen_lock_test_busy()

    def configure_protection_history(
        self,
        history: DeviceProtectionHistory,
        writer: Callable[[Literal["screen", "sleep"], DeviceCheckRecord], object]
        | None,
        *,
        persistence_error: bool = False,
    ) -> None:
        """Linux composition supplies metadata, never auth or chat access rights."""
        checks = self._local_protection
        if checks is None:
            return
        self._history_writer = writer
        checks.set_history(history, persistence_error=persistence_error)
        checks.set_completion_callback(self._queue_protection_history)

    def _queue_protection_history(
        self, mechanism: str, record: DeviceCheckRecord
    ) -> None:
        if mechanism not in ("screen", "sleep") or self._closing or self._disposed:
            return
        writer, checks = self._history_writer, self._local_protection
        if checks is None:
            return
        if mechanism == "screen" and record.contract == SCREEN_CONTRACT:
            restore = getattr(
                self._screen_lock_adapter, "enable_saved_screen_monitoring", None
            )
            if callable(restore):
                restore()
        if writer is None:
            checks.set_persistence_error(True)
            return
        self._history_save_revision += 1
        revision = self._history_save_revision
        self._history_save_versions[mechanism] = revision

        async def save() -> None:
            # Metadata writes have their own short boundary. They never hold the
            # registration/UI lock while awaiting an OS cycle or a disk worker.
            async with self._history_save_lock:
                failed = False
                try:
                    await finish_worker(asyncio.to_thread(writer, mechanism, record))
                except asyncio.CancelledError:
                    if self._history_save_versions.get(mechanism) == revision:
                        self._history_save_failures.add(mechanism)
                        checks.set_persistence_error(True)
                    raise
                except Exception:
                    failed = True
                if self._history_save_versions.get(mechanism) == revision:
                    if failed:
                        self._history_save_failures.add(mechanism)
                    else:
                        self._history_save_failures.discard(mechanism)
                    checks.set_persistence_error(bool(self._history_save_failures))

        task = asyncio.create_task(save())
        self._history_save_tasks.add(task)
        task.add_done_callback(self._history_save_tasks.discard)

    async def close_protection_checks(self) -> None:
        timer = self._protection_intent_expiry
        self._cancel_protection_intent()
        if timer is not None:
            await asyncio.gather(timer, return_exceptions=True)
        if self._local_protection is not None:
            await self._local_protection.aclose()

        async def drain() -> None:
            while self._history_save_tasks:
                await asyncio.gather(
                    *tuple(self._history_save_tasks), return_exceptions=True
                )

        await finish_worker(drain())

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

    def _portable_route(self) -> bool:
        return getattr(self._page, "platform", None) is ft.PagePlatform.LINUX

    async def request_profile_deletion(self) -> None:
        view = self._pin_login_view
        if view is None:
            return
        await self._request_profile_deletion(
            _ProfileDeletionOrigin(view, self._security_epoch)
        )

    async def _request_workspace_profile_deletion(
        self, workspace: WorkspaceDeletionOrigin
    ) -> None:
        await self._request_profile_deletion(
            _ProfileDeletionOrigin(workspace, self._security_epoch)
        )

    def _deletion_origin_current(self, origin: _ProfileDeletionOrigin) -> bool:
        if origin.epoch != self._security_epoch:
            return False
        source = origin.source
        if isinstance(source, PinLoginView):
            return self._pin_login_view is source
        return self._chat_controller.profile_deletion_origin_current(source)

    async def _request_profile_deletion(self, origin: _ProfileDeletionOrigin) -> None:
        source = origin.source
        if (
            self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or self._deletion_started
            or self._profile_deletion_view is not None
            or self._reset_dialog_open
            or self._code_pin_view is not None
            or self._code_display_view is not None
            or self._recovery_view is not None
            or self._code_entry_view is not None
            or self._operation_lock.locked()
            or not self._auth_service.profile_deletion_available
        ):
            return
        if self._deletion_origin_current(origin):
            self._cancel_protection_intent()
        epoch = origin.epoch
        async with self._operation_lock:
            # Отмена должна видеть запрос уже во время сохранения редактора.
            self._profile_deletion_origin = origin
            if isinstance(source, WorkspaceDeletionOrigin):
                if not await self._chat_controller.suspend_for_profile_deletion(source):
                    if self._profile_deletion_origin is origin:
                        self._profile_deletion_origin = None
                    return
            elif self._pin_login_view is source:
                source.clear_pin()
                self._cancel_lock_task()
            else:
                self._profile_deletion_origin = None
                return
            if (
                self._profile_deletion_origin is not origin
                or not self._deletion_origin_current(origin)
            ):
                return
            try:
                if isinstance(source, PinLoginView):
                    # Дожидаемся чтения счётчика до захвата подтверждения.
                    await self._auth_service.pin_lock_seconds_remaining()
                    if (
                        self._profile_deletion_origin is not origin
                        or not self._deletion_origin_current(origin)
                    ):
                        return
                scope = await self._auth_service.capture_profile_deletion()
            except Exception:
                if self._profile_deletion_origin is not origin:
                    return
                self._profile_deletion_origin = None
                if isinstance(source, PinLoginView) and self._deletion_origin_current(
                    origin
                ):
                    await self._refresh_pin_countdown(source, epoch)
                    if not self._deletion_origin_current(origin):
                        return
                    source.show_message(
                        deletion_error_message(
                            self._auth_service.profile_deletion_diagnostic
                        )
                    )
                    self._page.update()
                elif isinstance(source, WorkspaceDeletionOrigin):
                    await self._resume_profile_deletion(origin)
                    self._chat_controller.show_profile_deletion_error(
                        deletion_error_message(
                            self._auth_service.profile_deletion_diagnostic
                        )
                    )
                return
            if (
                self._disposed
                or self._closing
                or self._profile_deletion_origin is not origin
                or not self._deletion_origin_current(origin)
            ):
                self._auth_service.cancel_profile_deletion()
                return

            async def confirm(phrase: str) -> None:
                await self.confirm_profile_deletion(phrase, scope, dialog, epoch)

            def cancel() -> None:
                self.cancel_profile_deletion(dialog)

            dialog = ProfileDeletionDialog(
                confirm, cancel, preparation_required=scope.preparation_required
            )
            self._profile_deletion_scope = scope
            self._profile_deletion_origin = origin
            self._profile_deletion_view = dialog
            self._page.show_dialog(dialog.dialog)

    def cancel_profile_deletion(
        self, view: ProfileDeletionDialog | None = None
    ) -> None:
        if view is not None and self._profile_deletion_view is not view:
            return
        if self._deletion_started:
            if self._auth_service.profile_deletion_pending:
                return
            self._deletion_cancelled = True
        cancel = getattr(self._auth_service, "cancel_profile_deletion", None)
        if callable(cancel):
            cancel()
        dialog = self._profile_deletion_view
        origin = self._profile_deletion_origin
        self._profile_deletion_view = None
        self._profile_deletion_scope = None
        self._profile_deletion_origin = None
        if dialog is not None:
            dialog.dispose()
            try:
                dialog.dialog.update()
            except (RuntimeError, AssertionError):
                pass
        if not self._deletion_started and origin is not None:
            self._page.run_task(self._resume_cancelled_profile_deletion, origin)

    async def _resume_cancelled_profile_deletion(
        self, origin: _ProfileDeletionOrigin
    ) -> None:
        # suspend_for_security может ещё дописывать редактор. Возврат раньше
        # его завершения позволил бы позднему suspend снять новый workspace.
        async with self._operation_lock:
            await self._resume_profile_deletion(origin)

    async def _resume_profile_deletion(self, origin: _ProfileDeletionOrigin) -> None:
        if (
            not self._disposed
            and not self._closing
            and not self._suspending
            and not self._in_background
            and not self._deletion_started
            and self._deletion_origin_current(origin)
        ):
            if isinstance(origin.source, WorkspaceDeletionOrigin):
                await self._chat_controller.resume_profile_deletion(origin.source)
            else:
                await self._refresh_pin_countdown(origin.source, origin.epoch)

    async def _refresh_pin_countdown(self, view: PinLoginView, epoch: int) -> None:
        def current() -> bool:
            return (
                not self._disposed
                and not self._closing
                and not self._suspending
                and not self._in_background
                and self._pin_login_view is view
                and self._security_epoch == epoch
                and self._profile_deletion_origin is None
                and self._profile_deletion_view is None
                and not self._deletion_started
            )

        if not current():
            return
        try:
            remaining = await self._auth_service.pin_lock_seconds_remaining()
        except Exception:
            if current():
                view.set_locked(1)
                view.show_message(tr("protection.unavailable"))
                self._page.update()
            return
        if current():
            view.set_locked(remaining)
            if remaining > 0:
                self._start_lock_countdown(view, remaining)
            self._page.update()

    async def confirm_profile_deletion(
        self,
        phrase: str,
        scope: DeletionScope,
        view: ProfileDeletionDialog,
        epoch: int,
    ) -> None:
        if (
            self._disposed
            or self._closing
            or self._deletion_started
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or self._profile_deletion_view is not view
            or self._profile_deletion_scope is not scope
            or self._profile_deletion_origin is None
            or not self._deletion_origin_current(self._profile_deletion_origin)
            or epoch != self._security_epoch
            or phrase != view.phrase
        ):
            return
        # Терминальное закрытие старого доступа предшествует первому await.
        self._deletion_started = True
        if self._local_protection is not None:
            self._local_protection.cancel_screen_test()
            self._local_protection.cancel_sleep_test()
        self._security_epoch += 1
        self._auth_service.prepare_profile_deletion()
        self._chat_controller.begin_profile_deletion()
        self._cancel_lock_task()
        self.cancel_reset()
        self._clear_secret_controls()
        self._key_view = self._pin_setup_view = self._pin_login_view = None
        self._profile_deletion_view = None
        self._profile_deletion_origin = None
        view.dispose()
        try:
            view.dialog.update()
        except (RuntimeError, AssertionError):
            pass
        self._profile_deletion_progress = ProfileDeletionProgressView(
            self.retry_profile_deletion
        )
        self._replace_page(self._profile_deletion_progress.control)
        async with self._operation_lock:
            await self._chat_controller.wait_profile_deletion()
            if self._deletion_cancelled:
                await self._reload_before_deletion_intent()
                return
            result = await self._auth_service.confirm_profile_deletion(scope)
            await self._complete_profile_deletion(result)

    async def _reload_before_deletion_intent(self) -> None:
        if (
            not self._disposed
            and not self._closing
            and self._on_profile_reload is not None
        ):
            await self._on_profile_reload()

    async def _complete_profile_deletion(self, result: AuthResult) -> None:
        if self._disposed or self._closing:
            return
        if result.status is AuthStatus.PROFILE_DELETED:
            self._profile_deletion_scope = None
            if self._on_profile_deleted is not None:
                await self._on_profile_deleted()
                return
        diagnostic = self._auth_service.profile_deletion_diagnostic
        if (
            self._deletion_cancelled
            and not self._auth_service.profile_deletion_pending
            and not (diagnostic is not None and diagnostic.prepared)
        ):
            await self._reload_before_deletion_intent()
            return
        if self._profile_deletion_progress is not None:
            self._profile_deletion_progress.show_error(
                result.message or tr("profile_deletion.unavailable"),
                retry_label=(
                    tr("profile_deletion.retry")
                    if self._auth_service.profile_deletion_pending
                    else tr("profile_deletion.retry_prepare")
                ),
            )
            self._page.update()

    async def retry_profile_deletion(self) -> None:
        if (
            self._disposed
            or self._closing
            or not self._deletion_started
            or self._operation_lock.locked()
        ):
            return
        async with self._operation_lock:
            if not self._auth_service.profile_deletion_pending:
                await self._reload_before_deletion_intent()
                return
            result = await self._auth_service.finish_profile_deletion()
            await self._complete_profile_deletion(result)

    async def request_recovery(self) -> None:
        """Linux начинает с заранее сохранённого кода, без системного запроса."""
        if self._profile_deletion_view is not None:
            return
        if not self._portable_route():
            await self.request_system_recovery()
            return
        if (
            self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or (self._pin_login_view is None and self._code_entry_view is None)
        ):
            return
        self._cancel_protection_intent()
        self._security_epoch += 1
        epoch = self._security_epoch
        async with self._operation_lock:
            try:
                await self._restore_code_entry(epoch=epoch)
            except Exception:
                if epoch == self._security_epoch and self._pin_login_view is not None:
                    self._pin_login_view.show_message(tr("protection.unavailable"))
                    self._page.update()

    async def _restore_code_entry(
        self, message: str = "", *, epoch: int | None = None
    ) -> None:
        current = self._security_epoch if epoch is None else epoch
        inspect = getattr(self._auth_service, "recovery_code_enrolled", None)
        try:
            enrolled = (
                await cast(Callable[[], Awaitable[bool]], inspect)()
                if callable(inspect)
                else False
            )
        except Exception:
            if (
                not self._disposed
                and not self._closing
                and current == self._security_epoch
            ):
                self._lock_auth_access()
                self._clear_secret_controls()
                self._key_view = self._pin_login_view = self._pin_setup_view = None
                self._show_storage_error(tr("protection.unavailable"))
            return
        if self._disposed or self._closing or current != self._security_epoch:
            return
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = self._pin_login_view = self._pin_setup_view = None
        self._code_entry_view = RecoveryCodeEntryView(
            self.submit_recovery_code,
            self.cancel_recovery,
            enrolled=enrolled,
            message=message,
            on_system_recovery=self.request_system_recovery
            if self._recovery_available()
            else None,
        )
        self._replace_page(self._code_entry_view.control)

    async def submit_recovery_code(self, value: str) -> None:
        view = self._code_entry_view
        if (
            self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or view is None
            or self._operation_lock.locked()
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            view.clear_secret()
            view.set_busy(True)
            self._page.update()
            result = await self._auth_service.recover_with_code(value)
            if (
                self._disposed
                or epoch != self._security_epoch
                or self._code_entry_view is not view
            ):
                return
            if (
                result.status is AuthStatus.PIN_CHOICE_REQUIRED
                and result.pending_setup_token
            ):
                self._recovery_source = "code"
                self._show_recovery_pin(result.pending_setup_token)
            else:
                view.set_busy(False)
                view.show_message(result.message or tr("portable.invalid"))
                self._page.update()

    async def _offer_code_settings(self) -> None:
        if (
            not self._portable_route()
            or self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or not callable(getattr(self._auth_service, "begin_recovery_code", None))
            or not self._chat_controller.session_active
        ):
            return
        epoch = self._security_epoch
        if not await self._chat_controller.suspend_for_security():
            return
        if self._disposed or self._closing or epoch != self._security_epoch:
            return
        self._clear_secret_controls()
        view = RecoveryCodePinView(
            self.begin_recovery_code,
            self.cancel_recovery_code_settings,
            protection_notice=self._code_protection_notice(),
        )
        self._code_pin_view = view
        self._replace_page(view.control)
        try:
            remaining = await self._auth_service.pin_lock_seconds_remaining()
        except Exception:
            if self._code_pin_view is view and epoch == self._security_epoch:
                view.set_locked(1)
                view.show_message(tr("protection.unavailable"))
                self._page.update()
            return
        if self._code_pin_view is view and epoch == self._security_epoch:
            if remaining > 0:
                self._start_lock_countdown(view, remaining)

    async def request_recovery_code_settings(self) -> None:
        if (
            not self._portable_route()
            or self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or self._profile_deletion_origin is not None
            or self._profile_deletion_view is not None
            or not self._chat_controller.session_active
        ):
            return
        self._cancel_protection_intent()
        self._security_epoch += 1
        async with self._operation_lock:
            await self._offer_code_settings()

    async def begin_recovery_code(self, pin: str) -> None:
        view = self._code_pin_view
        if (
            self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or view is None
            or self._operation_lock.locked()
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            view.clear_secret()
            view.set_busy(True)
            self._page.update()
            result = await self._auth_service.begin_recovery_code(pin)
            if (
                self._disposed
                or epoch != self._security_epoch
                or self._code_pin_view is not view
            ):
                self._auth_service.cancel_recovery_code_issue()
                return
            issue = result.recovery_code_issue
            if result.status is AuthStatus.RECOVERY_CODE_ISSUED and issue is not None:
                self._clear_secret_controls(cancel_code_issue=False)
                self._pending_code_issue_id = issue.attempt_id
                self._code_display_view = RecoveryCodeDisplayView(
                    issue.code,
                    self.confirm_recovery_code,
                    self.cancel_recovery_code_settings,
                    on_copy=self.copy_recovery_code,
                    protection_notice=self._code_protection_notice(),
                )
                self._replace_page(self._code_display_view.control)
            else:
                view.set_busy(False)
                view.show_message(result.message or tr("portable.pin_required"))
                if result.status is AuthStatus.LOCKED:
                    self._start_lock_countdown(view, result.lock_seconds_remaining)
                self._page.update()

    async def confirm_recovery_code(self, value: str) -> None:
        view, issue_id = self._code_display_view, self._pending_code_issue_id
        if (
            self._disposed
            or self._closing
            or self._suspending
            or self._in_background
            or view is None
            or issue_id is None
            or self._operation_lock.locked()
        ):
            return
        epoch = self._security_epoch
        async with self._operation_lock:
            view.repeat_field.value = ""
            view.set_busy(True)
            self._page.update()
            result = await self._auth_service.confirm_recovery_code(issue_id, value)
            if (
                self._disposed
                or epoch != self._security_epoch
                or self._code_display_view is not view
            ):
                return
            if result.status is AuthStatus.RECOVERY_CODE_SAVED:
                self._clear_secret_controls()
                await self._chat_controller.resume_after_security()
                if not self._disposed and self._chat_controller.session_active:
                    self._page.show_dialog(
                        ft.SnackBar(content=ft.Text(tr("recovery_code.saved_notice")))
                    )
            else:
                view.set_busy(False)
                view.show_message(result.message or tr("protection.unavailable"))
                self._page.update()

    async def cancel_recovery_code_settings(self) -> None:
        if (
            self._disposed
            or self._closing
            or (self._code_pin_view is None and self._code_display_view is None)
        ):
            return
        self._security_epoch += 1
        self._clear_secret_controls()
        await self._chat_controller.resume_after_security()

    async def copy_recovery_code(self, value: str) -> None:
        view = self._code_display_view
        if self._disposed or self._closing or self._suspending or view is None:
            return
        try:
            await ft.Clipboard().set(value)
        except Exception:
            if self._code_display_view is view:
                view.show_message(tr("protection.unavailable"))
                self._page.update()

    async def request_system_recovery(self) -> None:
        if (
            self._disposed
            or self._profile_deletion_view is not None
            or self._suspending
            or self._in_background
            or self._operation_lock.locked()
            or not self._offer_recovery()
            or (
                self._pin_login_view is None
                and self._recovery_view is None
                and self._code_entry_view is None
            )
        ):
            return
        self._cancel_protection_intent()
        if getattr(self._page, "platform", None) is ft.PagePlatform.LINUX:
            if self._recovery_view is None or not self._recovery_available():
                self._show_recovery_view(
                    message=(
                        tr("recovery.linux_setup")
                        if not self._recovery_available()
                        else ""
                    )
                )
                return
        self._security_epoch += 1
        epoch = self._security_epoch
        async with self._operation_lock:
            self._show_recovery_view(busy=True)
            self._recovery_source = "system"
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
            or (
                self._recovery_view is None
                and self._pending_recovery_token is None
                and self._code_entry_view is None
            )
            or (
                self._pending_recovery_token is not None
                and self._operation_lock.locked()
            )
        ):
            return
        self._security_epoch += 1
        epoch = self._security_epoch
        self._lock_auth_access()
        self._show_pin_login(tr("recovery.cancelled"))
        view = self._pin_login_view
        await self._cancel_native_recovery()
        if view is not None:
            await self._refresh_pin_countdown(view, epoch)

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
                await self._offer_code_settings()
            else:
                if self._recovery_source == "code":
                    await self._restore_code_entry(result.message)
                    return
                self._show_recovery_view(
                    message=result.message or tr("recovery.failed")
                )

    def _show_recovery_view(self, *, message: str = "", busy: bool = False) -> None:
        self._cancel_lock_task()
        self._chat_controller.deactivate()
        self._clear_secret_controls()
        self._key_view = self._pin_login_view = self._pin_setup_view = None
        self._recovery_view = DeviceRecoveryView(
            self.request_system_recovery,
            self.cancel_recovery,
            message=message,
            busy=busy,
            linux=getattr(self._page, "platform", None) is ft.PagePlatform.LINUX,
        )
        self._replace_page(self._recovery_view.control)

    def _show_recovery_pin(self, token: str) -> None:
        portable = self._recovery_source == "code"
        self._clear_secret_controls()
        self._key_view = self._pin_login_view = None
        self._pending_recovery_token = token

        async def confirm(pin: str) -> None:
            await self.confirm_recovery(pin, token)

        self._pin_setup_view = PinSetupView(
            tr(
                "recovery_code.verified_notice"
                if portable
                else "recovery.verified_notice"
            ),
            confirm,
            self._auth_service.suggest_pin,
            self.cancel_recovery,
            title=tr("recovery.choose_new_pin"),
            instructions=tr(
                "recovery.choose_with_lock_notice",
                instructions=tr("recovery.choose_instructions"),
                notice=tr("recovery.lock_cancels_change"),
            ),
            confirm_label=tr("recovery.save_new_pin"),
        )
        self._replace_page(self._pin_setup_view.control)

    async def request_reset(self) -> None:
        if self._profile_deletion_view is not None:
            return
        if (
            self._disposed
            or self._suspending
            or self._in_background
            or self._reset_dialog_open
            or self._operation_lock.locked()
            or not self._chat_controller.session_active
        ):
            return
        self._cancel_protection_intent()
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
        if self._deletion_started:
            self._security_epoch += 1
            self.cancel_profile_deletion()
            self._lock_auth_access()
            self._clear_secret_controls()
            return
        epoch, recovery_active = self._begin_session_seal()
        await self._finish_session_seal(epoch, recovery_active)

    def _begin_session_seal(self) -> tuple[int, bool]:
        self._suspending = True
        self._security_epoch += 1
        epoch = self._security_epoch
        self._cancel_lock_task()
        self.cancel_profile_deletion()
        recovery_active = (
            self._recovery_view is not None or self._pending_recovery_token is not None
        )
        try:
            # Захват черновика и completion lease предшествует отзыву доступа.
            self._chat_controller.begin_lock()
        finally:
            self._lock_auth_access()
            self.cancel_reset()
            self._clear_secret_controls()
            self._key_view = self._pin_setup_view = self._pin_login_view = None
            self._replace_page(ft.Container())
        return epoch, recovery_active

    def prepare_system_lock(self, _reason: str) -> None:
        """Callback шины синхронно закрывает доступ до возврата диспетчеру."""
        self._trace_app("system_event", system_reason=_reason)
        if self._disposed or self._closing or self._suspending:
            return
        if self._deletion_started:
            self._security_epoch += 1
            self.cancel_profile_deletion()
            self._lock_auth_access()
            self._clear_secret_controls()
            return
        epoch, recovery_active = self._begin_session_seal()
        self._system_lock_task = asyncio.create_task(
            self._finish_session_seal(epoch, recovery_active)
        )

    def handle_language_change(self) -> None:
        """Linux-проверка и неиспользованный grant не переживают смену языка."""
        self.cancel_profile_deletion()
        self._chat_controller.handle_language_change()
        if self._pin_protection_panel is not None:
            self._pin_protection_panel.refresh(self._protection_snapshot())
        if (
            self._pending_recovery_token is not None
            or self._code_entry_view is not None
            or self._code_pin_view is not None
            or self._code_display_view is not None
            or (self._recovery_view is not None and self._operation_lock.locked())
        ):
            self.prepare_system_lock("language_change")
        if (
            self._protection_setup_view is not None
            and self._local_protection is not None
        ):
            localize_tree(self._protection_setup_view.control)
            self._protection_setup_view.set_snapshot(self._local_protection.snapshot)
            self._page.update()

    def handle_page_resize(self, event: ft.PageResizeEvent) -> None:
        panel = self._pin_protection_panel
        if (
            not self._disposed
            and not self._closing
            and panel is not None
            and panel.is_open
        ):
            panel.resize(event.width, event.height)

    async def wait_system_lock(self) -> None:
        """Закрытие ждёт уже захваченный черновик, не обрывая его узкую запись."""
        if self._system_lock_task is not None:
            await asyncio.shield(self._system_lock_task)

    async def _finish_session_seal(self, epoch: int, recovery_active: bool) -> None:
        try:
            if recovery_active:
                await self._cancel_native_recovery()
            saved = await self._chat_controller.flush_drafts()
            async with self._operation_lock:
                result = await self._auth_service.initialize()
                if self._disposed or self._closing or epoch != self._security_epoch:
                    return
                message = result.message if saved else self._draft_lock_warning()
                if result.initial_route is InitialRoute.SETUP:
                    self._show_key_entry(message)
                elif result.initial_route is InitialRoute.PIN:
                    self._show_pin_login(message, result.lock_seconds_remaining)
                else:
                    self._show_storage_error(message)
        except Exception:
            if not self._disposed and not self._closing:
                self._show_storage_error(tr("service.local_storage_open"))
        finally:
            if not self._closing:
                self._suspending = False

    async def lock_application(self) -> None:
        """Делегирует безопасную блокировку активной чат-сессии."""
        await self._chat_controller.lock_application()

    def prepare_close(self) -> None:
        """Отзывает новые операции до ожидания native cancel и записи черновиков."""
        if self._disposed or self._closing:
            return
        if self._local_protection is not None:
            self._local_protection.update_observers(None, None)
        self.cancel_profile_deletion()
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
        if self._profile_deletion_progress is not None:
            self._profile_deletion_progress.dispose()
        self._chat_controller.dispose()

    async def flush_drafts(self) -> bool:
        return await self._chat_controller.flush_drafts()

    async def _activate_session(
        self,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        *,
        present_workspace: bool = True,
        preserve_protection_intent: bool = False,
    ) -> None:
        self._cancel_lock_task()
        self._clear_secret_controls(
            preserve_protection_intent=preserve_protection_intent
        )
        self._key_view = None
        self._pin_setup_view = None
        self._pin_login_view = None
        if present_workspace:
            await self._chat_controller.activate(api_key, key_validity, key_limit)
        else:
            await self._chat_controller.activate(
                api_key, key_validity, key_limit, present_workspace=False
            )

    async def _handle_chat_lock(self) -> None:
        self._lock_auth_access()
        epoch = self._security_epoch
        generation = self._chat_controller.session_generation
        if not self._disposed and not self._closing:
            message = tr("service.app_locked")
            if self._chat_controller.draft_save_failed:
                message = tr(
                    "app.lock_with_warning",
                    locked=message,
                    warning=self._draft_lock_warning(),
                )
            try:
                remaining = await self._auth_service.pin_lock_seconds_remaining()
            except Exception:
                if (
                    not self._disposed
                    and not self._closing
                    and epoch == self._security_epoch
                    and generation == self._chat_controller.session_generation
                ):
                    self._show_storage_error(tr("protection.unavailable"))
                return
            if (
                not self._disposed
                and not self._closing
                and epoch == self._security_epoch
                and generation == self._chat_controller.session_generation
            ):
                self._show_pin_login(message, remaining)

    @staticmethod
    def _draft_lock_warning() -> str:
        return tr("service.draft_lock_failed")

    def _show_key_entry(self, message: str = "", *, success: bool = False) -> None:
        self._trace_app("key_entry_build")
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
        self._trace_app("key_entry_shown")

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
        self._trace_app("pin_setup_build", auth_status=result.status)
        try:
            self._build_pin_setup(result)
        except Exception as error:
            self._trace_app("pin_setup_failed", error=error)
            raise
        self._trace_app("pin_setup_shown")

    def _build_pin_setup(self, result: AuthResult) -> None:
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

        async def show_protection(_event: ft.Event[ft.IconButton]) -> None:
            await self.show_pin_protection(view)

        shield = protection_shield(self._protection_snapshot(), show_protection)
        if self._local_protection is None:
            shield.tooltip = tr("protection_panel.open")
        self._pin_protection_shield = shield
        view = PinLoginView(
            self.submit_pin,
            on_forgot_pin=self.request_recovery if self._offer_recovery() else None,
            on_delete_profile=(
                self.request_profile_deletion
                if bool(
                    getattr(self._auth_service, "profile_deletion_available", False)
                )
                else None
            ),
            notice=self._protection_notice(),
            protection_shield=shield,
        )
        self._pin_login_view = view
        if message:
            view.show_message(message)
        self._replace_page(view.control)
        if self._local_protection is not None:
            self._local_protection.app_state_changed()
            self._update_protection_controls()
        if lock_seconds > 0:
            self._start_lock_countdown(view, lock_seconds)

    def _show_storage_error(self, message: str) -> None:
        self._cancel_protection_intent()
        self._chat_controller.deactivate()
        view = StorageErrorView(
            message or tr("service.local_storage_open"),
            self.start,
        )
        self._replace_page(view.control)

    def _replace_page(self, control: ft.Control) -> None:
        if self._disposed or self._closing:
            return
        intent = self._protection_test_intent
        if (
            intent is not None
            and intent.authorized_control is not None
            and intent.authorized_control is not control
        ):
            self._cancel_protection_intent()
        if self._profile_deletion_view is not None:
            self.cancel_profile_deletion()
        localize_tree(control)
        self._page.controls.clear()
        self._page.add(control)

    def _clear_secret_controls(
        self,
        *,
        cancel_code_issue: bool = True,
        preserve_protection_intent: bool = False,
    ) -> None:
        if not preserve_protection_intent:
            self._cancel_protection_intent()
        self._pin_protection_shield = None
        if self._profile_deletion_view is not None and not self._deletion_started:
            self.cancel_profile_deletion()
        if self._protection_setup_view is not None:
            self._protection_setup_view.dispose()
            self._protection_setup_view = None
        if cancel_code_issue:
            cancel = getattr(self._auth_service, "cancel_recovery_code_issue", None)
            if callable(cancel):
                cancel()
        for view in (
            self._code_entry_view,
            self._code_pin_view,
            self._code_display_view,
        ):
            if view is not None:
                view.dispose()
        self._code_entry_view = None
        self._code_pin_view = None
        self._code_display_view = None
        self._pending_code_issue_id = None
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

    def _start_lock_countdown(
        self, view: PinLoginView | RecoveryCodePinView, seconds: int
    ) -> None:
        self._cancel_lock_task()
        view.set_locked(seconds)
        self._lock_task = self._page.run_task(self._lock_countdown, view)

    def _pin_countdown_view_current(
        self, view: PinLoginView | RecoveryCodePinView
    ) -> bool:
        return (
            not self._disposed
            and not self._closing
            and (self._pin_login_view is view or self._code_pin_view is view)
        )

    async def _lock_countdown(self, view: PinLoginView | RecoveryCodePinView) -> None:
        while self._pin_countdown_view_current(view):
            try:
                remaining = await self._auth_service.pin_lock_seconds_remaining()
            except Exception:
                # Ошибка чтения не превращается в UI-разрешение проверки PIN.
                if self._pin_countdown_view_current(view):
                    view.show_message(tr("protection.unavailable"))
                    self._page.update()
                return
            if not self._pin_countdown_view_current(view):
                return
            view.set_locked(remaining)
            self._page.update()
            if remaining <= 0:
                return
            await asyncio.sleep(1)

    def _cancel_lock_task(self) -> None:
        if self._lock_task is not None and not self._lock_task.done():
            self._lock_task.cancel()
        self._lock_task = None
