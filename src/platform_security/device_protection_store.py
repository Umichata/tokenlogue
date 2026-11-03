"""Small device-local check history, independent of portable chat profiles."""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import threading
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator, Literal

from platform_security.local_protection import (
    CheckState,
    DeviceCheckRecord,
    DeviceProtectionHistory,
)

_APP_ID = b"io.github.umichata.tokenlogue/device-protection/v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_CONTRACT = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_RECORD_FIELDS = {"state", "checked_at", "last_success_at", "contract", "origin"}
_MAX_TIME = 253402300799


class ProtectionStoreError(RuntimeError):
    """Storage is unavailable, corrupt or not safely bound to this OS account."""


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for name, item in pairs:
        if name in value:
            raise ProtectionStoreError("invalid_history")
        value[name] = item
    return value


def _record(value: object) -> DeviceCheckRecord | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != _RECORD_FIELDS:
        raise ProtectionStoreError("invalid_history")
    checked = value["checked_at"]
    success = value["last_success_at"]
    contract = value["contract"]
    if (
        value["state"] not in ("confirmed", "problem")
        or type(checked) is not int
        or not 0 < checked <= _MAX_TIME
        or (
            success is not None
            and (type(success) is not int or not 0 < success <= checked)
        )
        or not isinstance(contract, str)
        or not _CONTRACT.fullmatch(contract)
        or value["origin"] not in ("manual", "observed")
        or (value["state"] == "confirmed" and success != checked)
    ):
        raise ProtectionStoreError("invalid_history")
    return DeviceCheckRecord(
        CheckState(value["state"]), checked, success, contract, value["origin"]
    )


def _encode(record: DeviceCheckRecord | None) -> dict[str, object] | None:
    if record is None:
        return None
    value = {
        "state": record.state.value,
        "checked_at": record.checked_at,
        "last_success_at": record.last_success_at,
        "contract": record.contract,
        "origin": record.origin,
    }
    _record(value)
    return value


class DeviceProtectionStore:
    """Atomic per-mechanism merge under a thread and cross-process file lock.

    The random installation identity lives outside the chat directory. An HMAC
    additionally binds it to machine-id and the OS uid. Raw identifiers never
    leave memory. Copying preferences or even this directory to another machine
    cannot select the previous machine's history. These are advisory metadata,
    never credentials or an authorization input. Profile deletion does not
    delete device history or extend its destructive file allowlist.
    """

    def __init__(self, directory: Path, *, machine_identity: bytes, user_id: int):
        if not re.fullmatch(rb"[0-9a-f]{32}", machine_identity):
            raise ProtectionStoreError("binding_unavailable")
        if type(user_id) is not int or user_id < 0:
            raise ProtectionStoreError("binding_unavailable")
        self.directory = directory
        self._machine_identity = machine_identity
        self._user_id = user_id
        self._mutex = threading.Lock()

    @classmethod
    def for_current_linux_account(cls) -> DeviceProtectionStore:
        """Only called by the Linux composition, never during module import."""
        try:
            with Path("/etc/machine-id").open("rb") as stream:
                machine = stream.read(34).strip()
            state = os.environ.get("XDG_STATE_HOME", "")
            base = (
                Path(state)
                if state and Path(state).is_absolute()
                else Path.home() / ".local/state"
            )
            return cls(
                base / "io.github.umichata.tokenlogue/device-protection",
                machine_identity=machine,
                user_id=os.getuid(),
            )
        except (OSError, ValueError) as error:
            raise ProtectionStoreError("binding_unavailable") from error

    @staticmethod
    def _check_file(descriptor: int) -> None:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
            or info.st_size > 8192
        ):
            raise ProtectionStoreError("unsafe_history")

    @contextmanager
    def _locked(self) -> Iterator[int]:
        with self._mutex:
            try:
                self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                directory = os.open(
                    self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                )
                try:
                    info = os.fstat(directory)
                    if info.st_uid != os.getuid() or info.st_mode & 0o077:
                        raise ProtectionStoreError("unsafe_history")
                    lock = os.open(
                        ".writer.lock",
                        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=directory,
                    )
                    try:
                        self._check_file(lock)
                        fcntl.flock(lock, fcntl.LOCK_EX)
                        yield directory
                    finally:
                        os.close(lock)
                finally:
                    os.close(directory)
            except (OSError, ValueError, TypeError) as error:
                raise ProtectionStoreError("history_unavailable") from error

    def _read(self, directory: int, name: str) -> object | None:
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            self._check_file(descriptor)
            with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as stream:
                return json.load(stream, object_pairs_hook=_unique_fields)
        except (UnicodeError, ValueError) as error:
            raise ProtectionStoreError("invalid_history") from error
        finally:
            os.close(descriptor)

    def _write(self, directory: int, name: str, value: object) -> None:
        temporary = ".pending-" + secrets.token_hex(16)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    def _binding(self, directory: int) -> str:
        value = self._read(directory, "identity.json")
        if value is None:
            value = {"version": 1, "installation": secrets.token_hex(32)}
            self._write(directory, "identity.json", value)
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "installation"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or not isinstance(value["installation"], str)
            or not _HEX.fullmatch(value["installation"])
        ):
            raise ProtectionStoreError("invalid_identity")
        material = (
            _APP_ID
            + b"\0"
            + self._machine_identity
            + b"\0"
            + str(self._user_id).encode("ascii")
        )
        return hmac.new(
            bytes.fromhex(value["installation"]), material, hashlib.sha256
        ).hexdigest()

    def _load(self, directory: int, binding: str) -> DeviceProtectionHistory:
        value = self._read(directory, "history-" + binding + ".json")
        if value is None:
            return DeviceProtectionHistory()
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "binding", "screen", "sleep"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or value["binding"] != binding
        ):
            raise ProtectionStoreError("invalid_history")
        return DeviceProtectionHistory(
            _record(value["screen"]), _record(value["sleep"])
        )

    def load(self) -> DeviceProtectionHistory:
        with self._locked() as directory:
            return self._load(directory, self._binding(directory))

    def save(
        self, mechanism: Literal["screen", "sleep"], record: DeviceCheckRecord
    ) -> DeviceProtectionHistory:
        if mechanism not in ("screen", "sleep"):
            raise ProtectionStoreError("invalid_mechanism")
        _encode(record)
        with self._locked() as directory:
            binding = self._binding(directory)
            history = self._load(directory, binding)
            old = getattr(history, mechanism)
            # A late worker cannot overwrite newer evidence from another process.
            if old is not None and old.checked_at > record.checked_at:
                raise ProtectionStoreError("stale_result")
            if (
                old is not None
                and old.checked_at == record.checked_at
                and old.state is CheckState.PROBLEM
                and record.state is CheckState.CONFIRMED
            ):
                # Whole-second timestamps cannot order conflicting concurrent
                # completions. Preserve the failure and expose a save warning.
                raise ProtectionStoreError("stale_result")
            if record.state is CheckState.PROBLEM and old is not None:
                successes = [
                    v
                    for v in (record.last_success_at, old.last_success_at)
                    if v is not None
                ]
                record = replace(
                    record, last_success_at=max(successes) if successes else None
                )
            history = replace(history, **{mechanism: record})
            self._write(
                directory,
                "history-" + binding + ".json",
                {
                    "version": 1,
                    "binding": binding,
                    "screen": _encode(history.screen),
                    "sleep": _encode(history.sleep),
                },
            )
            return history
