"""Узкий D-Bus transport без shell и перенаправления системной шины из env."""

from __future__ import annotations

import asyncio
import ctypes
import os
import platform
import stat
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class DBusError(RuntimeError):
    """Имя протокола и проверяемый sender без частного текста сервиса."""

    def __init__(self, name: str, *, sender: str = "") -> None:
        super().__init__(name)
        self.name = name
        self.sender = sender


@dataclass(frozen=True)
class DBusReply:
    sender: str
    signature: str
    body: list[Any]
    path: str = ""
    interface: str = ""
    member: str = ""
    serial: int = 0


class DBusTransport(Protocol):
    """Минимальный явный seam транспорта для изолированных unit-тестов."""

    async def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: list[Any] | None = None,
        *,
        timeout: float = 10,
    ) -> DBusReply: ...

    def close(self) -> None: ...


class _Opaque(ctypes.Union):
    # Выравнивание и запас больше публичных DBusMessageIter и DBusError.
    _fields_ = [("alignment", ctypes.c_void_p), ("bytes", ctypes.c_byte * 128)]


def _trusted_path(path: Path, *, owner: int, socket: bool = False) -> None:
    info = path.lstat()
    if info.st_uid != owner or stat.S_ISLNK(info.st_mode):
        raise DBusError("untrusted_dbus_path")
    if socket:
        if not stat.S_ISSOCK(info.st_mode):
            raise DBusError("untrusted_dbus_socket")
    elif not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise DBusError("untrusted_dbus_library")


def _library() -> ctypes.CDLL:
    machine = platform.machine()
    triplet = {"x86_64": "x86_64-linux-gnu", "aarch64": "aarch64-linux-gnu"}.get(
        machine
    )
    if triplet is None:
        raise DBusError("unsupported_dbus_platform")
    path = Path(f"/usr/lib/{triplet}/libdbus-1.so.3").resolve(strict=True)
    _trusted_path(path, owner=0)
    lib = ctypes.CDLL(str(path))
    pointer = ctypes.c_void_p
    functions: dict[str, tuple[Any, list[Any]]] = {
        "dbus_threads_init_default": (ctypes.c_int, []),
        "dbus_error_init": (None, [pointer]),
        "dbus_error_free": (None, [pointer]),
        "dbus_connection_open_private": (pointer, [ctypes.c_char_p, pointer]),
        "dbus_bus_register": (ctypes.c_int, [pointer, pointer]),
        "dbus_connection_set_exit_on_disconnect": (None, [pointer, ctypes.c_int]),
        "dbus_connection_get_is_connected": (ctypes.c_int, [pointer]),
        "dbus_connection_read_write": (ctypes.c_int, [pointer, ctypes.c_int]),
        "dbus_connection_pop_message": (pointer, [pointer]),
        "dbus_connection_close": (None, [pointer]),
        "dbus_connection_unref": (None, [pointer]),
        "dbus_connection_flush": (None, [pointer]),
        "dbus_message_new_method_call": (
            pointer,
            [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p],
        ),
        "dbus_message_unref": (None, [pointer]),
        "dbus_message_get_type": (ctypes.c_int, [pointer]),
        "dbus_message_get_reply_serial": (ctypes.c_uint32, [pointer]),
        "dbus_message_get_serial": (ctypes.c_uint32, [pointer]),
        "dbus_message_iter_init_append": (None, [pointer, pointer]),
        "dbus_message_iter_init": (ctypes.c_int, [pointer, pointer]),
        "dbus_message_iter_get_arg_type": (ctypes.c_int, [pointer]),
        "dbus_message_iter_get_element_type": (ctypes.c_int, [pointer]),
        "dbus_message_iter_get_basic": (None, [pointer, pointer]),
        "dbus_message_iter_next": (ctypes.c_int, [pointer]),
        "dbus_message_iter_recurse": (None, [pointer, pointer]),
        "dbus_message_iter_append_basic": (
            ctypes.c_int,
            [pointer, ctypes.c_int, pointer],
        ),
        "dbus_message_iter_open_container": (
            ctypes.c_int,
            [pointer, ctypes.c_int, ctypes.c_char_p, pointer],
        ),
        "dbus_message_iter_close_container": (ctypes.c_int, [pointer, pointer]),
        "dbus_connection_send": (ctypes.c_int, [pointer, pointer, pointer]),
    }
    for name in ("sender", "signature", "path", "interface", "member", "error_name"):
        functions[f"dbus_message_get_{name}"] = (ctypes.c_char_p, [pointer])
    for name, (result, arguments) in functions.items():
        function = getattr(lib, name)
        function.restype = result
        function.argtypes = arguments
    if lib.dbus_threads_init_default() != 1:
        raise DBusError("dbus_thread_initialization_failed")
    return lib


