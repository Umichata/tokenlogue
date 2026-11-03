"""Сервис локального управления чатами и политики расходов."""

from __future__ import annotations

import asyncio
import secrets
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
from chat.paid_consent import PaidConsent
from i18n import tr
from storage.access_context import finish_worker, repository_session


class ChatRepository(Protocol):
    def set_paid_without_confirmation(
        self, chat_id: str, enabled: bool, revision: str, updated_at: datetime
    ) -> bool: ...
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
        self._paid_scope = object()
        self._paid_epochs: dict[str, int] = {}
        self._paid_changes_pending: dict[str, int] = {}

    def paid_consent(self, chat: Chat) -> PaidConsent | None:
        if (
            chat.mode is not ChatMode.PAID
            or chat.paid_without_confirmation is not True
            or not chat.paid_policy_revision
            or self._paid_changes_pending.get(chat.id, 0) > 0
        ):
            return None
        return PaidConsent(
            chat.id,
            chat.paid_policy_revision,
            self._paid_epochs.get(chat.id, 0),
            self._paid_scope,
            getattr(getattr(self._repository, "access", None), "epoch", None),
        )

    def paid_consent_is_current(self, consent: PaidConsent) -> bool:
        return (
            consent.scope is self._paid_scope
            and self._paid_changes_pending.get(consent.chat_id, 0) == 0
            and consent.epoch == self._paid_epochs.get(consent.chat_id, 0)
            and consent.session_epoch
            == getattr(getattr(self._repository, "access", None), "epoch", None)
        )

    def paid_consent_matches(self, chat: Chat, consent: PaidConsent) -> bool:
        return (
            self.paid_consent_is_current(consent)
            and chat.id == consent.chat_id
            and chat.mode is ChatMode.PAID
            and chat.paid_without_confirmation is True
            and chat.paid_policy_revision == consent.revision
        )

    @repository_session("_repository")
    async def set_paid_without_confirmation(self, chat_id: str, enabled: bool) -> Chat:
        _require_identifier(chat_id, tr("service.label.chat"))
        if type(enabled) is not bool:
            raise ValueError(tr("service.paid_confirmation_invalid"))
        # Revocation is visible before awaiting SQLite, including failed writes.
        # A pending dispatch must not retain a permission while a change queues.
        self._paid_epochs[chat_id] = self._paid_epochs.get(chat_id, 0) + 1
        self._paid_changes_pending[chat_id] = (
            self._paid_changes_pending.get(chat_id, 0) + 1
        )

        async def change_and_readback() -> Chat:
            changed = await asyncio.to_thread(
                self._repository.set_paid_without_confirmation,
                chat_id,
                enabled,
                secrets.token_hex(16),
                _as_utc(self._now()),
            )
            if not changed:
                raise KeyError(tr("service.chat_missing"))
            chat = await asyncio.to_thread(self._repository.get_chat, chat_id)
            if chat is None:
                raise KeyError(tr("service.chat_missing"))
            return chat

        try:
            # A cancelled owner must not release consent while its SQLite worker
            # can still commit. The counted fence also covers post-write readback.
            return await finish_worker(change_and_readback())
        finally:
            remaining = self._paid_changes_pending[chat_id] - 1
            if remaining:
                self._paid_changes_pending[chat_id] = remaining
            else:
                del self._paid_changes_pending[chat_id]

    @repository_session("_repository")
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
            raise ChatPolicyError(tr("service.paid_confirmation_invalid"))
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

    @repository_session("_repository")
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
            raise ChatPolicyError(tr("service.paid_confirmation_invalid"))
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

    @repository_session("_repository")
    async def list_chats(self) -> list[Chat]:
        return await asyncio.to_thread(self._repository.list_chats)

    @repository_session("_repository")
    async def get_chat(self, chat_id: str) -> Chat | None:
        _require_identifier(chat_id, tr("service.label.chat"))
        return await asyncio.to_thread(self._repository.get_chat, chat_id)

    @repository_session("_repository")
    async def rename_chat(self, chat_id: str, title: str) -> bool:
        _require_identifier(chat_id, tr("service.label.chat"))
        if not isinstance(title, str):
            raise ValueError(tr("service.title_text"))
        normalized = " ".join(title.split())
        if not normalized:
            raise ValueError(tr("service.title_empty"))
        if len(normalized) > 120:
            raise ValueError(tr("service.title_long"))
        return await asyncio.to_thread(
            self._repository.rename_chat,
            chat_id,
            normalized,
            _as_utc(self._now()),
        )

    @repository_session("_repository")
    async def touch_chat(self, chat_id: str) -> bool:
        _require_identifier(chat_id, tr("service.label.chat"))
        return await asyncio.to_thread(
            self._repository.touch_chat,
            chat_id,
            _as_utc(self._now()),
        )

    @repository_session("_repository")
    async def delete_chat(self, chat_id: str) -> bool:
        _require_identifier(chat_id, tr("service.label.chat"))
        return await asyncio.to_thread(self._repository.delete_chat, chat_id)

    @repository_session("_repository")
    async def list_messages(self, chat_id: str) -> list[Message]:
        _require_identifier(chat_id, tr("service.label.chat"))
        return await asyncio.to_thread(self._repository.list_messages, chat_id)

    def _build_chat(self, mode: ChatMode, selected_model: CatalogModel) -> Chat:
        timestamp = _as_utc(self._now())
        return Chat(
            id=str(self._uuid_factory()),
            title="Новый чат",
            title_origin="placeholder",
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
        raise ChatPolicyError(tr("service.mode_model_invalid"))
    if not isinstance(paid_confirmed, bool):
        raise ChatPolicyError(tr("service.paid_confirmation_invalid"))
    if mode is ChatMode.FREE:
        if not free_mode_allowed(key_validity):
            raise ChatPolicyError(tr("service.invalid_key_blocks"))
        if model.id == FREE_ROUTER_MODEL.id:
            return FREE_ROUTER_MODEL
        if (
            not catalog.available
            or model not in catalog.free_models
            or not is_free_model(model)
        ):
            raise ChatPolicyError(tr("service.free_model_required"))
        return model

    if mode is ChatMode.PAID:
        if (
            not paid_mode_allowed(key_validity, key_limit)
            or not catalog.available
            or model.id == FREE_ROUTER_MODEL.id
            or model not in catalog.paid_models
            or not is_paid_model(model)
        ):
            raise ChatPolicyError(tr("service.paid_model_required"))
        if not paid_confirmed:
            raise PaidConfirmationRequired(tr("service.paid_creation_confirmation"))
        return model

    raise ChatPolicyError(tr("service.mode_unknown"))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("service.identifier_invalid", field=label))
