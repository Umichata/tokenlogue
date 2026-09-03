"""Офлайн-тесты сценариев локальной аутентификации."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import (  # noqa: E402
    AuthStatus,
    CredentialState,
    InitialRoute,
    KeyLimitState,
    KeyValidityState,
)
from auth.pin import PinHasher  # noqa: E402
from auth.service import AuthService  # noqa: E402
from chat.models import Chat, ChatMode  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402

TEST_CREDENTIAL = "unit-test-credential"


class StubValidator:
    def __init__(self, result: KeyValidationResult) -> None:
        self.result = result
        self.calls = 0

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        _ = api_key
        self.calls += 1
        return self.result


class BlockingValidator(StubValidator):
    def __init__(self, result: KeyValidationResult) -> None:
        super().__init__(result)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        _ = api_key
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return self.result


class MemoryCredentials:
    def __init__(self) -> None:
        self.api_key: str | None = None
        self.registration_id: str | None = None
        self.get_calls = 0
        self.fail_save_after_write = False
        self.fail_delete = False

    async def inspect_state(self) -> CredentialState:
        return CredentialState(
            has_api_key=self.api_key is not None,
            registration_id=self.registration_id,
        )

    async def save_credentials(self, api_key: str, registration_id: str) -> None:
        self.api_key = api_key
        self.registration_id = registration_id
        if self.fail_save_after_write:
            raise RuntimeError("injected storage failure")

    async def get_api_key(self) -> str | None:
        self.get_calls += 1
        return self.api_key

    async def delete_credentials(self) -> None:
        if self.fail_delete:
            raise RuntimeError("injected delete failure")
        self.api_key = None
        self.registration_id = None


class MutableClock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database = AuthDatabase(self.temp_dir.name)
        self.credentials = MemoryCredentials()
        self.clock = MutableClock(1_000.0)
        self.validator = StubValidator(_accepted_key())
        self.hasher = PinHasher(
            iterations=1_000,
            randbelow=lambda _: 7,
            token_bytes=lambda size: bytes(range(size)),
        )
        self.service = self._new_service()

    def _new_service(self, validator: KeyValidator | None = None) -> AuthService:
        return AuthService(
            validator if validator is not None else self.validator,
            self.credentials,
            self.database,
            pin_hasher=self.hasher,
            clock=self.clock,
        )

    async def _complete_setup(self) -> str:
        setup = await self.service.start_setup(TEST_CREDENTIAL)
        self.assertIsNotNone(setup.pin)
        pin = setup.pin or ""
        completed = await self.service.complete_setup()
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        return pin

    async def test_setup_preserves_leading_zero_and_waits_for_confirmation(
        self,
    ) -> None:
        setup = await self.service.start_setup(TEST_CREDENTIAL)

        self.assertEqual(setup.status, AuthStatus.PIN_CREATED)
        self.assertIsNotNone(setup.pin)
        self.assertEqual(len(setup.pin or ""), 4)
        self.assertTrue((setup.pin or "").startswith("0"))
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        self.assertIsNone(self.database.get_auth_state())

        completed = await self.service.complete_setup()

        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        secure_state = await self.credentials.inspect_state()
        stored = self.database.get_auth_state()
        self.assertTrue(secure_state.complete)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.registration_id, secure_state.registration_id)

    async def test_login_reads_key_only_after_correct_pin(self) -> None:
        pin = await self._complete_setup()
        restarted_service = self._new_service()

        initial = await restarted_service.initialize()
        self.assertEqual(initial.initial_route, InitialRoute.PIN)
        validation_calls_before_login = self.validator.calls
        wrong = await restarted_service.login("9999")
        self.assertEqual(wrong.status, AuthStatus.INVALID_PIN)
        self.assertEqual(self.credentials.get_calls, 0)
        self.assertEqual(self.validator.calls, validation_calls_before_login)

        correct = await restarted_service.login(pin)
        self.assertEqual(correct.status, AuthStatus.AUTHENTICATED)
        self.assertIsNotNone(correct.api_key)
        self.assertEqual(self.credentials.get_calls, 1)
        self.assertEqual(self.validator.calls, validation_calls_before_login)
        self.assertEqual(correct.key_validity, KeyValidityState.UNKNOWN)
        self.assertEqual(correct.key_limit.state, KeyLimitState.UNKNOWN)

    async def test_reset_authentication_preserves_local_chats(self) -> None:
        await self._complete_setup()
        repository = SqliteChatRepository(self.database.path)
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        repository.create_chat(
            Chat(
                id="chat-preserved-on-reset",
                title="Новый чат",
                mode=ChatMode.FREE,
                requested_model_id="openrouter/free",
                requested_model_name="Автоматический выбор бесплатной модели",
                prompt_price_per_token=Decimal("0"),
                completion_price_per_token=Decimal("0"),
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

        result = await self.service.reset_authentication()

        self.assertEqual(result.status, AuthStatus.SETUP_REQUIRED)
        self.assertEqual(
            [chat.id for chat in repository.list_chats()],
            ["chat-preserved-on-reset"],
        )

    async def test_fifth_failure_locks_for_thirty_seconds_across_restart(self) -> None:
        pin = await self._complete_setup()

        result = None
        for _ in range(5):
            result = await self.service.login("9999")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, AuthStatus.LOCKED)
        self.assertEqual(result.lock_seconds_remaining, 30)

        self.database = AuthDatabase(self.temp_dir.name)
        restarted_service = self._new_service()
        initial = await restarted_service.initialize()
        self.assertEqual(initial.lock_seconds_remaining, 30)
        blocked = await restarted_service.login(pin)
        self.assertEqual(blocked.status, AuthStatus.LOCKED)
        self.assertEqual(self.credentials.get_calls, 0)

        self.clock.value += 31
        allowed = await restarted_service.login(pin)
        self.assertEqual(allowed.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(self.credentials.get_calls, 1)

    async def test_backward_clock_jump_cannot_extend_lock(self) -> None:
        pin = await self._complete_setup()
        for _ in range(5):
            await self.service.login("9999")

        self.clock.value -= 3_600
        restarted_service = self._new_service()

        initial = await restarted_service.initialize()
        self.assertEqual(initial.lock_seconds_remaining, 0)
        allowed = await restarted_service.login(pin)
        self.assertEqual(allowed.status, AuthStatus.AUTHENTICATED)

    async def test_registration_id_mismatch_clears_both_stores(self) -> None:
        await self._complete_setup()
        self.credentials.registration_id = "different-registration"

        result = await self._new_service().initialize()

        self.assertEqual(result.initial_route, InitialRoute.SETUP)
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        self.assertIsNone(self.database.get_auth_state())

    async def test_partial_secure_storage_failure_rolls_back_registration(self) -> None:
        setup = await self.service.start_setup(TEST_CREDENTIAL)
        self.assertIsNotNone(setup.pin)
        self.credentials.fail_save_after_write = True

        result = await self.service.complete_setup()

        self.assertEqual(result.status, AuthStatus.STORAGE_ERROR)
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        self.assertIsNone(self.database.get_auth_state())

    async def test_partial_reset_is_recovered_on_next_start(self) -> None:
        await self._complete_setup()
        self.credentials.fail_delete = True

        failed_reset = await self.service.reset_authentication()

        self.assertEqual(failed_reset.status, AuthStatus.STORAGE_ERROR)
        self.assertIsNone(self.database.get_auth_state())
        self.assertTrue((await self.credentials.inspect_state()).has_artifacts)

        self.credentials.fail_delete = False
        recovered = await self._new_service().initialize()
        self.assertEqual(recovered.initial_route, InitialRoute.SETUP)
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)

    async def test_concurrent_key_check_is_rejected_without_second_request(
        self,
    ) -> None:
        validator = BlockingValidator(_accepted_key())
        service = self._new_service(validator)

        first = asyncio.create_task(service.start_setup(TEST_CREDENTIAL))
        await validator.started.wait()
        second = await service.start_setup(TEST_CREDENTIAL)
        validator.release.set()
        first_result = await first

        self.assertEqual(second.status, AuthStatus.BUSY)
        self.assertEqual(first_result.status, AuthStatus.PIN_CREATED)
        self.assertEqual(validator.calls, 1)

    async def test_reset_removes_both_authentication_stores(self) -> None:
        await self._complete_setup()

        reset = await self.service.reset_authentication()

        self.assertEqual(reset.status, AuthStatus.SETUP_REQUIRED)
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        self.assertIsNone(self.database.get_auth_state())

    async def test_pin_only_state_is_cleared_safely(self) -> None:
        record = self.hasher.create_record("1234")
        self.database.save_auth_state("database-only", record)

        result = await self.service.initialize()

        self.assertEqual(result.initial_route, InitialRoute.SETUP)
        self.assertIsNone(self.database.get_auth_state())

    async def test_key_only_state_is_cleared_safely(self) -> None:
        await self.credentials.save_credentials(TEST_CREDENTIAL, "secure-only")

        result = await self.service.initialize()

        self.assertEqual(result.initial_route, InitialRoute.SETUP)
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)

    async def test_null_limit_is_accepted_with_notice(self) -> None:
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT
        )

        result = await self.service.start_setup(TEST_CREDENTIAL)

        self.assertEqual(result.status, AuthStatus.PIN_CREATED)
        self.assertIsNotNone(result.pin)
        self.assertEqual(result.key_validity, KeyValidityState.VALID)
        self.assertEqual(result.key_limit.state, KeyLimitState.NOT_SET)
        self.assertIsNone(result.key_limit.remaining)
        self.assertNotIn("положитель", result.message.casefold())
        self.assertNotIn("баланс", result.message.casefold())

    async def test_zero_limit_key_can_complete_registration(self) -> None:
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
            limit_remaining=Decimal("0"),
        )

        result = await self.service.start_setup(TEST_CREDENTIAL)
        completed = await self.service.complete_setup()

        self.assertEqual(result.status, AuthStatus.PIN_CREATED)
        self.assertIsNotNone(result.pin)
        self.assertEqual(result.key_validity, KeyValidityState.VALID)
        self.assertEqual(result.key_limit.state, KeyLimitState.EXHAUSTED)
        self.assertIn("Бесплатный режим остаётся доступным", result.message)
        self.assertEqual(completed.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(completed.key_validity, KeyValidityState.VALID)
        self.assertEqual(completed.key_limit.state, KeyLimitState.EXHAUSTED)
        self.assertTrue((await self.credentials.inspect_state()).complete)
        self.assertIsNotNone(self.database.get_auth_state())

    async def test_positive_limit_is_available_key_limit_not_balance(self) -> None:
        result = await self.service.start_setup(TEST_CREDENTIAL)

        self.assertEqual(result.status, AuthStatus.PIN_CREATED)
        self.assertEqual(result.key_validity, KeyValidityState.VALID)
        self.assertEqual(result.key_limit.state, KeyLimitState.AVAILABLE)
        self.assertEqual(result.key_limit.remaining, Decimal("5"))
        self.assertIn("Доступный лимит ключа", result.message)
        self.assertNotIn("баланс", result.message.casefold())

    async def test_login_does_not_wait_for_slow_key_validation(self) -> None:
        pin = await self._complete_setup()
        blocking_validator = BlockingValidator(_accepted_key())

        result = await asyncio.wait_for(
            self._new_service(blocking_validator).login(pin),
            timeout=0.2,
        )

        self.assertEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(result.key_validity, KeyValidityState.UNKNOWN)
        self.assertEqual(result.key_limit.state, KeyLimitState.UNKNOWN)
        self.assertEqual(blocking_validator.calls, 0)
        self.assertFalse(blocking_validator.started.is_set())

    async def test_401_after_pin_does_not_delete_local_data(self) -> None:
        await self._assert_stored_network_status_preserves_auth(
            KeyValidationStatus.INVALID,
            "chat-preserved-after-401",
        )

    async def test_403_after_pin_does_not_delete_local_data(self) -> None:
        await self._assert_stored_network_status_preserves_auth(
            KeyValidationStatus.RESTRICTED,
            "chat-preserved-after-403",
        )

    async def test_primary_401_and_403_do_not_create_registration(self) -> None:
        for status in (KeyValidationStatus.INVALID, KeyValidationStatus.RESTRICTED):
            with self.subTest(status=status):
                self.validator.result = KeyValidationResult(status)

                result = await self.service.start_setup(TEST_CREDENTIAL)

                self.assertEqual(result.status, AuthStatus.INVALID_KEY)
                self.assertIsNone(result.pin)
                self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
                self.assertIsNone(self.database.get_auth_state())

    async def _assert_stored_network_status_preserves_auth(
        self,
        status: KeyValidationStatus,
        chat_id: str,
    ) -> None:
        pin = await self._complete_setup()
        repository = SqliteChatRepository(self.database.path)
        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        repository.create_chat(
            Chat(
                id=chat_id,
                title="Новый чат",
                mode=ChatMode.FREE,
                requested_model_id="openrouter/free",
                requested_model_name="Автоматический выбор бесплатной модели",
                prompt_price_per_token=Decimal("0"),
                completion_price_per_token=Decimal("0"),
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        validation_calls = self.validator.calls
        self.validator.result = KeyValidationResult(status)

        result = await self._new_service().login(pin)

        self.assertEqual(result.status, AuthStatus.AUTHENTICATED)
        self.assertEqual(result.key_validity, KeyValidityState.UNKNOWN)
        self.assertTrue((await self.credentials.inspect_state()).complete)
        self.assertIsNotNone(self.database.get_auth_state())
        self.assertEqual(self.validator.calls, validation_calls)
        self.assertEqual(
            [chat.id for chat in repository.list_chats()],
            [chat_id],
        )

    async def test_pin_records_use_unique_salts_and_versioned_parameters(self) -> None:
        salts = iter((b"a" * 16, b"b" * 16))
        hasher = PinHasher(iterations=1_000, token_bytes=lambda _: next(salts))

        first = hasher.create_record("1234")
        second = hasher.create_record("1234")

        self.assertNotEqual(first.salt, second.salt)
        self.assertEqual(first.version, 1)
        self.assertEqual(first.algorithm, "pbkdf2_hmac_sha256")
        self.assertEqual(first.iterations, 1_000)


def _accepted_key() -> KeyValidationResult:
    return KeyValidationResult(
        KeyValidationStatus.ACCEPTED,
        limit_remaining=Decimal("5"),
    )


if __name__ == "__main__":
    unittest.main()
