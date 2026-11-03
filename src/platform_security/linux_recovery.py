"""Свежий auth_self через настоящую системную polkit authority Linux."""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_security.device_recovery import (
    RecoveryRequest,
    RecoveryResult,
    RecoveryStatus,
)
from platform_security.linux_dbus import (
    BusConnection,
    DBusError,
    DBusReply,
    DBusTransport,
    verify_system_service,
)

ACTION_ID = "io.github.umichata.tokenlogue.recover-pin"
POLICY_NAME = "io.github.umichata.tokenlogue.policy"
POLICY_SHA256 = "6a950d4274d281ab0dff137fe68d3722d7c7872ccd0f897439cf9f6ed3faed53"
_POLKIT = "org.freedesktop.PolicyKit1"
_AUTHORITY = "/org/freedesktop/PolicyKit1/Authority"
_AUTHORITY_INTERFACE = "org.freedesktop.PolicyKit1.Authority"
_LOGIND = "org.freedesktop.login1"
_LOGIN_PATH = "/org/freedesktop/login1"
_DBUS = "org.freedesktop.DBus"


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_time: int
    uid: int

    def subject(self) -> list[Any]:
        # uid именно int32, как polkit_unix_process_new_for_owner в polkit 124.
        return [
            "unix-process",
            {
                "pid": ("u", self.pid),
                "start-time": ("t", self.start_time),
                "uid": ("i", self.uid),
            },
        ]


@dataclass(frozen=True)
class _Session:
    owner: str
    path: str
    identifier: str
    uid: int


@dataclass
class _Operation:
    bus: DBusTransport | None = None
    owner: str | None = None
    cancellation_id: str | None = None


def _process_identity() -> ProcessIdentity:
    pid, uid = os.getpid(), os.getuid()
    if uid == 0 or os.geteuid() != uid:
        raise DBusError("session_unavailable")
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    start = int(fields[19])
    statuses = Path(f"/proc/{pid}/status").read_text().splitlines()
    uid_line = next(line for line in statuses if line.startswith("Uid:"))
    if any(int(value) != uid for value in uid_line.split()[1:]):
        raise DBusError("session_unavailable")
    if start <= 0:
        raise DBusError("session_unavailable")
    return ProcessIdentity(pid, start, uid)


def _authority_uids() -> set[int]:
    """polkit 124 штатно сбрасывает root до отдельного polkitd UID."""
    path = Path("/etc/passwd")
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise DBusError("transport_unavailable")
    allowed = {0}
    for line in path.read_text().splitlines():
        fields = line.split(":")
        if len(fields) == 7 and fields[0] == "polkitd":
            uid = int(fields[2])
            if uid <= 0 or fields[6] not in (
                "/usr/sbin/nologin",
                "/sbin/nologin",
                "/bin/false",
            ):
                raise DBusError("transport_unavailable")
            allowed.add(uid)
    return allowed


def _verify_installed_policy() -> None:
    path = Path("/usr/share/polkit-1/actions") / POLICY_NAME
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise DBusError("policy_missing") from None
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o644
        or info.st_nlink != 1
        or info.st_size > 16384
    ):
        raise DBusError("policy_unsafe")
    for parent in (path.parent, path.parent.parent, Path("/usr/share"), Path("/usr")):
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise DBusError("policy_unsafe")
    if hashlib.sha256(path.read_bytes()).hexdigest() != POLICY_SHA256:
        raise DBusError("policy_unsafe")