def _types(signature: str) -> list[str]:
    """Разделяет только используемые типы, не исполняя входные строки."""
    result: list[str] = []
    index = 0
    while index < len(signature):
        start = index
        while index < len(signature) and signature[index] == "a":
            index += 1
        if index >= len(signature):
            raise DBusError("invalid_dbus_signature")
        if signature[index] in "({":
            stack = [")" if signature[index] == "(" else "}"]
            index += 1
            while stack and index < len(signature):
                item = signature[index]
                if item in "({":
                    stack.append(")" if item == "(" else "}")
                elif item in ")}":
                    if item != stack.pop():
                        raise DBusError("invalid_dbus_signature")
                index += 1
            if stack:
                raise DBusError("invalid_dbus_signature")
        elif signature[index] in "ybnqiuxtdsogv":
            index += 1
        else:
            raise DBusError("invalid_dbus_signature")
        result.append(signature[start:index])
    return result


_BASIC = {
    "y": ctypes.c_ubyte,
    "b": ctypes.c_uint32,
    "n": ctypes.c_int16,
    "q": ctypes.c_uint16,
    "i": ctypes.c_int32,
    "u": ctypes.c_uint32,
    "x": ctypes.c_int64,
    "t": ctypes.c_uint64,
    "d": ctypes.c_double,
    "s": ctypes.c_char_p,
    "o": ctypes.c_char_p,
    "g": ctypes.c_char_p,
}


