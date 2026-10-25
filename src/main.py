"""Точка сборки мультиплатформенного приложения Tokenlogue."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

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
from platform_security.device_recovery import DeviceRecovery
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
from storage.database_connections import DatabaseOwnershipError
from storage.draft_repository import SqliteDraftRepository
from storage.message_repository import SqliteMessageRepository
from storage.secure_credentials import FletSecureCredentials
from ui import StorageErrorView, configure_page
from ui.branding import set_page_animations_active


async def main(page: ft.Page) -> None:
    """Собирает зависимости и подключает обработчики жизненного цикла."""
    configure_page(page)
    page.controls.clear()
    data_directory = os.environ.get("FLET_APP_STORAGE_DATA")
    preferences = PreferencesStore(
        Path(data_directory) / "tokenlogue-preferences.json" if data_directory else None
    )

    def configure_material_language() -> None:
        page.locale_configuration = ft.LocaleConfiguration(
            supported_locales=[ft.Locale("ru"), ft.Locale("en")],
            current_locale=ft.Locale(get_language()),
        )

    def update_language() -> None:
        configure_material_language()
        localize_tree(page)
        page.update()

    configure_localization(preferences, update_language)
    configure_material_language()
    credentials: FletSecureCredentials | None = None
    try:
        database_path = (
            Path(data_directory) / DATABASE_FILENAME if data_directory else None
        )
        if database_path is not None and (
            not database_path.exists() or database_path.stat().st_size == 0
        ):
            credentials = FletSecureCredentials()
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
    access = DataAccess()
    platform_bridge = (
        DeviceRecovery() if page.platform is ft.PagePlatform.ANDROID else None
    )
    protection = DataProtection(
        database.path,
        database,
        credentials.storage_backend,
        access,
        durable_write=(
            platform_bridge.sync_secure_storage if platform_bridge is not None else None
        ),
    )
    recovery = platform_bridge
    if recovery is not None and not await recovery.supports_recovery():
        recovery = None
    key_validator = OpenRouterClient()
    auth_service = AuthService(
        key_validator,
        credentials,
        database,
        protection=protection,
        recovery_provider=recovery,
    )
    chat_repository = SqliteChatRepository(database.path, access=access)
    message_repository = SqliteMessageRepository(database.path, access=access)
    drafts = ChatDraftService(SqliteDraftRepository(database.path, access=access))
    chat_service = ChatService(chat_repository)
    budget_service = ChatBudgetService(message_repository)
    catalog_client = ModelCatalogClient()
    catalog_service = ModelCatalogService(catalog_client)
    sending_service = MessageSendingService(
        chat_service,
        message_repository,
        ChatCompletionsClient(),
        catalog_client,
        key_validator,
    )
    controller = AppController(
        page,
        auth_service,
        key_validator,
        chat_service,
        catalog_service,
        budget_service,
        sending_service,
        drafts,
        data_access=access,
    )

    async def close_session(_event: object = None) -> None:
        try:
            controller.prepare_close()
            set_page_animations_active(page, False)
            await controller.cancel_system_recovery()
            await controller.flush_drafts()
        finally:
            controller.dispose()

    page.on_app_lifecycle_state_change = controller.handle_lifecycle_change
    page.on_disconnect = close_session
    page.on_close = close_session
    await controller.start()


if __name__ == "__main__":
    ft.run(main)
