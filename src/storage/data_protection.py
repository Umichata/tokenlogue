"""Связывает PIN, системное подтверждение, защищённый ключ и миграцию."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import math
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auth.contracts import AuthRepository
from auth.models import PinRecord, StoredAuthState
from auth.pin import PinHasher, is_valid_pin
from auth.pin_policy import (
    APP_PIN_MAX_FAILED_ATTEMPTS,
    format_lock_time,
    pin_check_gate,
    sample_clock,
)
from i18n import tr
from platform_security.device_recovery import (
    RecoveryProvider,
    RecoveryRequest,
    RecoveryStatus,
)
from storage.data_access import DataAccess, DataAccessError
from storage.encrypted_migration import inspect_protection, migrate_database
from storage.encryption_initialization import plaintext_evidence
from storage.field_cipher import FieldCipher
from storage.recovery_code import (
    LOCK_SECONDS,
    MAX_FAILED_ATTEMPTS,
    PROOF_TTL_SECONDS,
    RecoveryCodeIssue,
    RecoveryProofKind,
    code_digest,
    generate_code,
    normalize_code,
)
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

    def __init__(
        self,
        code: str = "protection.unavailable",
        *,
        lock_seconds_remaining: int = 0,
        pin_attempts_remaining: int | None = None,
    ) -> None:
        self.code = code
        self.lock_seconds_remaining = lock_seconds_remaining
        self.pin_attempts_remaining = pin_attempts_remaining
        super().__init__(
            tr("auth.lock_countdown", time=format_lock_time(lock_seconds_remaining))
            if lock_seconds_remaining
            else tr("auth.pin_attempts_remaining", remaining=pin_attempts_remaining)
            if pin_attempts_remaining is not None
            else tr(code)
        )


@dataclass
class _RecoveryGrant:
    token: str = field(repr=False)
    epoch: int
    identity: str
    registration_id: str = field(repr=False)
    cipher: FieldCipher = field(repr=False)
    binding: dict[str, Any] = field(repr=False)
    proof_kind: RecoveryProofKind
    generation: int
    expires_at: float
    code_generation: int | None = None


@dataclass
class _PendingCodeIssue:
    attempt_id: str = field(repr=False)
    verifier: str = field(repr=False)
    binding: dict[str, Any] = field(repr=False)
    registration_id: str = field(repr=False)
    epoch: int
    generation: int
    code_generation: int
    expires_at: float


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
    """Ключ не читается до PIN, системного proof или доверенного резервного кода."""

    def __init__(
        self,
        path: Path,
        repository: AuthRepository,
        storage: SecureStorageBackend,
        access: DataAccess,
        *,
        pin_hasher: PinHasher | None = None,
        durable_write: Callable[[], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        pin_elapsed_clock: Callable[[], float] | None = None,
        pin_boot_token: Callable[[], str | None] | None = None,
    ) -> None:
        self.path = path
        self.repository = repository
        self._pin_gate = pin_check_gate(repository)
        self.storage = storage
        self.access = access
        self.pin_hasher = pin_hasher or PinHasher()
        self._durable_write = durable_write
        self._clock = clock
        self._pin_elapsed_clock = pin_elapsed_clock
        self._pin_boot_token = pin_boot_token
        self._monotonic = monotonic
        self._generation = 0
        self._startup_recovered = False
        self._grant: _RecoveryGrant | None = None
        self._request: RecoveryRequest | None = None
        self._provider: RecoveryProvider | None = None
        self._lock = asyncio.Lock()
        self._replacement: tuple[FieldCipher, int, int] | None = None
        self._code_issue: _PendingCodeIssue | None = None

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
        deletion = self.path.with_name(self.path.name + ".profile-deletion.json")
        temporary = deletion.with_name(deletion.name + ".write")
        if generation != self._generation or any(
            path.exists() or path.is_symlink() for path in (deletion, temporary)
        ):
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

    def _code_record(self, binding: dict[str, Any]) -> dict[str, Any] | None:
        value = binding.get("recovery_code")
        if value is None:
            return None
        try:
            fields = {
                "version",
                "generation",
                "database_id",
                "key_id",
                "registration_id",
                "state",
                "failed_attempts",
                "locked_until",
            }
            if not isinstance(value, dict):
                raise ValueError()
            if value.get("state") == "active":
                fields.add("verifier")
            if (
                set(value) != fields
                or type(value["version"]) is not int
                or value["version"] != 1
                or type(value["generation"]) is not int
                or not 1 <= value["generation"] < 2**63
                or value["state"] not in {"active", "consumed"}
                or value["database_id"] != binding["database_id"]
                or value["key_id"] != binding["key_id"]
                or not isinstance(value["registration_id"], str)
                or not value["registration_id"]
                or type(value["failed_attempts"]) is not int
                or not 0 <= value["failed_attempts"] <= MAX_FAILED_ATTEMPTS
            ):
                raise ValueError()
            until = value["locked_until"]
            if until is not None and (
                type(until) not in {int, float} or not math.isfinite(until) or until < 0
            ):
                raise ValueError()
            if (
                (value["failed_attempts"] == MAX_FAILED_ATTEMPTS) != (until is not None)
                or value["state"] == "consumed"
                and value["failed_attempts"] != 0
            ):
                raise ValueError()
            if value["state"] == "active" and (
                not isinstance(value["verifier"], str)
                or len(value["verifier"]) != 64
                or any(c not in "0123456789abcdef" for c in value["verifier"])
            ):
                raise ValueError()
            return value
        except (KeyError, TypeError, ValueError):
            raise DataProtectionError("protection.binding_mismatch") from None

    async def _code_binding(self) -> tuple[dict[str, Any], str]:
        binding = await self._binding()
        stored = await asyncio.to_thread(self.repository.get_auth_state)
        registration = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
        metadata = await asyncio.to_thread(inspect_protection, self.path)
        if (
            binding is None
            or stored is None
            or binding.get("protected") is not True
            or metadata is None
            or metadata.database_id != binding["database_id"]
            or metadata.key_id != binding["key_id"]
            or not isinstance(registration, str)
            or not registration
            or registration != stored.registration_id
            or "pending" in binding
        ):
            raise DataProtectionError("protection.binding_mismatch")
        record = self._code_record(binding)
        if record is not None and record["registration_id"] != registration:
            raise DataProtectionError("protection.binding_mismatch")
        return binding, registration

    async def recovery_code_enrolled(self) -> bool:
        """Наличие резервного способа проверяется без чтения ключа переписки."""
        binding = await self._binding()
        if binding is None or self._code_record(binding) is None:
            return False
        binding, _registration = await self._code_binding()
        record = self._code_record(binding)
        return record is not None and record["state"] == "active"

    @staticmethod
    def _digest_code(
        value: str, binding: dict[str, Any], registration: str, generation: int
    ) -> str:
        return code_digest(
            value,
            database_id=binding["database_id"],
            key_id=binding["key_id"],
            registration_id=registration,
            generation=generation,
        )

    async def begin_recovery_code(self, pin: str) -> RecoveryCodeIssue:
        if self._pin_gate.busy:
            raise DataProtectionError("protection.access_closed")
        async with self._pin_gate:
            return await self._begin_recovery_code(pin)

    async def _begin_recovery_code(self, pin: str) -> RecoveryCodeIssue:
        """Выдача требует уже открытой защищённой сессии и повторного PIN."""
        if self._lock.locked():
            raise DataProtectionError("protection.access_closed")
        if not isinstance(pin, str) or not is_valid_pin(pin):
            raise DataProtectionError("portable.pin_required")
        try:
            with self.access.authorize("read") as cipher:
                database_id, key_id = cipher.database_id, cipher.key_id
            self.cancel_grant()
            generation, epoch = self._generation, self.access.epoch
            async with self._lock:
                binding, registration = await self._code_binding()
                stored = await asyncio.to_thread(self.repository.get_auth_state)
                if stored is None or (
                    binding["database_id"] != database_id
                    or binding["key_id"] != key_id
                    or not hmac.compare_digest(
                        binding["fingerprint"],
                        _fingerprint(stored.registration_id, stored.pin_record),
                    )
                ):
                    raise DataProtectionError("protection.binding_mismatch")
                self._check_open_code_session(generation, epoch)
                attempts = await asyncio.to_thread(
                    self.repository.pin_attempt_state,
                    sample_clock(
                        self._clock, self._pin_elapsed_clock, self._pin_boot_token
                    ),
                )
                if attempts.lock_seconds_remaining:
                    raise DataProtectionError(
                        "portable.pin_required",
                        lock_seconds_remaining=attempts.lock_seconds_remaining,
                    )
                valid = await asyncio.to_thread(
                    self.pin_hasher.verify, pin, stored.pin_record
                )
                self._check_open_code_session(generation, epoch)
                if not valid:
                    attempts = await asyncio.to_thread(
                        self.repository.register_pin_failure,
                        sample_clock(
                            self._clock, self._pin_elapsed_clock, self._pin_boot_token
                        ),
                    )
                    raise DataProtectionError(
                        "portable.pin_required",
                        lock_seconds_remaining=attempts.lock_seconds_remaining,
                        pin_attempts_remaining=max(
                            0, APP_PIN_MAX_FAILED_ATTEMPTS - attempts.failed_attempts
                        ),
                    )
                await asyncio.to_thread(self.repository.reset_login_attempts)
                self._check_open_code_session(generation, epoch)
                existing = self._code_record(binding)
                code_generation = existing["generation"] + 1 if existing else 1
                if code_generation >= 2**63:
                    raise DataProtectionError()
                code = generate_code()
                normalized = normalize_code(code)
                assert normalized is not None
                attempt = secrets.token_urlsafe(24)
                self._code_issue = _PendingCodeIssue(
                    attempt,
                    self._digest_code(
                        normalized, binding, registration, code_generation
                    ),
                    binding,
                    registration,
                    epoch,
                    generation,
                    code_generation,
                    self._monotonic() + PROOF_TTL_SECONDS,
                )
                return RecoveryCodeIssue(attempt, code)
        except DataProtectionError as error:
            if error.lock_seconds_remaining or error.pin_attempts_remaining is not None:
                raise
            raise DataProtectionError("portable.pin_required") from None
        except DataAccessError:
            raise DataProtectionError("portable.pin_required") from None
        except Exception:
            raise DataProtectionError() from None

    def _check_open_code_session(self, generation: int, epoch: int) -> None:
        self._check_generation(generation)
        if not self.access.unlocked or self.access.epoch != epoch:
            raise DataProtectionError("protection.access_closed")

    def cancel_recovery_code_issue(self) -> None:
        """Отмена не записывает новый verifier и не погашает прежний код."""
        self._code_issue = None

    async def _restore_code_binding(self, binding: dict[str, Any]) -> None:
        """Держит сериализацию до завершения отката даже при повторной отмене UI."""
        restore = asyncio.create_task(self._save_binding(binding))
        while not restore.done():
            try:
                await asyncio.shield(restore)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            restore.result()
        except (Exception, asyncio.CancelledError):
            # При продолжающемся отказе backend известный PIN остаётся прежним.
            # Состояние verifier нельзя объявлять подтверждённым без чтения backend.
            pass

    async def confirm_recovery_code(self, attempt_id: str, value: str) -> None:
        issue = self._code_issue
        if self._lock.locked() or issue is None or attempt_id != issue.attempt_id:
            raise DataProtectionError("portable.issue_expired")
        try:
            async with self._lock:
                self._check_open_code_session(issue.generation, issue.epoch)
                if self._monotonic() >= issue.expires_at:
                    self._code_issue = None
                    raise DataProtectionError("portable.issue_expired")
                normalized = normalize_code(value)
                if normalized is None or not hmac.compare_digest(
                    self._digest_code(
                        normalized,
                        issue.binding,
                        issue.registration_id,
                        issue.code_generation,
                    ),
                    issue.verifier,
                ):
                    raise DataProtectionError("portable.invalid")
                binding, registration = await self._code_binding()
                self._check_open_code_session(issue.generation, issue.epoch)
                if (
                    self._code_issue is not issue
                    or binding != issue.binding
                    or registration != issue.registration_id
                    or self._monotonic() >= issue.expires_at
                ):
                    raise DataProtectionError("portable.issue_expired")
                prepared = dict(binding)
                prepared["recovery_code"] = {
                    "version": 1,
                    "generation": issue.code_generation,
                    "database_id": binding["database_id"],
                    "key_id": binding["key_id"],
                    "registration_id": registration,
                    "state": "active",
                    "verifier": issue.verifier,
                    "failed_attempts": 0,
                    "locked_until": None,
                }
                try:
                    await self._save_binding(prepared)
                    self._check_open_code_session(issue.generation, issue.epoch)
                    if (
                        self._code_issue is not issue
                        or self._monotonic() >= issue.expires_at
                    ):
                        raise DataProtectionError("portable.issue_expired")
                except (Exception, asyncio.CancelledError) as error:
                    # При неоднозначном ACK сохраняем рабочий прежний verifier.
                    # Этот шаг не меняет PIN и не лишает пользователя доступа.
                    await self._restore_code_binding(binding)
                    if isinstance(error, asyncio.CancelledError):
                        self._code_issue = None
                        raise
                    if isinstance(error, DataProtectionError):
                        raise
                    raise DataProtectionError() from None
                self._code_issue = None
        except (DataProtectionError, DataAccessError):
            raise
        except Exception:
            raise DataProtectionError() from None

    async def recover_with_code(self, value: str) -> str:
        """Проверяет доверенный verifier до DEK и выдаёт одноразовое право смены PIN."""
        if self._lock.locked() or self._request is not None:
            raise DataProtectionError("protection.access_closed")
        self.cancel_grant()
        generation, epoch = self._generation, self.access.epoch
        try:
            async with self._lock:
                # Контекст попытки захвачен до первого await, включая старый intent.
                await self.reconcile()
                self._check_generation(generation)
                if self.access.epoch != epoch:
                    raise DataProtectionError("protection.access_closed")
                binding = await self._binding()
                if binding is None or self._code_record(binding) is None:
                    raise DataProtectionError("portable.not_enrolled")
                binding, registration = await self._code_binding()
                self._check_generation(generation)
                if self.access.epoch != epoch:
                    raise DataProtectionError("protection.access_closed")
                record = self._code_record(binding)
                assert record is not None
                if record["state"] != "active":
                    raise DataProtectionError("portable.not_enrolled")
                now = self._clock()
                until = record["locked_until"]
                if until is not None and until > now:
                    raise DataProtectionError("portable.rate_limited")
                normalized = normalize_code(value)
                valid = normalized is not None and hmac.compare_digest(
                    self._digest_code(
                        normalized, binding, registration, record["generation"]
                    ),
                    record["verifier"],
                )
                if not valid:
                    failures = (record["failed_attempts"] if until is None else 0) + 1
                    failed = dict(
                        record,
                        failed_attempts=failures,
                        locked_until=now + LOCK_SECONDS
                        if failures >= MAX_FAILED_ATTEMPTS
                        else None,
                    )
                    await self._save_binding(dict(binding, recovery_code=failed))
                    raise DataProtectionError("portable.invalid")
                identity = await self._identity()
                stored = await asyncio.to_thread(self.repository.get_auth_state)
                current, current_registration = await self._code_binding()
                self._check_generation(generation)
                if (
                    stored is None
                    or self.access.epoch != epoch
                    or current != binding
                    or current_registration != registration
                ):
                    raise DataProtectionError("protection.access_closed")
                cipher, checked_binding = await self._key_after_proof(
                    stored, recovery=True, generation=generation
                )
                self._check_generation(generation)
                if self.access.epoch != epoch or checked_binding != binding:
                    raise DataProtectionError("protection.access_closed")
                token = secrets.token_urlsafe(24)
                self._grant = _RecoveryGrant(
                    token,
                    epoch,
                    identity,
                    registration,
                    cipher,
                    binding,
                    RecoveryProofKind.CODE,
                    generation,
                    self._monotonic() + PROOF_TTL_SECONDS,
                    record["generation"],
                )
                return token
        except (DataProtectionError, DataAccessError):
            raise
        except Exception:
            raise DataProtectionError() from None

    async def reconcile(self) -> None:
        """Доводит выбранную смену PIN из защищённого журнала до одного состояния."""
        self._check_generation(self._generation)
        try:
            binding = await self._binding()
            if binding is None or "pending" not in binding:
                return
            registration_id, record = _parse_record(binding["pending"])
            proof = binding.get("pending_proof")
            if proof is not None:
                if (
                    not isinstance(proof, dict)
                    or set(proof) != {"kind", "code_generation"}
                    or proof["kind"]
                    not in {
                        RecoveryProofKind.SYSTEM.value,
                        RecoveryProofKind.CODE.value,
                    }
                ):
                    raise DataProtectionError("protection.binding_mismatch")
                code_record = self._code_record(binding)
                if proof["kind"] == RecoveryProofKind.CODE.value and (
                    code_record is None
                    or code_record["state"] != "consumed"
                    or type(proof["code_generation"]) is not int
                    or code_record["generation"] != proof["code_generation"]
                    or code_record["registration_id"] != registration_id
                ):
                    raise DataProtectionError("protection.binding_mismatch")
                if (
                    proof["kind"] == RecoveryProofKind.SYSTEM.value
                    and proof["code_generation"] is not None
                ):
                    raise DataProtectionError("protection.binding_mismatch")
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
            completed.pop("pending_proof", None)
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
        # Единственное чтение DEK находится за PIN или явным системным/code proof.
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
        if self._pin_gate.busy:
            raise DataProtectionError("protection.access_closed")
        async with self._pin_gate:
            await self._unlock_checked(pin, stored)

    async def _unlock_checked(self, pin: str, stored: StoredAuthState) -> None:
        if not isinstance(pin, str) or not is_valid_pin(pin):
            raise DataProtectionError("protection.access_closed")
        attempts = await asyncio.to_thread(
            self.repository.pin_attempt_state,
            sample_clock(self._clock, self._pin_elapsed_clock, self._pin_boot_token),
        )
        if attempts.lock_seconds_remaining:
            raise DataProtectionError(
                "portable.pin_required",
                lock_seconds_remaining=attempts.lock_seconds_remaining,
            )
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

    async def recover(self, provider: RecoveryProvider) -> str:
        """Одно системное подтверждение разрешает только выбор нового app PIN."""
        if self._lock.locked() or self._request is not None:
            raise DataProtectionError()
        self.cancel_grant()
        generation = self._generation
        epoch = self.access.epoch
        async with self._lock:
            await self.reconcile()
            self._check_generation(generation)
            if epoch != self.access.epoch:
                raise DataProtectionError("protection.access_closed")
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
                token,
                epoch,
                identity,
                registration_id,
                cipher,
                binding,
                RecoveryProofKind.SYSTEM,
                generation,
                self._monotonic() + PROOF_TTL_SECONDS,
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
            or grant.generation != self._generation
            or self._monotonic() >= grant.expires_at
            or await self._identity() != grant.identity
        ):
            raise DataProtectionError("protection.access_closed")
        generation = self._generation
        async with self._lock:
            try:
                if self._grant is not grant:
                    raise DataProtectionError("protection.access_closed")
                registration_id = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
                if registration_id != grant.registration_id:
                    raise DataProtectionError("protection.binding_mismatch")
                record = await asyncio.to_thread(self.pin_hasher.create_record, pin)
                current = await self._binding()
                if (
                    self._grant is not grant
                    or generation != self._generation
                    or grant.epoch != self.access.epoch
                    or self._monotonic() >= grant.expires_at
                    or await self._identity() != grant.identity
                    or current != grant.binding
                    or await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
                    != grant.registration_id
                ):
                    raise DataProtectionError("protection.access_closed")
                if (
                    self._grant is not grant
                    or generation != self._generation
                    or grant.epoch != self.access.epoch
                    or self._monotonic() >= grant.expires_at
                ):
                    raise DataProtectionError("protection.access_closed")
                prepared = dict(grant.binding)
                if grant.proof_kind is RecoveryProofKind.CODE:
                    enrolled = self._code_record(prepared)
                    if (
                        enrolled is None
                        or enrolled["state"] != "active"
                        or enrolled["generation"] != grant.code_generation
                    ):
                        raise DataProtectionError("protection.access_closed")
                    # Погашение и новый PIN принадлежат одной защищённой записи.
                    consumed = dict(
                        enrolled, state="consumed", failed_attempts=0, locked_until=None
                    )
                    consumed.pop("verifier")
                    prepared["recovery_code"] = consumed
                prepared["pending"] = _record_json(grant.registration_id, record)
                prepared["pending_proof"] = {
                    "kind": grant.proof_kind.value,
                    "code_generation": grant.code_generation,
                }
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
        self._code_issue = None
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