class BusConnection:
    """Одна приватная connection сохраняет caller для нативной отмены polkit."""

    def __init__(self, address: str):
        self._lib = _library()
        self._connection: Any = None
        self._replies: dict[int, Any] = {}
        self._signals: deque[DBusReply] = deque()
        self._pending: set[int] = set()
        error = _Opaque()
        self._lib.dbus_error_init(ctypes.byref(error))
        try:
            connection = self._lib.dbus_connection_open_private(
                address.encode(), ctypes.byref(error)
            )
            if not connection:
                raise DBusError("dbus_connection_failed")
            self._connection = connection
            self._lib.dbus_connection_set_exit_on_disconnect(connection, 0)
            if not self._lib.dbus_bus_register(connection, ctypes.byref(error)):
                self.close()
                raise DBusError("dbus_registration_failed")
        finally:
            self._lib.dbus_error_free(ctypes.byref(error))

    @classmethod
    def system(cls) -> BusConnection:
        # DBUS_SYSTEM_BUS_ADDRESS никогда не используется в production.
        socket = Path("/run/dbus/system_bus_socket")
        _trusted_path(socket, owner=0, socket=True)
        for parent in (Path("/run"), socket.parent):
            info = parent.stat()
            if info.st_uid != 0 or info.st_mode & 0o022:
                raise DBusError("untrusted_system_bus_directory")
        return cls("unix:path=/run/dbus/system_bus_socket")

    @classmethod
    def session(cls) -> BusConnection:
        uid = os.getuid()
        directory = Path(f"/run/user/{uid}")
        info = directory.lstat()
        if info.st_uid != uid or info.st_mode & 0o077 or not stat.S_ISDIR(info.st_mode):
            raise DBusError("untrusted_session_bus_directory")
        socket = directory / "bus"
        _trusted_path(socket, owner=uid, socket=True)
        return cls(f"unix:path={socket}")

    @classmethod
    def for_test_address(cls, address: str) -> BusConnection:
        """Явный seam отдельной тестовой шины, не env-переключатель приложения."""
        return cls(address)

    def _append(self, iterator: _Opaque, signature: str, value: Any) -> None:
        lib = self._lib
        if signature in _BASIC:
            if signature in "sog":
                if not isinstance(value, str) or "\0" in value:
                    raise DBusError("invalid_dbus_string")
                basic = ctypes.c_char_p(value.encode())
            else:
                basic = _BASIC[signature](value)
            if not lib.dbus_message_iter_append_basic(
                ctypes.byref(iterator), ord(signature), ctypes.byref(basic)
            ):
                raise DBusError("dbus_memory_error")
            return
        child = _Opaque()
        if signature == "v":
            inner, inner_value = value
            if len(_types(inner)) != 1:
                raise DBusError("invalid_dbus_variant")
            code, contained, values, types = "v", inner, [inner_value], [inner]
        elif signature.startswith("a"):
            contained = signature[1:]
            code = "a"
            values = list(value.items()) if isinstance(value, dict) else value
            types = [contained] * len(values)
        elif signature.startswith(("(", "{")):
            code = "r" if signature[0] == "(" else "e"
            contained = None
            types, values = _types(signature[1:-1]), value
            if len(types) != len(values):
                raise DBusError("invalid_dbus_struct")
        else:
            raise DBusError("unsupported_dbus_type")
        if not lib.dbus_message_iter_open_container(
            ctypes.byref(iterator),
            ord(code),
            contained.encode() if contained else None,
            ctypes.byref(child),
        ):
            raise DBusError("dbus_memory_error")
        for child_type, child_value in zip(types, values, strict=True):
            self._append(child, child_type, child_value)
        if not lib.dbus_message_iter_close_container(
            ctypes.byref(iterator), ctypes.byref(child)
        ):
            raise DBusError("dbus_memory_error")

    def _read(self, iterator: _Opaque) -> Any:
        code = self._lib.dbus_message_iter_get_arg_type(ctypes.byref(iterator))
        signature = chr(code)
        if signature in _BASIC:
            basic = _BASIC[signature]()
            self._lib.dbus_message_iter_get_basic(
                ctypes.byref(iterator), ctypes.byref(basic)
            )
            if signature in "sog":
                return (basic.value or b"").decode("utf-8", errors="strict")
            return bool(basic.value) if signature == "b" else basic.value
        if signature not in "arev":
            raise DBusError("unsupported_dbus_reply_type")
        child = _Opaque()
        self._lib.dbus_message_iter_recurse(ctypes.byref(iterator), ctypes.byref(child))
        values: list[Any] = []
        while self._lib.dbus_message_iter_get_arg_type(ctypes.byref(child)):
            if len(values) > 65536:
                raise DBusError("oversized_dbus_reply")
            values.append(self._read(child))
            self._lib.dbus_message_iter_next(ctypes.byref(child))
        if signature == "v":
            if len(values) != 1:
                raise DBusError("invalid_dbus_variant_reply")
            return values[0]
        if signature == "a" and self._lib.dbus_message_iter_get_element_type(
            ctypes.byref(iterator)
        ) == ord("e"):
            result: dict[Any, Any] = {}
            for pair in values:
                if len(pair) != 2 or pair[0] in result:
                    raise DBusError("invalid_dbus_dictionary_reply")
                result[pair[0]] = pair[1]
            return result
        return values

    def _decode(self, message: Any) -> DBusReply:
        def text(field: str) -> str:
            return (
                getattr(self._lib, f"dbus_message_get_{field}")(message) or b""
            ).decode("utf-8", errors="strict")

        iterator = _Opaque()
        values: list[Any] = []
        self._lib.dbus_message_iter_init(message, ctypes.byref(iterator))
        while self._lib.dbus_message_iter_get_arg_type(ctypes.byref(iterator)):
            values.append(self._read(iterator))
            self._lib.dbus_message_iter_next(ctypes.byref(iterator))
        return DBusReply(
            text("sender"),
            text("signature"),
            values,
            text("path"),
            text("interface"),
            text("member"),
            int(self._lib.dbus_message_get_serial(message)),
        )

    def _pump(self) -> None:
        if not self._connection:
            raise DBusError("dbus_closed")
        self._lib.dbus_connection_read_write(self._connection, 0)
        if not self._lib.dbus_connection_get_is_connected(self._connection):
            raise DBusError("dbus_disconnected")
        while message := self._lib.dbus_connection_pop_message(self._connection):
            kind = self._lib.dbus_message_get_type(message)
            serial = self._lib.dbus_message_get_reply_serial(message)
            if kind in (2, 3) and serial in self._pending:
                self._replies[serial] = message
                continue
            try:
                if kind == 4:
                    if len(self._signals) >= 4096:
                        raise DBusError("dbus_signal_overflow")
                    self._signals.append(self._decode(message))
            finally:
                self._lib.dbus_message_unref(message)

    async def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: list[Any] | None = None,
        *,
        timeout: float = 10,
    ) -> DBusReply:
        if not self._connection:
            raise DBusError("dbus_closed")
        types, values = _types(signature), body or []
        if len(types) != len(values):
            raise DBusError("invalid_dbus_arguments")
        message = self._lib.dbus_message_new_method_call(
            destination.encode(), path.encode(), interface.encode(), member.encode()
        )
        if not message:
            raise DBusError("dbus_message_failed")
        serial = ctypes.c_uint32()
        try:
            iterator = _Opaque()
            self._lib.dbus_message_iter_init_append(message, ctypes.byref(iterator))
            for value_type, value in zip(types, values, strict=True):
                self._append(iterator, value_type, value)
            if not self._lib.dbus_connection_send(
                self._connection, message, ctypes.byref(serial)
            ):
                raise DBusError("dbus_send_failed")
            self._pending.add(serial.value)
        finally:
            self._lib.dbus_message_unref(message)
        deadline = time.monotonic() + timeout
        try:
            while serial.value not in self._replies:
                self._pump()
                if time.monotonic() >= deadline:
                    raise TimeoutError("dbus_call_timeout")
                await asyncio.sleep(0.01)
            reply = self._replies.pop(serial.value)
            try:
                if self._lib.dbus_message_get_type(reply) == 3:
                    name = self._lib.dbus_message_get_error_name(reply) or b""
                    sender = self._lib.dbus_message_get_sender(reply) or b""
                    raise DBusError(
                        name.decode("ascii", errors="replace"),
                        sender=sender.decode("ascii", errors="replace"),
                    )
                return self._decode(reply)
            finally:
                self._lib.dbus_message_unref(reply)
        finally:
            self._pending.discard(serial.value)
            leftover = self._replies.pop(serial.value, None)
            if leftover:
                self._lib.dbus_message_unref(leftover)

    async def add_match(self, rule: str) -> None:
        reply = await self.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "AddMatch",
            "s",
            [rule],
        )
        if reply.sender != "org.freedesktop.DBus" or reply.signature or reply.body:
            raise DBusError("untrusted_add_match_reply")

    async def next_signal(self, timeout: float = 1) -> DBusReply:
        deadline = time.monotonic() + timeout
        while not self._signals:
            self._pump()
            if time.monotonic() >= deadline:
                raise TimeoutError("dbus_signal_timeout")
            await asyncio.sleep(0.01)
        return self._signals.popleft()

    def close(self) -> None:
        if self._connection:
            self._lib.dbus_connection_close(self._connection)
            self._lib.dbus_connection_unref(self._connection)
            self._connection = None
        for message in self._replies.values():
            self._lib.dbus_message_unref(message)
        self._replies.clear()
        self._signals.clear()

    async def aclose(self) -> None:
        self.close()


