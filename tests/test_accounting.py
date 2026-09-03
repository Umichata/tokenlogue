"""Тесты лимитов, резервов и точной Decimal-оценки."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.accounting import (  # noqa: E402
    AccountingStatus,
    BudgetReservation,
    BudgetState,
    ChatBudgetService,
    confirmed_provider_price_limit,
    estimate_max_cost,
    format_decimal_usd,
    model_price_increased,
    parse_chat_limit_input,
)
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import (  # noqa: E402
    CatalogModel,
    Chat,
    ChatMode,
    Message,
    MessageRole,
    MessageStatus,
    PriceComponents,
)
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import (  # noqa: E402
    BudgetConflictError,
    SqliteMessageRepository,
)

NOW = datetime(2026, 4, 1, tzinfo=UTC)


class AccountingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database = AuthDatabase(self.temp_dir.name)
        self.chat_repository = SqliteChatRepository(database.path)
        self.message_repository = SqliteMessageRepository(database.path)
        self.service = ChatBudgetService(self.message_repository)
        self.chat_repository.create_chat(_chat("free", ChatMode.FREE))
        self.chat_repository.create_chat(_chat("paid", ChatMode.PAID))

    async def test_existing_chat_starts_unconfigured(self) -> None:
        budget = await self.service.get_chat_budget("paid")

        self.assertFalse(budget.limits_configured)
        self.assertIsNone(budget.token_limit)
        self.assertIsNone(budget.max_completion_tokens)
        self.assertIsNone(budget.cost_limit_usd)
        self.assertEqual(budget.state, BudgetState.UNCONFIGURED)

    def test_limit_input_uses_decimal_and_free_has_no_money_field(self) -> None:
        free = parse_chat_limit_input(ChatMode.FREE, "8192", "1024", None)
        paid = parse_chat_limit_input(ChatMode.PAID, "8192", "1024", "0.1000")

        self.assertEqual(free.cost_limit_usd, Decimal("0"))
        self.assertEqual(paid.cost_limit_usd, Decimal("0.1000"))
        self.assertIsInstance(paid.cost_limit_usd, Decimal)
        self.assertEqual(format_decimal_usd(Decimal("10")), "10")
        self.assertEqual(format_decimal_usd(Decimal("0.1000")), "0.1")

    async def test_configures_free_with_immutable_zero_cost(self) -> None:
        chat_before = self.chat_repository.get_chat("free")
        budget = await self.service.configure_chat_limits(
            "free",
            token_limit=1000,
            max_completion_tokens=128,
            cost_limit_usd=None,
            updated_at=NOW,
        )

        self.assertTrue(budget.limits_configured)
        self.assertEqual(budget.cost_limit_usd, Decimal("0"))
        chat_after = self.chat_repository.get_chat("free")
        assert chat_before is not None and chat_after is not None
        self.assertEqual(chat_after.mode, chat_before.mode)
        self.assertEqual(chat_after.requested_model_id, chat_before.requested_model_id)
        with self.assertRaises(ValueError):
            await self.service.update_chat_limits(
                "free",
                token_limit=1000,
                max_completion_tokens=128,
                cost_limit_usd=Decimal("0.01"),
                cost_increase_confirmed=True,
                updated_at=NOW,
            )

    async def test_paid_configuration_and_increase_require_confirmation(self) -> None:
        with self.assertRaises(ValueError):
            await self.service.configure_chat_limits(
                "paid",
                token_limit=1000,
                max_completion_tokens=128,
                cost_limit_usd=Decimal("1"),
                updated_at=NOW,
            )
        await self.service.configure_chat_limits(
            "paid",
            token_limit=1000,
            max_completion_tokens=128,
            cost_limit_usd=Decimal("1"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )

        with self.assertRaises(BudgetConflictError):
            await self.service.update_chat_limits(
                "paid",
                token_limit=1000,
                max_completion_tokens=128,
                cost_limit_usd=Decimal("2"),
                updated_at=NOW,
            )
        updated = await self.service.update_chat_limits(
            "paid",
            token_limit=1000,
            max_completion_tokens=128,
            cost_limit_usd=Decimal("2"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )
        self.assertEqual(updated.cost_limit_usd, Decimal("2"))

    async def test_rejects_invalid_token_and_completion_limits(self) -> None:
        for token_limit, completion_limit in ((0, 16), (100, 15), (100, 101)):
            with self.subTest(
                token_limit=token_limit,
                completion_limit=completion_limit,
            ):
                with self.assertRaises(ValueError):
                    await self.service.configure_chat_limits(
                        "free",
                        token_limit=token_limit,
                        max_completion_tokens=completion_limit,
                        cost_limit_usd=Decimal("0"),
                        updated_at=NOW,
                    )
        for cost in (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(cost=cost):
                with self.assertRaises(ValueError):
                    await self.service.configure_chat_limits(
                        "paid",
                        token_limit=100,
                        max_completion_tokens=16,
                        cost_limit_usd=cost,
                        cost_increase_confirmed=True,
                        updated_at=NOW,
                    )

    async def test_remaining_budget_subtracts_used_and_reserved(self) -> None:
        await self.service.configure_chat_limits(
            "paid",
            token_limit=100,
            max_completion_tokens=32,
            cost_limit_usd=Decimal("1"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )
        self.message_repository.reserve_turn(
            BudgetReservation(
                turn_id="turn",
                user_message_id="user",
                chat_id="paid",
                reserved_tokens=30,
                reserved_cost_usd=Decimal("0.25"),
                created_at=NOW,
            ),
            content="message",
            requested_model_id="vendor/model",
            retry=False,
        )

        remaining = await self.service.calculate_remaining_budget("paid")

        self.assertEqual(remaining.tokens, 70)
        self.assertEqual(remaining.cost_usd, Decimal("0.75"))

    async def test_limits_cannot_drop_below_reserved_values(self) -> None:
        await self.service.configure_chat_limits(
            "paid",
            token_limit=100,
            max_completion_tokens=32,
            cost_limit_usd=Decimal("1"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )
        self.message_repository.reserve_turn(
            BudgetReservation(
                turn_id="turn",
                user_message_id="user",
                chat_id="paid",
                reserved_tokens=40,
                reserved_cost_usd=Decimal("0.4"),
                created_at=NOW,
            ),
            content="message",
            requested_model_id="vendor/model",
            retry=False,
        )

        with self.assertRaises(BudgetConflictError):
            await self.service.update_chat_limits(
                "paid",
                token_limit=39,
                max_completion_tokens=16,
                cost_limit_usd=Decimal("1"),
                updated_at=NOW,
            )
        with self.assertRaises(BudgetConflictError):
            await self.service.update_chat_limits(
                "paid",
                token_limit=100,
                max_completion_tokens=16,
                cost_limit_usd=Decimal("0.39"),
                updated_at=NOW,
            )

    async def test_unknown_reservation_requires_explicit_release(self) -> None:
        await self.service.configure_chat_limits(
            "paid",
            token_limit=100,
            max_completion_tokens=32,
            cost_limit_usd=Decimal("1"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )
        self.message_repository.reserve_turn(
            BudgetReservation(
                turn_id="turn",
                user_message_id="user",
                chat_id="paid",
                reserved_tokens=30,
                reserved_cost_usd=Decimal("0.2"),
                created_at=NOW,
            ),
            content="message",
            requested_model_id="vendor/model",
            retry=False,
        )
        self.message_repository.mark_request_sent("turn", NOW)
        self.message_repository.mark_unknown_outcome(
            "turn",
            assistant_message_id="assistant",
            partial_content=None,
            requested_model_id="vendor/model",
            actual_model_id=None,
            generation_id=None,
            finish_reason=None,
            error_type=ChatErrorType.ACCOUNTING_UNKNOWN,
            updated_at=NOW,
        )

        with self.assertRaises(ValueError):
            await self.service.release_unknown_reservation(
                "turn",
                confirmed=False,
                updated_at=NOW,
            )
        await self.service.release_unknown_reservation(
            "turn",
            confirmed=True,
            updated_at=NOW,
        )

        budget = await self.service.get_chat_budget("paid")
        turn = self.message_repository.get_turn("turn")
        self.assertEqual(budget.reserved_tokens, 0)
        self.assertEqual(budget.cost_reserved_usd, Decimal("0"))
        self.assertEqual(budget.state, BudgetState.READY)
        assert turn is not None
        self.assertEqual(turn.accounting_status, AccountingStatus.RELEASED)

    def test_maximum_cost_includes_every_component_and_override(self) -> None:
        base = PriceComponents(
            prompt=Decimal("0.01"),
            completion=Decimal("0.02"),
            request=Decimal("0.5"),
            internal_reasoning=Decimal("0.03"),
            input_cache_read=Decimal("0.04"),
            input_cache_write=Decimal("0.05"),
        )
        override = PriceComponents(request=Decimal("20"))

        result = estimate_max_cost((base, override), 10, 4)

        self.assertEqual(result, Decimal("20"))

    def test_internal_reserve_uses_per_token_prices_without_million_factor(
        self,
    ) -> None:
        pricing = PriceComponents(
            prompt=Decimal("0.000003"),
            completion=Decimal("0.000015"),
            request=Decimal("0.001"),
        )

        result = estimate_max_cost((pricing,), 100, 10)

        self.assertEqual(result, Decimal("0.00145"))

    def test_provider_limit_remains_per_token_inside_domain(self) -> None:
        chat = replace(
            _chat("paid-wire", ChatMode.PAID),
            prompt_price_per_token=Decimal("0.000003"),
            completion_price_per_token=Decimal("0.000015"),
            request_price=Decimal("0.001"),
        )

        limit = confirmed_provider_price_limit(chat)

        self.assertEqual(limit.prompt_per_token, Decimal("0.000003"))
        self.assertEqual(limit.completion_per_token, Decimal("0.000015"))
        self.assertEqual(limit.request, Decimal("0.001"))

    def test_new_paid_component_requires_price_reconfirmation(self) -> None:
        chat = _chat("paid-snapshot", ChatMode.PAID)
        current = CatalogModel(
            id=chat.requested_model_id,
            name="Model",
            prompt_price_per_token=chat.prompt_price_per_token,
            completion_price_per_token=chat.completion_price_per_token,
            request_price=Decimal("0.01"),
        )

        self.assertTrue(model_price_increased(chat, current))

    def test_cache_override_increase_requires_price_reconfirmation(self) -> None:
        confirmed_override = PriceComponents(input_cache_write=Decimal("0.000001"))
        chat = replace(
            _chat("paid-cache-snapshot", ChatMode.PAID),
            pricing_overrides=(confirmed_override,),
        )
        current = CatalogModel(
            id=chat.requested_model_id,
            name="Model",
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            pricing_overrides=(PriceComponents(input_cache_write=Decimal("0.000002")),),
        )

        self.assertEqual(
            estimate_max_cost(current.all_pricing, 5, 0),
            Decimal("0.000010"),
        )
        self.assertTrue(model_price_increased(chat, current))

    async def test_reservation_transaction_rolls_back_on_message_failure(self) -> None:
        await self.service.configure_chat_limits(
            "free",
            token_limit=100,
            max_completion_tokens=16,
            cost_limit_usd=Decimal("0"),
            updated_at=NOW,
        )
        self.chat_repository.create_message(
            Message(
                id="duplicate-message",
                chat_id="free",
                turn_id="older-turn",
                role=MessageRole.USER,
                content="existing",
                status=MessageStatus.FAILED,
                requested_model_id="openrouter/free",
                actual_model_id=None,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                created_at=NOW,
            )
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.message_repository.reserve_turn(
                BudgetReservation(
                    turn_id="rolled-back-turn",
                    user_message_id="duplicate-message",
                    chat_id="free",
                    reserved_tokens=20,
                    reserved_cost_usd=Decimal("0"),
                    created_at=NOW,
                ),
                content="new",
                requested_model_id="openrouter/free",
                retry=False,
            )

        budget = await self.service.get_chat_budget("free")
        self.assertEqual(budget.reserved_tokens, 0)
        self.assertIsNone(self.message_repository.get_turn("rolled-back-turn"))

    async def test_deleting_chat_cascades_budget_turns_and_messages(self) -> None:
        await self.service.configure_chat_limits(
            "free",
            token_limit=100,
            max_completion_tokens=16,
            cost_limit_usd=Decimal("0"),
            updated_at=NOW,
        )
        self.message_repository.reserve_turn(
            BudgetReservation(
                turn_id="turn-to-delete",
                user_message_id="message-to-delete",
                chat_id="free",
                reserved_tokens=20,
                reserved_cost_usd=Decimal("0"),
                created_at=NOW,
            ),
            content="message",
            requested_model_id="openrouter/free",
            retry=False,
        )

        self.chat_repository.delete_chat("free")

        self.assertIsNone(self.message_repository.get_chat_budget("free"))
        self.assertIsNone(self.message_repository.get_turn("turn-to-delete"))
        self.assertEqual(self.chat_repository.list_messages("free"), [])


def _chat(chat_id: str, mode: ChatMode) -> Chat:
    return Chat(
        id=chat_id,
        title="Новый чат",
        mode=mode,
        requested_model_id=(
            "openrouter/free" if mode is ChatMode.FREE else "vendor/model"
        ),
        requested_model_name="Model",
        prompt_price_per_token=Decimal("0")
        if mode is ChatMode.FREE
        else Decimal("0.001"),
        completion_price_per_token=(
            Decimal("0") if mode is ChatMode.FREE else Decimal("0.002")
        ),
        created_at=NOW,
        updated_at=NOW,
    )


if __name__ == "__main__":
    unittest.main()
