"""Draft persistence and migration tests using temporary SQLite only."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import PinRecord  # noqa: E402
from chat.accounting import BudgetReservation  # noqa: E402
from chat.drafts import ChatDraft, ChatDraftService, DraftStorageError  # noqa: E402
from chat.models import Chat, ChatMode  # noqa: E402
from storage import database as database_module  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402

NOW = datetime(2026, 9, 1, tzinfo=UTC)
EXACT_TEXT = " \tПривет 🙂\n\n𐍈 e\u0301 尾\r\n "


def create_chat(path: Path, chat_id: str) -> None:
    SqliteChatRepository(path).create_chat(
        Chat(
            id=chat_id,
            title="Новый чат",
            mode=ChatMode.FREE,
            requested_model_id="openrouter/free",
            requested_model_name="Free",
            prompt_price_per_token=Decimal(0),
            completion_price_per_token=Decimal(0),
            created_at=NOW,
            updated_at=NOW,
        )
    )


def reservation(chat_id: str, turn_id: str = "turn") -> BudgetReservation:
    return BudgetReservation(
        turn_id=turn_id,
        user_message_id=turn_id + "-user",
        chat_id=chat_id,
        reserved_tokens=20,
        reserved_cost_usd=Decimal(0),
        created_at=NOW,
    )


def snapshot(path: Path) -> dict[str, list[tuple]]:
    with closing(sqlite3.connect(path)) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("auth_state", "chats", "messages", "turns", "chat_budgets")
        }


class DraftRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.database = AuthDatabase(temp.name)
        self.path = self.database.path
        create_chat(self.path, "a")
        create_chat(self.path, "b")
        self.repository = SqliteDraftRepository(self.path)
        self.messages = SqliteMessageRepository(self.path)

    def test_exact_text_independent_drafts_and_no_history_or_budget_effect(
        self,
    ) -> None:
        before = snapshot(self.path)
        self.repository.save_draft(ChatDraft("a", 1, EXACT_TEXT))
        self.assertEqual(self.repository.get_draft("b").text, "")
        self.repository.save_draft(ChatDraft("b", 1, "second chat"))
        reopened = SqliteDraftRepository(self.path)
        self.assertEqual(reopened.get_draft("a").text, EXACT_TEXT)
        self.assertEqual(reopened.get_draft("b").text, "second chat")
        self.assertEqual(snapshot(self.path), before)

    def test_delete_cascades_only_its_draft_and_late_save_cannot_recreate_it(
        self,
    ) -> None:
        self.repository.save_draft(ChatDraft("a", 1, EXACT_TEXT))
        self.repository.save_draft(ChatDraft("b", 1, "keep b"))
        SqliteChatRepository(self.path).delete_chat("a")
        with self.assertRaises(DraftStorageError):
            self.repository.save_draft(ChatDraft("a", 2, "late"))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(
                connection.execute("SELECT chat_id FROM chat_drafts").fetchall(),
                [("b",)],
            )
        self.assertEqual(self.repository.get_draft("b").text, "keep b")

    def test_stale_writes_and_duplicate_revisions_do_not_replace_newer_text(
        self,
    ) -> None:
        newest = ChatDraft("a", 3, "new")
        self.repository.save_draft(newest)
        self.repository.save_draft(ChatDraft("a", 2, "old"))
        self.repository.save_draft(ChatDraft("a", 3, "different same revision"))
        self.assertEqual(self.repository.get_draft("a"), newest)

    def test_reservation_clears_only_matching_revision_and_blocks_stale_resave(
        self,
    ) -> None:
        self.messages.set_chat_limits(
            "a", 1000, 128, Decimal(0), cost_increase_confirmed=False, updated_at=NOW
        )
        old = ChatDraft("a", 1, EXACT_TEXT)
        self.repository.save_draft(old)
        self.repository.save_draft(ChatDraft("b", 1, "keep b"))
        self.messages.reserve_turn(
            reservation("a"),
            content="sent message",
            requested_model_id="openrouter/free",
            retry=False,
            draft_revision=1,
        )
        self.assertEqual(self.repository.get_draft("a"), ChatDraft("a", 1))
        self.repository.save_draft(old)
        self.assertEqual(self.repository.get_draft("a"), ChatDraft("a", 1))
        self.assertEqual(self.repository.get_draft("b").text, "keep b")
        self.repository.save_draft(ChatDraft("a", 2, EXACT_TEXT))
        self.assertEqual(self.repository.get_draft("a").text, EXACT_TEXT)

    def test_reservation_does_not_clear_newer_revision_even_with_identical_text(
        self,
    ) -> None:
        self.messages.set_chat_limits(
            "a", 1000, 128, Decimal(0), cost_increase_confirmed=False, updated_at=NOW
        )
        self.repository.save_draft(ChatDraft("a", 2, EXACT_TEXT))
        self.messages.reserve_turn(
            reservation("a"),
            content=EXACT_TEXT.strip(),
            requested_model_id="openrouter/free",
            retry=False,
            draft_revision=1,
        )
        self.assertEqual(self.repository.get_draft("a"), ChatDraft("a", 2, EXACT_TEXT))

    def test_reservation_rollback_restores_draft_history_turn_and_budget(self) -> None:
        self.messages.set_chat_limits(
            "a", 1000, 128, Decimal(0), cost_increase_confirmed=False, updated_at=NOW
        )
        self.repository.save_draft(ChatDraft("a", 1, EXACT_TEXT))
        before = snapshot(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "CREATE TRIGGER fail_budget BEFORE UPDATE ON chat_budgets BEGIN SELECT RAISE(ABORT, 'fixture rollback'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.messages.reserve_turn(
                reservation("a"),
                content="message",
                requested_model_id="openrouter/free",
                retry=False,
                draft_revision=1,
            )
        self.assertEqual(snapshot(self.path), before)
        self.assertEqual(self.repository.get_draft("a").text, EXACT_TEXT)

    def test_invalid_types_are_rejected_before_sqlite_and_repr_hides_text(self) -> None:
        self.assertNotIn(EXACT_TEXT, repr(ChatDraft("a", 1, EXACT_TEXT)))
        with patch("storage.draft_repository.sqlite3.connect") as connect:
            for revision in (True, -1, 0, 1.5):
                with self.subTest(revision=revision):
                    with self.assertRaises(ValueError):
                        self.repository.save_draft(ChatDraft("a", revision, "text"))  # type: ignore[arg-type]
            connect.assert_not_called()


class DraftMigrationTests(unittest.TestCase):
    def _legacy_database(self, data_dir: str) -> AuthDatabase:
        with patch.object(database_module, "SCHEMA_VERSION", 4):
            database = AuthDatabase(data_dir)
        database.save_auth_state(
            "fake-registration",
            PinRecord(1, "pbkdf2_hmac_sha256", 1000, b"s" * 16, b"v" * 32),
        )
        database.register_failed_attempt(100, 1, 30)
        create_chat(database.path, "a")
        messages = SqliteMessageRepository(database.path)
        messages.set_chat_limits(
            "a", 1000, 128, Decimal(0), cost_increase_confirmed=False, updated_at=NOW
        )
        messages.reserve_turn(
            reservation("a"),
            content="stored user",
            requested_model_id="openrouter/free",
            retry=False,
        )
        messages.finalize_known_turn(
            "turn",
            assistant_message_id="assistant",
            content="stored assistant",
            successful=True,
            requested_model_id="openrouter/free",
            actual_model_id="fake/actual",
            generation_id="fake-generation",
            finish_reason="stop",
            prompt_tokens=7,
            completion_tokens=3,
            total_tokens=10,
            cost_usd=Decimal(0),
            updated_at=NOW,
            error_type=None,
            generated_title=None,
        )
        return database

    def test_v4_to_v5_preserves_registration_lock_history_chats_and_accounting(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            original = self._legacy_database(data_dir)
            before = snapshot(original.path)
            migrated = AuthDatabase(data_dir)
            self.assertEqual(snapshot(migrated.path), before)
            with closing(sqlite3.connect(migrated.path)) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0], 5
                )
                self.assertEqual(
                    connection.execute("SELECT * FROM chat_drafts").fetchall(), []
                )
                foreign_keys = connection.execute(
                    "PRAGMA foreign_key_list(chat_drafts)"
                ).fetchall()
                self.assertEqual(foreign_keys[0][2], "chats")
                self.assertEqual(foreign_keys[0][6], "CASCADE")
            drafts = SqliteDraftRepository(migrated.path)
            drafts.save_draft(ChatDraft("a", 1, EXACT_TEXT))
            reopened = AuthDatabase(data_dir)
            self.assertEqual(
                SqliteDraftRepository(reopened.path).get_draft("a").text, EXACT_TEXT
            )
            self.assertEqual(snapshot(reopened.path), before)

    def test_failed_migration_rolls_back_ddl_and_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            original = self._legacy_database(data_dir)
            before = snapshot(original.path)
            migrate = database_module._migrate_4_to_5

            def fail(connection: sqlite3.Connection) -> None:
                migrate(connection)
                raise sqlite3.OperationalError("fixture migration failure")

            with patch.object(database_module, "_migrate_4_to_5", side_effect=fail):
                with self.assertRaises(sqlite3.OperationalError):
                    AuthDatabase(data_dir)
            self.assertEqual(snapshot(original.path), before)
            with closing(sqlite3.connect(original.path)) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0], 4
                )
                self.assertIsNone(
                    connection.execute(
                        "SELECT name FROM sqlite_master WHERE name='chat_drafts'"
                    ).fetchone()
                )


class DraftServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        database = AuthDatabase(temp.name)
        create_chat(database.path, "a")
        self.repo = SqliteDraftRepository(database.path)
        self.service = ChatDraftService(self.repo)
        await self.service.load("a")

    async def test_concurrent_save_finishes_with_latest_revision(self) -> None:
        started, release = threading.Event(), threading.Event()
        save = self.repo.save_draft

        def delayed(draft: ChatDraft) -> ChatDraft:
            if draft.revision == 1:
                started.set()
                if not release.wait(2):
                    raise TimeoutError("fixture timed out")
            return save(draft)

        with patch.object(self.repo, "save_draft", side_effect=delayed):
            self.service.record_edit("a", "old")
            first = asyncio.create_task(self.service.flush("a"))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            newest = self.service.record_edit("a", EXACT_TEXT)
            second = asyncio.create_task(self.service.flush("a"))
            release.set()
            await asyncio.gather(first, second)
        self.assertEqual(self.repo.get_draft("a"), newest)

    async def test_cancelled_save_cannot_overtake_or_unlock_a_running_worker(
        self,
    ) -> None:
        started, release = threading.Event(), threading.Event()
        save = self.repo.save_draft
        revisions: list[int] = []

        def delayed(draft: ChatDraft) -> ChatDraft:
            revisions.append(draft.revision)
            if draft.revision == 1:
                started.set()
                if not release.wait(2):
                    raise TimeoutError("fixture timed out")
            return save(draft)

        with patch.object(self.repo, "save_draft", side_effect=delayed):
            self.service.record_edit("a", "old")
            first = asyncio.create_task(self.service.flush("a"))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            first.cancel()
            self.service.record_edit("a", EXACT_TEXT)
            second = asyncio.create_task(self.service.flush("a"))
            await asyncio.sleep(0)
            self.assertEqual(revisions, [1])
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            await second
        self.assertEqual(self.repo.get_draft("a").text, EXACT_TEXT)

    async def test_storage_failure_preserves_memory_and_safe_error_then_retries(
        self,
    ) -> None:
        draft = self.service.record_edit("a", EXACT_TEXT)
        with patch.object(
            self.repo, "save_draft", side_effect=RuntimeError(EXACT_TEXT)
        ):
            with self.assertRaises(DraftStorageError) as caught:
                await self.service.flush("a")
        self.assertNotIn(EXACT_TEXT, str(caught.exception))
        self.assertEqual(self.service.current("a"), draft)
        self.assertTrue(self.service.failed("a"))
        await self.service.flush("a")
        self.assertEqual(self.repo.get_draft("a"), draft)
        self.assertFalse(self.service.failed("a"))

    async def test_old_reservation_acknowledgement_does_not_erase_new_text(
        self,
    ) -> None:
        sent = self.service.record_edit("a", EXACT_TEXT)
        await self.service.flush("a")
        self.service.record_edit("a", "different")
        newest = self.service.record_edit("a", EXACT_TEXT)
        self.service.acknowledge_reserved(sent)
        self.assertEqual(self.service.current("a"), newest)
        await self.service.flush("a")
        self.assertEqual(self.repo.get_draft("a"), newest)

    async def test_late_read_cannot_restore_a_consumed_revision(self) -> None:
        sent = self.service.record_edit("a", EXACT_TEXT)
        await self.service.flush("a")
        started, release = threading.Event(), threading.Event()
        read = self.repo.get_draft

        def delayed(chat_id: str) -> ChatDraft:
            stored = read(chat_id)
            started.set()
            if not release.wait(2):
                raise TimeoutError("fixture timed out")
            return stored

        with patch.object(self.repo, "get_draft", side_effect=delayed):
            load = asyncio.create_task(self.service.load("a"))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            with closing(sqlite3.connect(self.repo.path)) as connection:
                with connection:
                    connection.execute(
                        "UPDATE chat_drafts SET content = '' WHERE chat_id = ?", ("a",)
                    )
            self.service.acknowledge_reserved(sent)
            release.set()
            self.assertEqual((await load).text, "")

    async def test_late_read_cannot_restore_a_deleted_draft(self) -> None:
        self.service.record_edit("a", EXACT_TEXT)
        await self.service.flush("a")
        started, release = threading.Event(), threading.Event()
        read = self.repo.get_draft

        def delayed(chat_id: str) -> ChatDraft:
            stored = read(chat_id)
            started.set()
            if not release.wait(2):
                raise TimeoutError("fixture timed out")
            return stored

        with patch.object(self.repo, "get_draft", side_effect=delayed):
            load = asyncio.create_task(self.service.load("a"))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            SqliteChatRepository(self.repo.path).delete_chat("a")
            self.service.forget("a")
            release.set()
            with self.assertRaises(DraftStorageError):
                await load
        with self.assertRaises(KeyError):
            self.service.current("a")


if __name__ == "__main__":
    unittest.main()
