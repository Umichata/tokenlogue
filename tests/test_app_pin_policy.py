"""App PIN 3/300 проверяется на временной SQLite с управляемыми часами."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import threading
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthStatus
from auth.pin_policy import (
    APP_PIN_LOCK_SECONDS,
    APP_PIN_MAX_FAILED_ATTEMPTS,
    PinClockSample,
)
from auth.service import AuthService
from storage.data_protection import DATA_KEY_ALIAS, DataProtectionError
from storage.secure_credentials import FletSecureCredentials
from tests.test_data_protection import ProtectionFixture
from tests.test_message_sending import FakeKeyValidator


class AppPinPolicyTests(ProtectionFixture):
    async def asyncSetUp(self):
        self.now = 1000.0
        self.elapsed = 10000.0
        self.boot = "controlled-boot-a"
        self.credentials = FletSecureCredentials(self.storage)
        await self.credentials.save_credentials(
            "synthetic-api-only", "fixture-registration"
        )
        self.protection._clock = lambda: self.now
        self.protection._pin_elapsed_clock = lambda: self.elapsed
        self.protection._pin_boot_token = lambda: self.boot
        self.auth = self.make_auth()

    def make_auth(self):
        return AuthService(
            FakeKeyValidator(),
            self.credentials,
            self.database,
            pin_hasher=self.hasher,
            clock=lambda: self.now,
            protection=self.protection,
            pin_elapsed_clock=lambda: self.elapsed,
            pin_boot_token=lambda: self.boot,
        )

    async def test_third_wrong_pin_atomically_locks_for_300_seconds(self):
        self.assertEqual((await self.auth.login("9999")).status, AuthStatus.INVALID_PIN)
        self.assertEqual((await self.auth.login("9999")).status, AuthStatus.INVALID_PIN)
        result = await self.auth.login("9999")
        self.assertEqual(result.status, AuthStatus.LOCKED)
        self.assertEqual(result.lock_seconds_remaining, 300)
        self.assertEqual(self.stored().attempts.failed_attempts, 3)
        self.assertNotIn("chat_data_key", " ".join(self.storage.read_keys))

    async def arm(self):
        result = None
        for _ in range(3):
            result = await self.auth.login("9999")
        assert result is not None
        return result

    async def test_atomic_threshold_caps_concurrent_failures_at_three(self):
        await self.auth.login("9999")
        await self.auth.login("9999")
        sample = PinClockSample(self.now, self.elapsed, self.boot)
        states = await asyncio.gather(
            *(
                asyncio.to_thread(self.database.register_pin_failure, sample)
                for _ in range(6)
            )
        )
        self.assertTrue(
            all(
                state.failed_attempts == 3 and state.lock_seconds_remaining == 300
                for state in states
            )
        )
        self.assertEqual(self.stored().attempts.failed_attempts, 3)

    async def test_versioned_lock_cell_survives_six_to_seven_migration(self):
        from storage.encrypted_migration import migrate_database
        from storage.field_cipher import FieldCipher

        await self.arm()
        with sqlite3.connect(self.database.path) as connection:
            raw = connection.execute("SELECT locked_until FROM auth_state").fetchone()[
                0
            ]
        migrate_database(
            self.database.path,
            FieldCipher(
                bytes(range(32)), "synthetic-migration-db", "synthetic-migration-key"
            ),
        )
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertEqual(
                connection.execute("SELECT locked_until FROM auth_state").fetchone()[0],
                raw,
            )
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 300)

    async def test_boundaries_and_cycle_reset_need_backend_clock(self):
        await self.arm()
        self.storage.read_keys.clear()
        self.now += 99999
        self.elapsed += 299
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 1)
        self.assertEqual((await self.auth.login("0123")).status, AuthStatus.LOCKED)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertNotIn("openrouter_api_key", " ".join(self.storage.read_keys))
        self.elapsed += 1
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)
        self.assertEqual((await self.auth.login("9999")).status, AuthStatus.INVALID_PIN)
        self.assertEqual(self.stored().attempts.failed_attempts, 1)
        self.assertEqual(
            (await self.auth.login("0123")).status, AuthStatus.AUTHENTICATED
        )
        self.assertEqual(self.stored().attempts.failed_attempts, 0)

    async def test_two_errors_restart_then_third_and_persisted_lock(self):
        for _ in range(2):
            await self.auth.login("9999")
        self.auth = self.make_auth()
        self.assertEqual(self.stored().attempts.failed_attempts, 2)
        self.assertEqual((await self.auth.login("9999")).lock_seconds_remaining, 300)
        self.elapsed += 51
        self.auth = self.make_auth()
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 249)

    async def test_legacy_three_four_without_deadline_migrate_once(self):
        for failed in (3, 4):
            with sqlite3.connect(self.database.path) as connection:
                connection.execute(
                    "UPDATE auth_state SET failed_attempts=?,locked_until=NULL",
                    (failed,),
                )
            self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 300)
            self.elapsed += 100
            self.auth = self.make_auth()
            self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 200)
            self.elapsed += 200
            self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)

    async def test_legacy_active_deadline_preserved_and_backward_anomaly_bounded(self):
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE auth_state SET failed_attempts=5,locked_until=?",
                (self.now + 17,),
            )
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 17)
        self.now -= 100000
        self.elapsed += 16
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 1)
        self.elapsed += 1
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE auth_state SET failed_attempts=5,locked_until=?",
                (self.now + 99999,),
            )
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 300)
        self.elapsed += 300
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)

    async def test_versioned_lock_survives_arbitrary_wall_jumps_without_renewal(self):
        await self.arm()
        for offset in (-86400, 1234567, -99999999, 3333):
            self.now += offset
            self.elapsed += 50
            self.auth = self.make_auth()
            self.assertEqual(
                await self.auth.pin_lock_seconds_remaining(),
                300 - int(self.elapsed - 10000),
            )
        self.elapsed += 100
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)

    async def test_new_boot_uses_only_remaining_budget_and_boot_uptime(self):
        await self.arm()
        self.elapsed += 100
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 200)
        self.boot = "controlled-boot-b"
        self.elapsed = 20
        self.now += 99999
        self.auth = self.make_auth()
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 180)
        self.elapsed += 179
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 1)
        self.elapsed += 1
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)

    async def test_unknown_boot_fallback_is_bounded_after_elapsed_regression(self):
        self.boot = None
        await self.arm()
        self.elapsed += 80
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 220)
        self.elapsed = 10
        self.auth = self.make_auth()
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 210)
        self.elapsed += 210
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 0)

    async def test_malformed_and_busy_checks_do_not_count(self):
        for value in ("", "12", "a123", "１２３４", "12345"):
            self.assertEqual(
                (await self.auth.login(value)).status, AuthStatus.INVALID_PIN
            )
        self.assertEqual(self.stored().attempts.failed_attempts, 0)
        async with self.auth._operation_lock:
            self.assertEqual((await self.auth.login("9999")).status, AuthStatus.BUSY)
        self.assertEqual(self.stored().attempts.failed_attempts, 0)

    async def test_login_and_repeat_pin_share_counter_and_deadline(self):
        await self.protection.unlock("0123", self.stored())
        await self.auth.login("9999")
        for _ in range(2):
            with self.assertRaises(DataProtectionError):
                await self.protection.begin_recovery_code("9999")
        self.assertEqual(self.stored().attempts.failed_attempts, 3)
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 300)
        with self.assertRaises(DataProtectionError):
            await self.protection.begin_recovery_code("0123")
        self.assertEqual((await self.auth.login("0123")).status, AuthStatus.LOCKED)
        self.elapsed += 300
        issue = await self.protection.begin_recovery_code("0123")
        self.assertTrue(issue.code)
        self.assertEqual(self.stored().attempts.failed_attempts, 0)

    async def test_repeat_malformed_does_not_invoke_kdf_or_count(self):
        await self.protection.unlock("0123", self.stored())
        with patch.object(
            self.hasher,
            "verify",
            side_effect=AssertionError("no cryptographic PIN check"),
        ):
            for value in ("", "12", "a123", "１２３４"):
                with self.assertRaises(DataProtectionError):
                    await self.protection.begin_recovery_code(value)
        self.assertEqual(self.stored().attempts.failed_attempts, 0)

    async def test_shared_gate_stops_correct_login_racing_third_repeat_failure(self):
        await self.protection.unlock("0123", self.stored())
        for _ in range(2):
            await self.auth.login("9999")
        entered, release = threading.Event(), threading.Event()
        verify = self.hasher.verify

        def blocked(pin, record):
            entered.set()
            release.wait(5)
            return verify(pin, record)

        with patch.object(self.hasher, "verify", side_effect=blocked):
            wrong = asyncio.create_task(self.protection.begin_recovery_code("9999"))
            await asyncio.to_thread(entered.wait, 3)
            try:
                self.assertEqual(
                    (await self.auth.login("0123")).status, AuthStatus.BUSY
                )
            finally:
                release.set()
            with self.assertRaises(DataProtectionError):
                await wrong
        self.storage.read_keys.clear()
        self.assertEqual((await self.auth.login("0123")).status, AuthStatus.LOCKED)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_schema_and_initialization_evidence_do_not_change(self):
        from storage.encryption_initialization import plaintext_evidence

        with sqlite3.connect(self.database.path) as connection:
            before = list(
                connection.execute("SELECT sql FROM sqlite_master ORDER BY name")
            )
        digest = plaintext_evidence(self.database.path)
        await self.arm()
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(
                list(connection.execute("SELECT sql FROM sqlite_master ORDER BY name")),
                before,
            )
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 6)
            self.assertEqual(
                connection.execute(
                    "SELECT typeof(locked_until),failed_attempts FROM auth_state"
                ).fetchone(),
                ("text", 3),
            )
        self.assertEqual(plaintext_evidence(self.database.path), digest)

    async def test_legacy_failure_api_cannot_bypass_versioned_lock(self):
        await self.arm()
        with self.assertRaises(ValueError):
            self.database.register_failed_attempt(self.now + 9999999, 5, 30)
        self.assertEqual(await self.auth.pin_lock_seconds_remaining(), 300)

    async def test_recovery_code_policy_and_grant_ttl_remain_separate(self):
        from storage.recovery_code import (
            LOCK_SECONDS,
            MAX_FAILED_ATTEMPTS,
            PROOF_TTL_SECONDS,
        )

        self.assertEqual((APP_PIN_MAX_FAILED_ATTEMPTS, APP_PIN_LOCK_SECONDS), (3, 300))
        self.assertEqual(
            (MAX_FAILED_ATTEMPTS, LOCK_SECONDS, PROOF_TTL_SECONDS), (5, 30, 300)
        )
