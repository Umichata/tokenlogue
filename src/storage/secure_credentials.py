"""Платформенное защищённое хранение OpenRouter API-ключа."""

from __future__ import annotations

from typing import Any, Protocol

import flet_secure_storage as fss

from auth.models import CredentialState
from i18n import tr

SECURE_STORAGE_NAMESPACE = "io.github.umichata.tokenlogue"
API_KEY_STORAGE_NAME = f"{SECURE_STORAGE_NAMESPACE}.openrouter_api_key.v1"
REGISTRATION_ID_STORAGE_NAME = f"{SECURE_STORAGE_NAMESPACE}.registration_id.v1"


class SecureStorageBackend(Protocol):
    """Минимальный интерфейс SecureStorage для платформы и тестов."""

    async def contains_key(self, key: str) -> bool: ...

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: Any) -> None: ...

    async def remove(self, key: str) -> None: ...


class SecureCredentialsError(RuntimeError):
    """Безопасная ошибка платформенного хранилища без исходного исключения."""


class FletSecureCredentials:
    """Адаптер SecureStorage с Android Keystore без обязательной биометрии."""

    def __init__(self, storage: SecureStorageBackend | None = None) -> None:
        self._storage: SecureStorageBackend = (
            storage
            if storage is not None
            else fss.SecureStorage(
                android_options=fss.AndroidOptions(
                    reset_on_error=False,
                    migrate_on_algorithm_change=True,
                    enforce_biometrics=False,
                    shared_preferences_name=(
                        f"{SECURE_STORAGE_NAMESPACE}.secure_credentials"
                    ),
                    preferences_key_prefix=SECURE_STORAGE_NAMESPACE,
                )
            )
        )

    @property
    def storage_backend(self) -> SecureStorageBackend:
        """Передаёт один backend координатору с отдельными aliases данных."""
        return self._storage

    async def replace_api_key(self, api_key: str) -> None:
        """Сохраняет новый API-ключ без удаления PIN, регистрации и DEK."""
        if not api_key:
            raise ValueError(tr("service.registration_missing"))
        old = await self.get_api_key()
        if old is None:
            raise SecureCredentialsError(tr("service.secure_read_failed"))
        try:
            await self._storage.set(API_KEY_STORAGE_NAME, api_key)
            if await self._storage.get(API_KEY_STORAGE_NAME) != api_key:
                raise SecureCredentialsError(tr("service.secure_save_failed"))
        except Exception:
            try:
                await self._storage.set(API_KEY_STORAGE_NAME, old)
            except Exception:
                pass
            raise SecureCredentialsError(tr("service.secure_save_failed")) from None

    async def inspect_state(self) -> CredentialState:
        """Читает только метаданные регистрации, не извлекая API-ключ."""
        try:
            has_api_key = await self._storage.contains_key(API_KEY_STORAGE_NAME)
            registration_id = await self._storage.get(REGISTRATION_ID_STORAGE_NAME)
        except Exception:
            raise SecureCredentialsError(tr("service.secure_unavailable")) from None
        return CredentialState(
            has_api_key=has_api_key,
            registration_id=registration_id or None,
        )

    async def save_credentials(self, api_key: str, registration_id: str) -> None:
        """Сохраняет связанные записи регистрации с компенсацией при ошибке."""
        if not api_key or not registration_id:
            raise ValueError(tr("service.registration_missing"))
        try:
            await self._storage.set(REGISTRATION_ID_STORAGE_NAME, registration_id)
            await self._storage.set(API_KEY_STORAGE_NAME, api_key)
        except Exception:
            await self._best_effort_remove()
            raise SecureCredentialsError(tr("service.secure_save_failed")) from None

    async def get_api_key(self) -> str | None:
        """Извлекает ключ после успешной локальной проверки PIN."""
        try:
            value = await self._storage.get(API_KEY_STORAGE_NAME)
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None
        return value if value else None

    async def delete_credentials(self) -> None:
        """Удаляет ключ и идентификатор одной регистрации."""
        failed = False
        for key in (API_KEY_STORAGE_NAME, REGISTRATION_ID_STORAGE_NAME):
            try:
                await self._storage.remove(key)
            except Exception:
                failed = True
        if failed:
            raise SecureCredentialsError(tr("service.secure_clear_failed")) from None

    async def _best_effort_remove(self) -> None:
        for key in (API_KEY_STORAGE_NAME, REGISTRATION_ID_STORAGE_NAME):
            try:
                await self._storage.remove(key)
            except Exception:
                pass
