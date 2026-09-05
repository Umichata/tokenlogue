"""Точка сборки мультиплатформенного приложения Tokenlogue."""

from __future__ import annotations

import asyncio

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
from storage.chat_repository import SqliteChatRepository
from storage.database import AuthDatabase
from storage.draft_repository import SqliteDraftRepository
from storage.message_repository import SqliteMessageRepository
from storage.secure_credentials import FletSecureCredentials
from ui import StorageErrorView, configure_page


async def main(page: ft.Page) -> None:
    """Собирает зависимости и подключает обработчики жизненного цикла."""
    configure_page(page)
    page.controls.clear()
    try:
        database = await asyncio.to_thread(AuthDatabase)
    except Exception:

        async def retry() -> None:
            await main(page)

        page.add(
            StorageErrorView(
                "Не удалось открыть каталог данных приложения.",
                on_retry=retry,
            ).control
        )
        return

    credentials = FletSecureCredentials()
    key_validator = OpenRouterClient()
    auth_service = AuthService(key_validator, credentials, database)
    chat_repository = SqliteChatRepository(database.path)
    message_repository = SqliteMessageRepository(database.path)
    drafts = ChatDraftService(SqliteDraftRepository(database.path))
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
    )

    async def close_session(_event: object = None) -> None:
        try:
            await controller.flush_drafts()
        finally:
            controller.dispose()

    page.on_disconnect = close_session
    page.on_close = close_session
    await controller.start()


if __name__ == "__main__":
    ft.run(main)
