"""Контракты зависимостей сервиса локальной аутентификации."""

from __future__ import annotations

from typing import Protocol

from api.openrouter import KeyValidationResult
from auth.models import CredentialState, LoginAttemptState, PinRecord, StoredAuthState


class KeyValidator(Protocol):
    async def validate_key(self, api_key: str) -> KeyValidationResult: ...


class CredentialStore(Protocol):
    async def inspect_state(self) -> CredentialState: ...

    async def save_credentials(self, api_key: str, registration_id: str) -> None: ...

    async def get_api_key(self) -> str | None: ...

    async def delete_credentials(self) -> None: ...


class AuthRepository(Protocol):
    def get_auth_state(self) -> StoredAuthState | None: ...

    def save_auth_state(self, registration_id: str, record: PinRecord) -> None: ...

    def clear_auth_data(self) -> None: ...

    def reset_login_attempts(self) -> None: ...

    def register_failed_attempt(
        self,
        now: float,
        max_attempts: int,
        lock_seconds: int,
    ) -> LoginAttemptState: ...
