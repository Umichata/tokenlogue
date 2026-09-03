"""Генерация и безопасная проверка четырёхзначного PIN."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable

from auth.models import PinRecord

PIN_LENGTH = 4
KDF_VERSION = 1
KDF_ALGORITHM = "pbkdf2_hmac_sha256"
KDF_ITERATIONS = 600_000
KDF_SALT_BYTES = 16
KDF_DERIVED_KEY_BYTES = 32


class PinHasher:
    """Генерирует PIN и создаёт его медленный проверочный хеш."""

    def __init__(
        self,
        *,
        iterations: int = KDF_ITERATIONS,
        randbelow: Callable[[int], int] = secrets.randbelow,
        token_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._iterations = iterations
        self._randbelow = randbelow
        self._token_bytes = token_bytes

    def generate_pin(self) -> str:
        """Возвращает четыре цифры, сохраняя возможные ведущие нули."""
        return f"{self._randbelow(10_000):04d}"

    def create_record(self, pin: str) -> PinRecord:
        """Создаёт новую случайную соль и verifier для корректного PIN."""
        if not is_valid_pin(pin):
            raise ValueError("PIN должен состоять ровно из четырёх цифр")
        salt = self._token_bytes(KDF_SALT_BYTES)
        verifier = _derive_pin(pin, salt, self._iterations)
        return PinRecord(
            version=KDF_VERSION,
            algorithm=KDF_ALGORITHM,
            iterations=self._iterations,
            salt=salt,
            verifier=verifier,
        )

    def verify(self, pin: str, record: PinRecord) -> bool:
        """Сравнивает verifier с постоянным по времени сравнением."""
        if not is_valid_pin(pin):
            return False
        if (
            record.version != KDF_VERSION
            or record.algorithm != KDF_ALGORITHM
            or record.iterations <= 0
            or len(record.salt) < KDF_SALT_BYTES
        ):
            return False
        candidate = _derive_pin(pin, record.salt, record.iterations)
        return hmac.compare_digest(candidate, record.verifier)


def is_valid_pin(pin: str) -> bool:
    """Проверяет четыре ASCII-цифры без принятия других Unicode-цифр."""
    return len(pin) == PIN_LENGTH and all("0" <= char <= "9" for char in pin)


def _derive_pin(pin: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("ascii"),
        salt,
        iterations,
        dklen=KDF_DERIVED_KEY_BYTES,
    )
