"""Actual request metrics use only synthetic ledger rows and temporary files."""

from __future__ import annotations

# ruff: noqa: E402
import sqlite3
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, PinRecord
from chat.accounting import BudgetReservation
from chat.errors import ChatErrorType
from chat.metrics import LastRequestState, build_chat_metrics
from chat.models import Chat, ChatMode
from storage.chat_repository import SqliteChatRepository
from storage.data_access import DataAccess, DataAccessError
from storage.database import AuthDatabase
from storage.draft_repository import SqliteDraftRepository
from storage.encrypted_migration import migrate_database, verify_protected_database
from storage.encryption_initialization import plaintext_evidence
from storage.field_cipher import CiphertextError, FieldCipher
from storage.message_repository import BudgetConflictError, SqliteMessageRepository
from storage.profile_deletion import ProfileDeletion, ProfileDeletionError
from storage.request_attempts import TABLE, has_request_attempts

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def chat(chat_id: str = "paid", mode: ChatMode = ChatMode.PAID) -> Chat:
    return Chat(
        id=chat_id,
        title="Synthetic metrics chat",
        mode=mode,
        requested_model_id="vendor/model"
        if mode is ChatMode.PAID
        else "openrouter/free",
        requested_model_name="Synthetic model",
        prompt_price_per_token=Decimal("0.000001"),
        completion_price_per_token=Decimal("0.000002"),
        created_at=NOW,
        updated_at=NOW,
    )


class ChatMetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = AuthDatabase(self.temporary.name)
        self.chats = SqliteChatRepository(self.database.path)
        self.messages = SqliteMessageRepository(self.database.path)
        self.chats.create_chat(chat())
        self.messages.set_chat_limits(
            "paid",
            10000,
            1024,
            Decimal("2"),
            cost_increase_confirmed=True,
            updated_at=NOW,
        )

    def reserve(self, turn_id: str, *, retry: bool = False, moment: int = 0) -> None:
        self.messages.reserve_turn(
            BudgetReservation(
                turn_id,
                f"user-{turn_id}",
                "paid",
                300,
                Decimal("0.2"),
                NOW + timedelta(seconds=moment),
            ),
            content="Synthetic request",
            requested_model_id="vendor/model",
            retry=retry,
        )

    def final(
        self,
        turn_id: str,
        *,
        successful: bool = True,
        moment: int = 1,
        total: int = 100,
        cost: str = "0.0000123456789",
    ) -> None:
        self.messages.finalize_known_turn(
            turn_id,
            assistant_message_id=f"assistant-{turn_id}",
            content="Synthetic answer" if successful else None,
            successful=successful,
            requested_model_id="vendor/model",
            actual_model_id="vendor/model",
            generation_id=None,
            finish_reason="stop",
            prompt_tokens=50,
            completion_tokens=40,
            total_tokens=total,
            cost_usd=Decimal(cost),
            error_type=None if successful else ChatErrorType.PROVIDER_UNAVAILABLE,
            generated_title=None,
            updated_at=NOW + timedelta(seconds=moment),
        )

    def sent_final(self, turn_id: str, **kwargs) -> None:
        self.reserve(turn_id)
        self.messages.mark_request_sent(turn_id, NOW)
        self.final(turn_id, **kwargs)

    def test_new_chat_has_no_request_and_metrics_read_does_not_create_schema(
        self,
    ) -> None:
        original = self.database.path.read_bytes()
        self.assertEqual(
            self.messages.get_last_request("paid").state, LastRequestState.NONE
        )
        with sqlite3.connect(self.database.path) as connection:
            self.assertFalse(has_request_attempts(connection))
        self.assertEqual(original, self.database.path.read_bytes())

    def test_rejected_dispatch_rolls_back_the_lazy_extension(self) -> None:
        original = self.database.path.read_bytes()
        with self.assertRaises(BudgetConflictError):
            self.messages.mark_request_sent("missing-turn", NOW)
        with sqlite3.connect(self.database.path) as connection:
            self.assertFalse(has_request_attempts(connection))
        self.assertEqual(original, self.database.path.read_bytes())

    def test_unconfigured_budget_is_unknown_rather_than_infinite(self) -> None:
        new_chat = chat("unconfigured", ChatMode.FREE)
        self.chats.create_chat(new_chat)
        budget = self.messages.get_chat_budget(new_chat.id)
        assert budget is not None
        metrics = build_chat_metrics(
            new_chat, budget, self.messages.get_last_request(new_chat.id)
        )
        self.assertIsNone(metrics.remaining.tokens)
        self.assertIsNone(metrics.remaining.cost_usd)
        self.assertIsNone(metrics.account_balance_usd)

    def test_final_uses_authoritative_total_once_and_decimal_actual_cost(self) -> None:
        self.sent_final("one")
        metrics = self.messages.get_last_request("paid")
        self.assertEqual(metrics.state, LastRequestState.FINAL)
        self.assertEqual(metrics.total_tokens, 100)
        self.assertEqual((metrics.prompt_tokens, metrics.completion_tokens), (50, 40))
        self.assertEqual(metrics.cost_usd, Decimal("0.0000123456789"))
        self.assertEqual(metrics.sent_at, NOW)
        self.assertEqual(metrics.attempt_sequence, 1)
        budget = self.messages.get_chat_budget("paid")
        assert budget is not None
        self.assertEqual(budget.total_tokens_used, 100)

    def test_failed_final_usage_is_still_actual_usage(self) -> None:
        self.sent_final("failed", successful=False)
        metrics = self.messages.get_last_request("paid")
        self.assertEqual(metrics.state, LastRequestState.FINAL)
        self.assertEqual(metrics.total_tokens, 100)
        self.assertEqual(metrics.cost_usd, Decimal("0.0000123456789"))

    def test_local_pre_http_failure_preserves_last_actual(self) -> None:
        self.sent_final("actual")
        previous = self.messages.get_last_request("paid")
        self.reserve("local")
        self.messages.release_local_failure("local", ChatErrorType.INTERRUPTED, NOW)
        self.assertEqual(self.messages.get_last_request("paid"), previous)

    def test_pending_and_unknown_new_attempt_mask_older_final(self) -> None:
        self.sent_final("old")
        self.reserve("new")
        self.messages.mark_request_sent("new", NOW + timedelta(seconds=10))
        pending = self.messages.get_last_request("paid")
        self.assertEqual(pending.state, LastRequestState.PENDING)
        self.assertEqual(pending.turn_id, "new")
        self.assertEqual(pending.attempt_sequence, 2)
        self.assertIsNone(pending.cost_usd)
        self.messages.mark_unknown_outcome(
            "new",
            assistant_message_id="unknown",
            partial_content=None,
            requested_model_id="vendor/model",
            actual_model_id=None,
            generation_id=None,
            finish_reason=None,
            error_type=ChatErrorType.ACCOUNTING_UNKNOWN,
            updated_at=NOW,
        )
        unknown = self.messages.get_last_request("paid")
        self.assertEqual(unknown.state, LastRequestState.UNKNOWN)
        self.assertEqual(unknown.turn_id, "new")
        self.assertEqual(unknown.attempt_sequence, pending.attempt_sequence)
        self.assertIsNone(unknown.total_tokens)
        self.assertIsNone(unknown.cost_usd)

    def test_retry_old_turn_is_latest_even_with_earlier_clock(self) -> None:
        self.reserve("old", moment=-5)
        self.messages.mark_request_sent("old", NOW + timedelta(seconds=1))
        self.messages.release_known_failure(
            "old", ChatErrorType.RATE_LIMIT_EXCEEDED, NOW
        )
        self.sent_final("newer", moment=20)
        self.reserve("old", retry=True, moment=30)
        self.messages.mark_request_sent("old", NOW - timedelta(days=1))
        self.final("old", moment=31, total=150, cost="0.3")
        self.assertEqual(
            [t.id for t in self.messages.list_turns("paid")], ["old", "newer"]
        )
        latest = self.messages.get_last_request("paid")
        self.assertEqual(latest.turn_id, "old")
        self.assertEqual(latest.total_tokens, 150)
        self.assertEqual(latest.cost_usd, Decimal("0.3"))
        self.assertEqual(latest.attempt_sequence, 3)
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0], 3
            )

    def test_pre_http_retry_keeps_the_same_turn_previous_actual_attempt(self) -> None:
        self.reserve("retry")
        self.messages.mark_request_sent("retry", NOW)
        self.messages.release_known_failure(
            "retry", ChatErrorType.RATE_LIMIT_EXCEEDED, NOW
        )
        actual = self.messages.get_last_request("paid")
        self.assertEqual(actual.state, LastRequestState.UNKNOWN)
        self.reserve("retry", retry=True)
        self.assertEqual(self.messages.get_last_request("paid"), actual)
        self.messages.release_local_failure("retry", ChatErrorType.INTERRUPTED, NOW)
        self.assertEqual(self.messages.get_last_request("paid"), actual)

    def test_releasing_unknown_reservation_does_not_confirm_zero_usage(self) -> None:
        self.reserve("unknown")
        self.messages.mark_request_sent("unknown", NOW)
        self.messages.mark_unknown_outcome(
            "unknown",
            assistant_message_id="assistant",
            partial_content=None,
            requested_model_id="vendor/model",
            actual_model_id=None,
            generation_id=None,
            finish_reason=None,
            error_type=ChatErrorType.ACCOUNTING_UNKNOWN,
            updated_at=NOW,
        )
        self.messages.release_unknown_reservation("unknown", NOW)
        actual = self.messages.get_last_request("paid")
        self.assertEqual(actual.state, LastRequestState.UNKNOWN)
        self.assertIsNone(actual.cost_usd)
        self.assertIsNone(actual.total_tokens)

    def test_late_old_reconciliation_does_not_reorder_actual_dispatches(self) -> None:
        self.sent_final("old")
        self.sent_final("new", moment=2)
        newest = self.messages.get_last_request("paid")
        with sqlite3.connect(self.database.path) as connection:
            # An existing reconciliation changes accounting, not dispatch order.
            connection.execute(
                "UPDATE turns SET updated_at=?,cost_usd='0.9' WHERE id='old'",
                ((NOW + timedelta(days=1)).isoformat(),),
            )
            from storage.request_attempts import synchronize_request_attempt

            synchronize_request_attempt(connection, "old")
        self.assertEqual(self.messages.get_last_request("paid"), newest)

    def test_budget_with_reservations_key_limit_and_account_are_distinct(self) -> None:
        self.sent_final("actual", cost="0.3")
        self.reserve("pending")
        budget = self.messages.get_chat_budget("paid")
        assert budget is not None
        snapshot = build_chat_metrics(
            chat(),
            budget,
            self.messages.get_last_request("paid"),
            pending=True,
            key_limit=KeyLimitInfo.from_validated_remaining(Decimal("7.25")),
            metadata_updated_at=NOW,
        )
        self.assertEqual(snapshot.remaining.tokens, 9600)
        self.assertEqual(snapshot.remaining.cost_usd, Decimal("1.5"))
        self.assertEqual(snapshot.key_limit.remaining, Decimal("7.25"))
        self.assertIsNone(snapshot.account_balance_usd)
        self.assertEqual(snapshot.last_request.cost_usd, Decimal("0.3"))
        self.assertTrue(snapshot.pending)
        self.assertEqual(snapshot.metadata_updated_at, NOW)
        with self.assertRaises(ValueError):
            build_chat_metrics(
                replace(chat(), id="other"), budget, snapshot.last_request
            )

    def test_unknown_key_limit_is_not_zero_or_infinity(self) -> None:
        budget = self.messages.get_chat_budget("paid")
        assert budget is not None
        snapshot = build_chat_metrics(
            chat(), budget, self.messages.get_last_request("paid")
        )
        self.assertIsNone(snapshot.account_balance_usd)
        self.assertIsNone(snapshot.key_limit.remaining)

    def test_concurrent_dispatch_cannot_create_duplicate_attempt(self) -> None:
        self.reserve("one")

        def dispatch() -> bool:
            try:
                self.messages.mark_request_sent("one", NOW)
            except BudgetConflictError:
                return False
            return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(
                sorted(executor.map(lambda _: dispatch(), range(2))), [False, True]
            )
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0], 1
            )

    def test_interrupted_dispatched_attempt_becomes_unknown_after_restart(self) -> None:
        self.reserve("one")
        self.messages.mark_request_sent("one", NOW)
        AuthDatabase(self.temporary.name)
        self.assertEqual(
            self.messages.get_last_request("paid").state, LastRequestState.UNKNOWN
        )

    def test_legacy_chronology_is_explicit_unknown_and_reads_are_byte_preserving(
        self,
    ) -> None:
        self.reserve("legacy")
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("UPDATE turns SET request_sent=1 WHERE id='legacy'")
        self.final("legacy")
        original = self.database.path.read_bytes()
        legacy = self.messages.get_last_request("paid")
        self.assertEqual(legacy.state, LastRequestState.UNKNOWN)
        self.assertFalse(legacy.chronology_known)
        self.assertIsNone(legacy.attempt_sequence)
        self.assertIsNone(legacy.total_tokens)
        self.assertEqual(original, self.database.path.read_bytes())
        self.reserve("current")
        self.messages.mark_request_sent("current", NOW)
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute(
                    f"SELECT chronology_known,total_tokens,cost_usd FROM {TABLE} ORDER BY sequence"
                ).fetchall(),
                [(0, 100, "0.0000123456789"), (1, None, None)],
            )

    def test_delete_chat_cascades_attempts(self) -> None:
        self.sent_final("one")
        self.chats.delete_chat("paid")
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0], 0
            )

    def test_plaintext_initialization_and_encryption_preserve_optional_ledger(
        self,
    ) -> None:
        self.database.save_auth_state(
            "metrics-registration",
            PinRecord(1, "pbkdf2_hmac_sha256", 100, b"s" * 16, b"v" * 32),
        )
        self.sent_final("one")
        before_evidence = plaintext_evidence(self.database.path)
        self.assertEqual(before_evidence, plaintext_evidence(self.database.path))
        with sqlite3.connect(self.database.path) as connection:
            before = connection.execute(f"SELECT * FROM {TABLE}").fetchall()
        cipher = FieldCipher(bytes(range(32)), "metrics-db", "metrics-key")
        migrate_database(self.database.path, cipher)
        verify_protected_database(self.database.path, cipher)
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute(f"SELECT * FROM {TABLE}").fetchall(), before
            )
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 7)
        access = DataAccess()
        access.open(cipher)
        messages = SqliteMessageRepository(self.database.path, access)
        self.assertEqual(
            messages.get_last_request("paid").cost_usd, Decimal("0.0000123456789")
        )
        access.lock()
        with self.assertRaises(DataAccessError):
            messages.get_last_request("paid")

    def test_existing_encrypted_history_is_byte_preserved_by_first_dispatch_extension(
        self,
    ) -> None:
        cipher = FieldCipher(bytes(range(32)), "metrics-db", "metrics-key")
        migrate_database(self.database.path, cipher)
        access = DataAccess()
        access.open(cipher)
        messages = SqliteMessageRepository(self.database.path, access)
        drafts = SqliteDraftRepository(self.database.path, access)
        from chat.drafts import ChatDraft

        drafts.save_draft(ChatDraft("paid", 1, "Synthetic retained draft"))
        self.messages = messages
        self.reserve("one")
        with sqlite3.connect(self.database.path) as connection:
            original_messages = connection.execute("SELECT * FROM messages").fetchall()
            original_drafts = connection.execute("SELECT * FROM chat_drafts").fetchall()
            original_chat = connection.execute("SELECT * FROM chats").fetchall()
        messages.mark_request_sent("one", NOW)
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                connection.execute("SELECT * FROM messages").fetchall(),
                original_messages,
            )
            self.assertEqual(
                connection.execute("SELECT * FROM chat_drafts").fetchall(),
                original_drafts,
            )
            self.assertEqual(
                connection.execute("SELECT * FROM chats").fetchall(), original_chat
            )
        verify_protected_database(self.database.path, cipher)

    def test_malformed_extension_fails_encryption_closed(
        self,
    ) -> None:
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(f"CREATE TABLE {TABLE} (sequence INTEGER PRIMARY KEY)")
        original = self.database.path.read_bytes()
        with self.assertRaises(CiphertextError):
            migrate_database(
                self.database.path, FieldCipher(bytes(range(32)), "db", "key")
            )
        self.assertEqual(original, self.database.path.read_bytes())


class AttemptProfileDeletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_protection_enrollment_with_ledger_preserves_actual_usage(
        self,
    ) -> None:
        from tests.test_data_protection import ProtectionFixture

        fixture = ProtectionFixture()
        fixture.setUp()
        try:
            chats = SqliteChatRepository(fixture.database.path)
            messages = SqliteMessageRepository(fixture.database.path)
            chats.create_chat(chat())
            messages.set_chat_limits(
                "paid",
                1000,
                128,
                Decimal("1"),
                cost_increase_confirmed=True,
                updated_at=NOW,
            )
            messages.reserve_turn(
                BudgetReservation("one", "user", "paid", 200, Decimal("0.1"), NOW),
                content="Synthetic enrollment request",
                requested_model_id="vendor/model",
                retry=False,
            )
            messages.mark_request_sent("one", NOW)
            messages.finalize_known_turn(
                "one",
                assistant_message_id="assistant",
                content="Synthetic answer",
                successful=True,
                requested_model_id="vendor/model",
                actual_model_id="vendor/model",
                generation_id="Synthetic generation",
                finish_reason="stop",
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                cost_usd=Decimal("0.0001"),
                error_type=None,
                generated_title=None,
                updated_at=NOW,
            )
            previous = messages.get_last_request("paid")
            await fixture.protection.unlock("0123", fixture.stored())
            protected = SqliteMessageRepository(fixture.database.path, fixture.access)
            self.assertEqual(protected.get_last_request("paid"), previous)
            self.assertEqual(
                SqliteChatRepository(fixture.database.path, fixture.access)
                .list_messages("paid")[0]
                .content,
                "Synthetic enrollment request",
            )
            fixture.protection.lock()
            await fixture.protection.unlock("0123", fixture.stored())
            self.assertEqual(protected.get_last_request("paid"), previous)
        finally:
            fixture.doCleanups()

    async def test_profile_delete_rejects_malformed_optional_extension(self) -> None:
        from tests.test_data_protection import ProtectionFixture

        fixture = ProtectionFixture()
        fixture.setUp()
        try:
            with sqlite3.connect(fixture.database.path) as connection:
                connection.execute(
                    f"CREATE TABLE {TABLE} (sequence INTEGER PRIMARY KEY)"
                )
            original = fixture.database.path.read_bytes()
            deletion = ProfileDeletion(fixture.database.path, fixture.storage)
            with self.assertRaises(ProfileDeletionError):
                await deletion.capture()
            self.assertEqual(fixture.database.path.read_bytes(), original)
            self.assertFalse(deletion.pending())
        finally:
            fixture.doCleanups()

    async def test_profile_delete_accepts_only_known_optional_ledger_schema(
        self,
    ) -> None:
        from tests.test_data_protection import ProtectionFixture

        fixture = ProtectionFixture()
        fixture.setUp()
        try:
            await fixture.enroll()
            await fixture.protection.unlock("0123", fixture.stored())
            chats = SqliteChatRepository(fixture.database.path, fixture.access)
            messages = SqliteMessageRepository(fixture.database.path, fixture.access)
            chats.create_chat(chat())
            messages.set_chat_limits(
                "paid",
                1000,
                128,
                Decimal("1"),
                cost_increase_confirmed=True,
                updated_at=NOW,
            )
            messages.reserve_turn(
                BudgetReservation("one", "user", "paid", 200, Decimal("0.1"), NOW),
                content="Synthetic deletion request",
                requested_model_id="vendor/model",
                retry=False,
            )
            messages.mark_request_sent("one", NOW)
            fixture.protection.lock()
            fixture.storage.read_keys.clear()
            deletion = ProfileDeletion(fixture.database.path, fixture.storage)
            scope = await deletion.capture()
            await deletion.accept(scope)
            await deletion.finish()
            self.assertFalse(fixture.database.path.exists())
            self.assertEqual(fixture.storage.values, {})
        finally:
            fixture.doCleanups()
