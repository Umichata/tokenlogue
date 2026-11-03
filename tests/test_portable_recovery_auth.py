"""Сервис аутентификации использует настоящий координатор с тестовым storage."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.models import AuthStatus  # noqa: E402
from auth.service import AuthService  # noqa: E402
from platform_security.device_recovery import RecoveryProvider  # noqa: E402
from storage.data_protection import (  # noqa: E402
    DATA_BINDING_ALIAS,
    DATA_KEY_ALIAS,
    DataProtectionError,
)
from storage.secure_credentials import (  # noqa: E402
    API_KEY_STORAGE_NAME,
    FletSecureCredentials,
)
from tests.test_auth_service import StubValidator  # noqa: E402
from tests.test_data_protection import ProtectionFixture, Provider  # noqa: E402


class PortableRecoveryAuthTests(ProtectionFixture):
    def service(self):
        self.storage.values[API_KEY_STORAGE_NAME] = "synthetic-offline-credential"
        return AuthService(
            StubValidator(
                KeyValidationResult(KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT)
            ),
            FletSecureCredentials(self.storage),
            self.database,
            pin_hasher=self.hasher,
            protection=self.protection,
        )

    async def test_closed_profile_cannot_issue_code_or_read_dek(self):
        await self.enroll()
        service = self.service()
        result = await service.begin_recovery_code("0123")
        self.assertEqual(result.status, AuthStatus.STORAGE_ERROR)
        self.assertIsNone(result.recovery_code_issue)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(await service.recovery_code_enrolled())

    async def test_storage_error_is_not_reported_as_unenrolled(self):
        await self.enroll()
        service = self.service()
        marker = "synthetic-private-backend-error"
        with patch.object(self.storage, "get", side_effect=RuntimeError(marker)):
            with self.assertRaises(DataProtectionError) as failure:
                await service.recovery_code_enrolled()
        self.assertTrue(
            marker not in str(failure.exception), "backend detail sanitized"
        )
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_concurrent_issue_is_busy_and_cancel_revokes_result(self):
        service = self.service()
        await service.login("0123")
        started, release = asyncio.Event(), asyncio.Event()
        original_begin = self.protection.begin_recovery_code

        async def delayed_begin(pin):
            started.set()
            await release.wait()
            return await original_begin(pin)

        with patch.object(
            self.protection, "begin_recovery_code", side_effect=delayed_begin
        ):
            pending = asyncio.create_task(service.begin_recovery_code("0123"))
            await started.wait()
            duplicate = await service.begin_recovery_code("0123")
            self.assertEqual(duplicate.status, AuthStatus.BUSY)
            release.set()
            issued = await pending
        issue = issued.recovery_code_issue
        assert issue is not None
        service.cancel_recovery_code_issue()
        stale = await service.confirm_recovery_code(issue.attempt_id, issue.code)
        self.assertEqual(stale.status, AuthStatus.STORAGE_ERROR)
        self.assertFalse(await service.recovery_code_enrolled())

    async def test_lock_during_system_reconcile_never_starts_a_new_proof(self):
        await self.enroll()
        service = self.service()
        provider = Provider()
        service._recovery_provider = cast(RecoveryProvider, provider)
        entered, release = asyncio.Event(), asyncio.Event()
        original_get = self.storage.get
        held = False

        async def blocked_binding(key):
            nonlocal held
            result = await original_get(key)
            if key == DATA_BINDING_ALIAS and not held:
                held = True
                entered.set()
                await release.wait()
            return result

        self.storage.read_keys.clear()
        with patch.object(self.storage, "get", side_effect=blocked_binding):
            pending = asyncio.create_task(service.recover_pin())
            await entered.wait()
            service.lock_access()
            release.set()
            result = await pending
        self.assertEqual(result.status, AuthStatus.STORAGE_ERROR)
        self.assertFalse(provider.started.is_set(), "stale attempt did not start proof")
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_real_service_code_proof_uses_common_pin_replacement(self):
        service = self.service()
        login = await service.login("0123")
        self.assertEqual(login.status, AuthStatus.AUTHENTICATED)
        issued = await service.begin_recovery_code("0123")
        self.assertEqual(issued.status, AuthStatus.RECOVERY_CODE_ISSUED)
        issue = issued.recovery_code_issue
        self.assertIsNotNone(issue)
        assert issue is not None
        self.assertTrue(issue.code not in repr(issued), "result repr is secret-free")
        confirmed = await service.confirm_recovery_code(issue.attempt_id, issue.code)
        self.assertEqual(confirmed.status, AuthStatus.RECOVERY_CODE_SAVED)
        service.lock_access()
        self.storage.read_keys.clear()
        rejected = await service.recover_with_code(issue.code[:-1])
        self.assertEqual(rejected.status, AuthStatus.STORAGE_ERROR)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        recovered = await service.recover_with_code(issue.code)
        self.assertEqual(recovered.status, AuthStatus.PIN_CHOICE_REQUIRED)
        self.assertFalse(self.access.unlocked)
        token = recovered.pending_setup_token
        assert token is not None
        completed = await service.complete_recovery("4567", token)
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        self.assertTrue(self.access.unlocked)
        self.assertFalse(await service.recovery_code_enrolled())


if __name__ == "__main__":
    unittest.main()
