"""Платформенное защищённое хранение OpenRouter API-ключа."""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Protocol

import flet_secure_storage as fss

from auth.models import CredentialState
from i18n import tr
from providers.creation import NewChatPolicy
from providers.models import ProviderId, detect_key

SECURE_STORAGE_NAMESPACE = "io.github.umichata.tokenlogue"
API_KEY_STORAGE_NAME = f"{SECURE_STORAGE_NAMESPACE}.openrouter_api_key.v1"
REGISTRATION_ID_STORAGE_NAME = f"{SECURE_STORAGE_NAMESPACE}.registration_id.v1"
PROVIDER_KEY_STORAGE_NAMES = {
    ProviderId.OPENROUTER: API_KEY_STORAGE_NAME,
    ProviderId.VSEGPT: f"{SECURE_STORAGE_NAMESPACE}.vsegpt_api_key.v1",
}
DEFAULT_PROVIDER_STORAGE_NAME = f"{SECURE_STORAGE_NAMESPACE}.default_provider.v1"
NEW_CHAT_POLICY_STORAGE_NAME = f"{SECURE_STORAGE_NAMESPACE}.new_chat_policy.v1"
PROVIDER_VALIDATION_STORAGE_NAMES = {
    provider: f"{SECURE_STORAGE_NAMESPACE}.{provider.value}_validation.v1"
    for provider in ProviderId
}
ALL_PROVIDER_STORAGE_NAMES = (
    *PROVIDER_KEY_STORAGE_NAMES.values(),
    DEFAULT_PROVIDER_STORAGE_NAME,
    NEW_CHAT_POLICY_STORAGE_NAME,
    *PROVIDER_VALIDATION_STORAGE_NAMES.values(),
)


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
        self._provider_write_lock = asyncio.Lock()
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
        provider = detect_key(api_key) or ProviderId.OPENROUTER
        policy = await self.get_new_chat_policy()
        names = (
            PROVIDER_KEY_STORAGE_NAMES[provider],
            PROVIDER_VALIDATION_STORAGE_NAMES[provider],
            DEFAULT_PROVIDER_STORAGE_NAME,
            NEW_CHAT_POLICY_STORAGE_NAME,
        )
        try:
            previous = {name: await self._storage.get(name) for name in names}
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None
        try:
            await self.save_provider_key(
                provider, api_key, authorization_confirmed=False
            )
            await self.set_default_provider(provider, creation_policy=policy)
        except BaseException:
            async with self._provider_write_lock:
                for name, value in previous.items():
                    try:
                        if value is None:
                            await self._storage.remove(name)
                        else:
                            await self._storage.set(name, value)
                    except Exception:
                        pass
            raise SecureCredentialsError(tr("service.secure_save_failed")) from None

    async def inspect_state(self) -> CredentialState:
        """Читает только метаданные регистрации, не извлекая API-ключ."""
        try:
            has_api_key = any(
                [
                    await self._storage.contains_key(name)
                    for name in PROVIDER_KEY_STORAGE_NAMES.values()
                ]
            )
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
            provider = detect_key(api_key) or ProviderId.OPENROUTER
            name = PROVIDER_KEY_STORAGE_NAMES[provider]
            await self._storage.set(name, api_key)
            if await self._storage.get(name) != api_key:
                raise SecureCredentialsError(tr("service.secure_save_failed"))
            await self._storage.set(DEFAULT_PROVIDER_STORAGE_NAME, provider.value)
            await self._storage.set(
                NEW_CHAT_POLICY_STORAGE_NAME, NewChatPolicy.MANUAL.value
            )
            if (
                await self._storage.get(NEW_CHAT_POLICY_STORAGE_NAME)
                != NewChatPolicy.MANUAL.value
            ):
                raise SecureCredentialsError(tr("service.secure_save_failed"))
        except Exception:
            await self._best_effort_remove()
            raise SecureCredentialsError(tr("service.secure_save_failed")) from None

    async def get_api_key(self) -> str | None:
        """Извлекает ключ после успешной локальной проверки PIN."""
        try:
            provider = await self.get_default_provider()
            value = await self._storage.get(PROVIDER_KEY_STORAGE_NAMES[provider])
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None
        return value if value else None

    async def delete_credentials(self) -> None:
        """Удаляет ключ и идентификатор одной регистрации."""
        failed = False
        for key in (*ALL_PROVIDER_STORAGE_NAMES, REGISTRATION_ID_STORAGE_NAME):
            try:
                await self._storage.remove(key)
            except Exception:
                failed = True
        if failed:
            raise SecureCredentialsError(tr("service.secure_clear_failed")) from None

    async def _best_effort_remove(self) -> None:
        for key in (*ALL_PROVIDER_STORAGE_NAMES, REGISTRATION_ID_STORAGE_NAME):
            try:
                await self._storage.remove(key)
            except Exception:
                pass

    async def get_provider_key(self, provider: ProviderId) -> str | None:
        """Читает только явно выбранный slot после локальной аутентификации."""
        try:
            value = await self._storage.get(PROVIDER_KEY_STORAGE_NAMES[provider])
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None
        return value or None

    async def get_default_provider(self) -> ProviderId:
        """Отсутствующая новая metadata не изменяет прежний OpenRouter slot."""
        try:
            value = await self._storage.get(DEFAULT_PROVIDER_STORAGE_NAME)
            if value in {provider.value for provider in ProviderId}:
                provider = ProviderId(value)
                if await self._storage.contains_key(
                    PROVIDER_KEY_STORAGE_NAMES[provider]
                ):
                    return provider
            for provider, name in PROVIDER_KEY_STORAGE_NAMES.items():
                if await self._storage.contains_key(name):
                    return provider
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None
        return ProviderId.OPENROUTER

    async def set_default_provider(
        self, provider: ProviderId, *, creation_policy: NewChatPolicy | None = None
    ) -> None:
        async with self._provider_write_lock:
            names = [DEFAULT_PROVIDER_STORAGE_NAME]
            if creation_policy is not None:
                names.append(NEW_CHAT_POLICY_STORAGE_NAME)
            try:
                previous = {name: await self._storage.get(name) for name in names}
                if not await self._storage.contains_key(
                    PROVIDER_KEY_STORAGE_NAMES[provider]
                ):
                    raise SecureCredentialsError(tr("service.secure_read_failed"))
            except Exception:
                raise SecureCredentialsError(tr("service.secure_save_failed")) from None
            changes = {DEFAULT_PROVIDER_STORAGE_NAME: provider.value}
            if creation_policy is not None:
                changes[NEW_CHAT_POLICY_STORAGE_NAME] = creation_policy.value
            try:
                for name, value in changes.items():
                    await self._storage.set(name, value)
                    if await self._storage.get(name) != value:
                        raise SecureCredentialsError(tr("service.secure_save_failed"))
            except BaseException:
                for name, value in previous.items():
                    try:
                        if value is None:
                            await self._storage.remove(name)
                        else:
                            await self._storage.set(name, value)
                    except Exception:
                        pass
                raise SecureCredentialsError(tr("service.secure_save_failed")) from None

    async def get_new_chat_policy(self) -> NewChatPolicy:
        """Retain an explicit legacy preference without changing any key slot."""
        try:
            value = await self._storage.get(NEW_CHAT_POLICY_STORAGE_NAME)
            if value is not None:
                return NewChatPolicy(value)
            legacy = await self._storage.get(DEFAULT_PROVIDER_STORAGE_NAME)
            return (
                NewChatPolicy(legacy)
                if legacy in {provider.value for provider in ProviderId}
                else NewChatPolicy.MANUAL
            )
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None

    async def set_new_chat_policy(self, policy: NewChatPolicy) -> None:
        """Persist a creation choice even when that service has no saved key yet."""
        if not isinstance(policy, NewChatPolicy):
            raise ValueError("invalid_new_chat_policy")
        async with self._provider_write_lock:
            try:
                previous = await self._storage.get(NEW_CHAT_POLICY_STORAGE_NAME)
            except Exception:
                raise SecureCredentialsError(tr("service.secure_read_failed")) from None
            try:
                await self._storage.set(NEW_CHAT_POLICY_STORAGE_NAME, policy.value)
                if (
                    await self._storage.get(NEW_CHAT_POLICY_STORAGE_NAME)
                    != policy.value
                ):
                    raise SecureCredentialsError(tr("service.secure_save_failed"))
            except BaseException:
                try:
                    if previous is None:
                        await self._storage.remove(NEW_CHAT_POLICY_STORAGE_NAME)
                    else:
                        await self._storage.set(NEW_CHAT_POLICY_STORAGE_NAME, previous)
                except Exception:
                    pass
                raise SecureCredentialsError(tr("service.secure_save_failed")) from None

    async def save_provider_key(
        self,
        provider: ProviderId,
        api_key: str,
        *,
        authorization_confirmed: bool,
    ) -> str:
        """Проверяет запись нового ключа и компенсирует отказ без стирания старого."""
        normalized = api_key.strip()
        if detect_key(normalized) is not provider:
            raise SecureCredentialsError(tr("providers.unknown_prefix"))
        async with self._provider_write_lock:
            name = PROVIDER_KEY_STORAGE_NAMES[provider]
            metadata_name = PROVIDER_VALIDATION_STORAGE_NAMES[provider]
            try:
                old = await self._storage.get(name)
                old_metadata = await self._storage.get(metadata_name)
            except Exception:
                raise SecureCredentialsError(tr("service.secure_read_failed")) from None
            revision = secrets.token_urlsafe(18)
            metadata = json.dumps(
                {
                    "revision": revision,
                    "authorization_confirmed": authorization_confirmed,
                    "checked_at": datetime.now(UTC).isoformat(),
                }
            )
            try:
                await self._storage.set(name, normalized)
                if await self._storage.get(name) != normalized:
                    raise SecureCredentialsError(tr("service.secure_save_failed"))
                await self._storage.set(metadata_name, metadata)
                if await self._storage.get(metadata_name) != metadata:
                    raise SecureCredentialsError(tr("service.secure_save_failed"))
            except BaseException:
                for slot, previous in ((name, old), (metadata_name, old_metadata)):
                    try:
                        if previous is None:
                            await self._storage.remove(slot)
                        else:
                            await self._storage.set(slot, previous)
                    except Exception:
                        pass
                raise SecureCredentialsError(tr("service.secure_save_failed")) from None
            return revision

    async def provider_metadata(self, provider: ProviderId) -> dict[str, Any]:
        try:
            value = await self._storage.get(PROVIDER_VALIDATION_STORAGE_NAMES[provider])
            metadata = json.loads(value) if value else {}
            return metadata if isinstance(metadata, dict) else {}
        except Exception:
            raise SecureCredentialsError(tr("service.secure_read_failed")) from None
