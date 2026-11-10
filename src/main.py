"""Точка сборки мультиплатформенного приложения Tokenlogue."""

from __future__ import annotations

import asyncio
import inspect
import os
from pathlib import Path
from typing import TYPE_CHECKING

import flet as ft

from api.chat_completions import ChatCompletionsClient
from api.models import ModelCatalogClient, ModelCatalogService
from api.openrouter import OpenRouterClient
from app import AppController
from auth.service import AuthService
from chat.accounting import ChatBudgetService
from chat.drafts import ChatDraftService
from chat.sending import MessageSendingService
from chat.service import ChatService
from i18n import configure_localization, get_language, localize_tree, tr
from platform_security.device_recovery import DeviceRecovery, RecoveryProvider
from platform_security.local_protection import SCREEN_CONTRACT, DeviceProtectionHistory
from platform_security.protection_trace import protection_trace_from_environment
from platform_security.windows_session import WindowsSessionAdapter
from preferences import PreferencesStore
from storage.chat_repository import SqliteChatRepository
from storage.data_access import DataAccess
from storage.data_protection import (
    DATA_BINDING_ALIAS,
    DATA_INITIALIZATION_ALIAS,
    DATA_KEY_ALIAS,
    DataProtection,
    DataProtectionError,
)
from storage.database import DATABASE_FILENAME, AuthDatabase
from storage.database_connections import (
    DatabaseOwnershipError,
    database_lock,
    deletion_pending,
)
from storage.draft_repository import SqliteDraftRepository
from storage.message_repository import SqliteMessageRepository
from storage.profile_deletion import ProfileDeletion, validate_profile_path
from storage.secure_credentials import FletSecureCredentials
from ui import StorageErrorView, configure_page
from ui.branding import set_page_animations_active
from ui.profile_deletion_view import ProfileDeletionProgressView

if TYPE_CHECKING:
    from platform_security.linux_recovery import LinuxRecovery
    from platform_security.linux_session import LinuxSessionWatcher


def _claim_profile(path: Path) -> None:
    """Lifetime flock удерживается и при отсутствии SQLite во время удаления."""
    validate_profile_path(path)
    with database_lock(path):
        pass


def _validate_profile(path: Path) -> Path:
    path = validate_profile_path(path, require_private=False)
    for name in (
        "tokenlogue-preferences.json",
        "." + path.name + ".owner.lock",
        *(path.name + suffix for suffix in ("-wal", "-shm", "-journal")),
    ):
        validate_profile_path(
            path.with_name(name), create_parent=False, require_private=False
        )
    return path


async def start_linux_session_watch(controller: AppController) -> LinuxSessionWatcher:
    """Создаёт Linux-подписку только после выбора Linux-композиции."""
    from platform_security.linux_session import (
        LinuxSessionWatcher,
        SessionObservation,
        SessionSecurityEvent,
        SessionWatchStatus,
    )

    def status_changed(status: SessionWatchStatus) -> None:
        controller.set_session_watch_status(
            system_events=status.system_events, screen_events=status.screen_events
        )
        controller.set_screen_lock_adapter(watcher, watcher.sleep_context)
        controller.set_sleep_adapter(watcher)

    def normal_lock(event: SessionSecurityEvent) -> None:
        before = controller.protection_app_state()
        controller.prepare_system_lock(event)
        # Receipt belongs only to the ordinary trusted event path, after revoke.
        if event is SessionSecurityEvent.SCREEN_LOCK:
            controller.record_normal_protection(
                "screen", watcher.screen_context, before
            )
        elif event is SessionSecurityEvent.SLEEP:
            controller.record_normal_protection("sleep", watcher.sleep_context, before)

    def observation(event: SessionObservation) -> None:
        if event.kind == "sleep_resume":
            controller.record_sleep_resume(
                event.context, event.actual_suspend, test_id=event.test_id
            )
        elif event.kind == "screen_locked":
            controller.record_screen_transition(
                event.context, True, test_id=event.test_id
            )
        elif event.kind == "screen_inactive":
            controller.record_screen_transition(
                event.context, False, test_id=event.test_id
            )

    watcher = LinuxSessionWatcher(
        normal_lock, on_status=status_changed, on_observation=observation
    )
    try:
        await watcher.start()
    except BaseException:
        await watcher.aclose()
        raise
    return watcher


