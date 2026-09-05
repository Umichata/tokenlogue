"""Revisioned local drafts, independent of views, message history and budgets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

DRAFT_STORAGE_MESSAGE = (
    "Не удалось сохранить черновик. Текст остаётся в редакторе. "
    "Повторите попытку перед переходом в другой чат."
)


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
    """Captures edits before awaits; serializes persistence per chat without debounce."""

    def __init__(self, repository: DraftRepository) -> None:
        self._repository = repository
        self._cache: dict[str, _CachedDraft] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._invalidations: dict[str, int] = {}

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
                # A reservation can have consumed this revision while another
                # chat was visible, including before its UI callback ran.
                entry.draft = stored
            return self.current(chat_id)

    def current(self, chat_id: str) -> ChatDraft:
        _require_chat_id(chat_id)
        return self._cache[chat_id].draft

    def record_edit(self, chat_id: str, text: str) -> ChatDraft:
        _require_chat_id(chat_id)
        if not isinstance(text, str):
            raise ValueError("Черновик должен быть текстом")
        entry = self._cache[chat_id]
        if text != entry.draft.text:
            entry.draft = ChatDraft(chat_id, entry.draft.revision + 1, text)
            entry.dirty = True
        return entry.draft

    async def flush(self, chat_id: str) -> None:
        _require_chat_id(chat_id)
        async with self._lock(chat_id):
            while (entry := self._cache.get(chat_id)) is not None and entry.dirty:
                snapshot = entry.draft
                write = asyncio.create_task(
                    asyncio.to_thread(self._repository.save_draft, snapshot)
                )
                cancelled = False
                try:
                    try:
                        stored = await asyncio.shield(write)
                    except asyncio.CancelledError:
                        # Keep the per-chat lock until the SQLite worker stops.
                        # A cancelled handler must not let a later write overtake it.
                        cancelled = True
                        stored = await write
                except Exception:
                    entry.failed = True
                    raise DraftStorageError() from None
                if self._cache.get(chat_id) is entry and entry.draft == snapshot:
                    if stored != snapshot:
                        entry.failed = True
                        raise DraftStorageError()
                    entry.dirty = False
                    entry.failed = False
                if cancelled:
                    raise asyncio.CancelledError()

    async def flush_all(self) -> None:
        for chat_id in tuple(self._cache):
            await self.flush(chat_id)

    def acknowledge_reserved(self, snapshot: ChatDraft) -> None:
        """Only update memory; SQLite consumes the same revision transactionally."""
        entry = self._cache.get(snapshot.chat_id)
        if entry is not None and entry.draft == snapshot:
            entry.draft = ChatDraft(snapshot.chat_id, snapshot.revision)
            entry.dirty = False
            entry.failed = False

    def failed(self, chat_id: str) -> bool:
        entry = self._cache.get(chat_id)
        return entry is not None and entry.failed

    def forget(self, chat_id: str) -> None:
        self._cache.pop(chat_id, None)
        self._invalidations[chat_id] = self._invalidations.get(chat_id, 0) + 1

    def _lock(self, chat_id: str) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())


def _require_chat_id(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Некорректный идентификатор чата")
