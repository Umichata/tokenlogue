"""SQLite-репозиторий многосессионных чатов в общей базе приложения."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from chat.models import (
    Chat,
    ChatMode,
    Message,
    MessageRole,
    MessageStatus,
    PriceComponents,
)
from i18n import tr
from storage.database_connections import (
    ContentAccess,
    encrypt_value,
)
from storage.database_connections import (
    connection as protected_connection,
)


class SqliteChatRepository:
    def __init__(
        self, database_path: str | Path, access: ContentAccess | None = None
    ) -> None:
        self.path = Path(database_path)
        self.access = access

    def create_chat(self, chat: Chat) -> None:
        _require_chat(chat)
        with self._connection("write", chat_id=chat.id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _insert_chat(connection, chat)
            _insert_budget(
                connection,
                chat,
                limits_configured=False,
                token_limit=None,
                max_completion_tokens=None,
                cost_limit_usd=Decimal("0") if chat.mode is ChatMode.FREE else None,
            )

    def create_chat_with_limits(
        self,
        chat: Chat,
        *,
        token_limit: int,
        max_completion_tokens: int,
        cost_limit_usd: Decimal,
    ) -> None:
        """Атомарно сохраняет чат и его первоначально подтверждённый бюджет."""
        _require_chat(chat)
        if isinstance(token_limit, bool) or not isinstance(token_limit, int):
            raise ValueError(tr("service.token_integer"))
        if token_limit <= 0:
            raise ValueError(tr("service.token_positive"))
        if isinstance(max_completion_tokens, bool) or not isinstance(
            max_completion_tokens,
            int,
        ):
            raise ValueError(tr("service.completion_integer_short"))
        if max_completion_tokens < 16 or max_completion_tokens > token_limit:
            raise ValueError(tr("service.completion_invalid"))
        if (
            not isinstance(cost_limit_usd, Decimal)
            or not cost_limit_usd.is_finite()
            or cost_limit_usd < 0
        ):
            raise ValueError(tr("service.money_invalid"))
        if chat.mode is ChatMode.FREE and cost_limit_usd != 0:
            raise ValueError(tr("service.free_no_money"))
        if chat.mode is ChatMode.PAID and cost_limit_usd <= 0:
            raise ValueError(tr("service.paid_positive_money"))
        with self._connection("write", chat_id=chat.id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            _insert_chat(connection, chat)
            _insert_budget(
                connection,
                chat,
                limits_configured=True,
                token_limit=token_limit,
                max_completion_tokens=max_completion_tokens,
                cost_limit_usd=cost_limit_usd,
            )

    def list_chats(self) -> list[Chat]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chats
                ORDER BY updated_at DESC, created_at DESC, id ASC
                """
            ).fetchall()
        return [_chat_from_row(row) for row in rows]

    def get_chat(self, chat_id: str) -> Chat | None:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM chats WHERE id = ?",
                (chat_id,),
            ).fetchone()
        return _chat_from_row(row) if row is not None else None

    def rename_chat(self, chat_id: str, title: str, updated_at: datetime) -> bool:
        _require_identifier(chat_id, tr("service.label.chat"))
        _require_text(title, tr("service.label.title"))
        with self._connection("write", chat_id=chat_id) as connection:
            cursor = connection.execute(
                """
                UPDATE chats
                SET title = ?, title_is_manual = 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    encrypt_value(
                        connection,
                        title,
                        table="chats",
                        field="title",
                        record_id=chat_id,
                    ),
                    _serialize_datetime(updated_at),
                    chat_id,
                ),
            )
            if getattr(connection, "cipher", None) is not None:
                connection.execute(
                    "UPDATE chats SET title_origin = 'manual' WHERE id = ?", (chat_id,)
                )
        return cursor.rowcount == 1

    def touch_chat(self, chat_id: str, updated_at: datetime) -> bool:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection("write", chat_id=chat_id) as connection:
            cursor = connection.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?",
                (_serialize_datetime(updated_at), chat_id),
            )
        return cursor.rowcount == 1

    def delete_chat(self, chat_id: str) -> bool:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection("write", chat_id=chat_id) as connection:
            cursor = connection.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cursor.rowcount == 1

    def create_message(self, message: Message) -> None:
        """Подготавливает локальную запись сообщения для следующего этапа."""
        if not isinstance(message, Message):
            raise ValueError(tr("service.message_invalid"))
        _require_identifier(message.id, tr("service.label.message"))
        _require_identifier(message.chat_id, tr("service.label.chat"))
        _require_identifier(message.turn_id, tr("service.label.turn"))
        _require_text(
            message.content,
            tr("service.label.message_text"),
            allow_empty=message.role is MessageRole.ASSISTANT,
        )
        with self._connection("write", chat_id=message.chat_id) as connection:
            connection.execute(
                """
                INSERT INTO messages (
                    id,
                    chat_id,
                    turn_id,
                    role,
                    content,
                    status,
                    requested_model_id,
                    actual_model_id,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.chat_id,
                    message.turn_id,
                    message.role.value,
                    encrypt_value(
                        connection,
                        message.content,
                        table="messages",
                        field="content",
                        record_id=message.id,
                        chat_id=message.chat_id,
                        role=message.role.value,
                    ),
                    message.status.value,
                    message.requested_model_id,
                    message.actual_model_id,
                    message.prompt_tokens,
                    message.completion_tokens,
                    message.total_tokens,
                    _serialize_datetime(message.created_at),
                    _serialize_datetime(message.created_at),
                ),
            )

    def list_messages(self, chat_id: str) -> list[Message]:
        _require_identifier(chat_id, tr("service.label.chat"))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT messages.*
                FROM messages
                LEFT JOIN turns ON turns.id = messages.turn_id
                WHERE messages.chat_id = ?
                ORDER BY
                    COALESCE(turns.created_at, messages.created_at) ASC,
                    COALESCE(turns.rowid, messages.rowid) ASC,
                    CASE messages.role WHEN 'user' THEN 0 ELSE 1 END ASC,
                    messages.created_at ASC,
                    messages.id ASC
                """,
                (chat_id,),
            ).fetchall()
        return [_message_from_row(row) for row in rows]

    @contextmanager
    def _connection(
        self, operation: str = "read", *, chat_id: str = "", record_id: str = ""
    ) -> Iterator[sqlite3.Connection]:
        with protected_connection(
            self.path, self.access, operation, chat_id=chat_id, record_id=record_id
        ) as connection:
            yield connection


def _chat_from_row(row: sqlite3.Row) -> Chat:
    return Chat(
        id=str(row["id"]),
        title=str(row["title"]),
        mode=ChatMode(str(row["mode"])),
        requested_model_id=str(row["requested_model_id"]),
        requested_model_name=str(row["requested_model_name"]),
        prompt_price_per_token=Decimal(str(row["prompt_price_per_token"])),
        completion_price_per_token=Decimal(str(row["completion_price_per_token"])),
        created_at=_parse_datetime(str(row["created_at"])),
        updated_at=_parse_datetime(str(row["updated_at"])),
        request_price=Decimal(str(row["request_price"])),
        internal_reasoning_price_per_token=Decimal(
            str(row["internal_reasoning_price_per_token"])
        ),
        input_cache_read_price_per_token=Decimal(
            str(row["input_cache_read_price_per_token"])
        ),
        input_cache_write_price_per_token=Decimal(
            str(row["input_cache_write_price_per_token"])
        ),
        pricing_overrides=_parse_overrides(str(row["pricing_overrides_json"])),
        pricing_snapshot_complete=bool(row["pricing_snapshot_complete"]),
        title_origin=str(row["title_origin"])
        if "title_origin" in row.keys()
        else "legacy",
    )


def _message_from_row(row: sqlite3.Row) -> Message:
    return Message(
        id=str(row["id"]),
        chat_id=str(row["chat_id"]),
        turn_id=str(row["turn_id"]),
        role=MessageRole(str(row["role"])),
        content=str(row["content"]),
        status=MessageStatus(str(row["status"])),
        requested_model_id=_optional_str(row["requested_model_id"]),
        actual_model_id=_optional_str(row["actual_model_id"]),
        prompt_tokens=_optional_int(row["prompt_tokens"]),
        completion_tokens=_optional_int(row["completion_tokens"]),
        total_tokens=_optional_int(row["total_tokens"]),
        created_at=_parse_datetime(str(row["created_at"])),
    )


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _insert_chat(connection: sqlite3.Connection, chat: Chat) -> None:
    connection.execute(
        """
        INSERT INTO chats (
            id,
            title,
            mode,
            requested_model_id,
            requested_model_name,
            prompt_price_per_token,
            completion_price_per_token,
            request_price,
            internal_reasoning_price_per_token,
            input_cache_read_price_per_token,
            input_cache_write_price_per_token,
            pricing_overrides_json,
            pricing_snapshot_complete,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat.id,
            encrypt_value(
                connection, chat.title, table="chats", field="title", record_id=chat.id
            ),
            chat.mode.value,
            chat.requested_model_id,
            chat.requested_model_name,
            str(chat.prompt_price_per_token),
            str(chat.completion_price_per_token),
            str(chat.request_price),
            str(chat.internal_reasoning_price_per_token),
            str(chat.input_cache_read_price_per_token),
            str(chat.input_cache_write_price_per_token),
            _serialize_overrides(chat.pricing_overrides),
            int(chat.pricing_snapshot_complete),
            _serialize_datetime(chat.created_at),
            _serialize_datetime(chat.updated_at),
        ),
    )

    if getattr(connection, "cipher", None) is not None:
        connection.execute(
            "UPDATE chats SET title_origin=?,title_is_manual=? WHERE id=?",
            (chat.title_origin, int(chat.title_origin == "manual"), chat.id),
        )


