"""Локальные черновики с ревизиями, независимые от интерфейса, истории и бюджетов."""

from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Protocol

from i18n import tr
from storage.access_context import await_task_completion, repository_session
from storage.data_access import CompletionLease, DataAccess

DRAFT_STORAGE_MESSAGE = tr("service.draft_save_failed")


@dataclass(frozen=True)
class ChatDraft:
    chat_id: str
    revision: int = 0
    text: str = field(default="", repr=False)


class DraftStorageError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(DRAFT_STORAGE_MESSAGE)


class DraftRepository(Protocol):
    def get_draft(self, chat_id: str) -> ChatDraft: ...

    def save_draft(self, draft: ChatDraft) -> ChatDraft: ...


@dataclass
class _CachedDraft:
    draft: ChatDraft
    dirty: bool = False
    failed: bool = False


class ChatDraftService:
    """Фиксирует правки до await и последовательно сохраняет их для каждого чата."""

    def __init__(self, repository: DraftRepository) -> None:
        self._repository = repository
        self._access: DataAccess | None = getattr(repository, "access", None)
        self._lock_leases: dict[str, CompletionLease] = {}
        self._cache: dict[str, _CachedDraft] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._invalidations: dict[str, int] = {}

    @repository_session("_repository")
    async def load(self, chat_id: str) -> ChatDraft:
        _require_chat_id(chat_id)
        async with self._lock(chat_id):
            before = self._cache.get(chat_id)
            before_draft = before.draft if before is not None else None
            invalidation = self._invalidations.get(chat_id, 0)
            try:
                stored = await asyncio.to_thread(self._repository.get_draft, chat_id)
            except Exception:
                raise DraftStorageError() from None
            if self._invalidations.get(chat_id, 0) != invalidation:
                raise DraftStorageError()
            entry = self._cache.get(chat_id)
            if entry is None:
                self._cache[chat_id] = _CachedDraft(stored)
            elif (
                not entry.dirty
                and entry is before
                and entry.draft == before_draft
                and stored.revision >= entry.draft.revision
            ):
                # Резерв мог поглотить эту ревизию во время просмотра другого чата,
                # в том числе до исполнения связанного UI callback.
                entry.draft = stored
            return self.current(chat_id)

    def current(self, chat_id: str) -> ChatDraft:
        if self._access is not None:
            self._access.assert_current()
        _require_chat_id(chat_id)
        return self._cache[chat_id].draft

    def record_edit(self, chat_id: str, text: str) -> ChatDraft:
        if self._access is not None:
            self._access.assert_current()
        _require_chat_id(chat_id)
        if not isinstance(text, str):
            raise ValueError(tr("service.draft_text"))
        entry = self._cache[chat_id]
        if text != entry.draft.text:
            entry.draft = ChatDraft(chat_id, entry.draft.revision + 1, text)
            entry.dirty = True
        return entry.draft

    async def flush(self, chat_id: str) -> None:
        with self._access.provenance() if self._access is not None else nullcontext():
            await self._flush(chat_id)

    async def _flush(self, chat_id: str) -> None:
        _require_chat_id(chat_id)
        async with self._lock(chat_id):
            while (entry := self._cache.get(chat_id)) is not None and entry.dirty:
                snapshot = entry.draft
                lease = self._lock_leases.pop(chat_id, None)
                if lease is None and self._access is not None:
                    lease = self._access.completion(
                        "draft", chat_id, str(snapshot.revision)
                    )

                async def save() -> ChatDraft:
                    if lease is None:
                        return await asyncio.to_thread(
                            self._repository.save_draft, snapshot
                        )
                    with lease.use():
                        return await asyncio.to_thread(
                            self._repository.save_draft, snapshot
                        )

                write = asyncio.create_task(save())
                cancelled = False
                try:
                    try:
                        stored = await asyncio.shield(write)
                    except asyncio.CancelledError:
                        # Удерживаем блокировку чата до завершения SQLite worker.
                        # Отмена обработчика не допускает опережающую запись.
                        cancelled = True
                        stored = await await_task_completion(write)
                except Exception:
                    entry.failed = True
                    raise DraftStorageError() from None
                finally:
                    if lease is not None:
                        lease.close()
                if self._cache.get(chat_id) is entry and entry.draft == snapshot:
                    if stored != snapshot:
                        entry.failed = True
                        raise DraftStorageError()
                    entry.dirty = False
                    entry.failed = False
                    if self._access is not None and not self._access.unlocked:
                        self.forget(chat_id)
                if cancelled:
                    raise asyncio.CancelledError()

    async def flush_all(self) -> None:
        with self._access.provenance() if self._access is not None else nullcontext():
            for chat_id in tuple(self._cache):
                await self.flush(chat_id)

    def acknowledge_reserved(self, snapshot: ChatDraft) -> None:
        """Обновляет только память, SQLite атомарно поглощает ту же ревизию."""
        entry = self._cache.get(snapshot.chat_id)
        if entry is not None and entry.draft == snapshot:
            entry.draft = ChatDraft(snapshot.chat_id, snapshot.revision)
            entry.dirty = False
            entry.failed = False

    def failed(self, chat_id: str) -> bool:
        entry = self._cache.get(chat_id)
        return entry is not None and entry.failed

    def forget(self, chat_id: str) -> None:
        lease = self._lock_leases.pop(chat_id, None)
        if lease is not None:
            lease.close()
        self._cache.pop(chat_id, None)
        self._invalidations[chat_id] = self._invalidations.get(chat_id, 0) + 1

    def prepare_lock(self) -> None:
        """Удерживает только несохранённые правки и разрешения их записи."""
        if self._access is None:
            return
        for chat_id, entry in tuple(self._cache.items()):
            if not entry.dirty:
                self.forget(chat_id)
            elif chat_id not in self._lock_leases and self._access.unlocked:
                self._lock_leases[chat_id] = self._access.completion(
                    "draft", chat_id, str(entry.draft.revision)
                )

    def _lock(self, chat_id: str) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())


def _require_chat_id(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("service.chat_id_invalid"))
