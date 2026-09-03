"""Регрессии Flet Event: UI-события не пересекают доменную границу."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import BudgetReservation  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, Chat, ChatMode  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
)

NOW = datetime(2026, 9, 3, tzinfo=UTC)
TEST_CREDENTIAL = "definitely-fake-event-boundary-credential"


class EventBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database = AuthDatabase(self.temp_dir.name)
        self.chat_repository = SqliteChatRepository(database.path)
        self.message_repository = SqliteMessageRepository(database.path)
        self.chat = Chat(
            id="event-boundary-chat",
            title="Event boundary",
            mode=ChatMode.FREE,
            requested_model_id=FREE_ROUTER_MODEL.id,
            requested_model_name=FREE_ROUTER_MODEL.name,
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            created_at=NOW,
            updated_at=NOW,
        )
        self.chat_repository.create_chat_with_limits(
            self.chat,
            token_limit=1000,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("0"),
        )
        self.event = ft.Event(name="click", control=ft.Button("sentinel"))

    async def test_event_content_is_rejected_before_reservation_and_http(self) -> None:
        completion = FakeCompletionClient(
            [
                ChatCompletionResult(
                    content="unused",
                    generation_id="unused",
                    requested_model_id=FREE_ROUTER_MODEL.id,
                    actual_model_id=FREE_ROUTER_MODEL.id,
                    finish_reason="stop",
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    cost_usd=Decimal("0"),
                    error_type=None,
                )
            ]
        )
        service = MessageSendingService(
            ChatService(self.chat_repository),
            self.message_repository,
            completion,
            FakeCatalogClient(()),
            FakeKeyValidator(),
        )

        result = await service.send_message(
            self.chat.id,
            cast(str, self.event),
            api_key=TEST_CREDENTIAL,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )

        self.assertEqual(result.error_type, ChatErrorType.INVALID_REQUEST)
        self.assertEqual(completion.calls, [])
        self.assertEqual(self.message_repository.list_turns(self.chat.id), [])
        self.assertEqual(self.chat_repository.list_messages(self.chat.id), [])
        budget = self.message_repository.get_chat_budget(self.chat.id)
        assert budget is not None
        self.assertEqual(budget.reserved_tokens, 0)
        self.assertEqual(budget.cost_reserved_usd, Decimal("0"))

    def test_repository_rejects_event_before_sqlite_connect(self) -> None:
        with patch("storage.message_repository.sqlite3.connect") as connect:
            with self.assertRaisesRegex(ValueError, "идентификатор попытки"):
                self.message_repository.get_turn(cast(str, self.event))
            connect.assert_not_called()

    def test_reservation_rejects_event_content_before_transaction(self) -> None:
        reservation = BudgetReservation(
            turn_id="event-turn",
            user_message_id="event-message",
            chat_id=self.chat.id,
            reserved_tokens=80,
            reserved_cost_usd=Decimal("0"),
            created_at=NOW,
        )

        with self.assertRaisesRegex(ValueError, "текст сообщения"):
            self.message_repository.reserve_turn(
                reservation,
                content=cast(str, self.event),
                requested_model_id=FREE_ROUTER_MODEL.id,
                retry=False,
            )

        self.assertEqual(self.message_repository.list_turns(self.chat.id), [])
        self.assertEqual(self.chat_repository.list_messages(self.chat.id), [])
        budget = self.message_repository.get_chat_budget(self.chat.id)
        assert budget is not None
        self.assertEqual(budget.reserved_tokens, 0)

    def test_bool_is_not_accepted_as_numeric_limit(self) -> None:
        with patch("storage.message_repository.sqlite3.connect") as connect:
            with self.assertRaisesRegex(ValueError, "токен-бюджет"):
                self.message_repository.set_chat_limits(
                    self.chat.id,
                    cast(int, True),
                    64,
                    Decimal("0"),
                    cost_increase_confirmed=False,
                    updated_at=NOW,
                )
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
