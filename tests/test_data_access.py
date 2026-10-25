"""Эпохи отзывают чтение, а узкие leases завершают только свою операцию."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.data_access import DataAccess, DataAccessError  # noqa: E402

if TYPE_CHECKING:
    from storage.field_cipher import FieldCipher


def cipher_marker() -> FieldCipher:
    """Проверка разрешений не вызывает алгоритм и не создаёт настоящего ключа."""
    return cast("FieldCipher", object())


class DataAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.access = DataAccess()
        self.first = cipher_marker()
        self.second = cipher_marker()

    def test_closed_access_never_reads_or_creates_completion(self):
        for operation in ("read", "write", "finish", "draft"):
            with self.assertRaises(DataAccessError):
                with self.access.authorize(
                    operation, chat_id="chat-a", record_id="turn-a"
                ):
                    self.fail("Закрытый доступ выдал cipher")
        with self.assertRaises(DataAccessError):
            self.access.completion("send", "chat-a", "turn-a")
        self.assertEqual(self.access.active_leases, 0)

    def test_old_session_does_not_inherit_new_login(self):
        self.access.open(self.first)
        with self.assertRaises(DataAccessError), self.access.session():
            self.access.lock()
            self.access.open(self.second)
            with self.assertRaises(DataAccessError):
                with self.access.authorize("read"):
                    self.fail("Старая сессия открыла новый workspace")
            with self.assertRaises(DataAccessError):
                self.access.completion("send", "chat-b", "turn-b")
        with self.access.authorize("read") as current:
            self.assertIs(current, self.second)

    async def test_to_thread_keeps_captured_epoch_across_lock_and_login(self):
        self.access.open(self.first)
        entered, released = threading.Event(), threading.Event()

        def read_later():
            entered.set()
            if not released.wait(3):
                raise TimeoutError("Не освобождён синтетический worker")
            with self.access.authorize("read"):
                return "unexpected plaintext"

        with self.assertRaises(DataAccessError), self.access.session():
            worker = asyncio.create_task(asyncio.to_thread(read_later))
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            self.access.lock()
            self.access.open(self.second)
            released.set()
            with self.assertRaises(DataAccessError):
                await worker

    async def test_read_started_before_lock_is_denied_at_return(self):
        self.access.open(self.first)
        entered, released = threading.Event(), threading.Event()

        def read():
            with self.access.authorize("read") as active:
                self.assertIs(active, self.first)
                entered.set()
                if not released.wait(3):
                    raise TimeoutError("Не освобождён синтетический reader")
            return "unexpected plaintext"

        with self.assertRaises(DataAccessError), self.access.session():
            worker = asyncio.create_task(asyncio.to_thread(read))
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            self.access.lock()
            self.access.open(self.second)
            released.set()
            with self.assertRaises(DataAccessError):
                await worker

    def test_send_completion_keeps_old_cipher_but_never_new_read_or_reservation(self):
        self.access.open(self.first)
        lease = self.access.completion("send", "chat-a", "turn-a")
        self.access.lock()
        self.access.open(self.second)
        with lease.use():
            with self.access.authorize(
                "finish", chat_id="chat-a", record_id="turn-a"
            ) as key:
                self.assertIs(key, self.first)
            for operation in ("read", "write", "reserve", "draft"):
                with self.assertRaises(DataAccessError):
                    with self.access.authorize(
                        operation, chat_id="chat-a", record_id="turn-a"
                    ):
                        self.fail("Lease завершения выдал расширенный доступ")
            for chat, turn in (("chat-b", "turn-a"), ("chat-a", "turn-b")):
                with self.assertRaises(DataAccessError):
                    with self.access.authorize("finish", chat_id=chat, record_id=turn):
                        self.fail("Lease завершил чужую отправку")
        lease.close()
        self.assertIsNone(lease.cipher)
        self.assertEqual(self.access.active_leases, 0)
        lease.close()
        self.assertEqual(self.access.active_leases, 0)
        with self.assertRaises(DataAccessError):
            with lease.use():
                self.fail("Закрытый lease использован повторно")
        with self.access.authorize("read") as current:
            self.assertIs(current, self.second)

    def test_lease_scope_is_strict_even_before_lock(self):
        self.access.open(self.first)
        lease = self.access.completion("send", "chat-a", "turn-a")
        try:
            with lease.use():
                for operation, chat, record in (
                    ("read", "", ""),
                    ("write", "chat-a", "turn-a"),
                    ("finish", "chat-b", "turn-a"),
                    ("finish", "chat-a", "turn-b"),
                ):
                    with self.subTest(operation=operation, chat=chat, record=record):
                        with self.assertRaises(DataAccessError):
                            with self.access.authorize(
                                operation, chat_id=chat, record_id=record
                            ):
                                pass
        finally:
            lease.close()

    async def test_draft_lease_only_finishes_its_revision_in_worker_after_lock(self):
        self.access.open(self.first)
        lease = self.access.completion("draft", "chat-a", "37")
        self.access.lock()

        def finish_draft():
            with self.access.authorize(
                "draft", chat_id="chat-a", record_id="37"
            ) as key:
                self.assertIs(key, self.first)
            for chat, revision in (("chat-b", "37"), ("chat-a", "38")):
                with self.assertRaises(DataAccessError):
                    with self.access.authorize(
                        "draft", chat_id=chat, record_id=revision
                    ):
                        self.fail("Черновик записал чужую ревизию")

        try:
            with lease.use():
                await asyncio.to_thread(finish_draft)
        finally:
            lease.close()
        self.assertFalse(self.access.unlocked)

    def test_unknown_operation_never_grants_permission(self):
        self.access.open(self.first)
        for operation in ("", "reaad", "reserve_all", "READ"):
            with self.subTest(operation=operation):
                with self.assertRaises(DataAccessError):
                    with self.access.authorize(operation):
                        pass


if __name__ == "__main__":
    unittest.main()
