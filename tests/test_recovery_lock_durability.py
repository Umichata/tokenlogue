"""Recovery/lock races decide by durable state, without opening real storage."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import threading
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthStatus  # noqa: E402
from auth.service import AuthService  # noqa: E402
from platform_security.device_recovery import RecoveryProvider  # noqa: E402
from storage.data_protection import (  # noqa: E402
    DATA_BINDING_ALIAS,
    DATA_KEY_ALIAS,  # noqa: E402
    DataProtectionError,
)
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests import test_encryption_initialization as fixtures  # noqa: E402
from tests.test_data_protection import Provider  # noqa: E402
from tests.test_message_sending import FakeKeyValidator  # noqa: E402


class RecoveryLockDurabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.EncryptionInitializationTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.protection = self.fx.protection()
        await self.protection.unlock("0123", self.fx.stored())
        self.fx.database.reset_login_attempts()
        with self.fx.access.authorize("read") as cipher:
            self.original_content = fixtures.snapshot(self.fx.database.path, cipher)
        self.original_key = self.fx.storage.values[DATA_KEY_ALIAS]
        self.original_registration = self.fx.stored().registration_id
        self.protection.lock()
        self.provider = Provider()
        self.credentials = FletSecureCredentials(self.fx.storage)
        self.auth = AuthService(
            FakeKeyValidator(),
            self.credentials,
            self.fx.database,
            pin_hasher=self.fx.hasher,
            protection=self.protection,
            recovery_provider=cast(RecoveryProvider, self.provider),
        )

    async def assert_restart_winner(self, expected_pin):
        self.protection.lock()
        self.protection = self.fx.restart()
        await self.protection.reconcile()
        self.assertFalse(self.fx.access.unlocked)
        stored = self.fx.stored()
        self.assertEqual(stored.registration_id, self.original_registration)
        old = self.fx.hasher.verify("0123", stored.pin_record)
        new = self.fx.hasher.verify("4567", stored.pin_record)
        self.assertNotEqual(old, new, "Exactly one PIN survives the transaction")
        self.assertEqual(old, expected_pin == "0123")
        self.assertTrue(
            self.fx.storage.values[DATA_KEY_ALIAS] == self.original_key, "DEK retained"
        )
        await self.protection.unlock(expected_pin, stored)
        with self.fx.access.authorize("read") as cipher:
            current = fixtures.snapshot(self.fx.database.path, cipher)
        for table, before in self.original_content.items():
            if table != "auth_state":
                self.assertEqual(current[table], before, table)
        with sqlite3.connect(self.fx.database.path) as connection:
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )

    async def grant(self):
        result = await self.auth.recover_pin()
        self.assertEqual(result.status, AuthStatus.PIN_CHOICE_REQUIRED)
        assert result.pending_setup_token is not None
        return result.pending_setup_token

    async def test_lock_while_final_api_reply_pending_cannot_report_authenticated(self):
        token = await self.grant()
        entered, release = asyncio.Event(), asyncio.Event()
        get = self.credentials.get_api_key

        async def delayed():
            entered.set()
            await release.wait()
            return await get()

        with patch.object(self.credentials, "get_api_key", delayed):
            completing = asyncio.create_task(self.auth.complete_recovery("4567", token))
            await entered.wait()
            # The new PIN has committed. Lock must not roll it back or reopen data.
            self.assertTrue(self.fx.hasher.verify("4567", self.fx.stored().pin_record))
            self.auth.lock_access()
            self.assertFalse(self.fx.access.unlocked)
            release.set()
            result = await completing
        self.assertNotEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertIsNone(result.api_key)
        self.assertFalse(self.fx.access.unlocked)
        self.assertTrue(self.fx.hasher.verify("4567", self.fx.stored().pin_record))
        self.assertFalse(self.fx.hasher.verify("0123", self.fx.stored().pin_record))
        self.assertEqual(self.fx.stored().registration_id, self.original_registration)
        self.assertTrue(
            self.fx.storage.values[DATA_KEY_ALIAS] == self.original_key, "DEK retained"
        )
        await self.assert_restart_winner("4567")

    async def test_lock_before_native_proof_rejects_late_success_without_dek_read(self):
        self.provider.release = asyncio.Event()
        recovering = asyncio.create_task(self.auth.recover_pin())
        await self.provider.started.wait()
        self.fx.storage.read_keys.clear()
        self.auth.lock_access()
        await self.auth.cancel_recovery()
        self.provider.release.set()
        result = await recovering
        self.assertNotEqual(result.status, AuthStatus.PIN_CHOICE_REQUIRED)
        self.assertIsNone(result.pending_setup_token)
        self.assertNotIn(DATA_KEY_ALIAS, self.fx.storage.read_keys)
        self.assertFalse(self.fx.access.unlocked)
        await self.assert_restart_winner("0123")

    async def test_lock_after_grant_before_save_preserves_previous_pin(self):
        token = await self.grant()
        self.assertTrue(self.fx.hasher.verify("0123", self.fx.stored().pin_record))
        self.auth.lock_access()
        result = await self.auth.complete_recovery("4567", token)
        self.assertNotEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertIsNone(result.api_key)
        self.assertFalse(self.fx.access.unlocked)
        await self.assert_restart_winner("0123")

    async def test_lock_during_new_pin_kdf_before_intent_keeps_old_pin(self):
        token = await self.grant()
        entered, release = threading.Event(), threading.Event()
        create = self.fx.hasher.create_record

        def delayed(pin):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic test barrier timeout")
            return create(pin)

        with patch.object(self.fx.hasher, "create_record", delayed):
            saving = asyncio.create_task(self.auth.complete_recovery("4567", token))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.auth.lock_access()
            release.set()
            result = await saving
        self.assertNotEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertIsNone(result.api_key)
        self.assertNotIn(
            "pending", json.loads(self.fx.storage.values[DATA_BINDING_ALIAS])
        )
        self.assertFalse(self.fx.access.unlocked)
        await self.assert_restart_winner("0123")

    async def lock_at_ack(self, *, boundary, committed, lost_reply, token=None):
        if token is None:
            token = await self.grant()
        durable = dict(self.fx.storage.values)
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def sync():
            nonlocal calls, durable
            calls += 1
            if calls == boundary:
                if committed:
                    durable = dict(self.fx.storage.values)
                entered.set()
                await release.wait()
                if lost_reply:
                    raise OSError("synthetic durable acknowledgement loss")
            durable = dict(self.fx.storage.values)

        self.protection._durable_write = sync
        self.fx.storage.read_keys.clear()
        saving = asyncio.create_task(self.auth.complete_recovery("4567", token))
        await asyncio.wait_for(entered.wait(), 2)
        self.assertFalse(saving.done(), "No success is returned before durable ACK")
        self.assertFalse(self.fx.access.unlocked)
        before_pin = "0123" if boundary < 3 else "4567"
        self.assertTrue(self.fx.hasher.verify(before_pin, self.fx.stored().pin_record))
        self.auth.lock_access()
        release.set()
        result = await saving
        self.assertNotEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertIsNone(result.api_key)
        self.assertFalse(self.fx.access.unlocked)
        self.assertFalse(self.protection._grant)
        # Model a cold backend restart. Uncommitted native memory is not durable.
        self.fx.storage.values = dict(durable)
        expected = "0123" if boundary == 1 and lost_reply and not committed else "4567"
        await self.assert_restart_winner(expected)

    async def test_lock_before_first_intent_ack_and_backend_did_not_commit(self):
        await self.lock_at_ack(boundary=1, committed=False, lost_reply=True)

    async def test_lock_after_first_intent_commit_and_ack_reply_was_lost(self):
        await self.lock_at_ack(boundary=1, committed=True, lost_reply=True)

    async def test_lock_during_first_ack_completes_durable_intent_without_opening(self):
        await self.lock_at_ack(boundary=1, committed=False, lost_reply=False)

    async def test_lock_at_pre_sql_barrier_preserves_committed_intent(self):
        await self.lock_at_ack(boundary=2, committed=True, lost_reply=False)

    async def test_lock_after_sql_commit_before_final_ack_keeps_new_pin(self):
        await self.lock_at_ack(boundary=3, committed=False, lost_reply=True)

    async def test_lock_after_final_binding_commit_but_lost_ack_keeps_new_pin(self):
        await self.lock_at_ack(boundary=3, committed=True, lost_reply=True)

    async def test_lock_while_sql_commit_pending_finishes_chosen_pin_without_access(
        self,
    ):
        token = await self.grant()
        entered, release = threading.Event(), threading.Event()
        save = self.fx.database.save_auth_state

        def delayed(registration, record):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic test barrier timeout")
            save(registration, record)

        with patch.object(self.fx.database, "save_auth_state", delayed):
            saving = asyncio.create_task(self.auth.complete_recovery("4567", token))
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.assertTrue(self.fx.hasher.verify("0123", self.fx.stored().pin_record))
            self.auth.lock_access()
            release.set()
            result = await saving
        self.assertNotEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertIsNone(result.api_key)
        self.assertFalse(self.fx.access.unlocked)
        await self.assert_restart_winner("4567")

    async def test_system_lock_and_cancel_do_not_clear_pin_attempts_or_deadline(self):
        self.auth._clock = lambda: 1000.0
        self.auth._pin_elapsed_clock = lambda: 10000.0
        self.auth._pin_boot_token = lambda: "synthetic-recovery-boot"
        self.assertEqual((await self.auth.login("9999")).status, AuthStatus.INVALID_PIN)
        self.assertEqual((await self.auth.login("9999")).status, AuthStatus.INVALID_PIN)
        before = self.fx.stored().attempts
        token = await self.grant()
        self.auth.lock_access()
        await self.auth.cancel_recovery()
        self.assertEqual(self.fx.stored().attempts, before)
        self.assertNotEqual(
            (await self.auth.complete_recovery("4567", token)).status,
            AuthStatus.AUTHENTICATED,
        )
        locked = await self.auth.login("9999")
        self.assertEqual(locked.status, AuthStatus.LOCKED)
        self.assertEqual(locked.lock_seconds_remaining, 300)
        before = self.fx.stored().attempts
        self.auth.lock_access()
        await self.auth.cancel_recovery()
        self.assertEqual(self.fx.stored().attempts, before)
        self.assertEqual((await self.auth.login("0123")).status, AuthStatus.LOCKED)

    async def test_code_grant_lock_preserves_old_pin_and_same_code_until_commit(self):
        await self.protection.unlock("0123", self.fx.stored())
        issue = await self.protection.begin_recovery_code("0123")
        await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        self.protection.lock()
        token = await self.protection.recover_with_code(issue.code)
        self.auth.lock_access()
        result = await self.auth.complete_recovery("4567", token)
        self.assertNotEqual(result.status, AuthStatus.AUTHENTICATED)
        await self.assert_restart_winner("0123")
        self.protection.lock()
        token = await self.protection.recover_with_code(issue.code)
        await self.protection.replace_pin(token, "4567")
        self.protection.lock()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(issue.code)
        await self.assert_restart_winner("4567")

    async def test_code_consumption_and_new_pin_survive_lock_after_durable_intent(self):
        await self.protection.unlock("0123", self.fx.stored())
        issue = await self.protection.begin_recovery_code("0123")
        await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        self.protection.lock()
        token = await self.protection.recover_with_code(issue.code)
        await self.lock_at_ack(boundary=1, committed=True, lost_reply=True, token=token)
        self.protection.lock()
        self.fx.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(issue.code)
        self.assertNotIn(DATA_KEY_ALIAS, self.fx.storage.read_keys)
        self.assertTrue(self.fx.hasher.verify("4567", self.fx.stored().pin_record))


if __name__ == "__main__":
    unittest.main()
