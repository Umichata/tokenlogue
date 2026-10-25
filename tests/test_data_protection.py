"""Защищённая привязка и восстановление используют только синтетические данные."""

from __future__ import annotations

# ruff: noqa: E402
import asyncio
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.pin import PinHasher
from platform_security.device_recovery import (
    DeviceRecovery,
    RecoveryResult,
    RecoveryStatus,
)
from storage.data_access import DataAccess
from storage.data_protection import (
    DATA_BINDING_ALIAS,
    DATA_KEY_ALIAS,
    DataProtection,
    DataProtectionError,
)
from storage.database import AuthDatabase
from storage.secure_credentials import REGISTRATION_ID_STORAGE_NAME
from tests.test_secure_credentials import FakeSecureStorage


class Provider:
    def __init__(self, status=RecoveryStatus.SUCCESS):
        self.status = status
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.cancelled = []

    async def authenticate(self, request):
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        return RecoveryResult(request, self.status)

    async def cancel(self, attempt):
        self.cancelled.append(attempt)


class ProtectionFixture(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = AuthDatabase(self.temporary.name)
        self.hasher = PinHasher(iterations=100)
        self.database.save_auth_state(
            "fixture-registration", self.hasher.create_record("0123")
        )
        self.storage = FakeSecureStorage()
        self.storage.values[REGISTRATION_ID_STORAGE_NAME] = "fixture-registration"
        self.access = DataAccess()
        self.protection = DataProtection(
            self.database.path,
            self.database,
            self.storage,
            self.access,
            pin_hasher=self.hasher,
        )

    def stored(self):
        result = self.database.get_auth_state()
        assert result is not None
        return result

    async def enroll(self):
        await self.protection.unlock("0123", self.stored())
        self.assertTrue(self.access.unlocked)
        self.protection.lock()
        self.storage.read_keys.clear()


class DataProtectionTests(ProtectionFixture):
    async def test_wrong_pin_never_reads_or_creates_dek(self):
        with self.assertRaises(DataProtectionError):
            await self.protection.unlock("9999", self.stored())
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.values)

    async def test_wrong_but_well_formed_key_readback_cannot_encrypt_existing_data(
        self,
    ):
        before = self.database.path.read_bytes()
        original_get = self.storage.get
        intercepted = False

        async def wrong_once(key):
            nonlocal intercepted
            value = await original_get(key)
            if key == DATA_KEY_ALIAS and value is not None and not intercepted:
                intercepted = True
                altered = json.loads(value)
                altered["key"] = base64.b64encode(bytes([7]) * 32).decode("ascii")
                return json.dumps(altered, sort_keys=True, separators=(",", ":"))
            return value

        with patch.object(self.storage, "get", side_effect=wrong_once):
            with self.assertRaises(DataProtectionError):
                await self.protection.unlock("0123", self.stored())
        self.assertEqual(self.database.path.read_bytes(), before)
        self.assertFalse(self.access.unlocked)
        durable_key = self.storage.values[DATA_KEY_ALIAS]
        self.storage.read_keys.clear()
        await self.protection.unlock("0123", self.stored())
        self.assertTrue(self.access.unlocked)
        self.assertEqual(self.storage.values[DATA_KEY_ALIAS], durable_key)
        self.assertEqual(self.storage.read_keys.count(DATA_KEY_ALIAS), 2)

    async def test_key_disk_commit_failure_blocks_migration_until_durable_ack(self):
        durable = {}
        fail_key_sync = True

        async def sync_storage():
            if DATA_KEY_ALIAS in self.storage.values and fail_key_sync:
                raise OSError("synthetic commit failure")
            durable.update(self.storage.values)

        protection = DataProtection(
            self.database.path,
            self.database,
            self.storage,
            self.access,
            pin_hasher=self.hasher,
            durable_write=sync_storage,
        )
        before = self.database.path.read_bytes()
        with self.assertRaises(DataProtectionError):
            await protection.unlock("0123", self.stored())
        self.assertEqual(self.database.path.read_bytes(), before)
        self.assertFalse(self.access.unlocked)
        self.assertIn(DATA_KEY_ALIAS, self.storage.values)
        self.assertNotIn(DATA_KEY_ALIAS, durable)
        original_key = self.storage.values[DATA_KEY_ALIAS]
        fail_key_sync = False
        await protection.unlock("0123", self.stored())
        self.assertEqual(durable[DATA_KEY_ALIAS], original_key)
        self.assertTrue(self.access.unlocked)

    async def test_metadata_inspection_and_reconcile_do_not_read_dek(self):
        await self.enroll()
        self.assertTrue(await self.protection.has_protection())
        await self.protection.reconcile()
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(self.access.unlocked)

    async def test_sqlite_verifier_substitution_cannot_read_dek(self):
        await self.enroll()
        self.database.save_auth_state(
            "fixture-registration", self.hasher.create_record("9999")
        )
        with self.assertRaises(DataProtectionError):
            await self.protection.unlock("9999", self.stored())
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(self.access.unlocked)

    async def test_attempt_counter_is_not_part_of_protected_binding(self):
        await self.enroll()
        self.database.register_failed_attempt(100, 5, 30)
        await self.protection.unlock("0123", self.stored())
        self.assertTrue(self.access.unlocked)

    async def test_missing_key_never_replaces_key_or_database(self):
        await self.enroll()
        self.storage.values.pop(DATA_KEY_ALIAS)
        before = self.database.path.read_bytes()
        with self.assertRaises(DataProtectionError):
            await self.protection.unlock("0123", self.stored())
        self.assertEqual(self.database.path.read_bytes(), before)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.values)
        self.assertFalse(self.access.unlocked)

    async def test_cancelled_native_challenge_reads_no_dek_and_preserves_pin(self):
        await self.enroll()
        before = self.stored()
        with self.assertRaises(DataProtectionError):
            await self.protection.recover(
                cast(DeviceRecovery, Provider(RecoveryStatus.CANCELLED))
            )
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertEqual(self.stored(), before)

    async def test_late_native_success_after_epoch_change_cannot_read_dek(self):
        await self.enroll()
        provider = Provider()
        provider.release = asyncio.Event()
        task = asyncio.create_task(
            self.protection.recover(cast(DeviceRecovery, provider))
        )
        await provider.started.wait()
        self.protection.lock()
        provider.release.set()
        with self.assertRaises(DataProtectionError):
            await task
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(self.access.unlocked)

    async def test_success_only_allows_new_pin_and_cancel_preserves_original(self):
        await self.enroll()
        before = self.stored()
        token = await self.protection.recover(cast(DeviceRecovery, Provider()))
        self.assertFalse(self.access.unlocked)
        self.assertEqual(self.stored(), before)
        await self.protection.cancel_recovery()
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(token, "4567")
        self.assertEqual(self.stored(), before)

    async def test_new_pin_preserves_key_and_grant_is_one_use(self):
        await self.enroll()
        key = self.storage.values[DATA_KEY_ALIAS]
        token = await self.protection.recover(cast(DeviceRecovery, Provider()))
        await self.protection.replace_pin(token, "4567")
        self.assertTrue(self.access.unlocked)
        self.assertTrue(self.hasher.verify("4567", self.stored().pin_record))
        self.assertFalse(self.hasher.verify("0123", self.stored().pin_record))
        self.assertEqual(self.storage.values[DATA_KEY_ALIAS], key)
        self.protection.lock()
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(token, "9999")

    async def test_protected_pending_pin_reconciles_without_reading_key(self):
        await self.enroll()
        token = await self.protection.recover(cast(DeviceRecovery, Provider()))
        original_save = self.database.save_auth_state

        def fail(registration_id, record):
            raise OSError("synthetic disk full")

        self.database.save_auth_state = fail
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(token, "4567")
        self.database.save_auth_state = original_save
        self.assertIn("pending", json.loads(self.storage.values[DATA_BINDING_ALIAS]))
        self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))
        self.storage.read_keys.clear()
        await self.protection.reconcile()
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertTrue(self.hasher.verify("4567", self.stored().pin_record))
        await self.protection.unlock("4567", self.stored())
        self.assertTrue(self.access.unlocked)

    async def test_missing_binding_cannot_enroll_over_encrypted_database(self):
        await self.enroll()
        self.storage.values.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.unlock("0123", self.stored())
        self.assertEqual(self.storage.values, {})

    async def test_pending_pin_does_not_write_into_a_different_database(self):
        from storage.encrypted_migration import migrate_database
        from storage.field_cipher import FieldCipher

        await self.enroll()
        token = await self.protection.recover(cast(DeviceRecovery, Provider()))
        with patch.object(
            self.database, "save_auth_state", side_effect=OSError("synthetic disk full")
        ):
            with self.assertRaises(DataProtectionError):
                await self.protection.replace_pin(token, "4567")
        other = AuthDatabase(Path(self.temporary.name) / "other")
        other.save_auth_state("other-registration", self.hasher.create_record("7890"))
        migrate_database(
            other.path, FieldCipher(bytes([7]) * 32, "other-database", "other-key")
        )
        os.replace(other.path, self.database.path)
        before = self.database.path.read_bytes()
        self.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.reconcile()
        self.assertEqual(self.database.path.read_bytes(), before)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertIn("pending", json.loads(self.storage.values[DATA_BINDING_ALIAS]))

    async def test_replacement_grant_closes_reads_and_background_revokes(self):
        await self.enroll()
        await self.protection.unlock("0123", self.stored())
        self.protection.begin_key_replacement()
        self.assertFalse(self.access.unlocked)
        self.assertTrue(self.protection.replacement_pending)
        self.protection.lock()
        with self.assertRaises(DataProtectionError):
            self.protection.finish_key_replacement()
        self.assertFalse(self.access.unlocked)


if __name__ == "__main__":
    unittest.main()
