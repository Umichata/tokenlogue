"""Блокировка сохраняет разрешённые записи и запрещает новые чтения и отправки."""

from __future__ import annotations

# ruff: noqa: E402
import asyncio
import sys
import threading
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState
from chat.accounting import AccountingStatus, BudgetReservation, ChatBudgetService
from chat.context import ContextMessage
from chat.drafts import ChatDraftService
from chat.models import MessageRole
from chat.service import ChatService
from storage.chat_repository import SqliteChatRepository
from storage.data_access import DataAccess, DataAccessError
from storage.draft_repository import SqliteDraftRepository
from storage.encrypted_migration import migrate_database
from storage.field_cipher import FieldCipher
from storage.message_repository import SqliteMessageRepository
from tests import test_message_sending as fixture


class ProtectedOperationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = fixture.MessageSendingTests()
        await self.fixture.asyncSetUp()
        self.addCleanup(self.fixture.temp_dir.cleanup)
        self.cipher = FieldCipher(bytes(range(32)), "operation-db", "operation-key")
        migrate_database(self.fixture.database.path, self.cipher)
        self.access = DataAccess()
        self.access.open(self.cipher)
        self.fixture.chat_repository = SqliteChatRepository(
            self.fixture.database.path, self.access
        )
        self.fixture.message_repository = SqliteMessageRepository(
            self.fixture.database.path, self.access
        )
        self.fixture.chat_service = ChatService(self.fixture.chat_repository)
        self.fixture.budget_service = ChatBudgetService(self.fixture.message_repository)
        await self.fixture._create_and_configure_free("free")

    def send(self, service, on_reserved=None):
        return service.send_message(
            "free",
            "SYNTHETIC_SENTINEL_USER",
            api_key=fixture.TEST_CREDENTIAL,
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
            on_reserved=on_reserved,
        )

    async def test_real_sent_response_is_encrypted_and_accounted_after_lock_and_relogin(
        self,
    ):
        client = fixture.BlockingCompletionClient(fixture._success(cost="0"))
        service = self.fixture._service(client)
        task = asyncio.create_task(self.send(service))
        await client.started.wait()
        self.access.lock()
        with self.assertRaises(DataAccessError):
            self.fixture.chat_repository.list_messages("free")
        self.access.open(self.cipher)
        client.release.set()
        with self.assertRaises(DataAccessError):
            await task
        messages = self.fixture.chat_repository.list_messages("free")
        self.assertEqual(len(messages), 2)
        turns = self.fixture.message_repository.list_turns("free")
        self.assertEqual(turns[0].accounting_status, AccountingStatus.FINAL)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(self.access.active_leases, 0)
        self.assertNotIn(
            b"SYNTHETIC_SENTINEL_USER", self.fixture.database.path.read_bytes()
        )

    async def test_lock_before_http_releases_reservation_without_request(self):
        client = fixture.FakeCompletionClient([fixture._success(cost="0")])
        service = self.fixture._service(client)

        async def locked(_turn):
            self.access.lock()

        with self.assertRaises(DataAccessError):
            await self.send(service, locked)
        self.assertEqual(client.calls, [])
        self.access.open(self.cipher)
        turns = self.fixture.message_repository.list_turns("free")
        self.assertEqual(turns[0].accounting_status, AccountingStatus.RELEASED)
        self.assertEqual(self.access.active_leases, 0)

    async def test_decrypted_content_and_provider_fields_are_absent_from_repr(self):
        client = fixture.FakeCompletionClient([fixture._success(cost="0")])
        await self.send(self.fixture._service(client))
        turn = self.fixture.message_repository.list_turns("free")[0]
        protected_turn = replace(
            turn, generation_id="GENERATION_SENTINEL", finish_reason="FINISH_SENTINEL"
        )
        protected_result = replace(
            fixture._success(cost="0"),
            content="CONTENT_SENTINEL",
            generation_id="GENERATION_SENTINEL",
            finish_reason="FINISH_SENTINEL",
        )
        context = ContextMessage(MessageRole.USER, "CONTEXT_SENTINEL")
        for value in (protected_turn, protected_result, context):
            self.assertNotIn("SENTINEL", repr(value))

    async def test_draft_worker_finishes_exact_revision_after_lock(self):
        repository = SqliteDraftRepository(self.fixture.database.path, self.access)
        drafts = ChatDraftService(repository)
        await drafts.load("free")
        snapshot = drafts.record_edit("free", "SYNTHETIC_DRAFT_SENTINEL")
        started, release = threading.Event(), threading.Event()
        original = repository.save_draft

        def delayed(draft):
            started.set()
            if not release.wait(5):
                raise TimeoutError("synthetic worker deadline")
            return original(draft)

        with patch.object(repository, "save_draft", side_effect=delayed):
            task = asyncio.create_task(drafts.flush("free"))
            await asyncio.to_thread(started.wait, 5)
            drafts.prepare_lock()
            self.access.lock()
            with self.assertRaises(DataAccessError):
                drafts.current("free")
            release.set()
            await task
        self.assertEqual(self.access.active_leases, 0)
        self.access.open(self.cipher)
        self.assertEqual(repository.get_draft("free"), snapshot)
        self.assertNotIn(
            b"SYNTHETIC_DRAFT_SENTINEL", self.fixture.database.path.read_bytes()
        )

    async def test_draft_repeated_cancel_keeps_lease_until_worker_finishes(self):
        repository = SqliteDraftRepository(self.fixture.database.path, self.access)
        drafts = ChatDraftService(repository)
        await drafts.load("free")
        snapshot = drafts.record_edit("free", "REPEATED_CANCEL_DRAFT_SENTINEL")
        started, release = threading.Event(), threading.Event()
        original = repository.save_draft

        def delayed(draft):
            started.set()
            if not release.wait(5):
                raise TimeoutError("synthetic worker deadline")
            return original(draft)

        with patch.object(repository, "save_draft", side_effect=delayed):
            task = asyncio.create_task(drafts.flush("free"))
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            self.access.lock()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            try:
                self.assertFalse(
                    task.done(), "owned worker must finish before cancellation returns"
                )
                self.assertEqual(self.access.active_leases, 1)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(self.access.active_leases, 0)
        self.access.open(self.cipher)
        self.assertEqual(repository.get_draft("free"), snapshot)
        self.assertNotIn(
            b"REPEATED_CANCEL_DRAFT_SENTINEL", self.fixture.database.path.read_bytes()
        )

    async def _repeat_cancel_send_worker(self, method):
        client = fixture.FakeCompletionClient([fixture._success(cost="0")])
        service = self.fixture._service(client)
        repository = self.fixture.message_repository
        original = getattr(repository, method)
        started, release = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            value = original(*args, **kwargs)
            started.set()
            if not release.wait(5):
                raise TimeoutError("synthetic worker deadline")
            return value

        with patch.object(repository, method, side_effect=delayed):
            task = asyncio.create_task(self.send(service))
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            self.access.lock()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
            try:
                self.assertFalse(
                    task.done(), "reservation worker must be joined before lease closes"
                )
                self.assertEqual(self.access.active_leases, 1)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(client.calls, [])
        self.assertEqual(self.access.active_leases, 0)
        self.access.open(self.cipher)
        turns = repository.list_turns("free")
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].accounting_status, AccountingStatus.RELEASED)
        budget = repository.get_chat_budget("free")
        assert budget is not None
        self.assertEqual(budget.reserved_tokens, 0)
        self.assertNotIn(
            b"SYNTHETIC_SENTINEL_USER", self.fixture.database.path.read_bytes()
        )

    async def test_repeated_cancel_after_reserve_releases_without_http(self):
        await self._repeat_cancel_send_worker("reserve_turn")

    async def test_repeated_cancel_after_mark_sent_releases_without_http(self):
        await self._repeat_cancel_send_worker("mark_request_sent")

    async def test_queued_old_flush_cannot_save_a_new_session_draft(self):
        repository = SqliteDraftRepository(self.fixture.database.path, self.access)
        drafts = ChatDraftService(repository)
        await drafts.load("free")
        drafts.record_edit("free", "OLD_SESSION_DRAFT")
        mutex = drafts._lock("free")
        await mutex.acquire()
        task = asyncio.create_task(drafts.flush("free"))
        await asyncio.sleep(0)
        self.access.lock()
        self.access.open(self.cipher)
        newer = drafts.record_edit("free", "NEW_SESSION_DRAFT_SENTINEL")
        mutex.release()
        with self.assertRaises(DataAccessError):
            await task
        self.assertEqual(repository.get_draft("free").revision, 0)
        self.assertEqual(drafts.current("free"), newer)
        await drafts.flush("free")
        self.assertEqual(repository.get_draft("free"), newer)

    async def test_old_flush_all_cannot_start_a_new_session_write_for_next_chat(self):
        await self.fixture._create_and_configure_free("other")
        repository = SqliteDraftRepository(self.fixture.database.path, self.access)
        drafts = ChatDraftService(repository)
        await drafts.load("free")
        await drafts.load("other")
        drafts.record_edit("free", "FIRST_SESSION_DRAFT")
        drafts.record_edit("other", "OLD_OTHER_DRAFT")
        started, release = threading.Event(), threading.Event()
        original = repository.save_draft

        def delayed(snapshot):
            result = original(snapshot)
            if snapshot.chat_id == "free":
                started.set()
                if not release.wait(5):
                    raise TimeoutError("synthetic worker deadline")
            return result

        with patch.object(repository, "save_draft", side_effect=delayed):
            task = asyncio.create_task(drafts.flush_all())
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            self.access.lock()
            self.access.open(self.cipher)
            newer = drafts.record_edit("other", "NEW_OTHER_SESSION_SENTINEL")
            release.set()
            with self.assertRaises(DataAccessError):
                await task
        self.assertEqual(repository.get_draft("other").revision, 0)
        await drafts.flush("other")
        self.assertEqual(repository.get_draft("other"), newer)

    async def test_completion_lease_cannot_finish_a_turn_from_another_chat(self):
        await self.fixture._create_and_configure_free("other")
        repository = self.fixture.message_repository
        repository.reserve_turn(
            BudgetReservation(
                "foreign-turn",
                "foreign-message",
                "other",
                100,
                Decimal("0"),
                fixture.NOW,
            ),
            content="FOREIGN_TURN_SENTINEL",
            requested_model_id="openrouter/free",
            retry=False,
        )
        lease = self.access.completion("send", "free", "foreign-turn")
        self.access.lock()
        before = self.fixture.database.path.read_bytes()
        try:
            with lease.use(), self.assertRaises(DataAccessError):
                repository.finalize_known_turn(
                    "foreign-turn",
                    assistant_message_id="assistant",
                    content="answer",
                    successful=True,
                    requested_model_id="openrouter/free",
                    actual_model_id="actual",
                    generation_id=None,
                    finish_reason=None,
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    cost_usd=Decimal("0"),
                    error_type=None,
                    generated_title=None,
                    updated_at=fixture.NOW,
                )
        finally:
            lease.close()
        self.assertEqual(self.fixture.database.path.read_bytes(), before)
        self.access.open(self.cipher)
        turn = repository.get_turn("foreign-turn")
        assert turn is not None
        self.assertEqual(turn.accounting_status, AccountingStatus.RESERVED)


if __name__ == "__main__":
    unittest.main()
