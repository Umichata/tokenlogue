"""Draft persistence in the app-private SQLite database; never message history."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from chat.drafts import ChatDraft, DraftStorageError


class SqliteDraftRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path)

    def get_draft(self, chat_id: str) -> ChatDraft:
        _require_identifier(chat_id)
        with self._connection() as connection:
            return _read(connection, chat_id)

    def save_draft(self, draft: ChatDraft) -> ChatDraft:
        if not isinstance(draft, ChatDraft):
            raise ValueError("Некорректный черновик")
        _require_identifier(draft.chat_id)
        if not isinstance(draft.text, str):
            raise ValueError("Черновик должен быть текстом")
        if (
            isinstance(draft.revision, bool)
            or not isinstance(draft.revision, int)
            or draft.revision <= 0
        ):
            raise ValueError("Некорректная ревизия черновика")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            # Never insert for a deleted chat. Strictly newer revisions are the
            # only overwrites, including after a reservation consumed the text.
            connection.execute(
                """
                INSERT INTO chat_drafts (chat_id, revision, content)
                SELECT ?, ?, ? WHERE EXISTS (SELECT 1 FROM chats WHERE id = ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    revision = excluded.revision, content = excluded.content
                WHERE excluded.revision > chat_drafts.revision
                """,
                (draft.chat_id, draft.revision, draft.text, draft.chat_id),
            )
            return _read(connection, draft.chat_id)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()


def _read(connection: sqlite3.Connection, chat_id: str) -> ChatDraft:
    row = connection.execute(
        """
        SELECT d.revision, d.content FROM chats AS c
        LEFT JOIN chat_drafts AS d ON d.chat_id = c.id WHERE c.id = ?
        """,
        (chat_id,),
    ).fetchone()
    if row is None:
        raise DraftStorageError()
    return ChatDraft(chat_id, row[0] or 0, row[1] if row[1] is not None else "")


def _require_identifier(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Некорректный идентификатор чата")
