"""Сохраняет черновики в приватной SQLite отдельно от истории сообщений."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from chat.drafts import ChatDraft, DraftStorageError
from i18n import tr
from storage.database_connections import (
    ContentAccess,
    encrypt_value,
)
from storage.database_connections import (
    connection as protected_connection,
)


class SqliteDraftRepository:
    def __init__(
        self, database_path: str | Path, access: ContentAccess | None = None
    ) -> None:
        self.path = Path(database_path)
        self.access = access

    def get_draft(self, chat_id: str) -> ChatDraft:
        _require_identifier(chat_id)
        with self._connection() as connection:
            return _read(connection, chat_id)

    def save_draft(self, draft: ChatDraft) -> ChatDraft:
        if not isinstance(draft, ChatDraft):
            raise ValueError(tr("service.draft_invalid"))
        _require_identifier(draft.chat_id)
        if not isinstance(draft.text, str):
            raise ValueError(tr("service.draft_text"))
        if (
            isinstance(draft.revision, bool)
            or not isinstance(draft.revision, int)
            or draft.revision <= 0
        ):
            raise ValueError(tr("service.draft_revision_invalid"))
        with self._connection(
            "draft", chat_id=draft.chat_id, record_id=str(draft.revision)
        ) as connection:
            connection.execute("BEGIN IMMEDIATE")
            # Не создаём черновик удалённого чата. Обновляем запись только более новой
            # ревизией, в том числе после поглощения текста резервированием.
            connection.execute(
                """
                INSERT INTO chat_drafts (chat_id, revision, content)
                SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM chats WHERE id = ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    revision = excluded.revision, content = excluded.content
                WHERE excluded.revision > chat_drafts.revision
                """,
                (
                    draft.chat_id,
                    draft.revision,
                    encrypt_value(
                        connection,
                        draft.text,
                        table="chat_drafts",
                        field="content",
                        record_id=draft.chat_id,
                        chat_id=draft.chat_id,
                        revision=draft.revision,
                    ),
                    draft.chat_id,
                ),
            )
            return _read(connection, draft.chat_id)

    @contextmanager
    def _connection(
        self, operation: str = "read", *, chat_id: str = "", record_id: str = ""
    ) -> Iterator[sqlite3.Connection]:
        with protected_connection(
            self.path, self.access, operation, chat_id=chat_id, record_id=record_id
        ) as connection:
            yield connection


def _read(connection: sqlite3.Connection, chat_id: str) -> ChatDraft:
    row = connection.execute(
        """
        SELECT c.id AS chat_id, d.revision, d.content FROM chats AS c
        LEFT JOIN chat_drafts AS d ON d.chat_id = c.id WHERE c.id = ?
        """,
        (chat_id,),
    ).fetchone()
    if row is None:
        raise DraftStorageError()
    return ChatDraft(
        chat_id,
        row["revision"] or 0,
        row["content"] if row["content"] is not None else "",
    )


def _require_identifier(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("service.chat_id_invalid"))
