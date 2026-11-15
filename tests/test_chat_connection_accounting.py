"""Connection changes preserve immutable dispatches and currency-specific money."""

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
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import (  # noqa: E402
    BudgetReservation,
    BudgetState,
    ChatBudgetService,
    ChatLimitConfiguration,
)
from chat.context import ContextMessage, prepare_history  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, ChatMode, ModelCatalog  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from providers.models import Currency, PriceUnit, ProviderId  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.encrypted_migration import migrate_database  # noqa: E402
from storage.field_cipher import FieldCipher  # noqa: E402
from storage.message_repository import (  # noqa: E402
    BudgetConflictError,
    SqliteMessageRepository,
)
from storage.provider_schema import ensure_provider_schema  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    BlockingCompletionClient,
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
    _chat,
    _known_error,
    _paid_model,
    _success,
)

NOW = datetime(2026, 11, 15, tzinfo=UTC)


class ChatConnectionAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = AuthDatabase(temporary.name)
        self.chats = SqliteChatRepository(self.database.path)
        self.messages = SqliteMessageRepository(self.database.path)
        self.service = ChatService(self.chats, now=lambda: NOW)
        self.or_model = _paid_model()
        self.vv_model = replace(
            self.or_model,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
            pricing_is_complete=False,
        )
        self.chats.create_chat_with_limits(
            _chat("trip", ChatMode.PAID, self.or_model),
            token_limit=8192,
            max_completion_tokens=64,
            cost_limit=Decimal("5"),
        )

    def current_chat(self):
        chat = self.chats.get_chat("trip")
        assert chat is not None
        return chat

    def current_budget(self):
        budget = self.messages.get_chat_budget("trip")
        assert budget is not None
        return budget

    def configuration(self, provider: ProviderId, cost: str = "100"):
        currency = Currency.USD if provider is ProviderId.OPENROUTER else Currency.RUB
        return ChatLimitConfiguration(
            8192,
            64,
            Decimal(cost) if currency is Currency.USD else None,
            cost_limit=Decimal(cost),
            currency=currency,
        )

    def switch(self, provider: ProviderId, *, mode=ChatMode.PAID, cost="100"):
        current = self.chats.get_chat("trip")
        assert current is not None
        model = self.or_model if provider is ProviderId.OPENROUTER else self.vv_model
        if mode is ChatMode.FREE:
            model = FREE_ROUTER_MODEL
        return self.chats.switch_connection(
            "trip",
            expected_revision=current.connection_revision,
            mode=mode,
            model=model,
            configuration=self.configuration(provider, cost),
            updated_at=NOW,
        )

    def reserve(self, turn_id: str, *, content="A useful follow-up"):
        chat = self.chats.get_chat("trip")
        assert chat is not None
        self.messages.reserve_turn(
            BudgetReservation(
                turn_id,
                "user-" + turn_id,
                "trip",
                64,
                Decimal("0"),
                NOW,
                currency=chat.currency,
                provider_id=chat.provider_id,
                connection_revision=chat.connection_revision,
            ),
            content=content,
            requested_model_id=chat.requested_model_id,
            retry=False,
        )
        self.messages.mark_request_sent(turn_id, NOW)

    def finish(self, turn_id: str, cost: str):
        chat = self.chats.get_chat("trip")
        assert chat is not None
        self.messages.finalize_known_turn(
            turn_id,
            assistant_message_id="assistant-" + turn_id,
            content="A complete and useful answer.",
            successful=True,
            requested_model_id=chat.requested_model_id,
            actual_model_id=chat.requested_model_id,
            generation_id=None,
            finish_reason="stop",
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
            cost=Decimal(cost),
            error_type=None,
            generated_title=None,
            updated_at=NOW,
        )

    def sql_rows(self, query: str):
        with sqlite3.connect(self.database.path) as connection:
            return connection.execute(query).fetchall()

    async def test_failed_switch_and_repeated_current_choice_do_not_reset_data(self):
        self.reserve("first")
        self.finish("first", "1")
        before = self.sql_rows("SELECT * FROM turns")
        changed = self.switch(ProviderId.VSEGPT)
        self.assertEqual(changed.connection_revision, 1)
        self.assertEqual(self.sql_rows("SELECT * FROM turns"), before)
        budget = self.messages.get_chat_budget("trip")
        assert budget is not None
        self.assertEqual((budget.total_tokens_used, budget.cost_used), (30, Decimal(0)))
        with self.assertRaises(BudgetConflictError):
            self.chats.switch_connection(
                "trip",
                expected_revision=0,
                mode=ChatMode.PAID,
                model=self.or_model,
                configuration=self.configuration(ProviderId.OPENROUTER, "5"),
                updated_at=NOW,
            )
        repeat = self.switch(ProviderId.VSEGPT, cost="999")
        self.assertEqual(repeat, changed)
        self.assertEqual(self.messages.get_chat_budget("trip"), budget)
        restored = self.switch(ProviderId.OPENROUTER, cost="5")
        self.assertEqual(restored.connection_revision, 2)
        old = self.messages.get_chat_budget("trip")
        assert old is not None
        self.assertEqual(
            (old.cost_limit, old.cost_used, old.total_tokens_used),
            (Decimal(5), Decimal(1), 30),
        )

    async def test_pending_and_unknown_attempt_block_switch_without_releasing_money(
        self,
    ):
        self.reserve("pending")
        with self.assertRaises(BudgetConflictError):
            self.switch(ProviderId.VSEGPT)
        self.messages.mark_unknown_outcome(
            "pending",
            assistant_message_id="unknown-answer",
            partial_content=None,
            requested_model_id=self.or_model.id,
            actual_model_id=None,
            generation_id=None,
            finish_reason=None,
            error_type=ChatErrorType.NETWORK_ERROR,
            updated_at=NOW,
        )
        before = self.messages.get_chat_budget("trip")
        with self.assertRaises(BudgetConflictError):
            self.switch(ProviderId.VSEGPT)
        self.assertEqual(self.messages.get_chat_budget("trip"), before)
        self.assertEqual(self.current_chat().connection_revision, 0)

    async def test_stale_limits_and_price_writers_cannot_cross_roundtrip(self):
        self.switch(ProviderId.VSEGPT)
        self.switch(ProviderId.OPENROUTER, cost="5")
        before = self.messages.get_chat_budget("trip")
        with self.assertRaises(BudgetConflictError):
            await ChatBudgetService(self.messages).update_chat_limits(
                "trip",
                token_limit=8192,
                max_completion_tokens=64,
                cost_limit=Decimal(7),
                cost_increase_confirmed=True,
                expected_revision=0,
                currency=Currency.USD,
            )
        with self.assertRaises(BudgetConflictError):
            self.messages.update_price_snapshot(
                "trip",
                prompt_price=Decimal(9),
                completion_price=Decimal(9),
                request_price=Decimal(9),
                internal_reasoning_price=Decimal(0),
                cache_read_price=Decimal(0),
                cache_write_price=Decimal(0),
                overrides_json="[]",
                updated_at=NOW,
                expected_connection_revision=0,
                expected_provider_id=ProviderId.OPENROUTER,
                expected_model_id=self.or_model.id,
            )
        self.assertEqual(self.messages.get_chat_budget("trip"), before)

    async def test_returning_to_free_model_keeps_paid_money_and_shared_tokens(self):
        self.reserve("paid")
        self.finish("paid", "1")
        self.switch(ProviderId.VSEGPT)
        self.switch(ProviderId.OPENROUTER, mode=ChatMode.FREE, cost="0")
        await ChatBudgetService(self.messages).update_chat_limits(
            "trip",
            token_limit=8192,
            max_completion_tokens=32,
            cost_limit=Decimal(0),
            expected_revision=2,
        )
        budget = self.messages.get_chat_budget("trip")
        assert budget is not None
        self.assertEqual(budget.state, BudgetState.READY)
        self.assertEqual(
            (budget.cost_limit, budget.cost_used, budget.total_tokens_used),
            (Decimal(5), Decimal(1), 30),
        )

    async def test_positive_free_charge_cannot_underflow_through_float_projection(self):
        self.switch(ProviderId.VSEGPT)
        self.switch(ProviderId.OPENROUTER, mode=ChatMode.FREE, cost="0")
        self.reserve("tiny-free-charge")
        self.finish("tiny-free-charge", "1E-999")
        self.assertEqual(self.current_budget().cost_used, Decimal("1E-999"))
        self.assertEqual(self.current_budget().state, BudgetState.EXHAUSTED)

    async def test_transaction_rollback_and_repeatable_additive_backfill(self):
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("DROP TABLE chat_monetary_budgets")
            connection.execute("ALTER TABLE chats DROP COLUMN connection_revision")
            connection.execute("ALTER TABLE turns DROP COLUMN retry_of_turn_id")
            connection.execute("ALTER TABLE turns DROP COLUMN connection_revision")
            connection.execute(
                "UPDATE chat_budgets SET cost_used='1.25',cost_used_usd='1.25',total_tokens_used=77"
            )
        with (
            self.assertRaises(RuntimeError),
            sqlite3.connect(self.database.path) as connection,
        ):
            connection.execute("BEGIN IMMEDIATE")
            with patch(
                "storage.provider_schema.create_monetary_schema",
                side_effect=RuntimeError("synthetic interruption"),
            ):
                ensure_provider_schema(connection)
        self.assertNotIn(
            "connection_revision",
            [x[1] for x in self.sql_rows("PRAGMA table_info(chats)")],
        )
        for _ in range(2):
            with sqlite3.connect(self.database.path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                ensure_provider_schema(connection)
        self.assertEqual(
            self.sql_rows(
                "SELECT provider_id,currency,cost_used FROM chat_monetary_budgets"
            ),
            [("openrouter", "USD", "1.25")],
        )
        self.assertEqual(self.current_budget().total_tokens_used, 77)
        cipher = FieldCipher(bytes(range(32)), "synthetic-db", "synthetic-key")
        migrate_database(self.database.path, cipher)
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT cost_used FROM chat_monetary_budgets"
                ).fetchone()[0],
                "1.25",
            )
        before = self.database.path.read_bytes()
        migrate_database(self.database.path, cipher)
        self.assertEqual(self.database.path.read_bytes(), before)

    async def test_switch_uses_dispatch_lock_and_rechecks_guard_in_transaction(self):
        client = BlockingCompletionClient(_success(cost="0.02"))
        sender = MessageSendingService(
            self.service,
            self.messages,
            client,
            FakeCatalogClient((self.or_model, self.vv_model)),
            FakeKeyValidator(),
            now=lambda: NOW,
        )
        sending = asyncio.create_task(
            sender.send_message(
                "trip",
                "Plan a weekend trip.",
                api_key="sk-or-v1-offline-connection-fixture",
                key_validity=KeyValidityState.VALID,
                key_limit=KeyLimitInfo.from_validated_remaining(None),
                paid_confirmed=True,
            )
        )
        await asyncio.wait_for(client.started.wait(), timeout=2)
        try:
            with self.assertRaises(RuntimeError):
                await sender.switch_chat_connection(
                    "trip",
                    expected_revision=0,
                    mode=ChatMode.PAID,
                    model=self.vv_model,
                    catalog=ModelCatalog((), (self.vv_model,), True),
                    key_validity=KeyValidityState.UNVERIFIED,
                    key_limit=KeyLimitInfo.unknown(),
                    configuration=self.configuration(ProviderId.VSEGPT),
                )
        finally:
            client.release.set()
        self.assertTrue((await sending).successful)
        calls = 0

        def guard():
            nonlocal calls
            calls += 1
            return calls < 4

        with self.assertRaises(BudgetConflictError):
            await sender.switch_chat_connection(
                "trip",
                expected_revision=0,
                mode=ChatMode.PAID,
                model=self.vv_model,
                catalog=ModelCatalog((), (self.vv_model,), True),
                key_validity=KeyValidityState.UNVERIFIED,
                key_limit=KeyLimitInfo.unknown(),
                configuration=self.configuration(ProviderId.VSEGPT),
                dispatch_guard=guard,
            )
        self.assertEqual(self.current_chat().connection_revision, 0)

    async def test_restart_preserves_tiny_rub_money_without_a_token_reserve(self):
        self.switch(ProviderId.VSEGPT)
        self.messages.reserve_turn(
            BudgetReservation(
                "money-only",
                "user-money-only",
                "trip",
                0,
                Decimal(0),
                NOW,
                reserved_cost=Decimal("1E-999"),
                currency=Currency.RUB,
                provider_id=ProviderId.VSEGPT,
                connection_revision=1,
            ),
            content="Keep this unresolved request.",
            requested_model_id=self.vv_model.id,
            retry=False,
        )
        self.database.recover_interrupted_turns()
        turn = self.messages.get_turn("money-only")
        assert turn is not None
        self.assertEqual(turn.accounting_status.value, "unknown")
        self.assertEqual(turn.reserved_cost, Decimal("1E-999"))
        with self.assertRaises(BudgetConflictError):
            self.switch(ProviderId.OPENROUTER, cost="5")

    async def test_nested_retry_after_switch_keeps_original_rows_and_one_context_pair(
        self,
    ):
        self.reserve("history", content="Plan a weekend trip.")
        self.finish("history", "0.25")
        self.reserve("failed", content="Suggest a quiet route.")
        self.messages.release_known_failure("failed", ChatErrorType.AUTHENTICATION, NOW)
        originals = self.sql_rows("SELECT * FROM turns WHERE id='failed'")
        original_user = self.sql_rows("SELECT * FROM messages WHERE turn_id='failed'")
        self.switch(ProviderId.VSEGPT)
        client = FakeCompletionClient(
            [
                replace(
                    _known_error(ChatErrorType.AUTHENTICATION),
                    provider_id=ProviderId.VSEGPT,
                    currency=Currency.RUB,
                ),
                _success(cost="0.02"),
            ]
        )
        sender = MessageSendingService(
            self.service,
            self.messages,
            client,
            FakeCatalogClient((self.or_model, self.vv_model)),
            FakeKeyValidator(),
            now=lambda: NOW,
        )
        preview = await sender.preview_failed_turn(
            "failed",
            api_key="sk-or-vis-offline-retry-example",
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
        )
        consent = sender.confirm_unknown_price(preview)
        first = await sender.retry_failed_turn(
            "failed",
            api_key="sk-or-vis-offline-retry-example",
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
            paid_confirmed=True,
            unknown_price_consent=consent,
        )
        self.assertFalse(first.successful)
        self.assertNotEqual(first.turn_id, "failed")
        self.assertIsNotNone(first.turn_id)
        assert first.turn_id is not None
        intermediate = self.sql_rows("SELECT * FROM turns WHERE provider_id='vsegpt'")
        self.switch(ProviderId.OPENROUTER, cost="5")
        final = await sender.retry_failed_turn(
            first.turn_id,
            api_key="sk-or-v1-offline-retry-example",
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=True,
        )
        self.assertTrue(final.successful)
        self.assertNotEqual(final.turn_id, first.turn_id)
        self.assertEqual(
            self.sql_rows("SELECT * FROM turns WHERE id='failed'"), originals
        )
        self.assertEqual(
            self.sql_rows("SELECT * FROM messages WHERE turn_id='failed'"),
            original_user,
        )
        self.assertEqual(
            self.sql_rows("SELECT * FROM turns WHERE provider_id='vsegpt'"),
            intermediate,
        )
        visible = self.chats.list_messages("trip")
        self.assertEqual(len(visible), 4)
        self.assertEqual(len({x.id for x in visible}), 4)
        self.assertEqual(len(prepare_history(visible).pairs), 2)
        self.assertEqual(
            [
                x.content
                for x in cast(tuple[ContextMessage, ...], client.calls[-1]["messages"])
            ],
            [
                "Plan a weekend trip.",
                "A complete and useful answer.",
                "Suggest a quiet route.",
            ],
        )
        identities = self.sql_rows(
            "SELECT provider_id,currency,connection_revision FROM chat_request_attempts ORDER BY sequence"
        )
        self.assertEqual(
            identities,
            [
                ("openrouter", "USD", 0),
                ("openrouter", "USD", 0),
                ("vsegpt", "RUB", 1),
                ("openrouter", "USD", 2),
            ],
        )
