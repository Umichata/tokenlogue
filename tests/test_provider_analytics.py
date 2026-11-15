"""Synthetic journals only: no saved profile, transport or credentials."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.accounting import (  # noqa: E402
    AccountingStatus,
    BudgetReservation,
    ChatBudget,
    ChatLimitConfiguration,
    TurnRecord,
)
from chat.analytics import (  # noqa: E402
    AnalyticsFilter,
    RequestAttempt,
    build_analytics,
)
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import CatalogModel, Chat, ChatMode  # noqa: E402
from providers.models import Currency, ProviderId  # noqa: E402
from storage.analytics_repository import SqliteAnalyticsRepository  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.encrypted_migration import (  # noqa: E402
    migrate_database,
    verify_protected_database,
)
from storage.field_cipher import FieldCipher  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from storage.provider_schema import ensure_provider_schema  # noqa: E402
from storage.request_attempts import (  # noqa: E402
    create_request_attempts_schema,
    ensure_request_attempts,
    validate_request_attempts_schema,
)

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def attempt(sequence: int, **kwargs) -> RequestAttempt:
    return RequestAttempt(sequence, "turn", "chat", **kwargs)


class AnalyticsProjectionTests(unittest.TestCase):
    def provider_history(self):
        return [
            attempt(
                1,
                requested_model_id="shared/model",
                sent_at=NOW,
                chronology_known=True,
                total_tokens=11,
                usage_source="api",
                cost=Decimal("0.0123"),
                cost_source="api",
            ),
            attempt(
                2,
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                requested_model_id="shared/model",
                sent_at=NOW,
                chronology_known=True,
                total_tokens=29,
                usage_source="api",
                cost=Decimal("12.34"),
                cost_source="api",
            ),
            attempt(
                3,
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                requested_model_id="vsegpt/archived",
                sent_at=NOW - timedelta(days=15),
                chronology_known=True,
            ),
            attempt(4, requested_model_id="legacy/model"),
        ]

    def test_provider_filter_scopes_models_usage_money_and_undated_rows(self):
        records = self.provider_history()
        for provider, currency, tokens, amount in (
            (ProviderId.OPENROUTER, Currency.USD, 11, Decimal("0.0123")),
            (ProviderId.VSEGPT, Currency.RUB, 29, Decimal("12.34")),
        ):
            with self.subTest(provider=provider):
                snapshot = build_analytics(
                    records,
                    AnalyticsFilter(provider_id=provider, timezone_name="UTC"),
                    NOW,
                )
                self.assertEqual(
                    {
                        (choice.provider_id, choice.model_id)
                        for choice in snapshot.models
                    },
                    {(provider, "shared/model")},
                )
                self.assertEqual(
                    {row.provider_id for row in snapshot.usage_rows}, {provider}
                )
                self.assertEqual(
                    sum(row.total_tokens or 0 for row in snapshot.usage_rows), tokens
                )
                self.assertEqual(
                    [
                        (panel.currency, panel.confirmed_total)
                        for panel in snapshot.spending
                    ],
                    [(currency, amount)],
                )
                self.assertEqual(snapshot.undated_requests, 0)
        all_time = build_analytics(
            records,
            AnalyticsFilter(
                period="all", provider_id=ProviderId.VSEGPT, timezone_name="UTC"
            ),
            NOW,
        )
        self.assertEqual(
            {choice.model_id for choice in all_time.models},
            {"shared/model", "vsegpt/archived"},
        )
        self.assertEqual(all_time.undated_requests, 0)

    def test_one_chat_roundtrip_keeps_dispatch_scopes_and_undated_cost_separate(self):
        records = [
            attempt(
                1,
                requested_model_id="shared/model",
                sent_at=NOW,
                chronology_known=True,
                total_tokens=11,
                usage_source="api",
                cost=Decimal("0.11"),
                cost_source="api",
                connection_revision=0,
            ),
            attempt(
                2,
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                requested_model_id="shared/model",
                sent_at=NOW,
                chronology_known=True,
                total_tokens=29,
                usage_source="api",
                cost=Decimal("12.34"),
                cost_source="api",
                connection_revision=1,
            ),
            attempt(
                3,
                requested_model_id="shared/model",
                sent_at=NOW,
                chronology_known=True,
                total_tokens=17,
                usage_source="api",
                cost=Decimal("0.17"),
                cost_source="api",
                connection_revision=2,
            ),
            attempt(
                4,
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                requested_model_id="shared/model",
                cost=Decimal("3"),
                cost_source="api",
                connection_revision=1,
            ),
        ]
        snapshot = build_analytics(
            records,
            AnalyticsFilter(period="all", timezone_name="UTC"),
            NOW,
        )
        self.assertEqual(
            {row.provider_id: row.total_tokens for row in snapshot.usage_rows},
            {ProviderId.OPENROUTER: 28, ProviderId.VSEGPT: 29},
        )
        panels = {panel.currency: panel for panel in snapshot.spending}
        self.assertEqual(panels[Currency.USD].confirmed_total, Decimal("0.28"))
        self.assertEqual(panels[Currency.RUB].confirmed_total, Decimal("12.34"))
        self.assertEqual(panels[Currency.RUB].undated_confirmed_total, Decimal("3"))
        self.assertEqual(panels[Currency.RUB].undated_requests, 1)
        for provider, expected in (
            (ProviderId.OPENROUTER, 2),
            (ProviderId.VSEGPT, 1),
        ):
            filtered = build_analytics(
                records,
                AnalyticsFilter(
                    provider_id=provider,
                    model_id="shared/model",
                    model_provider_id=provider,
                    timezone_name="UTC",
                ),
                NOW,
            )
            self.assertEqual(sum(row.requests for row in filtered.usage_rows), expected)
            self.assertEqual(
                {(row.provider_id, row.model_id) for row in filtered.models},
                {(provider, "shared/model")},
            )

    def test_all_view_distinguishes_equal_model_ids_by_provider_identity(self):
        records = self.provider_history()
        overview = build_analytics(records, AnalyticsFilter(timezone_name="UTC"), NOW)
        self.assertEqual(len(overview.models), 2)
        for provider, currency, tokens in (
            (ProviderId.OPENROUTER, Currency.USD, 11),
            (ProviderId.VSEGPT, Currency.RUB, 29),
        ):
            snapshot = build_analytics(
                records,
                AnalyticsFilter(
                    model_id="shared/model",
                    model_provider_id=provider,
                    timezone_name="UTC",
                ),
                NOW,
            )
            self.assertEqual(snapshot.models, overview.models)
            self.assertEqual(len(snapshot.usage_rows), 1)
            self.assertEqual(snapshot.usage_rows[0].provider_id, provider)
            self.assertEqual(snapshot.usage_rows[0].total_tokens, tokens)
            self.assertEqual(
                [panel.currency for panel in snapshot.spending], [currency]
            )

    def test_incompatible_model_resets_without_leaking_other_provider(self):
        snapshot = build_analytics(
            self.provider_history(),
            AnalyticsFilter(
                provider_id=ProviderId.VSEGPT,
                model_id="shared/model",
                model_provider_id=ProviderId.OPENROUTER,
                timezone_name="UTC",
            ),
            NOW,
        )
        self.assertIsNone(snapshot.filters.model_id)
        self.assertIsNone(snapshot.filters.model_provider_id)
        self.assertEqual(
            [row.provider_id for row in snapshot.usage_rows], [ProviderId.VSEGPT]
        )
        empty = build_analytics(
            [self.provider_history()[0]],
            AnalyticsFilter(
                period="all", provider_id=ProviderId.VSEGPT, timezone_name="UTC"
            ),
            NOW,
        )
        self.assertEqual((empty.models, empty.usage_rows, empty.spending), ((), (), ()))
        self.assertEqual(empty.undated_requests, 0)

    def test_named_zones_work_without_an_operating_system_database(self):
        from zoneinfo import TZPATH, ZoneInfo, reset_tzpath

        original = TZPATH
        try:
            reset_tzpath(())
            ZoneInfo.clear_cache()
            rows = [
                attempt(
                    1,
                    sent_at=datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
                    chronology_known=True,
                    cost=Decimal("1"),
                    cost_source="api",
                ),
                attempt(
                    2,
                    sent_at=datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
                    chronology_known=True,
                    cost=Decimal("2"),
                    cost_source="api",
                ),
            ]
            snapshot = build_analytics(
                rows,
                AnalyticsFilter(period="all", timezone_name="America/New_York"),
                NOW,
            )
            self.assertEqual(snapshot.spending[0].days[0].confirmed, 3)
            self.assertEqual(snapshot.timezone_name, "America/New_York")
        finally:
            reset_tzpath(original)
            ZoneInfo.clear_cache()

    def test_currency_model_identity_and_exact_decimal_panels(self):
        rows = [
            attempt(
                1,
                requested_model_id="same",
                sent_at=NOW,
                chronology_known=True,
                prompt_tokens=7,
                completion_tokens=3,
                total_tokens=10,
                usage_source="api",
                cost=Decimal("0.100000000000000001"),
                cost_source="api",
            ),
            attempt(
                2,
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                requested_model_id="same",
                sent_at=NOW,
                chronology_known=True,
                prompt_tokens=20,
                completion_tokens=30,
                total_tokens=50,
                usage_source="api",
                cost=Decimal("9.200000000000000003"),
                cost_source="api",
            ),
        ]
        snapshot = build_analytics(rows, AnalyticsFilter(timezone_name="UTC"), NOW)
        self.assertEqual(len(snapshot.usage_rows), 2)
        self.assertEqual(snapshot.usage_rows[0].provider_id, ProviderId.VSEGPT)
        totals = {panel.currency: panel.confirmed_total for panel in snapshot.spending}
        self.assertEqual(
            totals,
            {
                Currency.USD: Decimal("0.100000000000000001"),
                Currency.RUB: Decimal("9.200000000000000003"),
            },
        )
        self.assertEqual(len(snapshot.spending[0].days), 7)
        self.assertEqual(snapshot.spending[0].days[0].confirmed, 0)

    def test_partial_tokens_unknown_cost_estimates_and_details_do_not_double_count(
        self,
    ):
        rows = [
            attempt(
                1,
                sent_at=NOW,
                chronology_known=True,
                prompt_tokens=20,
                total_tokens=25,
                usage_source="api",
                cached_tokens=8,
                reasoning_tokens=5,
            ),
            attempt(
                2,
                sent_at=NOW,
                chronology_known=True,
                prompt_tokens=90,
                completion_tokens=10,
                total_tokens=100,
                usage_source="estimated",
                cost=Decimal("3.5"),
                cost_source="estimated",
            ),
        ]
        snapshot = build_analytics(rows, AnalyticsFilter(timezone_name="UTC"), NOW)
        usage = snapshot.usage_rows[0]
        self.assertEqual(usage.prompt_tokens, 20)
        self.assertIsNone(usage.completion_tokens)
        self.assertEqual(usage.total_tokens, 25)
        self.assertEqual(usage.estimated_total_tokens, 100)
        self.assertEqual(usage.unknown_usage_requests, 1)
        panel = snapshot.spending[0]
        self.assertEqual(panel.confirmed_total, 0)
        self.assertEqual(panel.estimated_total, Decimal("3.5"))
        self.assertEqual(panel.unknown_cost_requests, 1)
        self.assertEqual(panel.days[-1].unknown_requests, 1)

    def test_undated_only_all_time_and_no_invented_date_or_model(self):
        rows = [
            attempt(
                1,
                prompt_tokens=1,
                completion_tokens=2,
                total_tokens=3,
                usage_source="api",
                cost=Decimal("4.25"),
                cost_source="api",
            )
        ]
        short = build_analytics(rows, AnalyticsFilter(timezone_name="UTC"), NOW)
        self.assertFalse(short.usage_rows)
        all_time = build_analytics(
            rows, AnalyticsFilter(period="all", timezone_name="UTC"), NOW
        )
        self.assertEqual(all_time.undated_requests, 1)
        self.assertIsNone(all_time.usage_rows[0].model_id)
        self.assertEqual(all_time.spending[0].confirmed_total, 0)
        self.assertEqual(all_time.spending[0].undated_confirmed_total, Decimal("4.25"))

    def test_period_bounds_and_timezone_changes_regroup_original_send_day(self):
        boundary = datetime(2026, 11, 8, 16, tzinfo=UTC)
        rows = [
            attempt(
                1,
                sent_at=boundary,
                chronology_known=True,
                cost=Decimal("1"),
                cost_source="api",
            )
        ]
        utc = build_analytics(rows, AnalyticsFilter(timezone_name="UTC"), NOW)
        yakutsk = build_analytics(
            rows, AnalyticsFilter(timezone_name="Asia/Yakutsk"), NOW
        )
        self.assertFalse(utc.spending)
        self.assertEqual(yakutsk.spending[0].days[0].day.isoformat(), "2026-11-09")
        self.assertEqual(yakutsk.spending[0].days[0].confirmed, 1)

    def test_dst_day_boundary_uses_named_timezone(self):
        rows = [
            attempt(
                1,
                sent_at=datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
                chronology_known=True,
                cost=Decimal("1"),
                cost_source="api",
            ),
            attempt(
                2,
                sent_at=datetime(2026, 11, 1, 6, 30, tzinfo=UTC),
                chronology_known=True,
                cost=Decimal("2"),
                cost_source="api",
            ),
        ]
        snapshot = build_analytics(
            rows,
            AnalyticsFilter(period="all", timezone_name="America/New_York"),
            datetime(2026, 11, 2, 12, tzinfo=UTC),
        )
        self.assertEqual(snapshot.spending[0].days[0].confirmed, 3)

    def test_duplicate_projection_retry_and_free_confirmed_zero(self):
        free = attempt(
            1,
            sent_at=NOW,
            chronology_known=True,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            usage_source="api",
            cost=Decimal("0"),
            cost_source="api",
        )
        snapshot = build_analytics(
            [free, free, replace(free, sequence=2)],
            AnalyticsFilter(timezone_name="UTC"),
            NOW,
        )
        self.assertEqual(snapshot.usage_rows[0].requests, 2)
        self.assertEqual(snapshot.usage_rows[0].total_tokens, 0)
        self.assertEqual(snapshot.spending[0].unknown_cost_requests, 0)

    def test_large_history_filters_and_sorting(self):
        rows = [
            attempt(
                i,
                requested_model_id="long-model-name-" * 20 if i % 2 else "b",
                sent_at=NOW - timedelta(days=i % 31),
                chronology_known=True,
                prompt_tokens=i,
                completion_tokens=1,
                total_tokens=i + 1,
                usage_source="api",
            )
            for i in range(1, 10001)
        ]
        snapshot = build_analytics(
            rows, AnalyticsFilter(period="30d", model_id="b", timezone_name="UTC"), NOW
        )
        self.assertEqual(len(snapshot.usage_rows), 1)
        self.assertLess(snapshot.usage_rows[0].requests, 5000)
        self.assertEqual(len(snapshot.spending[0].days), 30)


class ProviderJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = AuthDatabase(self.temporary.name).path
        self.chats = SqliteChatRepository(self.path)
        self.messages = SqliteMessageRepository(self.path)
        self.analytics = SqliteAnalyticsRepository(self.path)

    def budget(self) -> ChatBudget:
        budget = self.messages.get_chat_budget("chat")
        assert budget is not None
        return budget

    def turn(self) -> TurnRecord:
        turn = self.messages.get_turn("turn")
        assert turn is not None
        return turn

    def create(self, provider=ProviderId.OPENROUTER):
        currency = Currency.USD if provider is ProviderId.OPENROUTER else Currency.RUB
        chat = Chat(
            id="chat",
            title="Synthetic",
            mode=ChatMode.PAID,
            requested_model_id="requested-original",
            requested_model_name="Synthetic",
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            created_at=NOW,
            updated_at=NOW,
            provider_id=provider,
            currency=currency,
        )
        self.chats.create_chat_with_limits(
            chat,
            token_limit=10000,
            max_completion_tokens=100,
            cost_limit=Decimal("100"),
        )
        return currency

    def reserve(self, currency=Currency.USD, *, retry=False):
        current = self.chats.get_chat("chat")
        assert current is not None
        self.messages.reserve_turn(
            BudgetReservation(
                "turn",
                "message",
                "chat",
                100,
                Decimal("5") if currency is Currency.USD else Decimal("0"),
                NOW,
                reserved_cost=Decimal("5"),
                currency=currency,
            ),
            content="synthetic",
            requested_model_id=current.requested_model_id,
            retry=retry,
        )
        self.messages.mark_request_sent("turn", NOW)

    def finish(self, **extra: Any):
        args: dict[str, Any] = dict(
            assistant_message_id="reply",
            content="answer",
            successful=True,
            requested_model_id="requested-original",
            actual_model_id="actual",
            generation_id=None,
            finish_reason=None,
            prompt_tokens=7,
            completion_tokens=3,
            total_tokens=10,
            cost=None,
            error_type=None,
            generated_title=None,
            updated_at=NOW + timedelta(days=1),
        )
        args.update(extra)
        self.messages.finalize_known_turn("turn", **args)

    def test_known_tokens_unknown_rub_cost_holds_money_and_saves_response(self):
        currency = self.create(ProviderId.VSEGPT)
        self.reserve(currency)
        self.finish()
        budget = self.budget()
        self.assertEqual(budget.total_tokens_used, 10)
        self.assertEqual(budget.cost_reserved, 5)
        self.assertEqual(budget.cost_used, 0)
        self.assertIsNone(budget.cost_limit_usd)
        self.assertEqual(budget.cost_used_usd, 0)
        turn = self.turn()
        self.assertEqual(turn.accounting_status, AccountingStatus.UNKNOWN)
        self.assertEqual(turn.total_tokens, 10)
        self.assertEqual(self.chats.list_messages("chat")[-1].content, "answer")
        saved = self.analytics.list_attempts()[0]
        self.assertEqual(saved.provider_id, ProviderId.VSEGPT)
        self.assertEqual(saved.currency, Currency.RUB)
        self.assertIsNone(saved.cost)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT cost_usd,reserved_cost_usd FROM turns").fetchone(),
                (None, "0"),
            )

    def test_connection_roundtrip_keeps_history_and_refines_actual_provider_ledger(
        self,
    ):
        self.create()
        self.reserve()
        self.finish(cost=Decimal("0.25"))
        first = self.analytics.list_attempts()[0]
        last = self.messages.get_last_request("chat")
        model = CatalogModel(
            "requested-original",
            "Synthetic model",
            Decimal("0"),
            Decimal("0"),
            request_price=Decimal("1"),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
        )
        changed = self.chats.switch_connection(
            "chat",
            expected_revision=0,
            mode=ChatMode.PAID,
            model=model,
            configuration=ChatLimitConfiguration(
                10000, 100, None, cost_limit=Decimal("100"), currency=Currency.RUB
            ),
            updated_at=NOW,
        )
        self.assertEqual(self.analytics.list_attempts(), [first])
        self.assertEqual(self.messages.get_last_request("chat"), last)
        self.assertEqual(last.currency, Currency.USD)
        self.assertEqual(changed.connection_revision, 1)

        def dispatch(turn_id, provider, currency, revision, amount):
            self.messages.reserve_turn(
                BudgetReservation(
                    turn_id,
                    turn_id + "-message",
                    "chat",
                    100,
                    Decimal("5") if currency is Currency.USD else Decimal("0"),
                    NOW,
                    reserved_cost=Decimal("5"),
                    currency=currency,
                    provider_id=provider,
                    connection_revision=revision,
                ),
                content="Synthetic next request",
                requested_model_id="requested-original",
                retry=False,
            )
            sequence = self.messages.mark_request_sent(turn_id, NOW)
            self.messages.finalize_known_turn(
                turn_id,
                assistant_message_id=turn_id + "-reply",
                content="Synthetic answer",
                successful=True,
                requested_model_id="requested-original",
                actual_model_id="actual",
                generation_id=None,
                finish_reason=None,
                prompt_tokens=7,
                completion_tokens=3,
                total_tokens=10,
                cost=Decimal(amount),
                error_type=None,
                generated_title=None,
                updated_at=NOW,
                attempt_sequence=sequence,
            )
            return sequence

        vsegpt_attempt = dispatch(
            "vsegpt-turn", ProviderId.VSEGPT, Currency.RUB, 1, "3"
        )
        self.chats.switch_connection(
            "chat",
            expected_revision=1,
            mode=ChatMode.PAID,
            model=replace(
                model, provider_id=ProviderId.OPENROUTER, currency=Currency.USD
            ),
            configuration=ChatLimitConfiguration(
                10000, 100, Decimal("100"), cost_limit=Decimal("100")
            ),
            updated_at=NOW,
        )
        last = self.messages.get_last_request("chat")
        self.assertEqual(last.provider_id, ProviderId.VSEGPT)
        self.assertEqual(last.currency, Currency.RUB)
        self.assertEqual(last.connection_revision, 1)
        dispatch("returned-turn", ProviderId.OPENROUTER, Currency.USD, 2, "0.5")
        self.messages.update_attempt_accounting(
            vsegpt_attempt, updated_at=NOW, cost=Decimal("4")
        )
        rows = self.analytics.list_attempts()
        self.assertEqual(rows[0], first)
        self.assertEqual([row.connection_revision for row in rows], [0, 1, 2])
        self.assertEqual(
            [(row.provider_id, row.currency) for row in rows],
            [
                (ProviderId.OPENROUTER, Currency.USD),
                (ProviderId.VSEGPT, Currency.RUB),
                (ProviderId.OPENROUTER, Currency.USD),
            ],
        )
        snapshot = build_analytics(rows, AnalyticsFilter(timezone_name="UTC"), NOW)
        self.assertEqual(
            {panel.currency: panel.confirmed_total for panel in snapshot.spending},
            {Currency.USD: Decimal("0.75"), Currency.RUB: Decimal("4")},
        )
        self.assertEqual(self.budget().cost_used, Decimal("0.75"))
        vsegpt_budget = self.messages.get_chat_budget(
            "chat", provider_id=ProviderId.VSEGPT
        )
        assert vsegpt_budget is not None
        self.assertEqual(vsegpt_budget.cost_used, Decimal("4"))
        self.assertEqual(self.budget().total_tokens_used, 30)

    def test_result_replay_and_late_refinement_are_idempotent_and_keep_send_time(self):
        self.create()
        self.reserve()
        self.finish()
        self.finish()
        saved = self.analytics.list_attempts()[0]
        self.assertEqual(saved.reserved_cost, Decimal("5"))
        self.assertEqual(saved.reserved_tokens, 100)
        self.messages.update_attempt_accounting(
            saved.sequence,
            updated_at=NOW + timedelta(days=3),
            cost=Decimal("0.123456789012345678"),
        )
        self.messages.update_attempt_accounting(
            saved.sequence,
            updated_at=NOW + timedelta(days=4),
            cost=Decimal("0.123456789012345678"),
        )
        budget = self.budget()
        self.assertEqual(budget.cost_used, Decimal("0.123456789012345678"))
        self.assertEqual(budget.total_tokens_used, 10)
        self.assertEqual(budget.cost_reserved, 0)
        self.assertEqual(len(self.analytics.list_attempts()), 1)
        self.assertEqual(self.analytics.list_attempts()[0].sent_at, NOW)
        self.assertEqual(self.analytics.list_attempts()[0].reserved_cost, Decimal("5"))

    def test_retry_keeps_original_requested_model_and_late_old_result_cannot_change_turn(
        self,
    ):
        self.create()
        self.reserve()
        self.messages.release_known_failure("turn", ChatErrorType.PAYMENT_REQUIRED, NOW)
        first = self.analytics.list_attempts()[0]
        # Change only mutable fixture metadata. The recorded dispatch keeps its
        # original requested model independently of the current chat and retry.
        with sqlite3.connect(self.path) as database:
            database.execute(
                "UPDATE chats SET requested_model_id=? WHERE id=?",
                ("retry-model", "chat"),
            )
        self.reserve(retry=True)
        self.finish(cost=Decimal("99"), attempt_sequence=first.sequence)
        self.assertEqual(self.turn().status.value, "pending")
        self.assertEqual(self.budget().cost_used, 0)
        self.finish(
            requested_model_id="retry-model",
            actual_model_id="retry-actual",
            cost=Decimal("2"),
        )
        self.messages.update_attempt_accounting(
            first.sequence,
            updated_at=NOW + timedelta(days=5),
            actual_model_id="old-actual",
            prompt_tokens=4,
            completion_tokens=1,
            total_tokens=5,
            cost=Decimal("1"),
        )
        saved = self.analytics.list_attempts()
        self.assertEqual(
            [item.requested_model_id for item in saved],
            ["requested-original", "retry-model"],
        )
        self.assertEqual(self.turn().actual_model_id, "retry-actual")
        self.assertEqual(self.budget().total_tokens_used, 15)
        self.assertEqual(self.budget().cost_used, 3)

    def test_unsent_cancel_has_no_attempt_and_chat_deletion_removes_analytics(self):
        self.create()
        self.reserve()
        self.messages.release_unsent_dispatch("turn", ChatErrorType.INTERRUPTED, NOW)
        self.assertFalse(self.analytics.list_attempts())
        self.reserve(retry=True)
        self.finish(cost=Decimal("0"))
        self.chats.delete_chat("chat")
        self.assertFalse(self.analytics.list_attempts())

    def test_legacy_read_and_migration_preserve_unknown_dates_and_model(self):
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO chats(id,title,mode,requested_model_id,requested_model_name,prompt_price_per_token,completion_price_per_token,created_at,updated_at) VALUES('chat','Synthetic','paid','mutable','Synthetic','0','0','old-created','old-updated')"
            )
            db.execute(
                "INSERT INTO turns(id,chat_id,status,requested_model_id,prompt_tokens,completion_tokens,total_tokens,cost_usd,accounting_status,request_sent,created_at,updated_at) VALUES('turn','chat','sent','mutable',2,3,5,'0.25','final',1,'old-created','late-update')"
            )
        before = self.path.read_bytes()
        saved = self.analytics.list_attempts()[0]
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(saved.sent_at)
        self.assertIsNone(saved.requested_model_id)
        with sqlite3.connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            ensure_provider_schema(db)
            ensure_request_attempts(db)
        saved = self.analytics.list_attempts()[0]
        self.assertIsNone(saved.sent_at)
        self.assertIsNone(saved.requested_model_id)
        self.assertEqual(saved.cost, Decimal("0.25"))
        cipher = FieldCipher(bytes(range(32)), "synthetic-db", "synthetic-key")
        migrate_database(self.path, cipher)
        verify_protected_database(self.path, cipher)
        contents = self.path.read_bytes()
        migrate_database(self.path, cipher)
        self.assertEqual(self.path.read_bytes(), contents)

    def test_old_and_new_attempt_schema_validate_and_migration_is_repeatable(self):
        for legacy in (True, False):
            with self.subTest(legacy=legacy), sqlite3.connect(":memory:") as db:
                create_request_attempts_schema(db, legacy=legacy)
                validate_request_attempts_schema(db)
        with sqlite3.connect(self.path) as db:
            ensure_provider_schema(db)
            first = list(db.execute("SELECT sql FROM sqlite_master ORDER BY name"))
            ensure_provider_schema(db)
            self.assertEqual(
                first, list(db.execute("SELECT sql FROM sqlite_master ORDER BY name"))
            )

    def test_unknown_price_permission_is_once_and_bound_to_budget_and_text(self):
        from chat.budget_consent import (
            BudgetConsentBasis,
            BudgetConsentRevoked,
            UnknownPriceConsent,
            budget_version,
            chat_prices,
            text_digest,
        )

        self.create(ProviderId.VSEGPT)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE chats SET pricing_snapshot_complete=0")
        chat = self.chats.get_chat("chat")
        assert chat is not None
        budget = self.budget()
        basis = BudgetConsentBasis(
            chat_id="chat",
            model_id="requested-original",
            text_sha256=text_digest("synthetic"),
            draft_revision=None,
            limits_version=budget_version(budget),
            pricing=chat_prices(chat),
            request_sha256="synthetic-digest",
            estimated_cost_usd=None,
            projected_remaining_usd=None,
            reserved_tokens=100,
            scope=object(),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            unknown_pricing=True,
        )
        consent = UnknownPriceConsent(basis)
        reservation = BudgetReservation(
            "turn",
            "message",
            "chat",
            100,
            Decimal("0"),
            NOW,
            reserved_cost=Decimal("100"),
            currency=Currency.RUB,
        )
        with self.assertRaises(BudgetConsentRevoked):
            self.messages.reserve_turn(
                reservation,
                content="changed",
                requested_model_id="requested-original",
                retry=False,
                budget_basis=basis,
                unknown_price_consent=consent,
            )
        self.messages.reserve_turn(
            reservation,
            content="synthetic",
            requested_model_id="requested-original",
            retry=False,
            budget_basis=basis,
            unknown_price_consent=consent,
        )
        self.messages.mark_request_sent("turn", NOW)
        self.finish()
        budget = self.budget()
        self.assertEqual(budget.cost_reserved, 100)
        second = BudgetReservation(
            "second",
            "second-message",
            "chat",
            100,
            Decimal("0"),
            NOW,
            reserved_cost=Decimal("0"),
            currency=Currency.RUB,
        )
        with self.assertRaises(BudgetConsentRevoked):
            self.messages.reserve_turn(
                second,
                content="synthetic",
                requested_model_id="requested-original",
                retry=False,
                budget_basis=basis,
                unknown_price_consent=consent,
            )
        fresh_basis = replace(
            basis, limits_version=budget_version(budget), scope=object()
        )
        self.messages.reserve_turn(
            second,
            content="synthetic",
            requested_model_id="requested-original",
            retry=False,
            budget_basis=fresh_basis,
            unknown_price_consent=UnknownPriceConsent(fresh_basis),
        )
        self.assertEqual(self.budget().cost_reserved, 100)
        self.assertIsNone(self.analytics.list_attempts()[0].cost)

    def test_legacy_journal_allows_budget_write_before_first_new_dispatch(self):
        self.create()
        with sqlite3.connect(self.path) as db:
            create_request_attempts_schema(db, legacy=True)
        budget = self.messages.set_chat_limits(
            "chat",
            10000,
            100,
            cost_limit=Decimal("101"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )
        self.assertEqual(budget.cost_limit, 101)
        with sqlite3.connect(self.path) as db:
            validate_request_attempts_schema(db)

    def test_additive_schema_failure_rolls_back_and_can_repeat(self):
        with sqlite3.connect(self.path) as db:

            def deny_budget_alter(action, _first, second, _database, _source):
                return (
                    sqlite3.SQLITE_DENY
                    if action == sqlite3.SQLITE_ALTER_TABLE and second == "chat_budgets"
                    else sqlite3.SQLITE_OK
                )

            db.execute("BEGIN IMMEDIATE")
            db.set_authorizer(deny_budget_alter)
            with self.assertRaises(sqlite3.DatabaseError):
                ensure_provider_schema(db)
            db.rollback()
            db.set_authorizer(None)
            self.assertNotIn(
                "provider_id",
                {row[1] for row in db.execute("PRAGMA table_info(chats)")},
            )
            db.execute("BEGIN IMMEDIATE")
            ensure_provider_schema(db)
            db.commit()
            self.assertIn(
                "provider_id",
                {row[1] for row in db.execute("PRAGMA table_info(chats)")},
            )

    def test_rub_limit_parser_never_places_amount_in_usd_field(self):
        from chat.accounting import parse_chat_limit_input

        parsed = parse_chat_limit_input(
            ChatMode.PAID, "8192", "1024", "500.123456789", currency=Currency.RUB
        )
        self.assertEqual(parsed.cost_limit, Decimal("500.123456789"))
        self.assertIsNone(parsed.cost_limit_usd)