async def main(page: ft.Page) -> None:
    """Собирает зависимости и подключает обработчики жизненного цикла."""
    configure_page(page)
    page.controls.clear()
    data_directory = os.environ.get("FLET_APP_STORAGE_DATA")
    try:
        if not data_directory:
            raise RuntimeError(tr("service.storage_path_missing"))
        database_path = await asyncio.to_thread(
            _validate_profile, Path(data_directory) / DATABASE_FILENAME
        )
    except Exception:

        async def retry_path() -> None:
            await main(page)

        page.add(
            StorageErrorView(tr("service.data_directory_failed"), retry_path).control
        )
        return
    preferences = PreferencesStore(
        database_path.with_name("tokenlogue-preferences.json")
    )

    def configure_material_language() -> None:
        page.locale_configuration = ft.LocaleConfiguration(
            supported_locales=[ft.Locale("ru"), ft.Locale("en")],
            current_locale=ft.Locale(get_language()),
        )

    controller: AppController | None = None

    def update_language() -> None:
        if controller is not None:
            controller.handle_language_change()
        configure_material_language()
        localize_tree(page)
        page.update()

    configure_localization(preferences, update_language)
    configure_material_language()
    credentials: FletSecureCredentials | None = None
    platform_bridge: DeviceRecovery | None = None
    deletion: ProfileDeletion | None = None
    try:
        if deletion_pending(database_path):
            await asyncio.to_thread(_claim_profile, database_path)
            credentials = FletSecureCredentials()
            platform_bridge = (
                DeviceRecovery()
                if getattr(page, "platform", None) is ft.PagePlatform.ANDROID
                else None
            )
            deletion = ProfileDeletion(
                database_path,
                credentials.storage_backend,
                durable_write=(
                    platform_bridge.sync_secure_storage
                    if platform_bridge is not None
                    else None
                ),
            )

            async def retry_deletion() -> None:
                await main(page)

            progress = ProfileDeletionProgressView(retry_deletion)
            page.add(progress.control)
            try:
                # Ни AuthDatabase, ни обычный PIN reconcile здесь не запускаются.
                await deletion.finish()
            finally:
                progress.dispose()
                page.controls.clear()
        if not database_path.exists() or database_path.stat().st_size == 0:
            credentials = credentials or FletSecureCredentials()
            backend = credentials.storage_backend
            if any(
                [
                    await backend.contains_key(DATA_KEY_ALIAS),
                    await backend.contains_key(DATA_BINDING_ALIAS),
                    await backend.contains_key(DATA_INITIALIZATION_ALIAS),
                ]
            ):
                raise DataProtectionError("protection.key_missing")
        database = await asyncio.to_thread(AuthDatabase)
    except Exception as error:
        message = (
            error.args[0]
            if isinstance(error, (DataProtectionError, DatabaseOwnershipError))
            else tr("service.data_directory_failed")
        )
        if deletion is not None and deletion.pending():
            message = tr("profile_deletion.unavailable")

        async def retry() -> None:
            await main(page)

        page.add(
            StorageErrorView(
                message,
                on_retry=retry,
            ).control
        )
        return

    credentials = credentials or FletSecureCredentials()
    if platform_bridge is None and page.platform is ft.PagePlatform.ANDROID:
        platform_bridge = DeviceRecovery()
    deletion = deletion or ProfileDeletion(
        database.path,
        credentials.storage_backend,
        durable_write=(
            platform_bridge.sync_secure_storage if platform_bridge is not None else None
        ),
    )
    access = DataAccess()
    protection = DataProtection(
        database.path,
        database,
        credentials.storage_backend,
        access,
        durable_write=(
            platform_bridge.sync_secure_storage if platform_bridge is not None else None
        ),
    )
    recovery: RecoveryProvider | None = platform_bridge
    saved_screen_history = False
    linux_recovery: LinuxRecovery | None = None
    if page.platform is ft.PagePlatform.LINUX:
        from platform_security.linux_recovery import LinuxRecovery

        linux_recovery = LinuxRecovery()
        recovery = linux_recovery
    elif recovery is not None and not await recovery.supports_recovery():
        recovery = None
    key_validator = OpenRouterClient()
    auth_service = AuthService(
        key_validator,
        credentials,
        database,
        protection=protection,
        recovery_provider=recovery,
        profile_deletion=deletion,
    )
    chat_repository = SqliteChatRepository(database.path, access=access)
    message_repository = SqliteMessageRepository(database.path, access=access)
    drafts = ChatDraftService(SqliteDraftRepository(database.path, access=access))
    chat_service = ChatService(chat_repository)
    budget_service = ChatBudgetService(message_repository)
    catalog_client = ModelCatalogClient()
    catalog_service = ModelCatalogService(catalog_client)
    completion_client = ChatCompletionsClient()
    sending_service = MessageSendingService(
        chat_service,
        message_repository,
        completion_client,
        catalog_client,
        key_validator,
    )

    async def reload_profile() -> None:
        await close_session(discard_profile=True)
        await main(page)

    async def deleted_profile() -> None:
        await reload_profile()
        page.show_dialog(ft.SnackBar(content=ft.Text(tr("profile_deletion.success"))))

    controller = AppController(
        page,
        auth_service,
        key_validator,
        chat_service,
        catalog_service,
        budget_service,
        sending_service,
        drafts,
        credits_reader=key_validator,
        data_access=access,
        on_profile_deleted=deleted_profile,
        on_profile_reload=reload_profile,
    )
    if page.platform is ft.PagePlatform.LINUX:
        # This store is outside the portable profile. Importing it only on Linux
        # also keeps its POSIX file-lock implementation out of other platforms.
        from platform_security.device_protection_store import DeviceProtectionStore
        from storage.access_context import finish_worker

        def load_device_history():
            store = DeviceProtectionStore.for_current_linux_account()
            try:
                return store, store.load(), False
            except Exception:
                # Retain the writer so a transient storage error can be retried
                # after a later actual check. Corrupt records are never reset.
                return store, DeviceProtectionHistory(), True

        try:
            history_store, history, history_error = await finish_worker(
                asyncio.to_thread(load_device_history)
            )
        except Exception:
            controller.configure_protection_history(
                DeviceProtectionHistory(), None, persistence_error=True
            )
        else:
            controller.configure_protection_history(
                history, history_store.save, persistence_error=history_error
            )
            saved_screen_history = (
                history.screen is not None
                and history.screen.contract == SCREEN_CONTRACT
            )
    protection_trace = (
        protection_trace_from_environment()
        if page.platform is ft.PagePlatform.LINUX
        else None
    )
    controller.set_protection_trace(protection_trace)

    watcher: LinuxSessionWatcher | None = None
    closed = False

    async def close_session(
        _event: object = None, *, discard_profile: bool = False
    ) -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        try:
            controller.prepare_close()
            set_page_animations_active(page, False)
            await controller.close_protection_checks()
            await controller.cancel_system_recovery()
            if not discard_profile:
                await controller.flush_drafts()
            await controller.wait_system_lock()
        finally:
            try:
                if watcher is not None:
                    await watcher.aclose()
            finally:
                try:
                    if linux_recovery is not None:
                        await linux_recovery.aclose()
                finally:
                    controller.dispose()
                    if protection_trace is not None:
                        protection_trace.close()
                    closers = []
                    for client in (key_validator, catalog_client, completion_client):
                        close = getattr(client, "aclose", None)
                        if callable(close):
                            work = close()
                            if inspect.isawaitable(work):
                                closers.append(work)
                    await asyncio.gather(
                        *closers,
                        return_exceptions=True,
                    )

    page.on_app_lifecycle_state_change = controller.handle_lifecycle_change
    page.on_resize = controller.handle_page_resize
    page.on_disconnect = close_session
    page.on_close = close_session
    try:
        if page.platform is ft.PagePlatform.LINUX:
            watcher = await start_linux_session_watch(controller)
            if saved_screen_history:
                watcher.enable_saved_screen_monitoring()
        elif page.platform is ft.PagePlatform.WINDOWS:
            controller.set_screen_lock_adapter(WindowsSessionAdapter())
        await controller.start()
    except BaseException:
        await close_session(discard_profile=True)
        raise


if __name__ == "__main__":
    ft.run(main)