class LinuxRecovery:
    """Подтверждение не читает SQLite, Secret Service или API-ключ."""

    def __init__(self, *, _test_bus_factory: Callable[[], DBusTransport] | None = None):
        self._bus_factory = _test_bus_factory or BusConnection.system
        self._active_attempt: str | None = None
        self._used_attempts: set[str] = set()
        self._operation: _Operation | None = None
        self._disposed = False
        self.unavailable_reason = "transport_unavailable"

    @property
    def challenge_in_progress(self) -> bool:
        return self._active_attempt is not None

    async def _daemon(self, bus: DBusTransport, member: str, name: str) -> DBusReply:
        reply = await bus.call(
            _DBUS, "/org/freedesktop/DBus", _DBUS, member, "s", [name]
        )
        if reply.sender != _DBUS:
            raise DBusError("transport_unavailable")
        return reply

    async def _owner(self, bus: DBusTransport, name: str, uids: set[int]) -> str:
        reply = await self._daemon(bus, "GetNameOwner", name)
        if (
            reply.signature != "s"
            or len(reply.body) != 1
            or not isinstance(reply.body[0], str)
            or not reply.body[0].startswith(":")
        ):
            raise DBusError("transport_unavailable")
        owner = reply.body[0]
        credentials = await self._daemon(bus, "GetConnectionUnixUser", owner)
        if (
            credentials.signature != "u"
            or len(credentials.body) != 1
            or type(credentials.body[0]) is not int
            or credentials.body[0] not in uids
        ):
            raise DBusError("transport_unavailable")
        await verify_system_service(bus, name, owner, credentials.body[0])
        return owner

    async def _session(self, bus: DBusTransport, identity: ProcessIdentity) -> _Session:
        owner = await self._owner(bus, _LOGIND, {0})
        reply = await bus.call(
            owner,
            _LOGIN_PATH,
            f"{_LOGIND}.Manager",
            "GetSessionByPID",
            "u",
            [identity.pid],
        )
        if (
            reply.sender != owner
            or reply.signature != "o"
            or len(reply.body) != 1
            or not isinstance(reply.body[0], str)
            or not reply.body[0].startswith(f"{_LOGIN_PATH}/session/")
        ):
            raise DBusError("session_unavailable")
        path = reply.body[0]
        reply = await bus.call(
            owner, path, f"{_DBUS}.Properties", "GetAll", "s", [f"{_LOGIND}.Session"]
        )
        if reply.sender != owner or reply.signature != "a{sv}" or len(reply.body) != 1:
            raise DBusError("session_unavailable")
        properties = reply.body[0]
        if not isinstance(properties, dict):
            raise DBusError("session_unavailable")
        user = properties.get("User")
        identifier = properties.get("Id")
        if (
            not isinstance(user, (list, tuple))
            or len(user) != 2
            or type(user[0]) is not int
            or user[0] != identity.uid
            or properties.get("Active") is not True
            or properties.get("Remote") is not False
            or properties.get("LockedHint") is not False
            or properties.get("State") != "active"
            or properties.get("Class") != "user"
            or properties.get("Type") not in ("x11", "wayland")
            or not isinstance(identifier, str)
            or not identifier
        ):
            raise DBusError("session_unavailable")
        return _Session(owner, path, identifier, identity.uid)

    async def _authority_call(
        self,
        bus: DBusTransport,
        owner: str,
        member: str,
        signature: str = "",
        body: list[Any] | None = None,
        *,
        timeout: float = 10,
    ) -> DBusReply:
        reply = await bus.call(
            owner,
            _AUTHORITY,
            _AUTHORITY_INTERFACE,
            member,
            signature,
            body,
            timeout=timeout,
        )
        if reply.sender != owner:
            raise DBusError("transport_unavailable")
        return reply

    async def _policy(self, bus: DBusTransport, owner: str) -> None:
        _verify_installed_policy()
        reply = await self._authority_call(bus, owner, "EnumerateActions", "s", ["C"])
        if reply.signature != "a(ssssssuuua{ss})" or len(reply.body) != 1:
            raise DBusError("policy_unsafe")
        actions = reply.body[0]
        if not isinstance(actions, list):
            raise DBusError("policy_unsafe")
        own = [
            action
            for action in actions
            if isinstance(action, list) and action and action[0] == ACTION_ID
        ]
        if len(own) != 1 or len(own[0]) != 10:
            raise DBusError("policy_missing")
        action = own[0]
        if (
            any(type(value) is not int for value in action[6:9])
            or action[6:9] != [0, 0, 1]
            or action[9] != {}
        ):
            raise DBusError("policy_unsafe")

    async def _temporary(
        self, bus: DBusTransport, owner: str, session: _Session
    ) -> None:
        reply = await self._authority_call(
            bus,
            owner,
            "EnumerateTemporaryAuthorizations",
            "(sa{sv})",
            [["unix-session", {"session-id": ("s", session.identifier)}]],
        )
        if (
            reply.signature != "a(ss(sa{sv})tt)"
            or len(reply.body) != 1
            or not isinstance(reply.body[0], list)
        ):
            raise DBusError("authorization_unsafe")
        for authorization in reply.body[0]:
            if not isinstance(authorization, list) or len(authorization) != 5:
                raise DBusError("authorization_unsafe")
            if authorization[1] == ACTION_ID:
                raise DBusError("authorization_unsafe")

    async def _check(
        self,
        bus: DBusTransport,
        owner: str,
        identity: ProcessIdentity,
        *,
        interactive: bool,
        cancellation_id: str,
        timeout: float = 10,
    ) -> tuple[bool, bool, dict[str, str]]:
        # Без details непривилегированный субъект проверяет только самого себя.
        reply = await self._authority_call(
            bus,
            owner,
            "CheckAuthorization",
            "(sa{sv})sa{ss}us",
            [identity.subject(), ACTION_ID, {}, int(interactive), cancellation_id],
            timeout=timeout,
        )
        if reply.signature != "(bba{ss})" or len(reply.body) != 1:
            raise DBusError("authorization_unsafe")
        result = reply.body[0]
        if (
            not isinstance(result, list)
            or len(result) != 3
            or type(result[0]) is not bool
            or type(result[1]) is not bool
            or not isinstance(result[2], dict)
            or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in result[2].items()
            )
        ):
            raise DBusError("authorization_unsafe")
        details = result[2]
        # Неизвестный structured detail не интерпретируется как свежий proof.
        if set(details) - {"polkit.dismissed"}:
            raise DBusError("authorization_unsafe")
        return result[0], result[1], details

    async def _fresh_preflight(
        self,
        bus: DBusTransport,
        owner: str,
        identity: ProcessIdentity,
    ) -> None:
        authorized, challenge, details = await self._check(
            bus,
            owner,
            identity,
            interactive=False,
            cancellation_id=f"tokenlogue-preflight-{secrets.token_hex(16)}",
        )
        if authorized or not challenge or details:
            raise DBusError("authorization_unsafe")

    async def _prepare(
        self, bus: DBusTransport
    ) -> tuple[ProcessIdentity, _Session, str]:
        identity = _process_identity()
        session = await self._session(bus, identity)
        owner = await self._owner(bus, _POLKIT, _authority_uids())
        await self._policy(bus, owner)
        await self._temporary(bus, owner, session)
        await self._fresh_preflight(bus, owner, identity)
        return identity, session, owner

    def _reason(self, error: Exception) -> None:
        reason = str(error)
        allowed = {
            "policy_missing",
            "policy_unsafe",
            "session_unavailable",
            "authorization_unsafe",
            "agent_unavailable",
            "transport_unavailable",
        }
        self.unavailable_reason = (
            reason if reason in allowed else "transport_unavailable"
        )

    async def supports_recovery(self) -> bool:
        if self._disposed:
            return False
        bus: DBusTransport | None = None
        try:
            _verify_installed_policy()
            bus = self._bus_factory()
            await self._prepare(bus)
            self.unavailable_reason = ""
            return True
        except Exception as error:
            self._reason(error)
            return False
        finally:
            if bus is not None:
                bus.close()

    async def _authenticate(
        self, request: RecoveryRequest, operation: _Operation
    ) -> RecoveryStatus:
        _verify_installed_policy()
        bus = self._bus_factory()
        operation.bus = bus
        identity, session, owner = await self._prepare(bus)
        if self._active_attempt != request.attempt_id:
            return RecoveryStatus.EXPIRED
        operation.owner = owner
        cancellation_id = f"tokenlogue-{secrets.token_hex(24)}"
        operation.cancellation_id = cancellation_id
        authorized, challenge, details = await self._check(
            bus,
            owner,
            identity,
            interactive=True,
            cancellation_id=cancellation_id,
            timeout=3600,
        )
        if self._active_attempt != request.attempt_id:
            return RecoveryStatus.EXPIRED
        if not authorized:
            if details.get("polkit.dismissed"):
                return RecoveryStatus.CANCELLED
            if challenge:
                self.unavailable_reason = "agent_unavailable"
                return RecoveryStatus.UNAVAILABLE
            return RecoveryStatus.ERROR
        if challenge or details:
            raise DBusError("authorization_unsafe")
        # После prompt неизменны process, session, authority, policy и отсутствие cache.
        if (
            _process_identity() != identity
            or await self._session(bus, identity) != session
            or await self._owner(bus, _POLKIT, _authority_uids()) != owner
        ):
            return RecoveryStatus.EXPIRED
        await self._policy(bus, owner)
        await self._temporary(bus, owner, session)
        await self._fresh_preflight(bus, owner, identity)
        if self._active_attempt != request.attempt_id:
            return RecoveryStatus.EXPIRED
        self.unavailable_reason = ""
        return RecoveryStatus.SUCCESS

    async def authenticate(
        self,
        request: RecoveryRequest,
        *,
        timeout: float = 120,
    ) -> RecoveryResult:
        if self._disposed:
            return RecoveryResult(request, RecoveryStatus.UNAVAILABLE)
        if request.attempt_id in self._used_attempts:
            return RecoveryResult(request, RecoveryStatus.EXPIRED)
        if self.challenge_in_progress:
            return RecoveryResult(request, RecoveryStatus.BUSY)
        if (
            not request.attempt_id
            or not request.database_id
            or type(request.epoch) is not int
            or request.epoch < 0
            or not request.reason
            or not request.title
            or not request.cancel_label
            or timeout <= 0
        ):
            return RecoveryResult(request, RecoveryStatus.ERROR)
        self._used_attempts.add(request.attempt_id)
        self._active_attempt = request.attempt_id
        self.unavailable_reason = ""
        operation = _Operation()
        self._operation = operation
        try:
            status = await asyncio.wait_for(
                self._authenticate(request, operation), timeout
            )
            return RecoveryResult(request, status)
        except TimeoutError:
            await self.cancel(request.attempt_id)
            return RecoveryResult(request, RecoveryStatus.TIMEOUT)
        except asyncio.CancelledError:
            await self.cancel(request.attempt_id)
            raise
        except Exception as error:
            self._reason(error)
            return RecoveryResult(request, RecoveryStatus.UNAVAILABLE)
        finally:
            if self._active_attempt == request.attempt_id:
                self._active_attempt = None
            if operation.bus is not None:
                operation.bus.close()
            if self._operation is operation:
                self._operation = None

    async def cancel(self, attempt_id: str) -> None:
        if self._active_attempt != attempt_id:
            return
        # Отзыв принят синхронно до первого await и до позднего ответа prompt.
        self._active_attempt = None
        operation = self._operation
        if (
            operation is None
            or operation.bus is None
            or operation.owner is None
            or operation.cancellation_id is None
        ):
            return
        try:
            await self._authority_call(
                operation.bus,
                operation.owner,
                "CancelCheckAuthorization",
                "s",
                [operation.cancellation_id],
                timeout=3,
            )
        except Exception:
            # Закрытие только своей connection отменяет собственный вызов, не чужие grants.
            operation.bus.close()

    async def aclose(self) -> None:
        """Закрытие не оставляет доступного callback от прежнего prompt."""
        self._disposed = True
        operation = self._operation
        attempt = self._active_attempt
        if attempt is not None:
            await self.cancel(attempt)
        if operation is not None and operation.bus is not None:
            operation.bus.close()