async def verify_system_service(
    bus: DBusTransport, service: str, owner: str, uid: int
) -> None:
    """Сверяет peer PID с root-managed unit, не требует чтения чужого /proc/exe."""
    known = {
        "org.freedesktop.PolicyKit1": (
            "polkit.service",
            ("/usr/lib/polkit-1/polkitd", "/usr/libexec/polkitd"),
        ),
        "org.freedesktop.login1": (
            "systemd-logind.service",
            ("/usr/lib/systemd/systemd-logind", "/lib/systemd/systemd-logind"),
        ),
    }
    if service not in known:
        raise DBusError("untrusted_system_service")

    async def daemon(member: str, name: str, signature: str) -> Any:
        reply = await bus.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            member,
            "s",
            [name],
        )
        if (
            reply.sender != "org.freedesktop.DBus"
            or reply.signature != signature
            or len(reply.body) != 1
        ):
            raise DBusError("untrusted_system_service")
        return reply.body[0]

    pid = await daemon("GetConnectionUnixProcessID", owner, "u")
    if type(pid) is not int or pid <= 1:
        raise DBusError("untrusted_system_service")
    unit, executables = known[service]
    status = Path(f"/proc/{pid}/status").read_text().splitlines()
    values = next(line for line in status if line.startswith("Uid:")).split()[1:]
    if len(values) != 4 or any(int(value) != uid for value in values):
        raise DBusError("untrusted_system_service")
    try:
        executable = Path(f"/proc/{pid}/exe").resolve(strict=True)
    except PermissionError:
        executable = None
    if executable is not None:
        accepted = {
            Path(path).resolve(strict=True)
            for path in executables
            if Path(path).exists()
        }
        if executable not in accepted:
            raise DBusError("untrusted_system_service")
        _trusted_path(executable, owner=0)

    # polkitd становится недоступен для readlink /proc/exe после setuid. Root systemd
    # доказывает владельца unit и точный MainPID без ослабления проверки до одного UID.
    systemd = await daemon("GetNameOwner", "org.freedesktop.systemd1", "s")
    if not isinstance(systemd, str) or not systemd.startswith(":"):
        raise DBusError("untrusted_system_service")
    if await daemon("GetConnectionUnixUser", systemd, "u") != 0:
        raise DBusError("untrusted_system_service")
    if await daemon("GetConnectionUnixProcessID", systemd, "u") != 1:
        raise DBusError("untrusted_system_service")
    reply = await bus.call(
        systemd,
        "/org/freedesktop/systemd1",
        "org.freedesktop.systemd1.Manager",
        "GetUnit",
        "s",
        [unit],
    )
    if reply.sender != systemd or reply.signature != "o" or len(reply.body) != 1:
        raise DBusError("untrusted_system_service")
    unit_path = reply.body[0]
    if not isinstance(unit_path, str) or not unit_path.startswith(
        "/org/freedesktop/systemd1/unit/"
    ):
        raise DBusError("untrusted_system_service")
    for name in ("MainPID", "ExecStart"):
        reply = await bus.call(
            systemd,
            unit_path,
            "org.freedesktop.DBus.Properties",
            "Get",
            "ss",
            ["org.freedesktop.systemd1.Service", name],
        )
        if reply.sender != systemd or reply.signature != "v" or len(reply.body) != 1:
            raise DBusError("untrusted_system_service")
        value = reply.body[0]
        if name == "MainPID":
            if type(value) is not int or value != pid:
                raise DBusError("untrusted_system_service")
        else:
            if not isinstance(value, list) or len(value) != 1 or not value[0]:
                raise DBusError("untrusted_system_service")
            path = value[0][0]
            if path not in executables:
                raise DBusError("untrusted_system_service")
            _trusted_path(Path(path).resolve(strict=True), owner=0)
    if await daemon("GetNameOwner", service, "s") != owner:
        raise DBusError("untrusted_system_service")
