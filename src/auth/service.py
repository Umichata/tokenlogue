"""Сценарии первого запуска, PIN-входа и сброса доступа."""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from collections.abc import Awaitable, Callable

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
    ) -> None:
        self._key_validator = key_validator
        self._credentials = credentials
        self._repository = repository
        self._pin_hasher = pin_hasher or PinHasher()
        self._clock = clock
        self._operation_lock = asyncio.Lock()
        self._pending_key: str | None = None
        self._pending_pin: str | None = None
        self._pending_registration_id: str | None = None
        self._pending_key_limit = KeyLimitInfo.unknown()

    async def initialize(self) -> AuthResult:
        """Определяет первый экран и исправляет несогласованное состояние."""
        return await self._run_exclusive(self._initialize)

    async def start_setup(self, api_key: str) -> AuthResult:
        """Проверяет ключ и создаёт временный PIN без записи на диск."""
        return await self._run_exclusive(lambda: self._start_setup(api_key))

    async def complete_setup(self) -> AuthResult:
        """Сохраняет PIN verifier и ключ после подтверждения пользователя."""
        return await self._run_exclusive(self._complete_setup)

    async def login(self, pin: str) -> AuthResult:
        """Проверяет PIN и получает ключ только после успешной проверки."""
        return await self._run_exclusive(lambda: self._login(pin))

    async def reset_authentication(self) -> AuthResult:
        """Удаляет только ключ и PIN-данные после подтверждения в UI."""
        return await self._run_exclusive(self._reset_authentication)

    def cancel_pending_setup(self) -> None:
        """Удаляет временные ссылки на ключ, PIN и идентификатор регистрации."""
        self._pending_key = None
        self._pending_pin = None
        self._pending_registration_id = None
        self._pending_key_limit = KeyLimitInfo.unknown()

    async def _initialize(self) -> AuthResult:
        try:
            stored = await asyncio.to_thread(self._repository.get_auth_state)
            credentials = await self._credentials.inspect_state()
        except Exception:
            return _storage_error(
                "Не удалось открыть защищённое хранилище приложения.",
                initial_route=InitialRoute.ERROR,
            )

        if stored is None and not credentials.has_artifacts:
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
                        "Не удалось обновить состояние локальной блокировки.",
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
        normalized_key = api_key.strip()
        if not normalized_key:
            return AuthResult(AuthStatus.INVALID_KEY, "Введите OpenRouter API-ключ.")

        try:
            validation = await self._key_validator.validate_key(normalized_key)
        except Exception:
            return AuthResult(AuthStatus.SERVICE_ERROR, "Не удалось проверить ключ.")
        if not validation.accepted:
            return _validation_error(validation.status)
        key_validity, key_limit = interpret_key_validation(validation)
        if key_validity is not KeyValidityState.VALID:
            return AuthResult(
                AuthStatus.INVALID_RESPONSE,
                "OpenRouter вернул ответ неожиданного формата.",
            )

        pin = self._pin_hasher.generate_pin()
        self._pending_key = normalized_key
        self._pending_pin = pin
        self._pending_registration_id = secrets.token_urlsafe(REGISTRATION_ID_BYTES)
        self._pending_key_limit = key_limit
        return AuthResult(
            AuthStatus.PIN_CREATED,
            _validated_key_message(key_limit),
            pin=pin,
            key_validity=key_validity,
            key_limit=key_limit,
        )

    async def _complete_setup(self) -> AuthResult:
        if (
            self._pending_key is None
            or self._pending_pin is None
            or self._pending_registration_id is None
            or self._pending_key_limit.state is KeyLimitState.UNKNOWN
        ):
            return AuthResult(
                AuthStatus.INVALID_STATE,
                "Настройка устарела. Проверьте ключ ещё раз.",
            )

        api_key = self._pending_key
        pin = self._pending_pin
        registration_id = self._pending_registration_id
        key_limit = self._pending_key_limit
        try:
            record = await asyncio.to_thread(self._pin_hasher.create_record, pin)
            await asyncio.to_thread(
                self._repository.save_auth_state,
                registration_id,
                record,
            )
            try:
                await self._credentials.save_credentials(api_key, registration_id)
            except Exception:
                await self._rollback_setup()
                return _storage_error(
                    "Не удалось сохранить ключ в защищённом хранилище."
                )
            return AuthResult(
                AuthStatus.AUTHENTICATED,
                "Локальная защита настроена.",
                api_key=api_key,
                key_validity=KeyValidityState.VALID,
                key_limit=key_limit,
            )
        except Exception:
            await self._rollback_setup()
            return _storage_error("Не удалось сохранить данные локальной защиты.")
        finally:
            self.cancel_pending_setup()

    async def _login(self, pin: str) -> AuthResult:
        if not is_valid_pin(pin):
            return AuthResult(
                AuthStatus.INVALID_PIN,
                "PIN должен состоять ровно из четырёх цифр.",
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

            api_key = await self._credentials.get_api_key()
            if not api_key:
                return await self._reset_inconsistent_state()
            await asyncio.to_thread(self._repository.reset_login_attempts)
            return AuthResult(
                AuthStatus.AUTHENTICATED,
                api_key=api_key,
                key_validity=KeyValidityState.UNKNOWN,
                key_limit=KeyLimitInfo.unknown(),
            )
        except Exception:
            return _storage_error("Не удалось проверить локальные данные доступа.")

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
            f"Неверный PIN. Осталось попыток: {attempts_left}.",
        )

    async def _reset_authentication(self) -> AuthResult:
        self.cancel_pending_setup()
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
            return _storage_error("Не удалось полностью сбросить данные доступа.")
        return AuthResult(
            AuthStatus.SETUP_REQUIRED,
            "Данные доступа удалены. Введите новый ключ.",
            initial_route=InitialRoute.SETUP,
        )

    async def _reset_inconsistent_state(self) -> AuthResult:
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
                "Не удалось восстановить согласованное состояние хранилища.",
                initial_route=InitialRoute.ERROR,
            )
        return AuthResult(
            AuthStatus.SETUP_REQUIRED,
            "Локальные данные были несогласованы. Настройте доступ заново.",
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
                "Дождитесь завершения текущей операции.",
            )
        async with self._operation_lock:
            return await operation()

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
        f"Слишком много попыток. Повторите через {seconds} сек.",
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
            "OpenRouter отклонил этот API-ключ.",
        ),
        KeyValidationStatus.RESTRICTED: (
            AuthStatus.INVALID_KEY,
            "OpenRouter отклонил проверку разрешений этого API-ключа.",
        ),
        KeyValidationStatus.TIMEOUT: (
            AuthStatus.TIMEOUT,
            "OpenRouter не ответил за отведённое время.",
        ),
        KeyValidationStatus.NETWORK_ERROR: (
            AuthStatus.NETWORK_ERROR,
            "Не удалось подключиться к OpenRouter. Проверьте сеть.",
        ),
        KeyValidationStatus.TLS_ERROR: (
            AuthStatus.TLS_ERROR,
            "Не удалось установить защищённое соединение с OpenRouter.",
        ),
        KeyValidationStatus.RATE_LIMITED: (
            AuthStatus.SERVICE_ERROR,
            "OpenRouter временно ограничил частоту проверок. Повторите позже.",
        ),
        KeyValidationStatus.SERVER_ERROR: (
            AuthStatus.SERVICE_ERROR,
            "Сервис OpenRouter временно недоступен.",
        ),
        KeyValidationStatus.INVALID_RESPONSE: (
            AuthStatus.INVALID_RESPONSE,
            "OpenRouter вернул ответ неожиданного формата.",
        ),
        KeyValidationStatus.UNEXPECTED_STATUS: (
            AuthStatus.SERVICE_ERROR,
            "OpenRouter не смог проверить ключ.",
        ),
    }
    auth_status, message = messages.get(
        status,
        (AuthStatus.SERVICE_ERROR, "Не удалось проверить ключ."),
    )
    return AuthResult(auth_status, message)


def _validated_key_message(key_limit: KeyLimitInfo) -> str:
    prefix = "Ключ OpenRouter успешно проверен."
    if key_limit.state is KeyLimitState.EXHAUSTED:
        return (
            f"{prefix} Расходный лимит этого ключа исчерпан. "
            "Бесплатный режим остаётся доступным. Сохраните созданный PIN."
        )
    if key_limit.state is KeyLimitState.NOT_SET:
        return (
            f"{prefix} Для ключа не установлен отдельный расходный лимит. "
            "Сохраните созданный PIN."
        )
    if key_limit.state is KeyLimitState.AVAILABLE:
        return (
            f"{prefix} Доступный лимит ключа: {key_limit.remaining} USD. "
            "Сохраните созданный PIN."
        )
    return f"{prefix} Сохраните созданный PIN."
