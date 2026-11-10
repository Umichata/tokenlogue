"""Request-scoped chat money permission and real atomic reservation regressions."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import (  # noqa: E402
    BudgetState,
    ChatBudget,
    calculate_remaining_budget,
)
from chat.budget_consent import BudgetConsentRevoked, budget_warning  # noqa: E402
from chat.drafts import ChatDraft  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import ChatMode  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    BlockingCompletionClient,
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
    _chat,
    _paid_model,
    _success,
)

NOW = datetime(2026, 11, 10, tzinfo=UTC)


class AuthArguments(TypedDict):
    api_key: str
    key_validity: KeyValidityState
    key_limit: KeyLimitInfo


AUTH: AuthArguments = {
    "api_key": "synthetic-budget-key",
    "key_validity": KeyValidityState.VALID,
    "key_limit": KeyLimitInfo.from_validated_remaining(None),
}


def budget(limit="1", spent="0", reserved="0"):
    return ChatBudget(
        "paid",
        True,
        8192,
        64,
        0,
        0,
        0,
        0,
        Decimal(limit),
        Decimal(spent),
        Decimal(reserved),
        BudgetState.READY,
        NOW,
    )


class WarningThresholdTests(unittest.TestCase):
    def test_exact_decimal_threshold_and_negative_remaining(self):
        for limit, spent, reserved, cost, expected in (
            ("1", "0", "0", "0.899999999999999999999", False),
            ("1", "0", "0", "0.9", True),
            ("1", "0", "0", "1", True),
            ("1", "0", "0", "1.000000000000000000001", True),
            ("1", "1", "0", "0.1", True),
            ("1", "0", "0.1", "0.8", True),
            ("0.000001", "0", "0", "0.0000009", True),
            ("1", "2", "0", "0", False),
        ):
            with self.subTest(limit=limit, spent=spent, reserved=reserved, cost=cost):
                warning = budget_warning(budget(limit, spent, reserved), Decimal(cost))
                self.assertEqual(warning is not None, expected)
        remaining = calculate_remaining_budget(budget("1", "1.000123"))
        self.assertEqual(remaining.cost_usd, Decimal("-0.000123"))


class BudgetPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = AuthDatabase(self.temp.name)
        self.chats = SqliteChatRepository(self.database.path)
        self.messages = SqliteMessageRepository(self.database.path)
        self.chat_service = ChatService(self.chats)
        self.model = replace(
            _paid_model(),
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            request_price=Decimal("1"),
        )
        self.catalog = FakeCatalogClient((self.model,))
        self.chats.create_chat_with_limits(
            _chat("paid", ChatMode.PAID, self.model),
            token_limit=8192,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("1"),
        )
        self.client = FakeCompletionClient([_success(cost="1.000123")])
        self.sender = self.make_sender(self.client)

    def make_sender(self, client):
        return MessageSendingService(
            self.chat_service, self.messages, client, self.catalog, FakeKeyValidator()
        )

    async def preview(self, text="hello", **kwargs):
        result = await self.sender.preview_message("paid", text, **AUTH, **kwargs)
        self.assertTrue(result.allowed, result.error_type)
        self.assertIsNotNone(result.budget_warning)
        return result

    async def send(self, text="hello", consent=None, **kwargs):
        return await self.sender.send_message(
            "paid", text, **AUTH, paid_confirmed=True, budget_consent=consent, **kwargs
        )

    async def test_warning_is_uncapped_cancel_reserves_nothing_and_send_is_one_use(
        self,
    ):
        preview = await self.preview()
        self.assertEqual(preview.max_completion_tokens, 64)
        self.assertEqual(preview.reserved_cost_usd, Decimal("1"))
        blocked = await self.send()
        self.assertEqual(blocked.error_type, ChatErrorType.COST_LIMIT_EXCEEDED)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.messages.list_turns("paid"), [])
        consent = self.sender.confirm_budget_warning(preview)
        finished = []
        reserved = []
        sent = await self.send(
            consent=consent,
            on_request_finished=lambda: finished.append(True),
            on_reserved=lambda turn: reserved.append(self.messages.get_turn(turn)),
        )
        self.assertTrue(sent.successful, sent.error_type)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(finished, [True])
        self.assertEqual(reserved[0].reserved_cost_usd, Decimal("1"))
        reopened = SqliteMessageRepository(self.database.path)
        current = reopened.get_chat_budget("paid")
        assert current is not None
        self.assertEqual(current.cost_limit_usd, Decimal("1"))
        self.assertEqual(
            calculate_remaining_budget(current).cost_usd, Decimal("-0.000123")
        )
        replay = await self.send(consent=consent)
        self.assertFalse(replay.successful)
        self.assertEqual(len(self.client.calls), 1)

    async def test_text_draft_revision_and_limit_changes_invalidate_permission(self):
        for change in ("text", "draft", "limit"):
            with self.subTest(change=change):
                preview = await self.preview()
                token = self.sender.confirm_budget_warning(preview)
                text = "hello changed" if change == "text" else "hello"
                kwargs = {"draft_revision": 1} if change == "draft" else {}
                if change == "limit":
                    self.messages.set_chat_limits(
                        "paid",
                        8192,
                        64,
                        Decimal("1.01"),
                        cost_increase_confirmed=True,
                        updated_at=NOW,
                    )
                result = await self.send(text, consent=token, **kwargs)
                self.assertFalse(result.successful)
                self.assertIsNotNone(result.budget_preview)
                self.assertEqual(self.client.calls, [])
                self.assertEqual(self.messages.list_turns("paid"), [])

    async def test_atomic_new_tiny_reservation_invalidates_and_returns_fresh_risk(self):
        preview = await self.preview()
        token = self.sender.confirm_budget_warning(preview)
        original = self.messages.reserve_turn

        def racing_reserve(*args, **kwargs):
            with sqlite3.connect(self.database.path) as connection:
                connection.execute(
                    "UPDATE chat_budgets SET cost_reserved_usd=? WHERE chat_id='paid'",
                    ("0.000000000000000000001",),
                )
            return original(*args, **kwargs)

        self.messages.reserve_turn = racing_reserve
        result = await self.send(consent=token)
        self.assertFalse(result.successful)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.messages.list_turns("paid"), [])
        assert result.budget_preview is not None
        assert result.budget_preview.budget_warning is not None
        assert preview.budget_warning is not None
        self.assertLess(
            result.budget_preview.budget_warning.projected_remaining_usd,
            preview.budget_warning.projected_remaining_usd,
        )

    async def test_concurrent_double_click_makes_one_request(self):
        self.client = BlockingCompletionClient(_success(cost="1"))
        self.sender = self.make_sender(self.client)
        token = self.sender.confirm_budget_warning(await self.preview())
        first = asyncio.create_task(self.send(consent=token))
        await self.client.started.wait()
        second = await self.send(consent=token)
        self.assertEqual(second.error_type, ChatErrorType.TURN_ALREADY_ACTIVE)
        self.client.release.set()
        self.assertTrue((await first).successful)
        self.assertEqual(len(self.client.calls), 1)

    async def test_already_exhausted_chat_can_confirm_only_its_next_request(self):
        self.client.results.append(_success(cost="1.000123"))
        first = self.sender.confirm_budget_warning(await self.preview())
        self.assertTrue((await self.send(consent=first)).successful)
        second_preview = await self.preview()
        assert second_preview.budget_warning is not None
        self.assertLess(second_preview.budget_warning.remaining_usd, 0)
        self.assertLess(second_preview.budget_warning.projected_remaining_usd, 0)
        denied = await self.send()
        self.assertFalse(denied.successful)
        second = self.sender.confirm_budget_warning(second_preview)
        self.assertTrue((await self.send(consent=second)).successful)
        current = self.messages.get_chat_budget("paid")
        assert current is not None
        self.assertEqual(current.cost_limit_usd, Decimal("1"))
        self.assertEqual(current.cost_used_usd, Decimal("2.000246"))

    async def test_retry_gets_distinct_permission_and_finished_notification(self):
        failure = ChatCompletionResult(
            content=None,
            generation_id=None,
            requested_model_id=self.model.id,
            actual_model_id=None,
            finish_reason=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            cost_usd=None,
            error_type=ChatErrorType.PERMISSION_DENIED,
            accounting_unknown=False,
        )
        self.client.results = [failure, _success(cost="1")]
        finished = []
        first_token = self.sender.confirm_budget_warning(await self.preview())
        failed = await self.send(
            consent=first_token, on_request_finished=lambda: finished.append(True)
        )
        self.assertFalse(failed.successful)
        assert failed.turn_id is not None
        preview = await self.sender.preview_failed_turn(failed.turn_id, **AUTH)
        self.assertTrue(preview.allowed)
        assert preview.budget_consent_basis is not None
        self.assertEqual(preview.budget_consent_basis.retry_turn_id, failed.turn_id)
        token = self.sender.confirm_budget_warning(preview)
        retried = await self.sender.retry_failed_turn(
            failed.turn_id,
            **AUTH,
            paid_confirmed=True,
            budget_consent=token,
            on_request_finished=lambda: finished.append(True),
        )
        self.assertTrue(retried.successful, retried.error_type)
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(finished, [True, True])

    async def test_price_and_unknown_accounting_are_not_bypassed(self):
        token = self.sender.confirm_budget_warning(await self.preview())
        self.catalog.models = (
            replace(self.model, request_price=Decimal("1.000000000000000000001")),
        )
        changed = await self.send(consent=token)
        self.assertEqual(
            changed.error_type, ChatErrorType.PRICE_RECONFIRMATION_REQUIRED
        )
        await self.sender.reconfirm_model_price(
            "paid", api_key=AUTH["api_key"], confirmed=True
        )
        repriced = await self.send(consent=token)
        self.assertEqual(repriced.error_type, ChatErrorType.COST_LIMIT_EXCEEDED)
        assert repriced.budget_preview is not None
        assert repriced.budget_preview.budget_warning is not None
        self.assertGreater(
            repriced.budget_preview.budget_warning.estimated_cost_usd, Decimal("1")
        )
        self.catalog.models = (self.model,)
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE chat_budgets SET state='accounting_unknown' WHERE chat_id='paid'"
            )
        unknown = await self.send(consent=token)
        self.assertEqual(unknown.error_type, ChatErrorType.ACCOUNTING_UNKNOWN)
        self.assertEqual(self.client.calls, [])

    async def test_newer_draft_inside_transaction_is_not_consumed(self):
        drafts = SqliteDraftRepository(self.database.path)
        drafts.save_draft(ChatDraft("paid", 1, "hello"))
        preview = await self.preview(draft_revision=1)
        token = self.sender.confirm_budget_warning(preview)
        original = self.messages.reserve_turn

        def racing_reserve(*args, **kwargs):
            drafts.save_draft(ChatDraft("paid", 2, "newer unsent text"))
            return original(*args, **kwargs)

        self.messages.reserve_turn = racing_reserve
        denied = await self.send(consent=token, draft_revision=1)
        self.assertFalse(denied.successful)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.messages.list_turns("paid"), [])
        self.assertEqual(drafts.get_draft("paid").text, "newer unsent text")

    async def test_foreign_service_cannot_mint_confirmation_from_preview(self):
        other = self.make_sender(self.client)
        with self.assertRaises(BudgetConsentRevoked):
            other.confirm_budget_warning(await self.preview())

    async def test_plain_boolean_cannot_authorize_local_money_exception(self):
        denied = await self.send(consent=True)
        self.assertEqual(denied.error_type, ChatErrorType.INVALID_REQUEST)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.messages.list_turns("paid"), [])

    async def test_model_token_key_and_provider_constraints_survive_permission(self):
        token = self.sender.confirm_budget_warning(await self.preview())
        original_model = self.model
        self.catalog.models = (replace(self.model, provider_max_completion_tokens=15),)
        provider = await self.send(consent=token)
        self.assertEqual(provider.error_type, ChatErrorType.MAX_TOKENS_EXCEEDED)
        self.catalog.models = (original_model,)
        validator = FakeKeyValidator()
        from api.openrouter import KeyValidationResult, KeyValidationStatus

        validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED, limit_remaining=Decimal("0.5")
        )
        restricted = MessageSendingService(
            self.chat_service, self.messages, self.client, self.catalog, validator
        )
        key_result = await restricted.send_message(
            "paid", "hello", **AUTH, paid_confirmed=True, budget_consent=token
        )
        self.assertEqual(key_result.error_type, ChatErrorType.KEY_LIMIT_EXCEEDED)
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE chat_budgets SET token_limit=40,max_completion_tokens=32 WHERE chat_id='paid'"
            )
        limited = await self.send(consent=token)
        self.assertEqual(limited.error_type, ChatErrorType.TOKEN_LIMIT_EXCEEDED)
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE chat_budgets SET token_limit=8192,max_completion_tokens=64 WHERE chat_id='paid'"
            )
            connection.execute(
                "UPDATE chats SET requested_model_id='vendor/other' WHERE id='paid'"
            )
        self.catalog.models = (replace(original_model, id="vendor/other"),)
        changed_model = await self.send(consent=token)
        self.assertEqual(changed_model.error_type, ChatErrorType.COST_LIMIT_EXCEEDED)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.messages.list_turns("paid"), [])

    async def test_cancelled_dispatched_request_notifies_once_without_awaiting_credits(
        self,
    ):
        self.client = BlockingCompletionClient(_success(cost="1"))
        self.sender = self.make_sender(self.client)
        finished = []
        token = self.sender.confirm_budget_warning(await self.preview())
        pending = asyncio.create_task(
            self.send(consent=token, on_request_finished=lambda: finished.append(True))
        )
        await self.client.started.wait()
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(finished, [True])
        current = self.messages.get_chat_budget("paid")
        assert current is not None
        self.assertEqual(current.state, BudgetState.ACCOUNTING_UNKNOWN)