def _insert_budget(
    connection: sqlite3.Connection,
    chat: Chat,
    *,
    limits_configured: bool,
    token_limit: int | None,
    max_completion_tokens: int | None,
    cost_limit_usd: Decimal | None,
) -> None:
    connection.execute(
        """
        INSERT INTO chat_budgets (
            chat_id, limits_configured, token_limit,
            max_completion_tokens, cost_limit_usd,
            state, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chat.id,
            int(limits_configured),
            token_limit,
            max_completion_tokens,
            str(cost_limit_usd) if cost_limit_usd is not None else None,
            "ready" if limits_configured else "unconfigured",
            _serialize_datetime(chat.updated_at),
        ),
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(tr("service.chat_integer_invalid"))


def _serialize_overrides(overrides: tuple[PriceComponents, ...]) -> str:
    return json.dumps(
        [
            {
                "prompt": str(item.prompt),
                "completion": str(item.completion),
                "request": str(item.request),
                "internal_reasoning": str(item.internal_reasoning),
                "input_cache_read": str(item.input_cache_read),
                "input_cache_write": str(item.input_cache_write),
            }
            for item in overrides
        ],
        separators=(",", ":"),
        sort_keys=True,
    )


def _parse_overrides(value: str) -> tuple[PriceComponents, ...]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(tr("service.storage_title_snapshot")) from error
    if not isinstance(payload, list):
        raise ValueError(tr("service.storage_title_snapshot"))
    parsed: list[PriceComponents] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(tr("service.storage_title_snapshot"))
        try:
            pricing = PriceComponents(
                prompt=Decimal(str(item["prompt"])),
                completion=Decimal(str(item["completion"])),
                request=Decimal(str(item["request"])),
                internal_reasoning=Decimal(str(item["internal_reasoning"])),
                input_cache_read=Decimal(str(item["input_cache_read"])),
                input_cache_write=Decimal(str(item["input_cache_write"])),
            )
        except (KeyError, ValueError) as error:
            raise ValueError(tr("service.storage_title_snapshot")) from error
        if not pricing.valid:
            raise ValueError(tr("service.storage_title_snapshot"))
        parsed.append(pricing)
    return tuple(parsed)


def _require_chat(value: object) -> None:
    if not isinstance(value, Chat):
        raise ValueError(tr("service.chat_object_invalid"))
    _require_identifier(value.id, tr("service.label.chat"))
    _require_text(value.title, tr("service.label.title"))
    _require_identifier(value.requested_model_id, tr("service.label.model"))


def _require_identifier(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("service.identifier_invalid", field=label))


def _require_text(value: object, label: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(tr("service.field_invalid", field=label))
