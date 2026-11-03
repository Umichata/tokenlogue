"""Единая политика app PIN без зависимостей от UI, KDF и SecureStorage.

SQLite locked_until сохраняет прежний numeric deadline либо versioned JSON.
Schema 6/7 не меняется. CLOCK_BOOTTIME продолжает срок после сна и restart.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

APP_PIN_MAX_FAILED_ATTEMPTS = 3
APP_PIN_LOCK_SECONDS = 300


class PinCheckGate:
    """Один профиль не проверяет PIN параллельно в разных маршрутах."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task | None = None
        self._depth = 0

    @property
    def busy(self) -> bool:
        return self._lock.locked() and self._owner is not asyncio.current_task()

    async def __aenter__(self):
        if self._owner is asyncio.current_task():
            self._depth += 1
            return self
        await self._lock.acquire()
        self._owner = asyncio.current_task()
        self._depth = 1
        return self

    async def __aexit__(self, *_exc) -> None:
        self._depth -= 1
        if self._depth == 0:
            self._owner = None
            self._lock.release()


_GATES: dict[str, PinCheckGate] = {}


def pin_check_gate(repository: object) -> PinCheckGate:
    path = getattr(repository, "path", None)
    key = (
        str(Path(path).resolve())
        if path is not None
        else f"repository:{id(repository)}"
    )
    return _GATES.setdefault(key, PinCheckGate())


@dataclass(frozen=True)
class PinClockSample:
    wall: float
    elapsed: float
    boot_token: str | None


@dataclass(frozen=True)
class PinLock:
    wall_deadline: float
    elapsed_deadline: float
    last_elapsed: float
    budget: float
    boot_token: str | None

    def encode(self) -> str:
        return json.dumps(
            dict(
                version=1,
                wall_deadline=self.wall_deadline,
                elapsed_deadline=self.elapsed_deadline,
                last_elapsed=self.last_elapsed,
                budget=self.budget,
                boot_token=self.boot_token,
            ),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


@lru_cache(maxsize=1)
def system_boot_token() -> str | None:
    try:
        value = (
            Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        )
        if len(value) == 36 and all(char in "0123456789abcdef-" for char in value):
            return hashlib.sha256(value.encode("ascii")).hexdigest()
    except (OSError, UnicodeError):
        pass
    # Some Android namespaces hide boot_id. Elapsed uptime still bounds the
    # budget, but no claim of independently identifying the boot is made there.
    return None


def elapsed_seconds() -> float:
    return time.clock_gettime(getattr(time, "CLOCK_BOOTTIME", 7))


def sample_clock(
    wall_clock: Callable[[], float],
    elapsed_clock: Callable[[], float] | None = None,
    boot_token: Callable[[], str | None] | None = None,
) -> PinClockSample:
    wall = float(wall_clock())
    elapsed = float(
        elapsed_clock()
        if elapsed_clock is not None
        else elapsed_seconds()
        if wall_clock is time.time
        else wall
    )
    token = boot_token() if boot_token is not None else system_boot_token()
    if (
        not math.isfinite(wall)
        or not math.isfinite(elapsed)
        or elapsed < 0
        or (
            token is not None
            and (not isinstance(token, str) or not token or len(token) > 128)
        )
    ):
        raise ValueError("pin_clock_unavailable")
    return PinClockSample(wall, elapsed, token)


def decode_lock(raw: object) -> tuple[float | None, PinLock | None]:
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        deadline = float(raw)
        if not math.isfinite(deadline):
            raise ValueError("invalid_pin_deadline")
        return deadline, None
    if not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError("invalid_pin_deadline")
    value = json.loads(raw)
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "version",
            "wall_deadline",
            "elapsed_deadline",
            "last_elapsed",
            "budget",
            "boot_token",
        }
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        raise ValueError("invalid_pin_deadline")
    for name in ("wall_deadline", "elapsed_deadline", "last_elapsed", "budget"):
        if type(value[name]) not in {int, float} or not math.isfinite(value[name]):
            raise ValueError("invalid_pin_deadline")
    if (
        value["last_elapsed"] < 0
        or value["elapsed_deadline"] < value["last_elapsed"]
        or not 0 < value["budget"] <= APP_PIN_LOCK_SECONDS
        or (
            value["boot_token"] is not None
            and (
                not isinstance(value["boot_token"], str)
                or not value["boot_token"]
                or len(value["boot_token"]) > 128
            )
        )
    ):
        raise ValueError("invalid_pin_deadline")
    lock = PinLock(
        float(value["wall_deadline"]),
        float(value["elapsed_deadline"]),
        float(value["last_elapsed"]),
        float(value["budget"]),
        value["boot_token"],
    )
    return lock.wall_deadline, lock


def arm_lock(sample: PinClockSample, seconds: float = APP_PIN_LOCK_SECONDS) -> PinLock:
    return PinLock(
        sample.wall + seconds,
        sample.elapsed + seconds,
        sample.elapsed,
        seconds,
        sample.boot_token,
    )


def normalize_attempts(
    failed: int, raw: object, sample: PinClockSample
) -> tuple[int, float | str | None, int]:
    if type(failed) is not int or failed < 0:
        raise ValueError("invalid_pin_attempts")
    deadline, lock = decode_lock(raw)
    if lock is None:
        if deadline is not None and deadline > sample.wall:
            lock = arm_lock(sample, min(APP_PIN_LOCK_SECONDS, deadline - sample.wall))
        elif failed >= APP_PIN_MAX_FAILED_ATTEMPTS and (
            deadline is None or failed in {3, 4}
        ):
            # Old policy allowed three/four failures without a lock. Do not give
            # another fresh set merely because the application was upgraded.
            lock = arm_lock(sample)
        elif deadline is not None:
            return 0, None, 0
        else:
            return failed, None, 0
    else:
        changed_boot = (
            lock.boot_token is not None
            and sample.boot_token is not None
            and lock.boot_token != sample.boot_token
        )
        if changed_boot or (
            sample.elapsed < lock.last_elapsed
            and (lock.boot_token is None or sample.boot_token is None)
        ):
            remaining = max(0.0, lock.budget - sample.elapsed)
            elapsed_deadline = sample.elapsed + remaining
        elif sample.elapsed < lock.last_elapsed:
            # Impossible for a normal kernel clock. Preserve only the remaining
            # budget once, without renewing it on subsequent polls.
            remaining = lock.budget
            elapsed_deadline = sample.elapsed + remaining
        else:
            remaining = max(
                0.0, min(lock.budget, lock.elapsed_deadline - sample.elapsed)
            )
            elapsed_deadline = lock.elapsed_deadline
        if remaining <= 0:
            return 0, None, 0
        lock = PinLock(
            sample.wall + remaining,
            elapsed_deadline,
            sample.elapsed,
            remaining,
            sample.boot_token,
        )
    return APP_PIN_MAX_FAILED_ATTEMPTS, lock.encode(), math.ceil(lock.budget)


def format_lock_time(seconds: int) -> str:
    minutes, remainder = divmod(max(0, seconds), 60)
    return f"{minutes:02d}:{remainder:02d}"
