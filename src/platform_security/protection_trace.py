"""Optional, bounded protection metadata without credentials or profile contents."""

from __future__ import annotations

import json
import os
import secrets
import stat
import time
from pathlib import Path

TRACE_DIRECTORY_ENV = "TOKENLOGUE_PROTECTION_TRACE_DIR"
_MAX_BYTES = 256 * 1024
_EVENTS = {
    "trace_started",
    "observer_changed",
    "prepare_started",
    "prepare_finished",
    "trial_started",
    "request_started",
    "request_finished",
    "screen_locked",
    "screen_inactive",
    "normal_reaction",
    "app_state",
    "screen_finished",
    "sleep_finished",
    "sleep_prepare_started",
    "sleep_request_started",
    "sleep_request_finished",
    "sleep_normal_reaction",
    "sleep_resume",
    "closed",
    "app_started",
    "key_submit_started",
    "key_result",
    "pin_setup_build",
    "pin_setup_shown",
    "pin_setup_failed",
    "key_entry_build",
    "key_entry_shown",
    "system_event",
}
_REASONS = {
    "not_checked",
    "observer_changed",
    "screen_test_preparing",
    "preparation_timeout",
    "activation_unavailable",
    "activation_untrusted",
    "locker_contract_unavailable",
    "already_locked_or_unconfirmed",
    "request_unavailable",
    "observation_unavailable",
    "state_unavailable",
    "session_changed",
    "screen_test_running",
    "awaiting_unlock",
    "timeout",
    "unlock_timeout",
    "pin_timeout",
    "app_state_unavailable",
    "normal_reaction_unproven",
    "normal_seal_failed",
    "locked_state_unproven",
    "cancelled",
    "screen_confirmed",
    "sleep_cycle_running",
    "actual_suspend_unproven",
    "sleep_confirmed",
    "sleep_test_preparing",
    "sleep_request_running",
    "sleep_unavailable",
    "sleep_permission_required",
    "sleep_inhibited",
    "contract_changed",
    "closed",
}
_BOOL_FIELDS = {
    "session_open",
    "data_open",
    "pin_visible",
    "normal_receipt",
    "was_open",
    "locked",
    "screen_connected",
    "sleep_connected",
    "page_linux",
    "key_view",
    "pin_setup_view",
    "pin_setup_visible",
    "same_key_view",
    "disposed",
    "suspending",
    "in_background",
    "setup_token_present",
    "actual_suspend",
}
_INT_FIELDS = {"test", "generation", "app_generation", "revision"}
_AUTH_STATUSES = {
    "setup_required",
    "pin_required",
    "pin_choice_required",
    "recovery_code_issued",
    "recovery_code_saved",
    "profile_deleted",
    "authenticated",
    "invalid_pin",
    "locked",
    "busy",
    "invalid_key",
    "network_error",
    "timeout",
    "tls_error",
    "service_error",
    "invalid_response",
    "storage_error",
    "invalid_state",
}
_EXCEPTION_CLASSES = {
    "TypeError",
    "ValueError",
    "AttributeError",
    "RuntimeError",
    "AssertionError",
    "RecursionError",
    "KeyError",
    "ImportError",
    "ModuleNotFoundError",
    "OSError",
    "PermissionError",
    "FileNotFoundError",
    "TimeoutError",
    "NotImplementedError",
}
_SYSTEM_REASONS = {
    "screen_lock",
    "sleep",
    "session_change",
    "shutdown",
    "trust_lost",
    "protection_emergency",
    "language_change",
}


class ProtectionTrace:
    """Write only allowlisted metadata to a new private file in an explicit directory."""

    def __init__(self, directory: Path) -> None:
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError("Trace directory must be private and owned by this user")
        self.path = directory / (
            f"protection-{os.getpid()}-{secrets.token_hex(6)}.jsonl"
        )
        self._descriptor: int | None = os.open(
            self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        self._started = time.monotonic()
        self._bytes = 0
        self({"event": "trace_started"})

    def __call__(self, record: dict[str, object]) -> None:
        event = record.get("event")
        if (
            self._descriptor is None
            or not isinstance(event, str)
            or event not in _EVENTS
        ):
            return
        safe: dict[str, object] = {
            "event": record["event"],
            "seconds": round(time.monotonic() - self._started, 6),
        }
        for key, value in record.items():
            if key in _BOOL_FIELDS and type(value) is bool:
                safe[key] = value
            elif key in _INT_FIELDS and type(value) is int and 0 <= value < 2**63:
                safe[key] = value
            elif key == "reason" and isinstance(value, str) and value in _REASONS:
                safe[key] = value
            elif (
                key == "state"
                and isinstance(value, str)
                and value
                in {
                    "untested",
                    "running",
                    "confirmed",
                    "problem",
                }
            ):
                safe[key] = value
            elif (
                key == "mechanism"
                and isinstance(value, str)
                and value in {"screen", "sleep"}
            ):
                safe[key] = value
            elif isinstance(value, str) and (
                (key == "auth_status" and value in _AUTH_STATUSES)
                or (key == "exception_class" and value in _EXCEPTION_CLASSES)
                or (key == "system_reason" and value in _SYSTEM_REASONS)
            ):
                safe[key] = value
        encoded = (json.dumps(safe, separators=(",", ":")) + "\n").encode()
        if self._bytes + len(encoded) > _MAX_BYTES:
            self.close()
            return
        try:
            os.write(self._descriptor, encoded)
            self._bytes += len(encoded)
        except OSError:
            self.close()

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            os.close(descriptor)


def protection_trace_from_environment() -> ProtectionTrace | None:
    directory = os.environ.get(TRACE_DIRECTORY_ENV)
    if not directory:
        return None
    try:
        return ProtectionTrace(Path(directory))
    except (OSError, ValueError):
        return None
