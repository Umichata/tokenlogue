"""Тесты SQLite-репозитория чатов и подготовленной истории сообщений."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import PinRecord  # noqa: E402
from chat.models import (  # noqa: E402
    Chat,
    ChatMode,
    Message,
    MessageRole,
    MessageStatus,
    PriceComponents,
)
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402


class ChatRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = AuthDatabase(self.temp_dir.name)
        self.repository = SqliteChatRepository(self.database.path)
        self.start = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)

    def test_crud_and_reverse_updated_sorting(self) -> None:
        older = _chat("older", self.start)
        newer = _chat("newer", self.start + timedelta(minutes=1))
        self.repository.create_chat(older)
        self.repository.create_chat(newer)

        self.assertEqual(
            [chat.id for chat in self.repository.list_chats()],
            ["newer", "older"],
        )
        self.assertEqual(self.repository.get_chat("older"), older)
        self.assertIsNone(self.repository.get_chat("missing"))

        renamed_at = self.start + timedelta(minutes=2)
        self.assertTrue(
            self.repository.rename_chat("older", "Переименованный", renamed_at)
        )
        renamed = self.repository.get_chat("older")
        self.assertIsNotNone(renamed)
        assert renamed is not None
        self.assertEqual(renamed.title, "Переименованный")
        self.assertEqual(renamed.updated_at, renamed_at)
        self.assertEqual(self.repository.list_chats()[0].id, "older")

        touched_at = self.start + timedelta(minutes=3)
        self.assertTrue(self.repository.touch_chat("newer", touched_at))
        self.assertEqual(self.repository.list_chats()[0].id, "newer")
        self.assertFalse(self.repository.touch_chat("missing", touched_at))
        self.assertFalse(self.repository.rename_chat("missing", "Название", touched_at))

        self.assertTrue(self.repository.delete_chat("older"))
        self.assertFalse(self.repository.delete_chat("older"))
        self.assertEqual([chat.id for chat in self.repository.list_chats()], ["newer"])

    def test_preserves_mode_model_and_exact_price_strings(self) -> None:
        chat = _chat(
            "paid",
            self.start,
            mode=ChatMode.PAID,
            model_id="vendor/paid-model",
            model_name="Paid model",
            prompt_price=Decimal("0.00000120"),
            completion_price=Decimal("0.00000340"),
        )

        self.repository.create_chat(chat)
        restored = self.repository.get_chat(chat.id)

        self.assertEqual(restored, chat)
        with closing(sqlite3.connect(self.database.path)) as connection:
            row = connection.execute(
                """
                SELECT prompt_price_per_token, completion_price_per_token
                FROM chats WHERE id = ?
                """,
                (chat.id,),
            ).fetchone()
        self.assertEqual(row, ("0.00000120", "0.00000340"))

    def test_atomic_chat_creation_stores_configured_budget(self) -> None:
        chat = _chat("configured", self.start)

        self.repository.create_chat_with_limits(
            chat,
            token_limit=8192,
            max_completion_tokens=1024,
            cost_limit_usd=Decimal("0"),
        )

        budget = SqliteMessageRepository(self.database.path).get_chat_budget(chat.id)
        self.assertIsNotNone(budget)
        assert budget is not None
        self.assertTrue(budget.limits_configured)
        self.assertEqual(budget.token_limit, 8192)
        self.assertEqual(budget.max_completion_tokens, 1024)
        self.assertEqual(budget.cost_limit_usd, Decimal("0"))

    def test_atomic_chat_creation_rolls_back_if_budget_insert_fails(self) -> None:
        chat = _chat("rolled-back", self.start)

        with patch(
            "storage.chat_repository._insert_budget",
            side_effect=sqlite3.IntegrityError("injected budget failure"),
        ):
            with self.assertRaises(sqlite3.IntegrityError):
                self.repository.create_chat_with_limits(
                    chat,
                    token_limit=8192,
                    max_completion_tokens=1024,
                    cost_limit_usd=Decimal("0"),
                )

        self.assertIsNone(self.repository.get_chat(chat.id))

    def test_preserves_full_price_snapshot_and_overrides(self) -> None:
        chat = replace(
            _chat("priced", self.start, mode=ChatMode.PAID),
            prompt_price_per_token=Decimal("0.000003"),
            completion_price_per_token=Decimal("0.000015"),
            request_price=Decimal("0.001"),
            internal_reasoning_price_per_token=Decimal("0.000004"),
            input_cache_read_price_per_token=Decimal("0.000001"),
            input_cache_write_price_per_token=Decimal("0"),
            pricing_overrides=(
                PriceComponents(
                    prompt=Decimal("0.000003"),
                    completion=Decimal("0.000005"),
                    request=Decimal("0.02"),
                    input_cache_write=Decimal("0.000002"),
                ),
            ),
            pricing_snapshot_complete=True,
        )

        self.repository.create_chat(chat)

        self.assertEqual(self.repository.get_chat(chat.id), chat)
        with closing(sqlite3.connect(self.database.path)) as connection:
            row = connection.execute(
                """
                SELECT prompt_price_per_token, completion_price_per_token,
                       request_price, input_cache_read_price_per_token,
                       input_cache_write_price_per_token, pricing_overrides_json
                FROM chats WHERE id = ?
                """,
                (chat.id,),
            ).fetchone()
        assert row is not None
        self.assertEqual(
            row[:5],
            ("0.000003", "0.000015", "0.001", "0.000001", "0"),
        )
        overrides = json.loads(row[5])
        self.assertEqual(overrides[0]["input_cache_write"], "0.000002")

    def test_messages_are_listed_and_deleted_with_chat(self) -> None:
        chat = _chat("chat", self.start)
        self.repository.create_chat(chat)
        later = _message(
            "later",
            chat.id,
            self.start + timedelta(seconds=1),
            role=MessageRole.ASSISTANT,
        )
        earlier = _message("earlier", chat.id, self.start)
        self.repository.create_message(later)
        self.repository.create_message(earlier)

        self.assertEqual(
            [message.id for message in self.repository.list_messages(chat.id)],
            ["earlier", "later"],
        )

        self.repository.delete_chat(chat.id)

        with closing(sqlite3.connect(self.database.path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        self.assertEqual(count, 0)

    def test_foreign_key_is_enabled_for_repository_writes(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create_message(
                _message("orphan", "missing-chat", self.start)
            )

    def test_only_one_assistant_message_is_allowed_per_turn(self) -> None:
        chat = _chat("chat", self.start)
        self.repository.create_chat(chat)
        self.repository.create_message(
            _message("assistant-1", chat.id, self.start, role=MessageRole.ASSISTANT)
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.create_message(
                _message(
                    "assistant-2",
                    chat.id,
                    self.start + timedelta(seconds=1),
                    role=MessageRole.ASSISTANT,
                )
            )

    def test_auth_state_is_unchanged_by_chat_operations(self) -> None:
        record = PinRecord(
            version=1,
            algorithm="pbkdf2_hmac_sha256",
            iterations=1_000,
            salt=b"s" * 16,
            verifier=b"v" * 32,
        )
        self.database.save_auth_state("registration", record)

        chat = _chat("chat", self.start)
        self.repository.create_chat(chat)
        self.repository.rename_chat(
            chat.id,
            "Новое название",
            self.start + timedelta(seconds=1),
        )

        state = self.database.get_auth_state()
        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state.registration_id, "registration")
        self.assertEqual(state.pin_record, record)

    def test_clearing_auth_does_not_delete_chats(self) -> None:
        record = PinRecord(
            version=1,
            algorithm="pbkdf2_hmac_sha256",
            iterations=1_000,
            salt=b"s" * 16,
            verifier=b"v" * 32,
        )
        self.database.save_auth_state("registration", record)
        self.repository.create_chat(_chat("chat", self.start))

        self.database.clear_auth_data()

        self.assertIsNone(self.database.get_auth_state())
        self.assertEqual([chat.id for chat in self.repository.list_chats()], ["chat"])


def _chat(
    chat_id: str,
    timestamp: datetime,
    *,
    mode: ChatMode = ChatMode.FREE,
    model_id: str = "openrouter/free",
    model_name: str = "Автоматический выбор бесплатной модели",
    prompt_price: Decimal = Decimal("0"),
    completion_price: Decimal = Decimal("0"),
) -> Chat:
    return Chat(
        id=chat_id,
        title="Новый чат",
        mode=mode,
        requested_model_id=model_id,
        requested_model_name=model_name,
        prompt_price_per_token=prompt_price,
        completion_price_per_token=completion_price,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _message(
    message_id: str,
    chat_id: str,
    timestamp: datetime,
    *,
    role: MessageRole = MessageRole.USER,
) -> Message:
    return Message(
        id=message_id,
        chat_id=chat_id,
        turn_id="turn",
        role=role,
        content="Локальное тестовое сообщение",
        status=MessageStatus.PENDING,
        requested_model_id="openrouter/free",
        actual_model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        created_at=timestamp,
    )


if __name__ == "__main__":
    unittest.main()
