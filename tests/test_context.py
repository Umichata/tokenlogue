"""Тесты консервативной сборки контекста разговора."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.context import (  # noqa: E402
    MESSAGE_OVERHEAD_TOKENS,
    ContextWindowExceeded,
    build_conversation_context,
    estimate_message_tokens,
)
from chat.models import Message, MessageRole, MessageStatus  # noqa: E402

NOW = datetime(2026, 4, 1, tzinfo=UTC)


class ContextTests(unittest.TestCase):
    def test_utf8_byte_estimate_is_documented_and_conservative(self) -> None:
        text = "Привет"

        estimate = estimate_message_tokens(text)

        self.assertEqual(estimate, len(text.encode("utf-8")) + MESSAGE_OVERHEAD_TOKENS)

    def test_context_contains_only_complete_successful_pairs_and_current_user(
        self,
    ) -> None:
        history = [
            _message("u1", "turn-1", MessageRole.USER, "question", MessageStatus.SENT),
            _message(
                "a1", "turn-1", MessageRole.ASSISTANT, "answer", MessageStatus.SENT
            ),
            _message("u2", "turn-2", MessageRole.USER, "failed", MessageStatus.FAILED),
            _message(
                "a2",
                "turn-2",
                MessageRole.ASSISTANT,
                "partial",
                MessageStatus.FAILED,
            ),
            _message(
                "u3", "turn-3", MessageRole.USER, "pending", MessageStatus.PENDING
            ),
        ]

        context = build_conversation_context(
            history,
            "current",
            context_length=1000,
            completion_reserve=32,
        )

        self.assertEqual(
            [(message.role.value, message.content) for message in context.messages],
            [
                ("user", "question"),
                ("assistant", "answer"),
                ("user", "current"),
            ],
        )

    def test_trimming_keeps_recent_pairs_in_chronological_order(self) -> None:
        history = [
            _message("u1", "turn-1", MessageRole.USER, "x" * 40, MessageStatus.SENT),
            _message(
                "a1", "turn-1", MessageRole.ASSISTANT, "y" * 40, MessageStatus.SENT
            ),
            _message("u2", "turn-2", MessageRole.USER, "recent", MessageStatus.SENT),
            _message(
                "a2", "turn-2", MessageRole.ASSISTANT, "answer", MessageStatus.SENT
            ),
        ]

        context = build_conversation_context(
            history,
            "current",
            context_length=120,
            completion_reserve=32,
        )

        self.assertEqual(
            [message.content for message in context.messages],
            ["recent", "answer", "current"],
        )

    def test_current_message_is_rejected_before_api_when_it_does_not_fit(self) -> None:
        with self.assertRaises(ContextWindowExceeded):
            build_conversation_context(
                [],
                "x" * 100,
                context_length=100,
                completion_reserve=16,
            )


def _message(
    message_id: str,
    turn_id: str,
    role: MessageRole,
    content: str,
    status: MessageStatus,
) -> Message:
    return Message(
        id=message_id,
        chat_id="chat",
        turn_id=turn_id,
        role=role,
        content=content,
        status=status,
        requested_model_id="vendor/model",
        actual_model_id=None,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        created_at=NOW + timedelta(seconds=len(message_id)),
    )


if __name__ == "__main__":
    unittest.main()
