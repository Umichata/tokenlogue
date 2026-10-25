"""Сценарии первого запуска, PIN-входа и сброса доступа."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from api.openrouter import KeyValidationStatus
from auth.contracts import AuthRepository, CredentialStore, KeyValidator
from auth.key_validation import interpret_key_validation
from auth.models import (
    AuthResult,
    AuthStatus,
    CredentialState,
    InitialRoute,
    KeyLimitInfo,
    KeyLimitState,
    KeyValidityState,
    StoredAuthState,
)
from auth.pin import PinHasher, is_valid_pin
from i18n import number, tr

if TYPE_CHECKING:
    from platform_security.device_recovery import DeviceRecovery
    from storage.data_protection import DataProtection

MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 30
REGISTRATION_ID_BYTES = 24


class AuthService:
    """Координирует API, SecureStorage и SQLite без зависимости от UI."""

    def __init__(
        self,
        key_validator: KeyValidator,
        credentials: CredentialStore,
        repository: AuthRepository,
        *,
        pin_hasher: PinHasher | None = None,
        clock: Callable[[], float] = time.time,
        protection: DataProtection | None = None,
        recovery_provider: DeviceRecovery | None = None,
    ) -> None:
        self._key_validator = key_validator
        self._credentials = credentials
        self._repository = repository
        self._pin_hasher = pin_hasher or PinHasher()
        self._clock = clock
        self._protection = protection
        self._recovery_provider = recovery_provider
        self._operation_lock = asyncio.Lock()
        self._setup_generation = 0
        self._pending_key: str | None = None
        self._pending_registration_id: str | None = None
        self._pending_key_limit = KeyLimitInfo.unknown()

    async def initialize(self) -> AuthResult:
        """Определяет первый экран и исправляет несогласованное состояние."""
        return await self._run_exclusive(self._initialize)

    async def start_setup(self, api_key: str) -> AuthResult:
        """Проверяет ключ и начинает выбор PIN без записи на диск."""
        return await self._run_exclusive(lambda: self._start_setup(api_key))

    def suggest_pin(self) -> str:
        """Предлагает случайный PIN без привязки к регистрации и без сохранения."""
        return self._pin_hasher.generate_pin()

    async def complete_setup(self, pin: str, pending_setup_token: str) -> AuthResult:
        """Связывает выбранный PIN с текущей подтверждаемой регистрацией."""
        return await self._run_exclusive(
            lambda: self._complete_setup(pin, pending_setup_token)
        )

    async def login(self, pin: str) -> AuthResult:
        """Проверяет PIN и получает ключ только после успешной проверки."""
        return await self._run_exclusive(lambda: self._login(pin))

    async def reset_authentication(self) -> AuthResult:
        """Сохраняет PIN при защищённой замене ключа и поддерживает прежний сброс."""
        return await self._run_exclusive(self._reset_authentication)

    @property
    def recovery_available(self) -> bool:
        return self._protection is not None and self._recovery_provider is not None

    @property
    def data_protection_enabled(self) -> bool:
        return self._protection is not None

    @property
    def key_replacement_pending(self) -> bool:
        """Выбирает пояснение формы без выдачи ключа и разрешения на вход."""
        return self._protection is not None and self._protection.replacement_pending

    def lock_access(self) -> None:
        self.cancel_pending_setup()
        if self._protection is not None:
            self._protection.lock()

    async def cancel_recovery(self) -> None:
        if self._protection is not None:
            await self._protection.cancel_recovery()

    async def recover_pin(self) -> AuthResult:
        async def recover() -> AuthResult:
            if self._protection is None or self._recovery_provider is None:
                return _storage_error(tr("protection.recovery_unavailable"))
            try:
                token = await self._protection.recover(self._recovery_provider)
                return AuthResult(
                    AuthStatus.PIN_CHOICE_REQUIRED, pending_setup_token=token
                )
            except Exception as error:
                from storage.data_protection import DataProtectionError

                message = (
                    error.args[0]
                    if isinstance(error, DataProtectionError)
                    else tr("protection.unavailable")
                )
                return _storage_error(message)

        return await self._run_exclusive(recover)

    async def complete_recovery(self, pin: str, token: str) -> AuthResult:
        async def complete() -> AuthResult:
            if self._protection is None or not is_valid_pin(pin):
                return AuthResult(AuthStatus.INVALID_PIN, tr("service.pin_ascii"))
            try:
                await self._protection.replace_pin(token, pin)
                api_key = await self._credentials.get_api_key()
                if not api_key:
                    self._protection.lock()
                    return _storage_error(tr("service.secure_read_failed"))
                return AuthResult(AuthStatus.AUTHENTICATED, api_key=api_key)
            except Exception:
                self._protection.lock()
                return _storage_error(tr("protection.unavailable"))

        return await self._run_exclusive(complete)

    def cancel_pending_setup(self) -> None:
        """Отзывает настройку и удаляет временные ссылки без изменения хранилищ."""
        self._setup_generation += 1
        self._pending_key = None
        self._pending_registration_id = None
        self._pending_key_limit = KeyLimitInfo.unknown()

    async def _initialize(self) -> AuthResult:
        try:
            if self._protection is not None:
                await self._protection.reconcile()
            stored = await asyncio.to_thread(self._repository.get_auth_state)
            credentials = await self._credentials.inspect_state()
        except Exception:
            return _storage_error(
                tr("service.secure_storage_open"),
                initial_route=InitialRoute.ERROR,
            )

        if stored is None and not credentials.has_artifacts:
            if self._protection is not None and await self._protection.has_protection():
                return _storage_error(
                    tr("protection.key_missing"), initial_route=InitialRoute.ERROR
                )
            return AuthResult(
                AuthStatus.SETUP_REQUIRED,
                initial_route=InitialRoute.SETUP,
            )

        if stored is not None and _states_match(stored, credentials):
            remaining = self._remaining_lock_seconds(stored.attempts.locked_until)
            if stored.attempts.locked_until is not None and remaining == 0:
                try:
                    await asyncio.to_thread(self._repository.reset_login_attempts)
                except Exception:
                    return _storage_error(
                        tr("service.lock_save_failed"),
                        initial_route=InitialRoute.ERROR,
                    )
            return AuthResult(
                AuthStatus.PIN_REQUIRED,
                initial_route=InitialRoute.PIN,
                lock_seconds_remaining=remaining,
            )

        return await self._reset_inconsistent_state()

    async def _start_setup(self, api_key: str) -> AuthResult:
        self.cancel_pending_setup()
        generation = self._setup_generation
        normalized_key = api_key.strip()
        if not normalized_key:
            return AuthResult(AuthStatus.INVALID_KEY, tr("service.enter_key"))

        try:
            stored = await asyncio.to_thread(self._repository.get_auth_state)
            credentials = await self._credentials.inspect_state()
        except Exception:
            return _storage_error(tr("service.auth_read_failed"))
        if generation != self._setup_generation:
            return _expired_setup()
        replacing = (
            self._protection is not None and self._protection.replacement_pending
        )
        if not replacing and stored is not None and _states_match(stored, credentials):
            return AuthResult(
                AuthStatus.PIN_REQUIRED,
                tr("service.auth_exists"),
                initial_route=InitialRoute.PIN,
            )
        if not replacing and (stored is not None or credentials.has_artifacts):
            return _expired_setup()
        if (
            not replacing
            and self._protection is not None
            and await self._protection.has_protection()
        ):
            return _storage_error(tr("protection.sign_in_first"))

        try:
            validation = await self._key_validator.validate_key(normalized_key)
        except Exception:
            if generation != self._setup_generation:
                return _expired_setup()
            return AuthResult(AuthStatus.SERVICE_ERROR, tr("service.key_check_failed"))
        if generation != self._setup_generation:
            return _expired_setup()
        if not validation.accepted:
            return _validation_error(validation.status)
        key_validity, key_limit = interpret_key_validation(validation)
        if key_validity is not KeyValidityState.VALID:
            return AuthResult(
                AuthStatus.INVALID_RESPONSE,
                tr("service.response_format"),
            )

        if replacing:
            try:
                assert self._protection is not None
                replace = getattr(self._credentials, "replace_api_key", None)
                if replace is None or not self._protection.replacement_pending:
                    return _expired_setup()
                await replace(normalized_key)
                if generation != self._setup_generation:
                    return _expired_setup()
                self._protection.finish_key_replacement()
                return AuthResult(
                    AuthStatus.AUTHENTICATED,
                    api_key=normalized_key,
                    key_validity=key_validity,
                    key_limit=key_limit,
                )
            except Exception:
                return _storage_error(tr("service.key_save_failed"))

        self._pending_key = normalized_key
        self._pending_registration_id = secrets.token_urlsafe(REGISTRATION_ID_BYTES)
        self._pending_key_limit = key_limit
        return AuthResult(
            AuthStatus.PIN_CHOICE_REQUIRED,
            _validated_key_message(key_limit),
            pending_setup_token=self._pending_registration_id,
            key_validity=key_validity,
            key_limit=key_limit,
        )

    async def _complete_setup(self, pin: str, pending_setup_token: str) -> AuthResult:
        if (
            self._pending_key is None
            or self._pending_registration_id is None
            or pending_setup_token != self._pending_registration_id
            or self._pending_key_limit.state is KeyLimitState.UNKNOWN
        ):
            return _expired_setup()

        if not isinstance(pin, str) or not is_valid_pin(pin):
            return AuthResult(
                AuthStatus.INVALID_PIN,
                tr("service.pin_ascii"),
            )
        generation = self._setup_generation
        api_key = self._pending_key
        registration_id = self._pending_registration_id
        key_limit = self._pending_key_limit
        persistence_started = False
        protection_started = False
        try:
            record = await asyncio.to_thread(self._pin_hasher.create_record, pin)
            if generation != self._setup_generation:
                return _expired_setup()
            # После начала записи завершаем обе части регистрации даже при фоне.
            # Отмена не должна оставлять ключ и verifier от разных регистраций.
            persistence_started = True
            await asyncio.to_thread(
                self._repository.save_auth_state,
                registration_id,
                record,
            )
            try:
                await self._credentials.save_credentials(api_key, registration_id)
            except Exception:
                await self._rollback_setup()
                return _storage_error(tr("service.key_save_failed"))
            if generation != self._setup_generation:
                return _expired_setup()
            if self._protection is not None:
                protection_started = True
                saved = await asyncio.to_thread(self._repository.get_auth_state)
                if saved is None:
                    return _storage_error(tr("protection.unavailable"))
                await self._protection.unlock(pin, saved)
                if generation != self._setup_generation:
                    self._protection.lock()
                    return _expired_setup()
            return AuthResult(
                AuthStatus.AUTHENTICATED,
                tr("service.protection_ready"),
                api_key=api_key,
                key_validity=KeyValidityState.VALID,
                key_limit=key_limit,
            )
        except Exception:
            if persistence_started and not protection_started:
                await self._rollback_setup()
            if generation != self._setup_generation:
                return _expired_setup()
            return _storage_error(tr("service.auth_save_failed"))
        finally:
            self.cancel_pending_setup()

    async def _login(self, pin: str) -> AuthResult:
        if not is_valid_pin(pin):
            return AuthResult(
                AuthStatus.INVALID_PIN,
                tr("service.pin_four"),
            )

        try:
            stored = await asyncio.to_thread(self._repository.get_auth_state)
            if stored is None:
                return await self._reset_inconsistent_state()

            remaining = self._remaining_lock_seconds(stored.attempts.locked_until)
            if remaining > 0:
                return _locked_result(remaining)
            if stored.attempts.locked_until is not None:
                await asyncio.to_thread(self._repository.reset_login_attempts)

            is_correct = await asyncio.to_thread(
                self._pin_hasher.verify,
                pin,
                stored.pin_record,
            )
            if not is_correct:
                return await self._register_failed_attempt()

            credentials = await self._credentials.inspect_state()
            if not _states_match(stored, credentials):
                return await self._reset_inconsistent_state()

            if self._protection is not None:
                await self._protection.unlock(pin, stored)
            api_key = await self._credentials.get_api_key()
            if not api_key:
                if self._protection is not None:
                    self._protection.lock()
                return await self._reset_inconsistent_state()
            await asyncio.to_thread(self._repository.reset_login_attempts)
            return AuthResult(
                AuthStatus.AUTHENTICATED,
                api_key=api_key,
                key_validity=KeyValidityState.UNKNOWN,
                key_limit=KeyLimitInfo.unknown(),
            )
        except Exception:
            if self._protection is not None:
                self._protection.lock()
            return _storage_error(
                tr("protection.unavailable")
                if self._protection
                else tr("service.auth_read_failed")
            )

    async def _register_failed_attempt(self) -> AuthResult:
        attempt_state = await asyncio.to_thread(
            self._repository.register_failed_attempt,
            self._clock(),
            MAX_FAILED_ATTEMPTS,
            LOCK_SECONDS,
        )
        remaining = self._remaining_lock_seconds(attempt_state.locked_until)
        if remaining > 0:
            return _locked_result(remaining)
        attempts_left = max(0, MAX_FAILED_ATTEMPTS - attempt_state.failed_attempts)
        return AuthResult(
            AuthStatus.INVALID_PIN,
            tr("service.wrong_pin", remaining=attempts_left),
        )

    async def _reset_authentication(self) -> AuthResult:
        self.cancel_pending_setup()
        if self._protection is not None:
            if not self._protection.access.unlocked:
                return AuthResult(
                    AuthStatus.INVALID_STATE, tr("protection.sign_in_first")
                )
            self._protection.begin_key_replacement()
            return AuthResult(
                AuthStatus.SETUP_REQUIRED,
                tr("protection.replace_key"),
                initial_route=InitialRoute.SETUP,
            )
        failed = False
        try:
            await self._credentials.delete_credentials()
        except Exception:
            failed = True
        try:
            await asyncio.to_thread(self._repository.clear_auth_data)
        except Exception:
            failed = True

        if failed:
            return _storage_error(tr("service.auth_reset_failed"))
        return AuthResult(
            AuthStatus.SETUP_REQUIRED,
            tr("service.auth_reset_done"),
            initial_route=InitialRoute.SETUP,
        )

    async def _reset_inconsistent_state(self) -> AuthResult:
        if self._protection is not None:
            return _storage_error(
                tr("protection.binding_mismatch"), initial_route=InitialRoute.ERROR
            )
        failed = False
        try:
            await self._credentials.delete_credentials()
        except Exception:
            failed = True
        try:
            await asyncio.to_thread(self._repository.clear_auth_data)
        except Exception:
            failed = True

        if failed:
            return _storage_error(
                tr("service.auth_repair_failed"),
                initial_route=InitialRoute.ERROR,
            )
        return AuthResult(
            AuthStatus.SETUP_REQUIRED,
            tr("service.auth_inconsistent"),
            initial_route=InitialRoute.SETUP,
        )

    async def _rollback_setup(self) -> None:
        try:
            await self._credentials.delete_credentials()
        except Exception:
            pass
        try:
            await asyncio.to_thread(self._repository.clear_auth_data)
        except Exception:
            pass

    async def _run_exclusive(
        self,
        operation: Callable[[], Awaitable[AuthResult]],
    ) -> AuthResult:
        if self._operation_lock.locked():
            return AuthResult(
                AuthStatus.BUSY,
                tr("service.operation_pending"),
            )
        async with self._operation_lock:
            try:
                return await operation()
            except Exception:
                if self._protection is not None:
                    self._protection.lock()
                return _storage_error(
                    tr("service.auth_read_failed"), initial_route=InitialRoute.ERROR
                )

    def _remaining_lock_seconds(self, locked_until: float | None) -> int:
        if locked_until is None or not math.isfinite(locked_until):
            return 0
        difference = locked_until - self._clock()
        if difference <= 0 or difference > LOCK_SECONDS:
            return 0
        return math.ceil(difference)


def _states_match(
    stored: StoredAuthState | None,
    credentials: CredentialState,
) -> bool:
    return (
        stored is not None
        and credentials.complete
        and stored.registration_id == credentials.registration_id
    )


def _locked_result(seconds: int) -> AuthResult:
    return AuthResult(
        AuthStatus.LOCKED,
        tr("auth.lock_seconds", seconds=seconds),
        lock_seconds_remaining=seconds,
    )


def _storage_error(
    message: str,
    *,
    initial_route: InitialRoute | None = None,
) -> AuthResult:
    return AuthResult(
        AuthStatus.STORAGE_ERROR,
        message,
        initial_route=initial_route,
    )


def _validation_error(status: KeyValidationStatus) -> AuthResult:
    messages = {
        KeyValidationStatus.INVALID: (
            AuthStatus.INVALID_KEY,
            tr("service.auth_rejected"),
        ),
        KeyValidationStatus.RESTRICTED: (
            AuthStatus.INVALID_KEY,
            tr("service.auth_restricted"),
        ),
        KeyValidationStatus.TIMEOUT: (
            AuthStatus.TIMEOUT,
            tr("service.auth_timeout"),
        ),
        KeyValidationStatus.NETWORK_ERROR: (
            AuthStatus.NETWORK_ERROR,
            tr("service.auth_network"),
        ),
        KeyValidationStatus.TLS_ERROR: (
            AuthStatus.TLS_ERROR,
            tr("service.auth_tls"),
        ),
        KeyValidationStatus.RATE_LIMITED: (
            AuthStatus.SERVICE_ERROR,
            tr("service.auth_rate"),
        ),
        KeyValidationStatus.SERVER_ERROR: (
            AuthStatus.SERVICE_ERROR,
            tr("service.auth_unavailable"),
        ),
        KeyValidationStatus.INVALID_RESPONSE: (
            AuthStatus.INVALID_RESPONSE,
            tr("service.response_format"),
        ),
        KeyValidationStatus.UNEXPECTED_STATUS: (
            AuthStatus.SERVICE_ERROR,
            tr("service.auth_unchecked"),
        ),
    }
    auth_status, message = messages.get(
        status,
        (AuthStatus.SERVICE_ERROR, tr("service.key_check_failed")),
    )
    return AuthResult(auth_status, message)


def _validated_key_message(key_limit: KeyLimitInfo) -> str:
    if key_limit.state is KeyLimitState.EXHAUSTED:
        return tr("service.validated.exhausted")
    if key_limit.state is KeyLimitState.NOT_SET:
        return tr("service.validated.unlimited")
    if key_limit.state is KeyLimitState.AVAILABLE:
        return tr(
            "service.validated.available",
            amount=number(key_limit.remaining)
            if key_limit.remaining is not None
            else "—",
        )
    return tr("service.validated.other")


def _expired_setup() -> AuthResult:
    return AuthResult(
        AuthStatus.INVALID_STATE,
        tr("service.setup_expired"),
    )
