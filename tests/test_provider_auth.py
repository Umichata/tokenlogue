"""VSEGPT-only registration, PIN and recovery with fake secure storage."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.models import (  # noqa: E402
    AuthStatus,
    InitialRoute,
    KeyLimitState,
    KeyValidityState,
)
from auth.pin import PinHasher  # noqa: E402
from auth.service import AuthService  # noqa: E402
from providers.models import ProviderId  # noqa: E402
from storage.data_access import DataAccess  # noqa: E402
from storage.data_protection import DATA_KEY_ALIAS, DataProtection  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests.test_auth_service import StubValidator  # noqa: E402
from tests.test_secure_credentials import FakeSecureStorage  # noqa: E402

KEY = "sk-or-vv-offline-auth-only-fixture"


class VsegptOnlyAuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = AuthDatabase(temporary.name)
        self.storage = FakeSecureStorage()
        self.credentials = FletSecureCredentials(self.storage)
        self.hasher = PinHasher(iterations=1000)
        self.access = DataAccess()
        self.protection = DataProtection(
            self.database.path,
            self.database,
            self.storage,
            self.access,
            pin_hasher=self.hasher,
        )
        self.validator = StubValidator(
            KeyValidationResult(
                KeyValidationStatus.UNVERIFIED, provider_id=ProviderId.VSEGPT
            )
        )
        self.service = AuthService(
            self.validator,
            self.credentials,
            self.database,
            pin_hasher=self.hasher,
            protection=self.protection,
        )
        self.addCleanup(self.service.lock_access)

    async def register(self):
        setup = await self.service.start_setup(KEY, allow_unverified=True)
        self.assertEqual(setup.status, AuthStatus.PIN_CHOICE_REQUIRED)
        self.assertEqual(setup.key_validity, KeyValidityState.UNVERIFIED)
        self.assertEqual(setup.key_limit.state, KeyLimitState.UNKNOWN)
        token = setup.pending_setup_token
        assert token is not None
        result = await self.service.complete_setup("0123", token)
        self.assertEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertTrue(self.access.unlocked)
        return result

    async def test_unverified_choice_is_required_before_pin_or_secure_persistence(self):
        result = await self.service.start_setup(KEY)
        self.assertEqual(result.status, AuthStatus.UNVERIFIED_KEY)
        self.assertIsNone(self.database.get_auth_state())
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        await self.register()
        self.assertEqual(
            await self.credentials.get_provider_key(ProviderId.VSEGPT), KEY
        )
        self.assertIsNone(
            await self.credentials.get_provider_key(ProviderId.OPENROUTER)
        )
        self.assertEqual(
            await self.credentials.get_default_provider(), ProviderId.VSEGPT
        )

    async def test_temporarily_unavailable_check_retains_error_then_explicit_unverified_setup(
        self,
    ):
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.TIMEOUT, provider_id=ProviderId.VSEGPT
        )
        result = await self.service.start_setup(KEY)
        self.assertEqual(result.status, AuthStatus.UNVERIFIED_KEY)
        self.assertIsNone(result.pending_setup_token)
        await self.register()
        self.assertEqual(self.validator.calls, 2)

    async def test_vsegpt_only_pin_lock_and_unlock_do_not_require_openrouter_or_network(
        self,
    ):
        await self.register()
        state = self.database.get_auth_state()
        assert state is not None
        registration_id = state.registration_id
        key_record = self.storage.values[DATA_KEY_ALIAS]
        calls = self.validator.calls
        self.service.lock_access()
        self.assertFalse(self.access.unlocked)
        self.assertEqual(
            (await self.service.initialize()).initial_route, InitialRoute.PIN
        )
        self.assertEqual(
            (await self.service.login("9999")).status, AuthStatus.INVALID_PIN
        )
        self.assertFalse(self.access.unlocked)
        result = await self.service.login("0123")
        self.assertEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(result.api_key, KEY)
        self.assertTrue(self.access.unlocked)
        self.assertEqual(self.validator.calls, calls)
        self.assertEqual(self.storage.values[DATA_KEY_ALIAS], key_record)
        current = self.database.get_auth_state()
        assert current is not None
        self.assertEqual(current.registration_id, registration_id)
        self.assertIsNone(
            await self.credentials.get_provider_key(ProviderId.OPENROUTER)
        )

    async def test_vsegpt_only_recovery_code_replaces_pin_without_changing_provider_key(
        self,
    ):
        await self.register()
        state = self.database.get_auth_state()
        assert state is not None
        registration_id = state.registration_id
        issued = await self.service.begin_recovery_code("0123")
        self.assertEqual(issued.status, AuthStatus.RECOVERY_CODE_ISSUED)
        issue = issued.recovery_code_issue
        assert issue is not None
        self.assertNotIn(issue.code, repr(issued))
        saved = await self.service.confirm_recovery_code(issue.attempt_id, issue.code)
        self.assertEqual(saved.status, AuthStatus.RECOVERY_CODE_SAVED)
        self.service.lock_access()
        recovered = await self.service.recover_with_code(issue.code)
        self.assertEqual(recovered.status, AuthStatus.PIN_CHOICE_REQUIRED)
        token = recovered.pending_setup_token
        assert token is not None
        completed = await self.service.complete_recovery("4567", token)
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(completed.api_key, KEY)
        self.service.lock_access()
        self.assertEqual(
            (await self.service.login("0123")).status, AuthStatus.INVALID_PIN
        )
        self.assertEqual(
            (await self.service.login("4567")).status, AuthStatus.AUTHENTICATED
        )
        current = self.database.get_auth_state()
        assert current is not None
        self.assertEqual(current.registration_id, registration_id)
        self.assertEqual(
            await self.credentials.get_provider_key(ProviderId.VSEGPT), KEY
        )
        self.assertIsNone(
            await self.credentials.get_provider_key(ProviderId.OPENROUTER)
        )

    async def test_known_invalid_vsegpt_key_cannot_be_saved_even_with_unverified_choice(
        self,
    ):
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.INVALID, provider_id=ProviderId.VSEGPT
        )
        rejected = await self.service.start_setup(KEY, allow_unverified=True)
        self.assertEqual(rejected.status, AuthStatus.INVALID_KEY)
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        self.assertIsNone(self.database.get_auth_state())
