"""Модели локальной аутентификации без зависимостей от UI и хранилищ."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class InitialRoute(str, Enum):
    """Начальный экран приложения."""

    SETUP = "setup"
    PIN = "pin"
    ERROR = "error"


class AuthStatus(str, Enum):
    """Результаты пользовательских сценариев доступа."""

    SETUP_REQUIRED = "setup_required"
    PIN_REQUIRED = "pin_required"
    PIN_CREATED = "pin_created"
    AUTHENTICATED = "authenticated"
    INVALID_PIN = "invalid_pin"
    LOCKED = "locked"
    BUSY = "busy"
    INVALID_KEY = "invalid_key"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    TLS_ERROR = "tls_error"
    SERVICE_ERROR = "service_error"
    INVALID_RESPONSE = "invalid_response"
    STORAGE_ERROR = "storage_error"
    INVALID_STATE = "invalid_state"


@dataclass(frozen=True)
class PinRecord:
    """Версионированные данные проверки PIN без исходного PIN."""

    version: int
    algorithm: str
    iterations: int
    salt: bytes = field(repr=False)
    verifier: bytes = field(repr=False)


@dataclass(frozen=True)
class LoginAttemptState:
    """Сохраняемое состояние неудачных попыток входа."""

    failed_attempts: int
    locked_until: float | None


@dataclass(frozen=True)
class StoredAuthState:
    """Связанная с одной регистрацией запись SQLite."""

    registration_id: str
    pin_record: PinRecord
    attempts: LoginAttemptState


@dataclass(frozen=True)
class CredentialState:
    """Метаданные SecureStorage без извлечения API-ключа."""

    has_api_key: bool
    registration_id: str | None

    @property
    def has_artifacts(self) -> bool:
        return self.has_api_key or self.registration_id is not None

    @property
    def complete(self) -> bool:
        return self.has_api_key and self.registration_id is not None


class KeyLimitState(str, Enum):
    """Оперативная трактовка расходного лимита конкретного API-ключа."""

    UNKNOWN = "unknown"
    NOT_SET = "not_set"
    EXHAUSTED = "exhausted"
    AVAILABLE = "available"


class KeyValidityState(str, Enum):
    """Оперативная валидность ключа, независимая от его расходного лимита."""

    UNKNOWN = "unknown"
    VALID = "valid"
    INVALID = "invalid"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class KeyLimitInfo:
    """Несохраняемый снимок `limit_remaining`, не являющийся балансом."""

    state: KeyLimitState
    remaining: Decimal | None = None

    def __post_init__(self) -> None:
        if self.state in {KeyLimitState.UNKNOWN, KeyLimitState.NOT_SET}:
            if self.remaining is not None:
                raise ValueError("Для этого состояния значение лимита не допускается")
            return
        if self.remaining is None or not self.remaining.is_finite():
            raise ValueError("Для известного лимита требуется конечное значение")
        if self.state is KeyLimitState.AVAILABLE and self.remaining <= 0:
            raise ValueError("Доступный лимит должен быть положительным")
        if self.state is KeyLimitState.EXHAUSTED and self.remaining > 0:
            raise ValueError("Исчерпанный лимит не может быть положительным")

    @classmethod
    def unknown(cls) -> KeyLimitInfo:
        return cls(KeyLimitState.UNKNOWN)

    @classmethod
    def from_validated_remaining(cls, remaining: Decimal | None) -> KeyLimitInfo:
        if remaining is None:
            return cls(KeyLimitState.NOT_SET)
        if remaining <= 0:
            return cls(KeyLimitState.EXHAUSTED, remaining)
        return cls(KeyLimitState.AVAILABLE, remaining)

    @property
    def paid_mode_allowed(self) -> bool:
        return self.state in {KeyLimitState.NOT_SET, KeyLimitState.AVAILABLE}


@dataclass(frozen=True)
class AuthResult:
    """Безопасный результат для управления переходами интерфейса."""

    status: AuthStatus
    message: str = ""
    initial_route: InitialRoute | None = None
    pin: str | None = field(default=None, repr=False)
    api_key: str | None = field(default=None, repr=False)
    lock_seconds_remaining: int = 0
    key_validity: KeyValidityState = KeyValidityState.UNKNOWN
    key_limit: KeyLimitInfo = field(default_factory=KeyLimitInfo.unknown)
