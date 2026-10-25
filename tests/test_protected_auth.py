"""Настоящий AuthService сохраняет защищённые данные при смене способа входа."""

from __future__ import annotations

import sys

# ruff: noqa: E402
import unittest
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthStatus, InitialRoute
from auth.service import AuthService
from platform_security.device_recovery import DeviceRecovery
from storage.data_protection import DATA_BINDING_ALIAS, DATA_KEY_ALIAS
from storage.secure_credentials import API_KEY_STORAGE_NAME, FletSecureCredentials
from tests.test_data_protection import ProtectionFixture, Provider
from tests.test_message_sending import FakeKeyValidator


class ProtectedAuthTests(ProtectionFixture):
    async def asyncSetUp(self):
        self.credentials = FletSecureCredentials(self.storage)
        await self.credentials.save_credentials(
            "synthetic-old-api", "fixture-registration"
        )
        self.auth = AuthService(
            FakeKeyValidator(),
            self.credentials,
            self.database,
            pin_hasher=self.hasher,
            protection=self.protection,
            recovery_provider=cast(DeviceRecovery, Provider()),
        )

    async def test_locked_reset_and_new_key_cannot_bypass_existing_pin(self):
        self.assertEqual(
            (await self.auth.login("0123")).status, AuthStatus.AUTHENTICATED
        )
        self.auth.lock_access()
        self.storage.read_keys.clear()
        before = dict(self.storage.values)
        self.assertEqual(
            (await self.auth.reset_authentication()).status, AuthStatus.INVALID_STATE
        )
        self.assertEqual(
            (await self.auth.start_setup("synthetic-new-api")).status,
            AuthStatus.PIN_REQUIRED,
        )
        self.assertEqual(self.storage.values, before)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(self.access.unlocked)

    async def test_authorized_api_replacement_keeps_pin_binding_and_dek(self):
        await self.auth.login("0123")
        key = self.storage.values[DATA_KEY_ALIAS]
        binding = self.storage.values[DATA_BINDING_ALIAS]
        pin = self.stored()
        self.assertEqual(
            (await self.auth.reset_authentication()).status, AuthStatus.SETUP_REQUIRED
        )
        self.assertFalse(self.access.unlocked)
        replaced = await self.auth.start_setup("synthetic-new-api")
        self.assertEqual(replaced.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(self.stored(), pin)
        self.assertEqual(self.storage.values[DATA_KEY_ALIAS], key)
        self.assertEqual(self.storage.values[DATA_BINDING_ALIAS], binding)
        self.auth.lock_access()
        result = await self.auth.login("0123")
        self.assertEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(result.api_key, "synthetic-new-api")

    async def test_api_loss_does_not_automatically_clear_auth_or_data_key(self):
        await self.auth.login("0123")
        self.auth.lock_access()
        self.storage.values.pop(API_KEY_STORAGE_NAME)
        before = dict(self.storage.values)
        state = self.stored()
        result = await self.auth.initialize()
        self.assertEqual(result.initial_route, InitialRoute.ERROR)
        self.assertEqual(self.storage.values, before)
        self.assertEqual(self.stored(), state)
        self.assertFalse(self.access.unlocked)

    async def test_native_recovery_keeps_api_and_new_pin_survives_restart(self):
        await self.auth.login("0123")
        self.auth.lock_access()
        result = await self.auth.recover_pin()
        assert result.pending_setup_token is not None
        self.assertEqual(result.status, AuthStatus.PIN_CHOICE_REQUIRED)
        self.assertFalse(self.access.unlocked)
        completed = await self.auth.complete_recovery(
            "4567", result.pending_setup_token
        )
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(completed.api_key, "synthetic-old-api")
        self.auth.lock_access()
        self.assertEqual((await self.auth.login("0123")).status, AuthStatus.INVALID_PIN)
        self.assertEqual(
            (await self.auth.login("4567")).status, AuthStatus.AUTHENTICATED
        )

    async def test_device_recovery_restores_protected_registration_after_sql_tamper(
        self,
    ):
        await self.auth.login("0123")
        self.auth.lock_access()
        self.database.save_auth_state(
            "tampered-registration", self.hasher.create_record("9999")
        )
        result = await self.auth.recover_pin()
        assert result.pending_setup_token is not None
        completed = await self.auth.complete_recovery(
            "4567", result.pending_setup_token
        )
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(self.stored().registration_id, "fixture-registration")
        self.auth.lock_access()
        self.assertEqual((await self.auth.initialize()).initial_route, InitialRoute.PIN)
        self.assertEqual(
            (await self.auth.login("4567")).status, AuthStatus.AUTHENTICATED
        )
        self.assertEqual(await self.credentials.get_api_key(), "synthetic-old-api")

    async def test_sql_registration_changed_during_pin_choice_does_not_replace_secure_identity(
        self,
    ):
        await self.auth.login("0123")
        self.auth.lock_access()
        result = await self.auth.recover_pin()
        assert result.pending_setup_token is not None
        self.database.save_auth_state(
            "later-tampered-registration", self.hasher.create_record("9999")
        )
        completed = await self.auth.complete_recovery(
            "4567", result.pending_setup_token
        )
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(self.stored().registration_id, "fixture-registration")
        self.auth.lock_access()
        self.assertEqual(
            (await self.auth.login("4567")).status, AuthStatus.AUTHENTICATED
        )

    async def test_setup_key_failure_does_not_rollback_completed_auth(self):
        self.database.clear_auth_data()
        await self.credentials.delete_credentials()
        initial = await self.auth.start_setup("synthetic-first-api")
        assert initial.pending_setup_token is not None
        self.storage.fail_set_key = DATA_KEY_ALIAS
        result = await self.auth.complete_setup("4567", initial.pending_setup_token)
        self.assertEqual(result.status, AuthStatus.STORAGE_ERROR)
        self.assertIsNotNone(self.database.get_auth_state())
        self.assertTrue((await self.credentials.inspect_state()).complete)
        self.assertIn(DATA_BINDING_ALIAS, self.storage.values)
        self.assertFalse(self.access.unlocked)


if __name__ == "__main__":
    unittest.main()
