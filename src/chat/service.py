"""Сервис локального управления чатами и политики расходов."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from auth.access import free_mode_allowed, paid_mode_allowed
from auth.models import KeyLimitInfo, KeyValidityState
from chat.accounting import validate_limit_configuration
from chat.models import (
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    Message,
    ModelCatalog,
    is_free_model,
    is_paid_model,
)


class ChatRepository(Protocol):
    def create_chat(self, chat: Chat) -> None: ...

    def create_chat_with_limits(
        self,
        chat: Chat,
        *,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal,
    ) -> None: ...

    def list_chats(self) -> list[Chat]: ...

    def get_chat(self, chat_id: str) -> Chat | None: ...

    def rename_chat(self, chat_id: str, title: str, updated_at: datetime) -> bool: ...

    def touch_chat(self, chat_id: str, updated_at: datetime) -> bool: ...

    def delete_chat(self, chat_id: str) -> bool: ...

    def list_messages(self, chat_id: str) -> list[Message]: ...


class ChatPolicyError(ValueError):
    """Выбранная модель нарушает политику режима чата."""


class PaidConfirmationRequired(ChatPolicyError):
    """Платный чат нельзя создать без текущего явного подтверждения."""


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        *,
        now: Callable[[], datetime] | None = None,
        uuid_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self._repository = repository
        self._now = now or (lambda: datetime.now(UTC))
        self._uuid_factory = uuid_factory

    async def create_chat(
        self,
        mode: ChatMode,
        model: CatalogModel,
        *,
        catalog: ModelCatalog,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        paid_confirmed: bool = False,
    ) -> Chat:
        if not isinstance(paid_confirmed, bool):
            raise ChatPolicyError("Некорректное подтверждение платного режима")
        selected_model = validate_model_for_mode(
            mode,
            model,
            catalog=catalog,
            key_validity=key_validity,
            key_limit=key_limit,
            paid_confirmed=paid_confirmed,
        )
        chat = self._build_chat(mode, selected_model)
        await asyncio.to_thread(self._repository.create_chat, chat)
        return chat

    async def create_chat_with_limits(
        self,
        mode: ChatMode,
        model: CatalogModel,
        *,
        catalog: ModelCatalog,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal | None,
        paid_confirmed: bool = False,
    ) -> Chat:
        if not isinstance(paid_confirmed, bool):
            raise ChatPolicyError("Некорректное подтверждение платного режима")
        selected_model = validate_model_for_mode(
            mode,
            model,
            catalog=catalog,
            key_validity=key_validity,
            key_limit=key_limit,
            paid_confirmed=paid_confirmed,
        )
        normalized_cost = validate_limit_configuration(
            mode,
            token_limit,
            max_completion_tokens,
            cost_limit_usd,
        )
        chat = self._build_chat(mode, selected_model)
        await asyncio.to_thread(
            self._repository.create_chat_with_limits,
            chat,
            token_limit=token_limit,
            max_completion_tokens=max_completion_tokens,
            cost_limit_usd=normalized_cost,
        )
        return chat

    async def list_chats(self) -> list[Chat]:
        return await asyncio.to_thread(self._repository.list_chats)

    async def get_chat(self, chat_id: str) -> Chat | None:
        _require_identifier(chat_id, "чата")
        return await asyncio.to_thread(self._repository.get_chat, chat_id)

    async def rename_chat(self, chat_id: str, title: str) -> bool:
        _require_identifier(chat_id, "чата")
        if not isinstance(title, str):
            raise ValueError("Название чата должно быть текстом")
        normalized = " ".join(title.split())
        if not normalized:
            raise ValueError("Название чата не может быть пустым")
        if len(normalized) > 120:
            raise ValueError("Название чата слишком длинное")
        return await asyncio.to_thread(
            self._repository.rename_chat,
            chat_id,
            normalized,
            _as_utc(self._now()),
        )

    async def touch_chat(self, chat_id: str) -> bool:
        _require_identifier(chat_id, "чата")
        return await asyncio.to_thread(
            self._repository.touch_chat,
            chat_id,
            _as_utc(self._now()),
        )

    async def delete_chat(self, chat_id: str) -> bool:
        _require_identifier(chat_id, "чата")
        return await asyncio.to_thread(self._repository.delete_chat, chat_id)

    async def list_messages(self, chat_id: str) -> list[Message]:
        _require_identifier(chat_id, "чата")
        return await asyncio.to_thread(self._repository.list_messages, chat_id)

    def _build_chat(self, mode: ChatMode, selected_model: CatalogModel) -> Chat:
        timestamp = _as_utc(self._now())
        return Chat(
            id=str(self._uuid_factory()),
            title="Новый чат",
            mode=mode,
            requested_model_id=selected_model.id,
            requested_model_name=selected_model.name,
            prompt_price_per_token=selected_model.prompt_price_per_token,
            completion_price_per_token=selected_model.completion_price_per_token,
            created_at=timestamp,
            updated_at=timestamp,
            request_price=selected_model.request_price,
            internal_reasoning_price_per_token=(
                selected_model.internal_reasoning_price_per_token
            ),
            input_cache_read_price_per_token=(
                selected_model.input_cache_read_price_per_token
            ),
            input_cache_write_price_per_token=(
                selected_model.input_cache_write_price_per_token
            ),
            pricing_overrides=selected_model.pricing_overrides,
            pricing_snapshot_complete=selected_model.pricing_is_complete,
        )


def validate_model_for_mode(
    mode: ChatMode,
    model: CatalogModel,
    *,
    catalog: ModelCatalog,
    key_validity: KeyValidityState,
    key_limit: KeyLimitInfo,
    paid_confirmed: bool,
) -> CatalogModel:
    """Не позволяет UI превратить бесплатный выбор в платный."""
    if not isinstance(mode, ChatMode) or not isinstance(model, CatalogModel):
        raise ChatPolicyError("Некорректный режим или модель чата")
    if not isinstance(paid_confirmed, bool):
        raise ChatPolicyError("Некорректное подтверждение платного режима")
    if mode is ChatMode.FREE:
        if not free_mode_allowed(key_validity):
            raise ChatPolicyError("Недействительный ключ запрещает модельные запросы")
        if model.id == FREE_ROUTER_MODEL.id:
            return FREE_ROUTER_MODEL
        if (
            not catalog.available
            or model not in catalog.free_models
            or not is_free_model(model)
        ):
            raise ChatPolicyError("Для бесплатного чата нужна модель с нулевыми ценами")
        return model

    if mode is ChatMode.PAID:
        if (
            not paid_mode_allowed(key_validity, key_limit)
            or not catalog.available
            or model.id == FREE_ROUTER_MODEL.id
            or model not in catalog.paid_models
            or not is_paid_model(model)
        ):
            raise ChatPolicyError("Для платного чата нужна совместимая платная модель")
        if not paid_confirmed:
            raise PaidConfirmationRequired(
                "Создание платного чата требует явного подтверждения"
            )
        return model

    raise ChatPolicyError("Неизвестный режим чата")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Некорректный идентификатор {label}")
