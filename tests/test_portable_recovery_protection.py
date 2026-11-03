"""Переносимое восстановление проверяется только на синтетической базе."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.data_access import DataAccess
from storage.data_protection import (
    DATA_BINDING_ALIAS,
    DATA_KEY_ALIAS,
    DataProtection,
    DataProtectionError,
)
from tests.test_data_protection import ProtectionFixture


class PortableRecoveryProtectionTests(ProtectionFixture):
    async def issue(self, pin="0123"):
        issue = await self.protection.begin_recovery_code(pin)
        await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        return issue.code

    def restart(self, **kwargs):
        self.protection.lock()
        self.access = DataAccess()
        self.protection = DataProtection(
            self.database.path,
            self.database,
            self.storage,
            self.access,
            pin_hasher=self.hasher,
            **kwargs,
        )
        return self.protection

    async def test_closed_profile_cannot_enroll_or_read_dek(self):
        await self.enroll()
        before = dict(self.storage.values)
        with self.assertRaises(DataProtectionError):
            await self.protection.begin_recovery_code("0123")
        self.assertTrue(self.storage.values == before, "storage remained unchanged")
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(await self.protection.recovery_code_enrolled())

    async def test_code_survives_restart_and_only_committed_pin_opens_data(self):
        await self.protection.unlock("0123", self.stored())
        key = self.storage.values[DATA_KEY_ALIAS]
        code = await self.issue()
        self.assertTrue(code not in repr(self.protection), "secret is absent from repr")
        self.assertTrue(
            code.replace("-", "") not in "".join(self.storage.values.values()),
            "secret is absent from persistent storage",
        )
        self.restart()
        self.storage.read_keys.clear()
        token = await self.protection.recover_with_code(code.lower().replace("-", " "))
        self.assertFalse(self.access.unlocked)
        self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))
        await self.protection.replace_pin(token, "4567")
        self.assertTrue(self.access.unlocked)
        self.assertTrue(self.storage.values[DATA_KEY_ALIAS] == key, "DEK unchanged")
        self.assertTrue(self.hasher.verify("4567", self.stored().pin_record))
        self.assertFalse(self.hasher.verify("0123", self.stored().pin_record))
        self.restart()
        self.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(code)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await self.protection.unlock("4567", self.stored())
        self.assertTrue(self.access.unlocked)

    async def test_repeat_pin_attempts_are_persisted_and_block_issue(self):
        await self.protection.unlock("0123", self.stored())
        self.protection._clock = lambda: 100
        before = self.storage.values[DATA_BINDING_ALIAS]
        for _ in range(3):
            with self.assertRaises(DataProtectionError):
                await self.protection.begin_recovery_code("9999")
        self.assertEqual(self.stored().attempts.failed_attempts, 3)
        with self.assertRaises(DataProtectionError):
            await self.protection.begin_recovery_code("0123")
        self.assertEqual(self.storage.values[DATA_BINDING_ALIAS], before)
        self.protection._clock = lambda: 400
        issue = await self.protection.begin_recovery_code("0123")
        self.assertTrue(issue.code not in repr(issue), "secret is absent from repr")
        self.assertEqual(self.stored().attempts.failed_attempts, 0)

    async def test_unconfirmed_and_cancelled_reissue_preserve_old_code(self):
        await self.protection.unlock("0123", self.stored())
        original = await self.issue()
        original_binding = self.storage.values[DATA_BINDING_ALIAS]
        issue = await self.protection.begin_recovery_code("0123")
        with self.assertRaises(DataProtectionError):
            await self.protection.confirm_recovery_code(issue.attempt_id, "A" * 31)
        self.assertEqual(self.storage.values[DATA_BINDING_ALIAS], original_binding)
        self.protection.cancel_recovery_code_issue()
        with self.assertRaises(DataProtectionError):
            await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        self.restart()
        token = await self.protection.recover_with_code(original)
        await self.protection.cancel_recovery()
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(token, "4567")
        # Отмена до intent не погасила прежний резервный способ.
        await self.protection.recover_with_code(original)

    async def test_confirmed_reissue_rejects_old_code_and_stale_confirmation(self):
        await self.protection.unlock("0123", self.stored())
        original = await self.issue()
        new = await self.protection.begin_recovery_code("0123")
        await self.protection.confirm_recovery_code(new.attempt_id, new.code)
        with self.assertRaises(DataProtectionError):
            await self.protection.confirm_recovery_code(new.attempt_id, new.code)
        self.restart()
        self.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(original)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await self.protection.recover_with_code(new.code)

    async def test_enrollment_write_failure_preserves_old_code(self):
        await self.protection.unlock("0123", self.stored())
        original = await self.issue()
        issue = await self.protection.begin_recovery_code("0123")
        before = self.storage.values[DATA_BINDING_ALIAS]
        self.storage.fail_set_key = DATA_BINDING_ALIAS
        with self.assertRaises(DataProtectionError):
            await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        self.assertEqual(self.storage.values[DATA_BINDING_ALIAS], before)
        self.storage.fail_set_key = None
        self.restart()
        await self.protection.recover_with_code(original)

    async def test_issue_and_grant_expire_and_lock_revokes_callbacks(self):
        await self.protection.unlock("0123", self.stored())
        now = [1.0]
        self.protection._monotonic = lambda: now[0]
        issue = await self.protection.begin_recovery_code("0123")
        now[0] = 302
        with self.assertRaises(DataProtectionError):
            await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        self.assertFalse(await self.protection.recovery_code_enrolled())
        code = await self.issue()
        self.protection.lock()
        token = await self.protection.recover_with_code(code)
        now[0] = 603
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(token, "4567")
        self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))
        token = await self.protection.recover_with_code(code)
        self.protection.lock()
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(token, "4567")
        self.assertTrue(await self.protection.recovery_code_enrolled())

    async def test_invalid_and_partial_codes_throttle_across_restart_without_dek(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.restart(clock=lambda: 100)
        self.storage.read_keys.clear()
        for value in ("A" * 32, code[:-1], code + "A", "А" * 32, "-" * 129):
            with self.assertRaises(DataProtectionError) as failure:
                await self.protection.recover_with_code(value)
            self.assertTrue(
                code not in str(failure.exception), "exception is secret-free"
            )
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.restart(clock=lambda: 101)
        with self.assertRaises(DataProtectionError) as failure:
            await self.protection.recover_with_code(code)
        self.assertEqual(failure.exception.code, "portable.rate_limited")
        self.protection._clock = lambda: 131
        await self.protection.recover_with_code(code)

    async def test_missing_dek_cannot_be_replaced_after_valid_code(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.restart()
        self.storage.values.pop(DATA_KEY_ALIAS)
        before = self.database.path.read_bytes()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(code)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.values)
        self.assertEqual(self.database.path.read_bytes(), before)
        self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))

    async def test_other_profile_code_and_binding_coordinates_are_rejected(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.restart()
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        binding["recovery_code"]["registration_id"] = "foreign-registration"
        self.storage.values[DATA_BINDING_ALIAS] = json.dumps(binding)
        self.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(code)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_two_recoveries_and_two_commits_have_one_winner(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.restart()
        started, release = asyncio.Event(), asyncio.Event()
        original_get = self.storage.get

        async def delayed_get(key):
            if key == DATA_BINDING_ALIAS and not started.is_set():
                started.set()
                await release.wait()
            return await original_get(key)

        with patch.object(self.storage, "get", side_effect=delayed_get):
            first = asyncio.create_task(self.protection.recover_with_code(code))
            await started.wait()
            with self.assertRaises(DataProtectionError):
                await self.protection.recover_with_code(code)
            release.set()
            token = await first
        saves = 0
        original_save = self.database.save_auth_state

        def save(registration, record):
            nonlocal saves
            saves += 1
            return original_save(registration, record)

        with patch.object(self.database, "save_auth_state", side_effect=save):
            results = await asyncio.gather(
                self.protection.replace_pin(token, "4567"),
                self.protection.replace_pin(token, "7890"),
                return_exceptions=True,
            )
        self.assertEqual(sum(result is None for result in results), 1)
        self.assertEqual(saves, 1)

    async def test_pending_intent_restart_consumes_code_without_reading_dek(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.restart()
        token = await self.protection.recover_with_code(code)
        with patch.object(
            self.database,
            "save_auth_state",
            side_effect=OSError("synthetic disk failure"),
        ):
            with self.assertRaises(DataProtectionError):
                await self.protection.replace_pin(token, "4567")
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        self.assertIn("pending", binding)
        self.assertEqual(binding["recovery_code"]["state"], "consumed")
        self.restart()
        self.storage.read_keys.clear()
        await self.protection.reconcile()
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(code)
        await self.protection.unlock("4567", self.stored())
        self.assertTrue(self.access.unlocked)

    async def test_ack_loss_before_or_after_intent_reconciles_on_fresh_instance(self):
        for committed in (False, True):
            for interrupted_ack in (1, 2, 3):
                with self.subTest(committed=committed, ack=interrupted_ack):
                    self.setUp()
                    await self.protection.unlock("0123", self.stored())
                    code = await self.issue()
                    self.protection.lock()
                    key = self.storage.values[DATA_KEY_ALIAS]
                    token = await self.protection.recover_with_code(code)
                    durable = dict(self.storage.values)
                    calls = 0

                    async def interrupted_sync():
                        nonlocal durable, calls
                        calls += 1
                        if calls == interrupted_ack and not committed:
                            raise OSError("synthetic lost pre-commit acknowledgement")
                        durable = dict(self.storage.values)
                        if calls == interrupted_ack:
                            raise OSError("synthetic lost post-commit acknowledgement")

                    self.protection._durable_write = interrupted_sync
                    with self.assertRaises(DataProtectionError):
                        await self.protection.replace_pin(token, "4567")
                    self.storage.values = dict(durable)
                    self.restart()
                    await self.protection.reconcile()
                    old_still_valid = self.hasher.verify(
                        "0123", self.stored().pin_record
                    )
                    self.assertNotEqual(
                        old_still_valid,
                        self.hasher.verify("4567", self.stored().pin_record),
                    )
                    self.assertTrue(
                        self.storage.values[DATA_KEY_ALIAS] == key, "DEK unchanged"
                    )
                    if old_still_valid:
                        await self.protection.recover_with_code(code)
                    else:
                        self.storage.read_keys.clear()
                        with self.assertRaises(DataProtectionError):
                            await self.protection.recover_with_code(code)
                        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
                    await self.protection.unlock(
                        "0123" if old_still_valid else "4567", self.stored()
                    )
                    self.assertTrue(self.access.unlocked)

    async def test_mutation_interruption_preserves_pin_and_consumption_together(self):
        for after_write in (False, True):
            for interrupted_write in (1, 2):
                with self.subTest(after_write=after_write, write=interrupted_write):
                    self.setUp()
                    await self.protection.unlock("0123", self.stored())
                    code = await self.issue()
                    self.protection.lock()
                    token = await self.protection.recover_with_code(code)
                    original_set = self.storage.set
                    writes = 0

                    async def interrupted_set(key, value):
                        nonlocal writes
                        if key == DATA_BINDING_ALIAS:
                            writes += 1
                            if writes == interrupted_write and not after_write:
                                raise OSError("synthetic interruption before mutation")
                        await original_set(key, value)
                        if key == DATA_BINDING_ALIAS and writes == interrupted_write:
                            raise OSError("synthetic interruption after mutation")

                    with patch.object(self.storage, "set", side_effect=interrupted_set):
                        with self.assertRaises(DataProtectionError):
                            await self.protection.replace_pin(token, "4567")
                    self.restart()
                    self.storage.read_keys.clear()
                    await self.protection.reconcile()
                    self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
                    old_valid = self.hasher.verify("0123", self.stored().pin_record)
                    if old_valid:
                        await self.protection.recover_with_code(code)
                    else:
                        with self.assertRaises(DataProtectionError):
                            await self.protection.recover_with_code(code)
                    await self.protection.unlock(
                        "0123" if old_valid else "4567", self.stored()
                    )
                    self.assertTrue(self.access.unlocked)

    async def test_lost_enrollment_ack_restores_old_record_and_pin_remains_valid(self):
        for committed in (False, True):
            with self.subTest(committed=committed):
                self.setUp()
                await self.protection.unlock("0123", self.stored())
                original = await self.issue()
                issue = await self.protection.begin_recovery_code("0123")
                durable = dict(self.storage.values)
                calls = 0

                async def interrupted_sync():
                    nonlocal calls, durable
                    calls += 1
                    if calls == 1 and not committed:
                        raise OSError("synthetic enrollment lost pre-commit ack")
                    durable = dict(self.storage.values)
                    if calls == 1:
                        raise OSError("synthetic enrollment lost post-commit ack")

                self.protection._durable_write = interrupted_sync
                with self.assertRaises(DataProtectionError):
                    await self.protection.confirm_recovery_code(
                        issue.attempt_id, issue.code
                    )
                self.storage.values = dict(durable)
                self.restart()
                await self.protection.unlock("0123", self.stored())
                self.protection.lock()
                await self.protection.recover_with_code(original)

    async def test_lock_during_last_await_revokes_before_durable_intent(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.protection.lock()
        token = await self.protection.recover_with_code(code)
        before = self.storage.values[DATA_BINDING_ALIAS]
        original_get = self.storage.get
        registration_reads = 0

        async def lock_at_last_read(key):
            nonlocal registration_reads
            result = await original_get(key)
            if key.endswith(".registration_id.v1"):
                registration_reads += 1
                if registration_reads == 2:
                    self.protection.lock()
            return result

        with patch.object(self.storage, "get", side_effect=lock_at_last_read):
            with self.assertRaises(DataProtectionError):
                await self.protection.replace_pin(token, "4567")
        self.assertEqual(self.storage.values[DATA_BINDING_ALIAS], before)
        self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))

    async def test_restart_after_consumption_allows_new_pin_then_fresh_issue(self):
        await self.protection.unlock("0123", self.stored())
        code = await self.issue()
        self.protection.lock()
        token = await self.protection.recover_with_code(code)
        await self.protection.replace_pin(token, "4567")
        self.restart()
        self.assertFalse(await self.protection.recovery_code_enrolled())
        await self.protection.unlock("4567", self.stored())
        fresh = await self.issue("4567")
        self.restart()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover_with_code(code)
        await self.protection.recover_with_code(fresh)

    async def test_stale_issue_during_storage_write_restores_previous_code(self):
        for revoke in ("lock", "cancel", "expiry"):
            with self.subTest(revoke=revoke):
                self.setUp()
                await self.protection.unlock("0123", self.stored())
                old = await self.issue()
                now = [1.0]
                self.protection._monotonic = lambda: now[0]
                issue = await self.protection.begin_recovery_code("0123")
                before = self.storage.values[DATA_BINDING_ALIAS]
                started, release = asyncio.Event(), asyncio.Event()
                original_set = self.storage.set
                held = False

                async def blocked_set(key, value):
                    nonlocal held
                    if key == DATA_BINDING_ALIAS and not held:
                        held = True
                        started.set()
                        await release.wait()
                    await original_set(key, value)

                with patch.object(self.storage, "set", side_effect=blocked_set):
                    pending = asyncio.create_task(
                        self.protection.confirm_recovery_code(
                            issue.attempt_id, issue.code
                        )
                    )
                    await started.wait()
                    if revoke == "lock":
                        self.protection.lock()
                    elif revoke == "cancel":
                        self.protection.cancel_recovery_code_issue()
                    else:
                        now[0] = 302
                    release.set()
                    with self.assertRaises(DataProtectionError):
                        await pending
                self.assertTrue(
                    self.storage.values[DATA_BINDING_ALIAS] == before,
                    "stale confirmation preserved previous verifier",
                )
                self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))
                self.restart()
                await self.protection.recover_with_code(old)

    async def test_task_cancel_after_issue_mutation_waits_for_old_record_restore(self):
        await self.protection.unlock("0123", self.stored())
        old = await self.issue()
        issue = await self.protection.begin_recovery_code("0123")
        before = self.storage.values[DATA_BINDING_ALIAS]
        mutation, restore_started, restore_release = (
            asyncio.Event(),
            asyncio.Event(),
            asyncio.Event(),
        )
        original_set = self.storage.set
        writes = 0

        async def interrupted_set(key, value):
            nonlocal writes
            if key != DATA_BINDING_ALIAS:
                await original_set(key, value)
                return
            writes += 1
            if writes == 1:
                await original_set(key, value)
                mutation.set()
                await asyncio.Event().wait()
            else:
                restore_started.set()
                await restore_release.wait()
                await original_set(key, value)

        with patch.object(self.storage, "set", side_effect=interrupted_set):
            pending = asyncio.create_task(
                self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
            )
            await mutation.wait()
            pending.cancel()
            try:
                await asyncio.wait_for(restore_started.wait(), 1)
            finally:
                restore_release.set()
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        self.assertTrue(
            self.storage.values[DATA_BINDING_ALIAS] == before,
            "cancelled confirmation restored previous verifier",
        )
        self.restart()
        await self.protection.recover_with_code(old)


if __name__ == "__main__":
    unittest.main()
