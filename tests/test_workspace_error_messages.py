"""Разные объяснения окна модели и остатков лимитов чата."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.errors import ChatErrorType, safe_error_message  # noqa: E402
from chat.sending import MessageSendPreview, SendMessageResult  # noqa: E402
from chat_workspace_controller import _preview_message, _result_message  # noqa: E402


def messages(error: ChatErrorType) -> tuple[str, str]:
    preview = MessageSendPreview(
        chat_id="test-chat",
        turn_id=None,
        model_id=None,
        model_name=None,
        estimated_prompt_tokens=None,
        max_completion_tokens=None,
        reserved_tokens=None,
        reserved_cost_usd=None,
        remaining_tokens_after_reservation=None,
        remaining_cost_after_reservation=None,
        error_type=error,
        safe_message=safe_error_message(error),
    )
    result = SendMessageResult(
        turn_id=None,
        successful=False,
        truncated=False,
        content=None,
        error_type=error,
        safe_message=safe_error_message(error),
    )
    return _preview_message(preview), _result_message(result)


class WorkspaceErrorMessageTests(unittest.TestCase):
    def test_context_explains_estimated_prompt_and_history(self) -> None:
        for text in messages(ChatErrorType.CONTEXT_LENGTH_EXCEEDED):
            with self.subTest(text=text):
                self.assertIn("оценке", text)
                self.assertIn("истори", text)
                self.assertIn("окно модели", text)
                self.assertNotIn("увелич", text.lower())

    def test_budget_explains_remaining_total_chat_limit(self) -> None:
        for error in (
            ChatErrorType.TOKEN_LIMIT_EXCEEDED,
            ChatErrorType.COST_LIMIT_EXCEEDED,
        ):
            for text in messages(error):
                with self.subTest(error=error, text=text):
                    self.assertIn("остат", text)
                    self.assertIn("общ", text)
                    self.assertIn("чата", text)
                    self.assertNotIn("окно модели", text)
                    self.assertNotIn("максимум ответа", text)

    def test_timeout_and_key_balance_are_not_relabelled_as_chat_limits(self) -> None:
        for error in (ChatErrorType.TIMEOUT, ChatErrorType.KEY_LIMIT_EXCEEDED):
            self.assertEqual(messages(error), (safe_error_message(error),) * 2)

    def test_server_retry_delay_remains_visible(self) -> None:
        result = SendMessageResult(
            turn_id=None,
            successful=False,
            truncated=False,
            content=None,
            error_type=ChatErrorType.RATE_LIMIT_EXCEEDED,
            safe_message=safe_error_message(ChatErrorType.RATE_LIMIT_EXCEEDED),
            retry_after=30,
        )
        self.assertIn("30", _result_message(result))
        self.assertNotIn("окно модели", _result_message(result))
