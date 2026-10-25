"""Связывает PIN, системное подтверждение, защищённый ключ и миграцию."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auth.contracts import AuthRepository
from auth.models import PinRecord, StoredAuthState
from auth.pin import PinHasher
from i18n import tr
from platform_security.device_recovery import (
    DeviceRecovery,
    RecoveryRequest,
    RecoveryStatus,
)
from storage.data_access import DataAccess, DataAccessError
from storage.encrypted_migration import inspect_protection, migrate_database
from storage.encryption_initialization import plaintext_evidence
from storage.field_cipher import FieldCipher
from storage.secure_credentials import (
    REGISTRATION_ID_STORAGE_NAME,
    SECURE_STORAGE_NAMESPACE,
    SecureStorageBackend,
)

DATA_KEY_ALIAS = f"{SECURE_STORAGE_NAMESPACE}.chat_data_key.v1"
DATA_BINDING_ALIAS = f"{SECURE_STORAGE_NAMESPACE}.chat_data_binding.v1"
DATA_INITIALIZATION_ALIAS = f"{SECURE_STORAGE_NAMESPACE}.chat_data_initialization.v1"


class DataProtectionError(RuntimeError):
    """Безопасный отказ без исходных сообщений backend и содержимого базы."""

    def __init__(self, code: str = "protection.unavailable") -> None:
        self.code = code
        super().__init__(tr(code))


@dataclass
class _RecoveryGrant:
    token: str = field(repr=False)
    epoch: int
    identity: str
    registration_id: str = field(repr=False)
    cipher: FieldCipher = field(repr=False)
    binding: dict[str, Any] = field(repr=False)


def _record_json(registration_id: str, record: PinRecord) -> dict[str, Any]:
    return {
        "registration_id": registration_id,
        "version": record.version,
        "algorithm": record.algorithm,
        "iterations": record.iterations,
        "salt": base64.b64encode(record.salt).decode("ascii"),
        "verifier": base64.b64encode(record.verifier).decode("ascii"),
    }


def _parse_record(value: dict[str, Any]) -> tuple[str, PinRecord]:
    registration_id = value["registration_id"]
    if not isinstance(registration_id, str) or not registration_id:
        raise DataProtectionError()
    return registration_id, PinRecord(
        version=value["version"],
        algorithm=value["algorithm"],
        iterations=value["iterations"],
        salt=base64.b64decode(value["salt"], validate=True),
        verifier=base64.b64decode(value["verifier"], validate=True),
    )


def _fingerprint(registration_id: str, record: PinRecord) -> str:
    value = json.dumps(_record_json(registration_id, record), sort_keys=True)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DataProtection:
    """Ключ не читается до app PIN или собственного нового Android challenge."""

    def __init__(
        self,
        path: Path,
        repository: AuthRepository,
        storage: SecureStorageBackend,
        access: DataAccess,
        *,
        pin_hasher: PinHasher | None = None,
        durable_write: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.path = path
        self.repository = repository
        self.storage = storage
        self.access = access
        self.pin_hasher = pin_hasher or PinHasher()
        self._durable_write = durable_write
        self._generation = 0
        self._startup_recovered = False
        self._grant: _RecoveryGrant | None = None
        self._request: RecoveryRequest | None = None
        self._provider: DeviceRecovery | None = None
        self._lock = asyncio.Lock()
        self._replacement: tuple[FieldCipher, int, int] | None = None

    async def _binding(self) -> dict[str, Any] | None:
        raw = await self.storage.get(DATA_BINDING_ALIAS)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            if (
                not isinstance(value, dict)
                or value.get("version") != 1
                or not all(
                    isinstance(value.get(name), str) and value[name]
                    for name in ("database_id", "key_id", "fingerprint")
                )
            ):
                raise ValueError()
            return value
        except (TypeError, ValueError):
            raise DataProtectionError() from None

    async def _sync_storage(self) -> None:
        """Android подтверждает commit платформенных preferences до замены базы."""
        if self._durable_write is not None:
            await self._durable_write()

    def _check_generation(self, generation: int) -> None:
        if generation != self._generation:
            raise DataProtectionError("protection.access_closed")

    async def _initialization(self) -> dict[str, Any] | None:
        raw = await self.storage.get(DATA_INITIALIZATION_ALIAS)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            if (
                not isinstance(value, dict)
                or type(value.get("version")) is not int
                or value["version"] != 1
                or value.get("phase") not in {"prepared", "key_ready", "complete"}
                or set(value)
                != {
                    "version",
                    "phase",
                    "database_id",
                    "key_id",
                    "fingerprint",
                    "plaintext_digest",
                }
                or not all(
                    isinstance(value.get(name), str) and value[name]
                    for name in (
                        "database_id",
                        "key_id",
                        "fingerprint",
                        "plaintext_digest",
                    )
                )
                or len(value["plaintext_digest"]) != 64
                or any(c not in "0123456789abcdef" for c in value["plaintext_digest"])
            ):
                raise ValueError()
            return value
        except (TypeError, ValueError):
            raise DataProtectionError("protection.initialization_unavailable") from None

    async def _save_initialization(
        self, value: dict[str, Any], generation: int
    ) -> None:
        self._check_generation(generation)
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        await self.storage.set(DATA_INITIALIZATION_ALIAS, encoded)
        self._check_generation(generation)
        await self._sync_storage()
        self._check_generation(generation)
        if await self.storage.get(DATA_INITIALIZATION_ALIAS) != encoded:
            raise DataProtectionError("protection.initialization_unavailable")
        self._check_generation(generation)

    async def _plaintext_proof(
        self, stored: StoredAuthState, fingerprint: str, generation: int
    ) -> str:
        """Повторная настройка требует той же доверенной регистрации и PIN."""
        self._check_generation(generation)
        current = await asyncio.to_thread(self.repository.get_auth_state)
        self._check_generation(generation)
        if current is None or not hmac.compare_digest(
            _fingerprint(current.registration_id, current.pin_record), fingerprint
        ):
            raise DataProtectionError("protection.binding_mismatch")
        registration = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
        self._check_generation(generation)
        if registration != stored.registration_id:
            raise DataProtectionError("protection.binding_mismatch")
        try:
            evidence = await asyncio.to_thread(plaintext_evidence, self.path)
        except Exception:
            raise DataProtectionError("protection.initialization_unavailable") from None
        self._check_generation(generation)
        return evidence

    async def _save_binding(self, binding: dict[str, Any]) -> None:
        serialized = json.dumps(binding, sort_keys=True, separators=(",", ":"))
        await self.storage.set(DATA_BINDING_ALIAS, serialized)
        await self._sync_storage()
        if await self.storage.get(DATA_BINDING_ALIAS) != serialized:
            raise DataProtectionError()

    async def has_protection(self) -> bool:
        """Проверка наличия не извлекает alias ключа данных."""
        try:
            return (
                await asyncio.to_thread(inspect_protection, self.path) is not None
                or await self._binding() is not None
                or await self._initialization() is not None
                or await self.storage.contains_key(DATA_KEY_ALIAS)
            )
        except Exception:
            raise DataProtectionError() from None

    async def reconcile(self) -> None:
        """Доводит выбранную смену PIN из защищённого журнала до одного состояния."""
        try:
            binding = await self._binding()
            if binding is None or "pending" not in binding:
                return
            registration_id, record = _parse_record(binding["pending"])
            if not self.path.is_file():
                raise DataProtectionError("protection.binding_mismatch")
            metadata = await asyncio.to_thread(inspect_protection, self.path)
            if metadata is not None:
                if (
                    metadata.database_id != binding["database_id"]
                    or metadata.key_id != binding["key_id"]
                ):
                    raise DataProtectionError("protection.binding_mismatch")
            elif binding.get("protected") is True:
                raise DataProtectionError("protection.binding_mismatch")
            else:
                current = await asyncio.to_thread(self.repository.get_auth_state)
                if current is None or _fingerprint(
                    current.registration_id, current.pin_record
                ) not in {
                    binding["fingerprint"],
                    _fingerprint(registration_id, record),
                }:
                    raise DataProtectionError("protection.binding_mismatch")
            if await self.storage.get(REGISTRATION_ID_STORAGE_NAME) != registration_id:
                raise DataProtectionError("protection.binding_mismatch")
            await self._sync_storage()
            await asyncio.to_thread(
                self.repository.save_auth_state, registration_id, record
            )
            completed = dict(binding)
            completed["fingerprint"] = _fingerprint(registration_id, record)
            completed.pop("pending")
            await self._save_binding(completed)
        except Exception:
            raise DataProtectionError() from None

    async def _key_after_proof(
        self, stored: StoredAuthState, *, recovery: bool, generation: int
    ) -> tuple[FieldCipher, dict[str, Any]]:
        expected_written_key: str | None = None
        metadata = await asyncio.to_thread(inspect_protection, self.path)
        self._check_generation(generation)
        binding = await self._binding()
        self._check_generation(generation)
        initial = await self._initialization()
        self._check_generation(generation)
        fingerprint = _fingerprint(stored.registration_id, stored.pin_record)
        exists = await self.storage.contains_key(DATA_KEY_ALIAS)
        self._check_generation(generation)
        if (
            binding is not None
            and binding.get("protected") is True
            and metadata is None
        ):
            raise DataProtectionError("protection.binding_mismatch")
        if binding is None:
            if metadata is not None or exists:
                raise DataProtectionError("protection.key_missing")
            if initial is not None and initial["phase"] != "prepared":
                raise DataProtectionError("protection.key_missing")
            if initial is not None and not hmac.compare_digest(
                initial["fingerprint"], fingerprint
            ):
                raise DataProtectionError("protection.binding_mismatch")
            binding = {
                "version": 1,
                "database_id": initial["database_id"]
                if initial
                else secrets.token_hex(16),
                "key_id": initial["key_id"] if initial else secrets.token_hex(16),
                "fingerprint": fingerprint,
            }
        elif not recovery and not hmac.compare_digest(
            binding["fingerprint"], fingerprint
        ):
            raise DataProtectionError("protection.binding_mismatch")
        if "pending" in binding:
            raise DataProtectionError()
        if initial is not None and any(
            initial[name] != binding[name] for name in ("database_id", "key_id")
        ):
            raise DataProtectionError("protection.binding_mismatch")
        if initial is not None and initial["phase"] == "complete" and metadata is None:
            raise DataProtectionError("protection.binding_mismatch")
        if metadata is not None and (
            metadata.database_id != binding["database_id"]
            or metadata.key_id != binding["key_id"]
        ):
            raise DataProtectionError("protection.binding_mismatch")
        preparing = initial is not None and initial["phase"] == "prepared"
        if preparing or (initial is None and not exists and metadata is None):
            if (
                metadata is not None
                or binding.get("protected") is not None
                or not hmac.compare_digest(binding["fingerprint"], fingerprint)
                or (
                    preparing
                    and initial is not None
                    and initial["fingerprint"] != fingerprint
                )
            ):
                raise DataProtectionError("protection.binding_mismatch")
            evidence = await self._plaintext_proof(stored, fingerprint, generation)
            if initial is not None:
                if not hmac.compare_digest(initial["plaintext_digest"], evidence):
                    raise DataProtectionError("protection.initialization_unavailable")
            else:
                # Только metadata. DEK хранится исключительно в отдельном alias.
                # Старое binding-only состояние допускается лишь с целой schema 6.
                initial = {
                    "version": 1,
                    "phase": "prepared",
                    "database_id": binding["database_id"],
                    "key_id": binding["key_id"],
                    "fingerprint": fingerprint,
                    "plaintext_digest": evidence,
                }
                await self._save_initialization(initial, generation)
            self._check_generation(generation)
            await self._save_binding(binding)
            self._check_generation(generation)
            if not exists:
                # Повторная попытка не удаляет aliases и не меняет сохранённый DEK.
                value = {
                    "version": 1,
                    "database_id": binding["database_id"],
                    "key_id": binding["key_id"],
                    "key": base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
                }
                encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
                self._check_generation(generation)
                await self.storage.set(DATA_KEY_ALIAS, encoded)
                self._check_generation(generation)
                expected_written_key = encoded
        # Единственное чтение DEK находится за проверкой PIN или native grant.
        if generation != self._generation:
            raise DataProtectionError("protection.access_closed")
        await self._sync_storage()
        if generation != self._generation:
            raise DataProtectionError("protection.access_closed")
        raw = await self.storage.get(DATA_KEY_ALIAS)
        if raw is None or (
            expected_written_key is not None and raw != expected_written_key
        ):
            raise DataProtectionError("protection.key_missing")
        if generation != self._generation:
            raise DataProtectionError("protection.access_closed")
        if await self.storage.get(DATA_KEY_ALIAS) != raw:
            raise DataProtectionError("protection.key_missing")
        try:
            value = json.loads(raw)
            if (
                value.get("version") != 1
                or value.get("database_id") != binding["database_id"]
                or value.get("key_id") != binding["key_id"]
            ):
                raise ValueError()
            key = base64.b64decode(value["key"], validate=True)
            if len(key) != 32:
                raise ValueError()
            cipher = FieldCipher(key, binding["database_id"], binding["key_id"])
        except Exception:
            raise DataProtectionError("protection.key_missing") from None
        if initial is not None and initial["phase"] == "prepared":
            # Этот durable шаг предшествует любой записи зашифрованного файла.
            # После него отсутствие ключа всегда означает закрытый доступ.
            initial = dict(initial, phase="key_ready")
            await self._save_initialization(initial, generation)
        return cipher, binding

    async def _migrate_and_confirm(self, cipher: FieldCipher) -> None:
        await asyncio.to_thread(migrate_database, self.path, cipher)
        if not self._startup_recovered:
            if self.access.active_leases:
                raise DataProtectionError()
            recover = getattr(self.repository, "recover_interrupted_turns", None)
            if recover is not None:
                await asyncio.to_thread(recover)
            self._startup_recovered = True
        binding = await self._binding()
        if (
            binding is None
            or binding["database_id"] != cipher.database_id
            or binding["key_id"] != cipher.key_id
        ):
            raise DataProtectionError()
        if binding.get("protected") is not True:
            binding["protected"] = True
            await self._save_binding(binding)
        initial = await self._initialization()
        if initial is not None and initial["phase"] != "complete":
            if (
                initial["database_id"] != cipher.database_id
                or initial["key_id"] != cipher.key_id
                or initial["phase"] != "key_ready"
            ):
                raise DataProtectionError("protection.initialization_unavailable")
            await self._save_initialization(
                dict(initial, phase="complete"), self._generation
            )

    async def unlock(self, pin: str, stored: StoredAuthState) -> None:
        """Нормальный путь перепроверяет PIN и защищённую привязку до DEK."""
        generation = self._generation
        async with self._lock:
            try:
                registration_id = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
                if registration_id != stored.registration_id:
                    raise DataProtectionError("protection.binding_mismatch")
                if not await asyncio.to_thread(
                    self.pin_hasher.verify, pin, stored.pin_record
                ):
                    raise DataProtectionError("protection.access_closed")
                if generation != self._generation:
                    raise DataAccessError()
                cipher, _binding = await self._key_after_proof(
                    stored, recovery=False, generation=generation
                )
                if generation != self._generation:
                    raise DataAccessError()
                await self._migrate_and_confirm(cipher)
                if generation != self._generation:
                    raise DataAccessError()
                self.access.open(cipher)
            except (DataProtectionError, DataAccessError):
                raise
            except Exception:
                raise DataProtectionError() from None

    async def _identity(self) -> str:
        metadata = await asyncio.to_thread(inspect_protection, self.path)
        if metadata is not None:
            return metadata.database_id
        stored = await asyncio.to_thread(self.repository.get_auth_state)
        if stored is None:
            raise DataProtectionError()
        return "legacy-" + _fingerprint(stored.registration_id, stored.pin_record)

    async def recover(self, provider: DeviceRecovery) -> str:
        """Одно системное подтверждение разрешает только выбор нового app PIN."""
        if self._lock.locked() or self._request is not None:
            raise DataProtectionError()
        self.cancel_grant()
        generation = self._generation
        epoch = self.access.epoch
        identity = await self._identity()
        if generation != self._generation or epoch != self.access.epoch:
            raise DataProtectionError("protection.access_closed")
        request = RecoveryRequest(
            secrets.token_urlsafe(24),
            identity,
            epoch,
            str(tr("protection.native_reason")),
            str(tr("protection.native_title")),
            str(tr("protection.native_cancel")),
        )
        self._request, self._provider = request, provider
        try:
            reply = await provider.authenticate(request)
            if (
                self._request is not request
                or generation != self._generation
                or epoch != self.access.epoch
                or await self._identity() != identity
                or reply.request != request
            ):
                raise DataProtectionError("protection.access_closed")
            if reply.status is not RecoveryStatus.SUCCESS:
                code = (
                    "protection.recovery_unavailable"
                    if reply.status is RecoveryStatus.UNAVAILABLE
                    else "protection.recovery_cancelled"
                )
                raise DataProtectionError(code)
            stored = await asyncio.to_thread(self.repository.get_auth_state)
            registration_id = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
            if (
                stored is None
                or not isinstance(registration_id, str)
                or not registration_id
            ):
                raise DataProtectionError("protection.binding_mismatch")
            cipher, binding = await self._key_after_proof(
                stored, recovery=True, generation=generation
            )
            if generation != self._generation or epoch != self.access.epoch:
                raise DataProtectionError("protection.access_closed")
            token = secrets.token_urlsafe(24)
            self._grant = _RecoveryGrant(
                token, epoch, identity, registration_id, cipher, binding
            )
            return token
        except (DataProtectionError, DataAccessError):
            raise
        except Exception:
            raise DataProtectionError() from None
        finally:
            if self._request is request:
                self._request = None
                self._provider = None

    async def replace_pin(self, token: str, pin: str) -> None:
        """Сохраняет выбранный PIN через журнал и лишь затем открывает переписку."""
        grant = self._grant
        if (
            grant is None
            or token != grant.token
            or grant.epoch != self.access.epoch
            or await self._identity() != grant.identity
        ):
            raise DataProtectionError("protection.access_closed")
        generation = self._generation
        async with self._lock:
            try:
                registration_id = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
                if registration_id != grant.registration_id:
                    raise DataProtectionError("protection.binding_mismatch")
                record = await asyncio.to_thread(self.pin_hasher.create_record, pin)
                if self._grant is not grant or generation != self._generation:
                    raise DataProtectionError("protection.access_closed")
                prepared = dict(grant.binding)
                prepared["pending"] = _record_json(grant.registration_id, record)
                await self._save_binding(prepared)
                # После durable intent завершаем согласование даже при отмене UI.
                await self.reconcile()
                await self._migrate_and_confirm(grant.cipher)
                if generation != self._generation or grant.epoch != self.access.epoch:
                    raise DataProtectionError("protection.access_closed")
                self.access.open(grant.cipher)
            except (DataProtectionError, DataAccessError):
                raise
            except Exception:
                raise DataProtectionError() from None
            finally:
                self._grant = None

    @property
    def replacement_pending(self) -> bool:
        return self._replacement is not None

    def begin_key_replacement(self) -> None:
        with self.access.authorize("read") as cipher:
            captured = cipher
        self.cancel_grant()
        self.access.lock()
        self._replacement = (captured, self.access.epoch, self._generation)

    def finish_key_replacement(self) -> None:
        grant = self._replacement
        self._replacement = None
        if (
            grant is None
            or grant[1] != self.access.epoch
            or grant[2] != self._generation
        ):
            raise DataProtectionError("protection.access_closed")
        self.access.open(grant[0])

    def cancel_grant(self) -> None:
        self._generation += 1
        self._grant = None
        self._replacement = None

    async def cancel_recovery(self) -> None:
        self.cancel_grant()
        request, provider = self._request, self._provider
        self._request = self._provider = None
        if request is not None and provider is not None:
            await provider.cancel(request.attempt_id)

    def lock(self) -> None:
        self.cancel_grant()
        self.access.lock()
