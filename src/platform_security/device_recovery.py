"""Одноразовое подтверждение устройства через собственный Flet service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum

from flet.controls.base_control import control
from flet.controls.services.service import Service


class RecoveryStatus(StrEnum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    ERROR = "error"
    EXPIRED = "expired"
    BUSY = "busy"


@dataclass(frozen=True)
class RecoveryRequest:
    attempt_id: str
    database_id: str
    epoch: int
    reason: str
    title: str
    cancel_label: str


@dataclass(frozen=True)
class RecoveryResult:
    request: RecoveryRequest
    status: RecoveryStatus


@control("TokenlogueDeviceRecovery")
class DeviceRecovery(Service):
    """Проверка устройства не извлекает ключи и не открывает базу самостоятельно."""

    _active_attempt: str | None = field(
        default=None, init=False, repr=False, metadata={"skip": True}
    )
    _used_attempts: set[str] = field(
        default_factory=set, init=False, repr=False, metadata={"skip": True}
    )

    @property
    def challenge_in_progress(self) -> bool:
        return self._active_attempt is not None

    async def sync_secure_storage(self) -> None:
        """Дожидается Android commit без чтения ключей через этот bridge."""
        try:
            result = await self._invoke_method("sync_secure_storage", timeout=30)
        except Exception:
            raise RuntimeError("secure_storage_sync_failed") from None
        if result is not True:
            raise RuntimeError("secure_storage_sync_failed")

    async def supports_recovery(self) -> bool:
        """Сведения о платформе не являются разрешением доступа к базе."""
        try:
            value = await self._invoke_method("capabilities", timeout=10)
            return bool(
                isinstance(value, dict)
                and type(value.get("api_level")) is int
                and value["api_level"] >= 30
                and value.get("recovery_supported") is True
            )
        except Exception:
            return False

    async def authenticate(
        self, request: RecoveryRequest, *, timeout: float = 120
    ) -> RecoveryResult:
        if request.attempt_id in self._used_attempts:
            return RecoveryResult(request, RecoveryStatus.EXPIRED)
        if self.challenge_in_progress:
            return RecoveryResult(request, RecoveryStatus.BUSY)
        if (
            not request.attempt_id
            or not request.database_id
            or request.epoch < 0
            or not request.reason
            or not request.title
            or not request.cancel_label
        ):
            return RecoveryResult(request, RecoveryStatus.ERROR)
        self._used_attempts.add(request.attempt_id)
        self._active_attempt = request.attempt_id
        try:
            reply = await asyncio.wait_for(
                self._invoke_method(
                    "authenticate",
                    {
                        "attempt_id": request.attempt_id,
                        "database_id": request.database_id,
                        "epoch": request.epoch,
                        "reason": request.reason,
                        "title": request.title,
                        "cancel_label": request.cancel_label,
                    },
                    timeout=timeout + 1,
                ),
                timeout,
            )
            if self._active_attempt != request.attempt_id:
                return RecoveryResult(request, RecoveryStatus.EXPIRED)
            if not isinstance(reply, dict):
                return RecoveryResult(request, RecoveryStatus.ERROR)
            if (
                reply.get("attempt_id") != request.attempt_id
                or reply.get("database_id") != request.database_id
                or type(reply.get("epoch")) is not int
                or reply.get("epoch") != request.epoch
            ):
                return RecoveryResult(request, RecoveryStatus.EXPIRED)
            try:
                status = RecoveryStatus(reply.get("status"))
            except (ValueError, TypeError):
                status = RecoveryStatus.ERROR
            return RecoveryResult(request, status)
        except TimeoutError:
            await self.cancel(request.attempt_id)
            return RecoveryResult(request, RecoveryStatus.TIMEOUT)
        except asyncio.CancelledError:
            await self.cancel(request.attempt_id)
            raise
        except Exception:
            return RecoveryResult(request, RecoveryStatus.ERROR)
        finally:
            if self._active_attempt == request.attempt_id:
                self._active_attempt = None

    async def cancel(self, attempt_id: str) -> None:
        if self._active_attempt != attempt_id:
            return
        # Отзыв действует до ожидания нативной отмены даже на старом Android.
        self._active_attempt = None
        try:
            await self._invoke_method("cancel", {"attempt_id": attempt_id}, timeout=5)
        except Exception:
            pass
