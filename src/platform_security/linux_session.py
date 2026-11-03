"""События защищённой Linux-сессии без доступа к ключам или данным приложения."""

from __future__ import annotations

import ast
import asyncio
import configparser
import copy
import functools
import grp
import hashlib
import os
import pwd
import re
import secrets
import stat
import time
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

from platform_security.linux_dbus import (
    BusConnection,
    DBusError,
    DBusReply,
    verify_system_service,
)
from platform_security.local_protection import (
    ObserverContext,
    ScreenLockUnavailable,
    ScreenState,
)

_DBUS = "org.freedesktop.DBus"
_DBUS_PATH = "/org/freedesktop/DBus"
_PROPERTIES = "org.freedesktop.DBus.Properties"
_LOGIN = "org.freedesktop.login1"
_LOGIN_PATH = "/org/freedesktop/login1"
_MANAGER = _LOGIN + ".Manager"
_SESSION = _LOGIN + ".Session"
_SCREEN = "org.cinnamon.ScreenSaver"
_SCREEN_PATH = "/org/cinnamon/ScreenSaver"


class SessionSecurityEvent(StrEnum):
    SCREEN_LOCK = "screen_lock"
    SLEEP = "sleep"
    SESSION_CHANGE = "session_change"
    SHUTDOWN = "shutdown"
    TRUST_LOST = "trust_lost"


class SessionWatchState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    WAITING_SCREEN_SERVICE = "waiting_screen_service"
    UNAVAILABLE = "unavailable"
    DISCONNECTED = "disconnected"
    CLOSED = "closed"


@dataclass(frozen=True)
class SessionWatchStatus:
    state: SessionWatchState
    code: str
    system_events: bool = False
    screen_events: bool = False


@dataclass(frozen=True)
class SessionObservation:
    """Independent trusted lifecycle evidence, never a request-success receipt."""

    kind: str
    context: ObserverContext
    actual_suspend: bool = False
    test_id: int | None = None


class SessionBus(Protocol):
    async def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: list | None = None,
        *,
        timeout: float = 10,
    ) -> DBusReply: ...

    async def add_match(self, rule: str) -> None: ...

    async def next_signal(self, *, timeout: float = 1) -> DBusReply | None: ...

    async def aclose(self) -> None: ...


def _root_file(path: Path) -> bool:
    """Файлы доверенного пакета и все каталоги не доступны на запись UID приложения."""
    try:
        absolute = path.absolute()
        for candidate in (absolute, *absolute.parents):
            info = candidate.lstat()
            if info.st_uid != 0 or (
                not stat.S_ISLNK(info.st_mode)
                and info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            ):
                return False
        resolved = path.resolve(strict=True)
        for candidate in (resolved, *resolved.parents):
            info = candidate.stat()
            if info.st_uid != 0 or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
                return False
        return resolved.is_file()
    except OSError:
        return False


def trusted_session_process(role: str, pid: int, uid: int) -> bool:
    """Проверяет владельца сигнала, а не доверяет одному well-known имени.

    Cinnamon является Python-программой с setproctitle. Проверяются также её
    установленный root-owned entrypoint и загруженная библиотека пакета. Это
    не защита от полностью скомпрометированного текущего Unix UID.
    """
    try:
        proc = Path("/proc") / str(pid)
        if pid <= 0 or proc.stat().st_uid != uid:
            return False
        if role in {"logind", "systemd"}:
            # На Mint обычному UID запрещён /proc/<root-pid>/exe. Владение
            # эксклюзивным именем на root-owned system bus вместе с UID 0
            # является границей доверия. Компрометация root вне модели угроз.
            identity = (proc / "status").read_text().splitlines()
            users = next(line for line in identity if line.startswith("Uid:"))
            command, entry = (
                ("systemd-logind", "/usr/lib/systemd/systemd-logind")
                if role == "logind"
                else ("systemd", "/usr/lib/systemd/systemd")
            )
            return (
                uid == 0
                and (role != "systemd" or pid == 1)
                and users.split()[1:] == ["0", "0", "0", "0"]
                and (proc / "comm").read_text().strip() == command
                and _root_file(Path(entry))
            )
        executable = (proc / "exe").resolve(strict=True)
        if not _root_file(executable):
            return False
        if role != "cinnamon" or uid != os.getuid():
            return False
        script = Path("/usr/share/cinnamon-screensaver/cinnamon-screensaver-main.py")
        library = Path("/usr/libexec/cinnamon-screensaver/libcscreensaver.so")
        if (
            executable.parent != Path("/usr/bin")
            or re.fullmatch(r"python3(?:\.\d+)?", executable.name) is None
            or not _root_file(script)
            or not _root_file(library)
        ):
            return False
        command = (proc / "cmdline").read_bytes().split(b"\0")
        title = command[0].decode("utf-8", errors="strict")
        expected_title = title == "cinnamon-screensaver"
        expected_script = len(command) > 1 and command[1] == os.fsencode(script)
        maps = (proc / "maps").read_text().splitlines()
        mapped = {
            fields[5] for line in maps if len(fields := line.split(maxsplit=5)) == 6
        }
        return (expected_title or expected_script) and str(library.resolve()) in mapped
    except (OSError, ValueError, UnicodeError, StopIteration):
        return False


@dataclass(frozen=True)
class _ProcessStamp:
    uid: int
    parent: int
    start: int
    cgroup: str


def process_stamp(pid: int) -> _ProcessStamp:
    """Kernel metadata prevents an exited PID from validating its replacement."""
    proc = Path("/proc") / str(pid)
    status = (proc / "status").read_text().splitlines()
    users = next(line for line in status if line.startswith("Uid:")).split()[1:]
    if len(users) != 4 or len(set(users)) != 1:
        raise RuntimeError("inconsistent_process_credentials")
    # comm may contain spaces and parentheses; fields after the LAST ')' are fixed.
    fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    if len(fields) < 20 or fields[0] in {"Z", "X"}:
        raise RuntimeError("service_process_exited")
    return _ProcessStamp(
        int(users[0]), int(fields[1]), int(fields[19]), (proc / "cgroup").read_text()
    )


def _activation_file_matches(text: str) -> bool:
    config = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        config.read_string(text)
        return config.sections() == ["D-BUS Service"] and dict(
            config["D-BUS Service"]
        ) == {"name": _SCREEN, "exec": "/usr/bin/cinnamon-screensaver"}
    except configparser.Error:
        return False


def _root_directory(path: Path) -> bool:
    try:
        for candidate in (path.absolute(), *path.absolute().parents):
            if not candidate.exists():
                continue
            info = candidate.lstat()
            if info.st_uid != 0 or (
                not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022
            ):
                return False
        resolved = path.resolve(strict=False)
        for candidate in (resolved, *resolved.parents):
            if candidate.exists():
                info = candidate.stat()
                if info.st_uid != 0 or info.st_mode & 0o022:
                    return False
        return not path.exists() or path.is_dir()
    except OSError:
        return False


def _configured_service_dirs() -> set[Path]:
    """Only root-owned daemon configuration may extend the activation layout."""
    seen: set[Path] = set()
    services: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve(strict=True)
        if resolved in seen:
            return
        if len(seen) >= 64 or not _root_file(path) or path.stat().st_size > 262144:
            raise RuntimeError("untrusted_activation_configuration")
        seen.add(resolved)
        root = ET.fromstring(path.read_text())
        if root.tag != "busconfig":
            raise RuntimeError("untrusted_activation_configuration")
        for node in root:
            if node.tag not in {"include", "includedir", "servicedir"}:
                continue
            text = (node.text or "").strip()
            if not text:
                raise RuntimeError("untrusted_activation_configuration")
            target = Path(text)
            if not target.is_absolute():
                target = path.parent / target
            if node.attrib.get("selinux_root_relative") == "yes":
                # The known SELinux context mapping is not an activation config.
                continue
            if node.tag == "include":
                if not target.exists() and node.attrib.get("ignore_missing") == "yes":
                    if not _root_directory(target.parent):
                        raise RuntimeError("untrusted_activation_configuration")
                    continue
                visit(target)
            elif not _root_directory(target):
                raise RuntimeError("untrusted_activation_configuration")
            elif node.tag == "servicedir":
                services.add(target)
            elif target.exists():
                children = list(target.glob("*.conf"))
                if len(children) > 64:
                    raise RuntimeError("untrusted_activation_configuration")
                for child in children:
                    visit(child)

    visit(Path("/usr/share/dbus-1/session.conf"))
    return services


def _no_activation_shadow(daemon_pid: int, uid: int, expected: Path) -> None:
    """Reject runtime/user overrides, including alternate filenames with this Name.

    Only the installed default dbus-daemon search layout is supported. Environment
    is used to detect extra search locations, never to select our D-Bus transport.
    No values or file contents escape this attestation.
    """
    raw = Path(f"/proc/{daemon_pid}/environ").read_bytes()
    selected = {}
    for entry in raw.split(b"\0"):
        key, _, value = entry.partition(b"=")
        if key in {b"XDG_DATA_HOME", b"XDG_DATA_DIRS", b"XDG_RUNTIME_DIR"}:
            selected[key] = os.fsdecode(value)
    home = Path(pwd.getpwuid(uid).pw_dir)
    runtime = Path(f"/run/user/{uid}")
    if selected.get(b"XDG_RUNTIME_DIR", str(runtime)) != str(runtime):
        raise RuntimeError("unsupported_activation_search_path")
    data_dirs = selected.get(b"XDG_DATA_DIRS", "/usr/local/share:/usr/share")
    directories = [runtime, home / ".local/share"]
    if selected.get(b"XDG_DATA_HOME"):
        directories.append(Path(selected[b"XDG_DATA_HOME"]))
    directories.extend(Path(item) for item in data_dirs.split(":"))
    service_dirs = set()
    for directory in dict.fromkeys(directories):
        if not directory.is_absolute():
            raise RuntimeError("unsupported_activation_search_path")
        service_dirs.add(directory / "dbus-1/services")
    service_dirs.update(_configured_service_dirs())
    for services in service_dirs:
        if not services.exists():
            continue
        files = list(services.glob("*.service"))
        if len(files) > 1024:
            raise RuntimeError("unsupported_activation_search_path")
        for candidate in files:
            if candidate == expected:
                continue
            if (
                candidate.is_symlink() and not _root_file(candidate)
            ) or candidate.stat().st_size > 65536:
                raise RuntimeError("ambiguous_activation_metadata")
            if candidate.name == expected.name:
                raise RuntimeError("overridden_activation_metadata")
            config = configparser.ConfigParser(interpolation=None, strict=True)
            try:
                config.read_string(candidate.read_text())
                if config.get("D-BUS Service", "Name", fallback="") == _SCREEN:
                    raise RuntimeError("overridden_activation_metadata")
            except (configparser.Error, UnicodeError) as error:
                raise RuntimeError("ambiguous_activation_metadata") from error


async def _bus_peer(bus: SessionBus, name: str) -> tuple[str, int, int]:
    values = []
    for member, argument, signature in (
        ("GetNameOwner", name, "s"),
        ("GetConnectionUnixUser", None, "u"),
        ("GetConnectionUnixProcessID", None, "u"),
    ):
        reply = await bus.call(
            _DBUS, _DBUS_PATH, _DBUS, member, "s", [argument or values[0]]
        )
        if (
            reply.sender != _DBUS
            or reply.signature != signature
            or len(reply.body) != 1
        ):
            raise RuntimeError("untrusted_activation_daemon")
        values.append(reply.body[0])
    owner, uid, pid = values
    if (
        not isinstance(owner, str)
        or re.fullmatch(r":\d+\.\d+", owner) is None
        or type(uid) is not int
        or type(pid) is not int
        or pid <= 0
    ):
        raise RuntimeError("untrusted_activation_daemon")
    return owner, uid, pid


async def _loaded_unit(
    bus: SessionBus, owner: str, unit: str, pid: int, executable: str, group: str
) -> None:
    manager = "org.freedesktop.systemd1"
    reply = await bus.call(
        owner, "/org/freedesktop/systemd1", manager + ".Manager", "GetUnit", "s", [unit]
    )
    if (
        reply.sender != owner
        or reply.signature != "o"
        or len(reply.body) != 1
        or not isinstance(reply.body[0], str)
        or not reply.body[0].startswith("/org/freedesktop/systemd1/unit/")
    ):
        raise RuntimeError("untrusted_activation_unit")
    path = reply.body[0]
    properties = {}
    for interface in (manager + ".Unit", manager + ".Service"):
        reply = await bus.call(owner, path, _PROPERTIES, "GetAll", "s", [interface])
        if (
            reply.sender != owner
            or reply.signature != "a{sv}"
            or len(reply.body) != 1
            or not isinstance(reply.body[0], dict)
        ):
            raise RuntimeError("untrusted_activation_unit")
        properties.update(reply.body[0])
    fragment = properties.get("FragmentPath")
    drops = properties.get("DropInPaths")
    start = properties.get("ExecStart")
    if (
        not isinstance(fragment, str)
        or not fragment
        or not _root_file(Path(fragment))
        or not isinstance(drops, list)
        or any(
            not isinstance(item, str) or not _root_file(Path(item)) for item in drops
        )
        or properties.get("ControlGroup") != group
        or type(properties.get("MainPID")) is not int
        or properties["MainPID"] != pid
        or not isinstance(start, list)
        or len(start) != 1
        or not isinstance(start[0], (list, tuple))
        or not start[0]
        or start[0][0] != executable
        or not _root_file(Path(executable))
    ):
        raise RuntimeError("untrusted_activation_unit")


async def verify_cinnamon_activation(
    system: SessionBus, desktop: SessionBus, pid: int | None, uid: int
) -> None:
    """Attest default package activation, including Cinnamon's daemonized child.

    Loaded user@UID and dbus units, their root-owned package files, daemon PID and
    cgroups supply origin evidence after double-fork reparenting. The separate
    logind check binds that per-user service to exactly one graphical desktop.
    Same UID/title/DISPLAY alone never passes. Root and full UID compromise remain
    outside this boundary.
    """
    before = process_stamp(pid) if pid is not None else None
    # org.freedesktop.DBus is a special daemon-owned name, not a unique peer name.
    reply = await desktop.call(
        _DBUS, _DBUS_PATH, _DBUS, "GetConnectionUnixProcessID", "s", [_DBUS]
    )
    if (
        reply.sender != _DBUS
        or reply.signature != "u"
        or len(reply.body) != 1
        or type(reply.body[0]) is not int
        or reply.body[0] <= 1
    ):
        raise RuntimeError("untrusted_activation_daemon")
    daemon = reply.body[0]
    peer = process_stamp(daemon)
    prefix = f"/user.slice/user-{uid}.slice/user@{uid}.service"
    group = prefix + "/session.slice/dbus.service"
    manager_pid = peer.parent
    manager_stamp = process_stamp(manager_pid)
    if (
        peer.uid != uid
        or manager_stamp.uid != uid
        or peer.cgroup != f"0::{group}\n"
        or manager_stamp.cgroup != f"0::{prefix}/init.scope\n"
        or (
            before is not None
            and (
                before.uid != uid
                or before.parent not in {daemon, manager_pid}
                or before.cgroup != peer.cgroup
                or before.start < peer.start
            )
        )
    ):
        raise RuntimeError("untrusted_activation_origin")
    executable = Path(f"/proc/{daemon}/exe").resolve(strict=True)
    arguments = Path(f"/proc/{daemon}/cmdline").read_bytes().rstrip(b"\0").split(b"\0")
    expected_arguments = [
        b"/usr/bin/dbus-daemon",
        b"--session",
        b"--address=systemd:",
        b"--nofork",
        b"--nopidfile",
        b"--systemd-activation",
        b"--syslog-only",
    ]
    service = Path("/usr/share/dbus-1/services/org.cinnamon.ScreenSaver.service")
    unit = Path("/usr/lib/systemd/user/dbus.service")
    launcher = Path("/usr/bin/cinnamon-screensaver")
    if (
        executable != Path("/usr/bin/dbus-daemon").resolve(strict=True)
        or not all(_root_file(path) for path in (executable, service, unit, launcher))
        or arguments != expected_arguments
        or not _activation_file_matches(service.read_text())
        or "ExecStart=" + " ".join(os.fsdecode(arg) for arg in expected_arguments)
        not in unit.read_text().splitlines()
    ):
        raise RuntimeError("untrusted_activation_metadata")
    _no_activation_shadow(daemon, uid, service)
    systemd = "org.freedesktop.systemd1"
    root_peer = await _bus_peer(system, systemd)
    if root_peer[1:] != (0, 1) or not trusted_session_process("systemd", 1, 0):
        raise RuntimeError("untrusted_system_manager")
    await _loaded_unit(
        system,
        root_peer[0],
        f"user@{uid}.service",
        manager_pid,
        "/usr/lib/systemd/systemd",
        prefix,
    )
    user_peer = await _bus_peer(desktop, systemd)
    if user_peer[1:] != (uid, manager_pid):
        raise RuntimeError("untrusted_user_manager")
    await _loaded_unit(
        desktop, user_peer[0], "dbus.service", daemon, "/usr/bin/dbus-daemon", group
    )
    if (
        await _bus_peer(system, systemd) != root_peer
        or await _bus_peer(desktop, systemd) != user_peer
        or (pid is not None and process_stamp(pid) != before)
        or process_stamp(daemon) != peer
        or process_stamp(manager_pid) != manager_stamp
    ):
        raise RuntimeError("activation_process_changed")


async def _prepare_cinnamon_activation(
    system: SessionBus, desktop: SessionBus, uid: int
) -> None:
    """Attest canonical fixed activation before asking D-Bus to start anything."""
    await verify_cinnamon_activation(system, desktop, None, uid)


# A narrowly supported package contract, not a claim that visibility means lock.
# These SHA-256 values describe ASTs of security-relevant upstream 6.6.1 methods,
# with docstrings/formatting excluded. Unknown changed code falls back to logind
# evidence. No third-party implementation is vendored or executed here.
_CINNAMON_CONTRACT_METHODS = {
    "manager.py": {
        "ScreensaverManager.lock": "0cd8d23464df1558c0b46eeb8230725f98426cfddd0e6ad7f802287e940ca7dc",
        "ScreensaverManager.set_active": "67acf1c526378464fc0aacc3f0cafc5f1612019ad359d6f17d9a75e015dd92d3",
        "ScreensaverManager.on_spawn_stage_complete": "a6c18bf36648853779113ede1c557bef17795012c52fadc73ae34a0cdc890ae0",
        "ScreensaverManager.despawn_stage": "ed550ed3061d35cc29b5d18a2ee2a0de13f3d35325329101ad1a0d66d0412986",
        "ScreensaverManager.set_locked": "6b903142681f8eff161f9bcafee0e30c2da17264cb72d79b8ea9a98894c5d74d",
        "ScreensaverManager.get_active": "1f320ae45674dd824bc31cb71da80e9c2431380a6396ccb1b409fc7fc72389bb",
        "ScreensaverManager.unlock": "b1c70ae2aca5e65742330b783a8a9cdc1bb26ca2c8461c31573bea165a3aee83",
    },
    "service.py": {
        "ScreensaverService.handle_lock": "9d74d50af0b28b0ee7639381dcab39ad20af1dd817cb2d84bd6b05963ab65c2b",
        "ScreensaverService.on_active_changed_idle": "00b33303637208c7f2e791cdb5561994d75cfcfefe5d215e40ae4d84eabd8600",
        "ScreensaverService.poke_process": "8f3b1026e146cfb1b4b2cf41f32d2b7f7c6a22d1952dcdb28a882f9f3acdecd5",
    },
    "cinnamon-screensaver-main.py": {
        "Main.do_startup": "c1e506381418eb06a2b36f168b30b5fa16e4a817b7462e414a4c8d811cf12c74",
    },
    "util/utils.py": {
        "user_can_lock": "59dedc8786c2ec03af39011e1a37db49e16151b1e054f7983c995bff19126b18",
    },
}
_XAPP_CONTRACT_METHODS = {
    "is_live_session": "6755ed8e7b1abbdf2fec7708ddccc1285e5677acaba794cdfeb16db173b5606a",
    "is_guest_session": "938d02253e59c163b129fa7fa956b564e5c1f62310023beff957a9bd82d4fd55",
}


def _source_stamp(path: Path) -> tuple[int, ...]:
    info = path.stat()
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_mode,
        info.st_uid,
        info.st_gid,
    )


@functools.lru_cache(maxsize=16)
def _source_methods_match(
    path: Path, stamp: tuple[int, ...], methods: tuple[tuple[str, str], ...]
) -> bool:
    if path.stat().st_size > 262144:
        return False
    tree = ast.parse(path.read_bytes())
    for name, digest in methods:
        nodes = tree.body
        target = None
        for part in name.split("."):
            target = next(
                (
                    node
                    for node in nodes
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                    and node.name == part
                ),
                None,
            )
            if target is None:
                return False
            nodes = target.body
        assert target is not None
        if ast.get_docstring(target) is not None:
            target.body = target.body[1:]
        if (
            hashlib.sha256(
                ast.dump(target, include_attributes=False).encode()
            ).hexdigest()
            != digest
        ):
            return False
    return _source_stamp(path) == stamp


def cinnamon_lock_contract(pid: int) -> bool:
    """Known canonical 6.6.1 Lock semantics, checked without private credentials.

    The caller must separately attest canonical argument-free D-Bus activation.
    An explicit Lock then sets Locked, unlike idle visibility. Account/live/guest
    restrictions are read before and after the request. No settings are changed.
    """
    try:
        uid = os.getuid()
        if uid == 0:
            return False
        root = Path("/usr/share/cinnamon-screensaver")
        for relative, methods in _CINNAMON_CONTRACT_METHODS.items():
            path = root / relative
            if not _root_file(path) or not _source_methods_match(
                path, _source_stamp(path), tuple(methods.items())
            ):
                return False
        xapp = Path("/usr/lib/python3/dist-packages/xapp/os.py")
        if not _root_file(xapp) or not _source_methods_match(
            xapp, _source_stamp(xapp), tuple(_XAPP_CONTRACT_METHODS.items())
        ):
            return False
        launcher = Path("/usr/bin/cinnamon-screensaver")
        if (
            not _root_file(launcher)
            or hashlib.sha256(launcher.read_bytes()).hexdigest()
            != "4c5091b617c1ab21593879bee86e62b24244091559b4d552a2f4758f6ef633ee"
        ):
            return False
        if not all(
            _root_file(path)
            for path in (
                Path(
                    "/usr/libexec/cinnamon-screensaver/cinnamon-screensaver-pam-helper"
                ),
                Path("/etc/pam.d/cinnamon-screensaver"),
            )
        ):
            return False
        return _cinnamon_account_can_lock(pid)
    except (OSError, ValueError, SyntaxError, UnicodeError, KeyError):
        return False


def _cinnamon_account_can_lock(pid: int) -> bool:
    try:
        uid = os.getuid()
        if uid == 0:
            return False
        user = pwd.getpwuid(uid)
        try:
            if user.pw_name in grp.getgrnam("nopasswdlogin").gr_mem:
                return False
        except KeyError:
            pass
        cmdline = Path("/proc/cmdline").read_text()
        if "boot=casper" in cmdline or "boot=live" in cmdline:
            return False
        # xapp uses the service's HOME, not the caller's AppImage/XDG paths.
        home = user.pw_dir
        for item in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
            if item.startswith(b"HOME="):
                home = os.fsdecode(item[5:])
        return "/tmp/guest" not in home
    except (OSError, ValueError, UnicodeError, KeyError):
        return False


def single_x11_display(display: str, uid: int) -> bool:
    """Conservative namespace evidence excludes a second independent X display.

    logind User.Display alone does not enumerate X servers outside login scopes.
    Both filesystem and abstract X11 listeners must name this single display.
    Extra/stale display sockets degrade monitoring rather than guessing a target.
    """
    try:
        match = re.fullmatch(r":(\d+)(?:\.0)?", display)
        if match is None:
            return False
        expected = "X" + match[1]
        directory = Path("/tmp/.X11-unix")
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != 0
            or not info.st_mode & stat.S_ISVTX
        ):
            return False
        names = set()
        for candidate in directory.iterdir():
            if re.fullmatch(r"X\d+", candidate.name) is None:
                continue
            item = candidate.lstat()
            if not stat.S_ISSOCK(item.st_mode) or item.st_uid not in {0, uid}:
                return False
            names.add(candidate.name)
        if names != {expected}:
            return False
        for line in Path("/proc/net/unix").read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) < 8:
                continue
            path = fields[7]
            match = re.fullmatch(r"@?/tmp/\.X11-unix/(X\d+)", path)
            if match is not None and match[1] != expected:
                return False
        return True
    except (OSError, UnicodeError):
        return False


@dataclass(frozen=True)
class _Peer:
    pid: int
    uid: int
    stamp: object


@dataclass
class _RequestedLock:
    context: ObserverContext
    capable: bool
    baseline_serial: int = 0
    test_id: int | None = None
    acknowledgement_serial: int = 0
    active_serial: int = 0
    inactive_serial: int = 0
    acknowledged: bool = False
    active_seen: bool = False
    inactive_seen: bool = False
    lock_published: bool = False
    inactive_published: bool = False


def _production_buses() -> tuple[SessionBus, SessionBus | None]:
    system = BusConnection.system()
    try:
        return system, BusConnection.session()
    except Exception:
        # No session transport must not discard a usable canonical system bus.
        return system, None


async def _verify_service(bus: SessionBus, name: str, owner: str, uid: int) -> None:
    # Общая проверка сопоставляет D-Bus PID с root-managed systemd MainPID/ExecStart.
    await verify_system_service(cast(BusConnection, bus), name, owner, uid)


class LinuxSessionWatcher:
    """Одна пара подписок на время жизни приложения.

    on_revoke вызывается синхронно при получении проверенного события. Он обязан
    сразу закрыть доступ и stale callbacks. Асинхронное сохранение черновика
    планирует сам контроллер с уже выданным узким completion lease. Ни unlock,
    ни возвращение активной сессии не вызывает callback открытия данных.
    """

    def __init__(
        self,
        on_revoke: Callable[[SessionSecurityEvent], None],
        *,
        on_status: Callable[[SessionWatchStatus], None] | None = None,
        on_observation: Callable[[SessionObservation], None] | None = None,
        bus_factory: Callable[
            [], tuple[SessionBus, SessionBus | None]
        ] = _production_buses,
        process_verifier: Callable[[str, int, int], bool] = trusted_session_process,
        service_verifier: Callable[
            [SessionBus, str, str, int], Awaitable[None]
        ] = _verify_service,
        process_snapshot: Callable[[int], object] = process_stamp,
        display_verifier: Callable[[str, int], bool] = single_x11_display,
        activation_verifier: Callable[
            [SessionBus, SessionBus, int, int], Awaitable[None]
        ] = verify_cinnamon_activation,
        activation_preparer: Callable[
            [SessionBus, SessionBus, int], Awaitable[None]
        ] = _prepare_cinnamon_activation,
        lock_contract_verifier: Callable[[int], bool] = cinnamon_lock_contract,
    ) -> None:
        self._on_revoke = on_revoke
        self._on_status = on_status
        self._on_observation = on_observation
        self._bus_factory = bus_factory
        self._process_verifier = process_verifier
        self._service_verifier = service_verifier
        self._process_snapshot = process_snapshot
        self._display_verifier = display_verifier
        self._activation_verifier = activation_verifier
        self._activation_preparer = activation_preparer
        self._lock_contract_verifier = lock_contract_verifier
        self._system: SessionBus | None = None
        self._desktop: SessionBus | None = None
        self._system_owner: str | None = None
        self._screen_owner: str | None = None
        self._session_path: str | None = None
        self._session_id: str | None = None
        self._session_active = False
        self._session_binding: dict = {}
        self._tasks: list[asyncio.Task[None]] = []
        self._started = False
        self._closed = False
        self._failed = False
        self._system_connected = False
        self._system_trusted = False
        self._screen_connected = False
        self._screen_per_user = False
        self._screen_history_compatible = False
        self._screen_generation = 0
        self._system_generation = 0
        self._watch_nonce = secrets.token_hex(16)
        self._sleep_gap_before: float | None = None
        self._sleep_signal_pending = False
        self._bound_sleep_test: tuple[ObserverContext, int] | None = None
        self._bound_sleep_issued = False
        self._bound_sleep_barrier = 0
        self._sleep_begin_serial = 0
        self._active_sleep_test: int | None = None
        self._screen_refresh_lock = asyncio.Lock()
        self._refresh_task: asyncio.Task[None] | None = None
        self._user_path: str | None = None
        self._desktop_paths: set[str] = set()
        self._display_target: str | None = None
        self._display_failed = False
        self._display_poll_interval = 0.25
        self._next_display_check = 0.0
        self._start_lock = asyncio.Lock()
        self._prepare_lock = asyncio.Lock()
        self._preparing_screen = False
        self._requested_lock: _RequestedLock | None = None
        self._screen_read_serial = 0
        self._bound_screen_test: tuple[ObserverContext, int] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._saved_screen_task: asyncio.Task[None] | None = None
        self._saved_screen_interval = 5.0
        self._saved_screen_retry = 15.0
        self.status = SessionWatchStatus(SessionWatchState.STARTING, "not_started")
        self._published_contexts: tuple[
            ObserverContext | None, ObserverContext | None
        ] = (None, None)

    @property
    def screen_context(self) -> ObserverContext | None:
        if (
            self._closed
            or not self._system_trusted
            or not self._system_connected
            or not self._screen_connected
            or self._screen_owner is None
            or self._session_id is None
            or not self.status.screen_events
        ):
            return None
        return ObserverContext(
            "linux",
            self._session_id,
            self._screen_generation,
            self._watch_nonce
            + "|"
            + str(self._system_owner)
            + "|"
            + self._screen_owner,
        )

    @property
    def sleep_context(self) -> ObserverContext | None:
        if (
            self._closed
            or not self._system_trusted
            or not self._system_connected
            or self._system_owner is None
            or self._session_id is None
        ):
            return None
        return ObserverContext(
            "linux",
            self._session_id,
            self._system_generation,
            self._watch_nonce + "|" + self._system_owner,
        )

    @property
    def screen_history_compatible(self) -> bool:
        # Missing transport is a live readiness warning, not proof that the
        # historical contract changed. A fresh owner must be re-attested first.
        return self.screen_context is None or self._screen_history_compatible

    @property
    def sleep_history_compatible(self) -> bool:
        return True

    @staticmethod
    def _sleep_gap() -> float | None:
        try:
            return time.clock_gettime(time.CLOCK_BOOTTIME) - time.monotonic()
        except (AttributeError, OSError, ValueError):
            return None

    def _observation(
        self, kind: str, *, actual_suspend: bool = False, test_id: int | None = None
    ) -> None:
        context = self.sleep_context if kind == "sleep_resume" else self.screen_context
        if context is not None and self._on_observation is not None:
            self._on_observation(
                SessionObservation(kind, context, actual_suspend, test_id)
            )

    def bind_screen_test(self, context: ObserverContext, test_id: int) -> None:
        if context != self.screen_context or type(test_id) is not int or test_id <= 0:
            raise ScreenLockUnavailable("observer_changed")
        self._bound_screen_test = (context, test_id)
        self._requested_lock = None

    def enable_saved_screen_monitoring(self) -> None:
        """Restore a validated saved contract by activation only, never OS Lock.

        Composition calls this only after loading this device's compatible
        history. Own bounded retries cover lazy owner exit and normal reconnect.
        """
        if self._closed or self._saved_screen_task is not None:
            return
        self._saved_screen_task = asyncio.create_task(self._restore_saved_screen())

    async def _restore_saved_screen(self) -> None:
        try:
            while not self._closed:
                if self.screen_context is None and not self._prepare_lock.locked():
                    try:
                        await self.prepare_screen_test(timeout=8.0)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # Historical proof remains separate from live readiness.
                        # No privilege changes, forced lock or tight retry loop.
                        pass
                await asyncio.sleep(
                    self._saved_screen_interval
                    if self.screen_context is not None
                    else self._saved_screen_retry
                )
        except asyncio.CancelledError:
            raise

    def bind_sleep_test(self, context: ObserverContext, test_id: int) -> None:
        if context != self.sleep_context or type(test_id) is not int or test_id <= 0:
            raise ScreenLockUnavailable("observer_changed")
        self._bound_sleep_test = (context, test_id)
        self._bound_sleep_issued = False
        self._bound_sleep_barrier = 0

    def unbind_sleep_test(self, context: ObserverContext, test_id: int) -> None:
        if self._bound_sleep_test == (context, test_id):
            self._bound_sleep_test = None
            self._bound_sleep_issued = False
            self._bound_sleep_barrier = 0

    async def prepare_sleep_test(self, *, timeout: float = 8.0) -> ObserverContext:
        """Attest ordinary logind suspend without an OS action or privilege prompt."""
        if self._closed or self._prepare_lock.locked():
            raise ScreenLockUnavailable("sleep_unavailable")
        async with self._prepare_lock:
            try:
                return await asyncio.wait_for(self._prepare_sleep_test(), timeout)
            except asyncio.CancelledError:
                raise
            except TimeoutError as error:
                raise ScreenLockUnavailable("preparation_timeout") from error
            except ScreenLockUnavailable:
                raise
            except Exception as error:
                raise ScreenLockUnavailable("sleep_unavailable") from error

    async def _prepare_sleep_test(self) -> ObserverContext:
        await self._restart_system_if_needed()
        await self.start()
        await self._refresh_system()
        context = self.sleep_context
        if context is None:
            raise ScreenLockUnavailable("observation_unavailable")
        await self._validate_sleep_request(context)
        return context

    async def _validate_sleep_request(self, context: ObserverContext) -> int:
        if (
            context != self.sleep_context
            or self._system is None
            or self._system_owner is None
        ):
            raise ScreenLockUnavailable("observer_changed")
        bus, owner = self._system, self._system_owner
        peer = await self._identity(bus, owner, "logind")
        path = await self._session_for_pid(os.getpid())
        props = await self._session_properties(path)
        if (
            path != self._session_path
            or props.get("Id") != context.session_id
            or props.get("User", [None])[0] != os.getuid()
            or props.get("Remote") is not False
            or props.get("Active") is not True
            or props.get("Type") != "x11"
            or props.get("Class") != "user"
            or any(
                props.get(key) != value for key, value in self._session_binding.items()
            )
        ):
            raise ScreenLockUnavailable("session_changed")
        reply = await bus.call(owner, _LOGIN_PATH, _MANAGER, "CanSuspend", timeout=2)
        if (
            reply.sender != owner
            or reply.signature != "s"
            or len(reply.body) != 1
            or reply.body[0] not in {"yes", "no", "na", "challenge"}
        ):
            raise ScreenLockUnavailable("sleep_unavailable")
        if reply.body[0] != "yes":
            raise ScreenLockUnavailable(
                "sleep_permission_required"
                if reply.body[0] == "challenge"
                else "sleep_unavailable"
            )
        await self._same_peer(bus, _LOGIN, owner, "logind", peer)
        # This is the final await. Its sender serial is a FIFO barrier for
        # queued logind signals before the fixed Suspend send below.
        inhibitors = await bus.call(
            owner, _LOGIN_PATH, _MANAGER, "ListInhibitors", timeout=2
        )
        if (
            inhibitors.sender != owner
            or inhibitors.signature != "a(ssssuu)"
            or len(inhibitors.body) != 1
            or type(inhibitors.body[0]) is not list
            or type(inhibitors.serial) is not int
            or not 0 < inhibitors.serial < 2**32
        ):
            raise ScreenLockUnavailable("sleep_unavailable")
        for item in inhibitors.body[0]:
            if (
                not isinstance(item, (list, tuple))
                or len(item) != 6
                or any(type(value) is not str for value in item[:4])
                or any(
                    type(value) is not int or not 0 <= value < 2**32
                    for value in item[4:]
                )
            ):
                raise ScreenLockUnavailable("sleep_unavailable")
            if "sleep" in item[0].split(":") and item[3] in {"block", "block-weak"}:
                raise ScreenLockUnavailable("sleep_inhibited")
            if item[3] not in {"block", "block-weak", "delay"}:
                raise ScreenLockUnavailable("sleep_unavailable")
        if context != self.sleep_context:
            raise ScreenLockUnavailable("observer_changed")
        return inhibitors.serial

    async def request_sleep(self, context: ObserverContext) -> None:
        """Only an explicit application action may call ordinary Suspend(false)."""
        barrier = await self._validate_sleep_request(context)
        if self._bound_sleep_test is None or self._bound_sleep_test[0] != context:
            raise ScreenLockUnavailable("observer_changed")
        assert self._system is not None and self._system_owner is not None
        owner = self._system_owner
        self._bound_sleep_barrier = barrier
        self._bound_sleep_issued = True
        try:
            reply = await self._system.call(
                owner, _LOGIN_PATH, _MANAGER, "Suspend", "b", [False], timeout=900
            )
        except DBusError as error:
            raise ScreenLockUnavailable(
                "sleep_permission_required"
                if error.name
                in {
                    "org.freedesktop.DBus.Error.AccessDenied",
                    "org.freedesktop.DBus.Error.AuthFailed",
                    "org.freedesktop.DBus.Error.InteractiveAuthorizationRequired",
                }
                else "sleep_unavailable"
            ) from error
        if reply.sender != owner or reply.signature != "" or reply.body:
            raise ScreenLockUnavailable("sleep_unavailable")

    async def read_screen_state(self, context: ObserverContext) -> ScreenState:
        """Read attested state without invoking the application's normal lock path.

        A generic ActiveChanged/GetActive is merely a visible screensaver. The
        alternative to logind evidence is a scoped explicit Lock of the attested
        canonical Cinnamon package with its known locking preconditions, plus
        actual activation evidence. Successful method return alone never passes.
        """
        if context != self.screen_context:
            raise ScreenLockUnavailable("observer_changed")
        assert self._system is not None and self._desktop is not None
        assert self._system_owner is not None and self._screen_owner is not None
        system_owner, screen_owner = self._system_owner, self._screen_owner
        system_peer = await self._identity(self._system, system_owner, "logind")
        screen_peer = await self._identity(self._desktop, screen_owner, "cinnamon")
        path = await self._session_for_pid(os.getpid())
        if path != self._session_path:
            raise ScreenLockUnavailable("observer_changed")
        props = await self._session_properties(path)
        if (
            props.get("Id") != context.session_id
            or props.get("User", [None])[0] != os.getuid()
            or props.get("Remote") is not False
            or props.get("Type") != "x11"
            or props.get("Class") != "user"
            or props.get("Active") is not True
            or type(props.get("LockedHint")) is not bool
            or props.get("Desktop") not in {"cinnamon", "cinnamon2d"}
            or any(
                props.get(key) != value for key, value in self._session_binding.items()
            )
            or not isinstance(props.get("Display"), str)
            or not self._display_verifier(props["Display"], os.getuid())
        ):
            raise ScreenLockUnavailable("session_changed")
        try:
            screen_path = await self._session_for_pid(screen_peer.pid)
        except DBusError as error:
            if (
                error.name != _LOGIN + ".NoSessionForPID"
                or error.sender != system_owner
            ):
                raise
            await self._per_user_desktop(screen_peer.pid)
        else:
            if screen_path != path:
                raise ScreenLockUnavailable("session_changed")
        reply = await self._desktop.call(
            screen_owner, _SCREEN_PATH, _SCREEN, "GetActive", timeout=2
        )
        if (
            reply.sender != screen_owner
            or reply.signature != "b"
            or len(reply.body) != 1
            or type(reply.body[0]) is not bool
        ):
            raise ScreenLockUnavailable("state_unavailable")
        await self._same_peer(self._system, _LOGIN, system_owner, "logind", system_peer)
        await self._same_peer(
            self._desktop, _SCREEN, screen_owner, "cinnamon", screen_peer
        )
        if context != self.screen_context:
            raise ScreenLockUnavailable("observer_changed")
        self._screen_read_serial = reply.serial
        active, hint = reply.body[0], props["LockedHint"]
        cycle = self._requested_lock
        compatible_now = self._screen_per_user and self._lock_contract_verifier(
            screen_peer.pid
        )
        if compatible_now != self._screen_history_compatible:
            self._screen_history_compatible = compatible_now
            if self._on_status is not None:
                self._on_status(self.status)
        capable_now = cycle is not None and compatible_now
        if cycle is not None and cycle.lock_published and not capable_now:
            self._invalidate_screen("cinnamon_untrusted")
            raise ScreenLockUnavailable("observer_changed")
        hint_proven = hint and (
            cycle is None
            or (
                cycle.context == context
                and cycle.acknowledged
                and self._fresh_active(cycle)
                and not cycle.inactive_seen
            )
        )
        contract = (
            cycle is not None
            and cycle.context == context
            and cycle.capable
            and cycle.acknowledged
            and self._fresh_active(cycle)
            and not cycle.inactive_seen
            and capable_now
        )
        return ScreenState(
            context,
            True
            if active and (hint_proven or contract)
            else False
            if not active and not hint
            else None,
        )

    async def request_screen_lock(self, context: ObserverContext) -> None:
        """Only an explicit user action calls the fixed Cinnamon Lock API."""
        state = await self.read_screen_state(context)
        baseline_serial = self._screen_read_serial
        if state.locked is not False:
            raise ScreenLockUnavailable("already_locked_or_unconfirmed")
        assert self._desktop is not None and self._screen_owner is not None
        assert self._system is not None
        owner = self._screen_owner
        peer = await self._identity(self._desktop, owner, "cinnamon")
        capable = self._screen_per_user and self._lock_contract_verifier(peer.pid)
        if context != self.screen_context or owner != self._screen_owner:
            raise ScreenLockUnavailable("observer_changed")
        bound = self._bound_screen_test
        cycle = _RequestedLock(
            context,
            capable,
            baseline_serial=baseline_serial,
            test_id=bound[1] if bound is not None and bound[0] == context else None,
        )
        self._requested_lock = cycle
        reply = await self._desktop.call(
            owner, _SCREEN_PATH, _SCREEN, "Lock", "s", [""], timeout=5
        )
        if (
            context != self.screen_context
            or reply.sender != owner
            or reply.signature != ""
            or reply.body
        ):
            raise ScreenLockUnavailable("request_unavailable")
        await self._same_peer(self._desktop, _SCREEN, owner, "cinnamon", peer)
        cycle.capable = (
            capable and self._screen_per_user and self._lock_contract_verifier(peer.pid)
        )
        if context != self.screen_context or self._requested_lock is not cycle:
            raise ScreenLockUnavailable("observer_changed")
        cycle.acknowledged = True
        cycle.acknowledgement_serial = reply.serial
        self._publish_requested_lock()

    @staticmethod
    def _serial_after(value: int, barrier: int) -> bool:
        return (
            type(value) is int
            and type(barrier) is int
            and 0 < value < 2**32
            and 0 < barrier < 2**32
            and 0 < ((value - barrier) & 0xFFFFFFFF) < 2**31
        )

    @classmethod
    def _fresh_active(cls, cycle: _RequestedLock) -> bool:
        # A half-range FIFO barrier rejects stale queued frames and ambiguous
        # wrap. Supported service Lock replies precede its ActiveChanged frame.
        return cls._serial_after(
            cycle.acknowledgement_serial, cycle.baseline_serial
        ) and cls._serial_after(cycle.active_serial, cycle.acknowledgement_serial)

    def _publish_requested_lock(self) -> None:
        cycle = self._requested_lock
        if (
            cycle is None
            or cycle.context != self.screen_context
            or not cycle.capable
            or not cycle.acknowledged
            or not self._fresh_active(cycle)
        ):
            return
        if not cycle.lock_published:
            cycle.lock_published = True
            self._observation("screen_locked", test_id=cycle.test_id)
        if (
            cycle.inactive_seen
            and self._serial_after(cycle.inactive_serial, cycle.active_serial)
            and not cycle.inactive_published
        ):
            cycle.inactive_published = True
            self._observation("screen_inactive", test_id=cycle.test_id)

    async def prepare_screen_test(self, *, timeout: float = 8.0) -> ObserverContext:
        """Prepare the ordinary lazy service without locking the OS or the app."""
        if self._closed or self._prepare_lock.locked():
            raise ScreenLockUnavailable("activation_unavailable")
        async with self._prepare_lock:
            self._preparing_screen = True
            try:
                return await asyncio.wait_for(self._prepare_screen_test(), timeout)
            except asyncio.CancelledError:
                raise
            except TimeoutError as error:
                raise ScreenLockUnavailable("preparation_timeout") from error
            except ScreenLockUnavailable:
                raise
            except DBusError as error:
                code = (
                    "preparation_timeout"
                    if error.name
                    in {
                        "org.freedesktop.DBus.Error.NoReply",
                        "org.freedesktop.DBus.Error.TimedOut",
                    }
                    else "activation_unavailable"
                )
                raise ScreenLockUnavailable(code) from error
            except Exception as error:
                raise ScreenLockUnavailable("activation_untrusted") from error
            finally:
                self._preparing_screen = False

    async def _restart_system_if_needed(self) -> None:
        if self._started and (
            self._failed or self._system is None or not self._system_connected
        ):
            async with self._start_lock:
                await self._stop_tasks()
                await self._close_buses()
                self._started = self._failed = False
                self._system_owner = self._screen_owner = None
                self._screen_generation += 1
                self._system_generation += 1
                self._requested_lock = None
                self._bound_screen_test = None
                self._bound_sleep_test = None
                self._bound_sleep_issued = False
                self._bound_sleep_barrier = 0
                self._sleep_begin_serial = 0
                self._active_sleep_test = None
                self._sleep_gap_before = None
                self._sleep_signal_pending = False
                self._status(
                    SessionWatchState.STARTING,
                    "reconnecting",
                    system=False,
                    screen=False,
                )

    async def _prepare_screen_test(self) -> ObserverContext:
        await self._restart_system_if_needed()
        await self.start()
        if self._system is None or not self._system_trusted:
            raise ScreenLockUnavailable("observation_unavailable")
        if self._desktop is None or not self._screen_connected:
            candidate_system, desktop = self._bus_factory()
            if candidate_system is not self._system:
                await candidate_system.aclose()
            if desktop is None:
                raise ScreenLockUnavailable("observation_unavailable")
            try:
                await desktop.add_match(
                    "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.cinnamon.ScreenSaver'"
                )
                await desktop.add_match(
                    f"type='signal',sender='{_SCREEN}',path='{_SCREEN_PATH}',interface='{_SCREEN}'"
                )
            except BaseException:
                await desktop.aclose()
                raise
            self._desktop = desktop
            self._screen_connected = True
            self._tasks.append(
                asyncio.create_task(self._consume(desktop, system=False))
            )
            if self._keepalive_task is not None:
                self._keepalive_task.cancel()
            self._keepalive_task = asyncio.create_task(self._keep_screen_service())
        await self._refresh_system()
        await self._refresh_screen()
        if self.screen_context is None:
            # The metadata attestation precedes the fixed platform activation.
            await self._per_user_desktop(None)
            reply = await self._desktop.call(
                _DBUS,
                _DBUS_PATH,
                _DBUS,
                "StartServiceByName",
                "su",
                [_SCREEN, 0],
                timeout=5,
            )
            if (
                reply.sender != _DBUS
                or reply.signature != "u"
                or reply.body not in ([1], [2])
            ):
                raise ScreenLockUnavailable("activation_unavailable")
            while self.screen_context is None:
                await self._refresh_system()
                await self._refresh_screen()
                if self.screen_context is None:
                    await asyncio.sleep(0.02)
        context = self.screen_context
        assert context is not None
        # Complete final attestation, never return a stale snapshot from startup.
        await self.read_screen_state(context)
        return context

    def _status(
        self, state: SessionWatchState, code: str, *, system: bool, screen: bool
    ) -> None:
        if self._closed and state != SessionWatchState.CLOSED:
            return
        status = SessionWatchStatus(state, code, system, screen)
        changed = self.status != status
        self.status = status
        contexts = self.screen_context, self.sleep_context
        if changed or contexts != self._published_contexts:
            self._published_contexts = contexts
            if self._on_status is not None:
                self._on_status(status)

    def _revoke(self, event: SessionSecurityEvent) -> None:
        if not self._closed:
            self._on_revoke(event)

    async def _daemon(
        self, bus: SessionBus, member: str, signature: str, body: list
    ) -> list:
        reply = await bus.call(_DBUS, _DBUS_PATH, _DBUS, member, signature, body)
        expected = {
            "NameHasOwner": "b",
            "GetNameOwner": "s",
            "GetConnectionUnixUser": "u",
            "GetConnectionUnixProcessID": "u",
        }
        if reply.sender != _DBUS or reply.signature != expected.get(member):
            raise RuntimeError("untrusted_bus_daemon_reply")
        return reply.body

    async def _owner(self, bus: SessionBus, name: str) -> str | None:
        present = await self._daemon(bus, "NameHasOwner", "s", [name])
        if len(present) != 1 or type(present[0]) is not bool:
            raise RuntimeError("invalid_bus_owner_reply")
        if present[0] is False:
            return None
        body = await self._daemon(bus, "GetNameOwner", "s", [name])
        if (
            len(body) != 1
            or not isinstance(body[0], str)
            or re.fullmatch(r":\d+\.\d+", body[0]) is None
        ):
            raise RuntimeError("invalid_bus_owner_reply")
        return body[0]

    async def _identity(self, bus: SessionBus, owner: str, role: str) -> _Peer:
        users = await self._daemon(bus, "GetConnectionUnixUser", "s", [owner])
        pids = await self._daemon(bus, "GetConnectionUnixProcessID", "s", [owner])
        if (
            len(users) != 1
            or type(users[0]) is not int
            or users[0] != (0 if role == "logind" else os.getuid())
            or len(pids) != 1
            or type(pids[0]) is not int
            or pids[0] <= 0
        ):
            raise RuntimeError("untrusted_service_process")
        stamp = self._process_snapshot(pids[0])
        if (
            not self._process_verifier(role, pids[0], users[0])
            or self._process_snapshot(pids[0]) != stamp
        ):
            raise RuntimeError("untrusted_service_process")
        if role == "logind":
            if users[0] != 0:
                raise RuntimeError("untrusted_service_process")
            await self._service_verifier(bus, _LOGIN, owner, 0)
        if self._process_snapshot(pids[0]) != stamp:
            raise RuntimeError("service_process_changed")
        return _Peer(pids[0], users[0], stamp)

    async def _same_peer(
        self, bus: SessionBus, name: str, owner: str, role: str, peer: _Peer
    ) -> None:
        if (
            await self._owner(bus, name) != owner
            or await self._identity(bus, owner, role) != peer
            or await self._owner(bus, name) != owner
            or self._process_snapshot(peer.pid) != peer.stamp
        ):
            raise RuntimeError("service_identity_changed")

    async def _login_call(
        self, path: str, interface: str, member: str, signature: str = "", body=None
    ) -> list:
        assert self._system is not None
        if self._system_owner is None:
            raise RuntimeError("logind_unavailable")
        reply = await self._system.call(
            self._system_owner, path, interface, member, signature, body
        )
        expected = {"GetSessionByPID": "o", "GetUser": "o", "GetAll": "a{sv}"}
        if reply.sender != self._system_owner or reply.signature != expected.get(
            member
        ):
            raise RuntimeError("untrusted_logind_reply")
        return reply.body

    async def _session_for_pid(self, pid: int) -> str:
        body = await self._login_call(
            _LOGIN_PATH, _MANAGER, "GetSessionByPID", "u", [pid]
        )
        if (
            len(body) != 1
            or not isinstance(body[0], str)
            or not body[0].startswith(_LOGIN_PATH + "/session/")
            or body[0].rsplit("/", 1)[1] in ("self", "auto", "")
        ):
            raise RuntimeError("invalid_session_path")
        return body[0]

    async def _refresh_system(self) -> None:
        assert self._system is not None
        owner = await self._owner(self._system, _LOGIN)
        if owner is None:
            raise RuntimeError("logind_unavailable")
        peer = await self._identity(self._system, owner, "logind")
        if self._system_owner != owner:
            self._system_trusted = False
            self._system_generation += 1
            self._bound_sleep_test = None
            self._bound_sleep_issued = False
            self._bound_sleep_barrier = 0
            self._sleep_begin_serial = 0
            self._active_sleep_test = None
            self._sleep_gap_before = None
            self._sleep_signal_pending = False
        self._system_owner = owner
        path = await self._session_for_pid(os.getpid())
        result = await self._login_call(path, _PROPERTIES, "GetAll", "s", [_SESSION])
        if len(result) != 1:
            raise RuntimeError("invalid_session_properties")
        properties = dict(result[0])
        user = properties.get("User")
        if (
            not isinstance(user, (tuple, list))
            or len(user) != 2
            or type(user[0]) is not int
            or user[0] != os.getuid()
            or properties.get("Remote") is not False
            or properties.get("Type") != "x11"
            or properties.get("Class") != "user"
            or type(properties.get("Active")) is not bool
            or type(properties.get("LockedHint")) is not bool
            or not isinstance(properties.get("Id"), str)
            or not properties["Id"]
        ):
            raise RuntimeError("unsupported_session")
        if self._session_path is not None and (
            path != self._session_path or properties["Id"] != self._session_id
        ):
            raise RuntimeError("session_identity_changed")
        self._session_path, self._session_id = path, properties["Id"]
        self._session_active = properties["Active"]
        self._session_binding = {
            key: copy.deepcopy(properties.get(key))
            for key in (
                "User",
                "Id",
                "Remote",
                "Type",
                "Class",
                "Display",
                "Desktop",
                "Seat",
            )
        }
        await self._same_peer(self._system, _LOGIN, owner, "logind", peer)
        self._system_trusted = True
        if properties.get("Active") is not True:
            self._revoke(SessionSecurityEvent.SESSION_CHANGE)
        if properties.get("LockedHint") is True:
            self._revoke(SessionSecurityEvent.SCREEN_LOCK)

    async def _session_properties(self, path: str) -> dict:
        result = await self._login_call(path, _PROPERTIES, "GetAll", "s", [_SESSION])
        if len(result) != 1 or not isinstance(result[0], dict):
            raise RuntimeError("invalid_session_properties")
        return copy.deepcopy(result[0])

    async def _per_user_desktop(self, pid: int | None) -> None:
        assert self._desktop is not None
        assert self._system is not None
        session_path, session_id = self._session_path, self._session_id
        if session_path is None or session_id is None:
            raise RuntimeError("missing_application_session")
        if pid is None:
            await self._activation_preparer(self._system, self._desktop, os.getuid())
        else:
            await self._activation_verifier(
                self._system, self._desktop, pid, os.getuid()
            )
        body = await self._login_call(
            _LOGIN_PATH, _MANAGER, "GetUser", "u", [os.getuid()]
        )
        if (
            len(body) != 1
            or not isinstance(body[0], str)
            or not body[0].startswith(_LOGIN_PATH + "/user/")
        ):
            raise RuntimeError("invalid_logind_user")
        user_path = body[0]
        # Register BEFORE GetAll can yield a concurrent User.Display/Sessions event.
        self._user_path = user_path
        result = await self._login_call(
            user_path, _PROPERTIES, "GetAll", "s", [_LOGIN + ".User"]
        )
        if len(result) != 1 or not isinstance(result[0], dict):
            raise RuntimeError("invalid_logind_user")
        user = copy.deepcopy(result[0])
        if user.get("Display") != [session_id, session_path]:
            raise RuntimeError("ambiguous_user_display")
        sessions = user.get("Sessions")
        if not isinstance(sessions, list) or not sessions or len(sessions) > 128:
            raise RuntimeError("invalid_user_sessions")
        paths: dict[str, str] = {}
        for item in sessions:
            if (
                not isinstance(item, (list, tuple))
                or len(item) != 2
                or not isinstance(item[0], str)
                or not isinstance(item[1], str)
                or not item[1].startswith(_LOGIN_PATH + "/session/")
                or item[1] in paths
            ):
                raise RuntimeError("invalid_user_sessions")
            paths[item[1]] = item[0]
        # A formerly tty session can become graphical while a LATER GetAll waits.
        # Register every path before the first such await and snapshot each reply.
        self._desktop_paths = set(paths)
        snapshots: dict[str, dict] = {}
        graphical = []
        for path, identity in paths.items():
            properties = await self._session_properties(path)
            snapshots[path] = properties
            if (
                properties.get("Id") != identity
                or properties.get("User", [None])[0] != os.getuid()
            ):
                raise RuntimeError("invalid_user_sessions")
            if properties.get("Remote") is False and properties.get("Type") in {
                "x11",
                "wayland",
            }:
                graphical.append((path, properties))
        if len(graphical) != 1 or graphical[0][0] != session_path:
            raise RuntimeError("ambiguous_graphical_sessions")
        properties = graphical[0][1]
        display = properties.get("Display")
        seat = properties.get("Seat")
        if (
            properties.get("Active") is not True
            or properties.get("Type") != "x11"
            or properties.get("Class") != "user"
            or properties.get("Desktop") not in {"cinnamon", "cinnamon2d"}
            or not isinstance(display, str)
            or re.fullmatch(r":\d+(?:\.0)?", display) is None
            or not isinstance(seat, (list, tuple))
            or len(seat) != 2
            or not seat[0]
        ):
            raise RuntimeError("unsupported_user_desktop")
        self._display_target = display
        self._display_failed = not self._display_verifier(display, os.getuid())
        self._next_display_check = time.monotonic() + self._display_poll_interval
        if self._display_failed:
            raise RuntimeError("unsupported_user_desktop")
        # Re-read EVERY session, including those classified as tty. In addition to
        # subscribed change events this rejects a changed/mixed first snapshot.
        trust_keys = (
            "User",
            "Id",
            "Remote",
            "Type",
            "Class",
            "Active",
            "Display",
            "Desktop",
            "Seat",
        )
        for path, snapshot in snapshots.items():
            current = await self._session_properties(path)
            if any(current.get(key) != snapshot.get(key) for key in trust_keys):
                raise RuntimeError("desktop_metadata_changed")
        again = await self._login_call(
            user_path, _PROPERTIES, "GetAll", "s", [_LOGIN + ".User"]
        )
        if (
            len(again) != 1
            or not isinstance(again[0], dict)
            or any(
                again[0].get(key) != user.get(key) for key in ("Display", "Sessions")
            )
        ):
            raise RuntimeError("desktop_metadata_changed")

    async def _refresh_screen(self) -> None:
        async with self._screen_refresh_lock:
            if self._desktop is None:
                return
            if (
                not self._screen_connected
                or not self._system_connected
                or self._system_owner is None
                or not self._system_trusted
            ):
                return
            generation = self._screen_generation
            owner = await self._owner(self._desktop, _SCREEN)
            if generation != self._screen_generation or not self._system_trusted:
                raise RuntimeError("stale_screen_attestation")
            if owner is None:
                if self._screen_owner is not None:
                    self._invalidate_screen("service_owner_changed")
                self._display_target = None
                self._display_failed = False
                self._status(
                    SessionWatchState.WAITING_SCREEN_SERVICE,
                    "cinnamon_waiting",
                    system=True,
                    screen=False,
                )
                return
            if self._screen_owner is not None and owner != self._screen_owner:
                self._invalidate_screen("service_owner_changed")
                generation = self._screen_generation
            peer = await self._identity(self._desktop, owner, "cinnamon")
            per_user = False
            try:
                path = await self._session_for_pid(peer.pid)
            except DBusError as error:
                if (
                    error.name != _LOGIN + ".NoSessionForPID"
                    or error.sender != self._system_owner
                ):
                    raise
                await self._per_user_desktop(peer.pid)
                per_user = True
            else:
                if path != self._session_path:
                    raise RuntimeError("screensaver_session_mismatch")
                self._display_target = None
                self._display_failed = False
            reply = await self._desktop.call(owner, _SCREEN_PATH, _SCREEN, "GetActive")
            if (
                reply.sender != owner
                or reply.signature != "b"
                or len(reply.body) != 1
                or type(reply.body[0]) is not bool
            ):
                raise RuntimeError("invalid_screensaver_state")
            await self._same_peer(self._desktop, _SCREEN, owner, "cinnamon", peer)
            if per_user:
                # Final synchronous snapshot closes the async attestation window.
                self._check_display_namespace(force=True)
            if (
                generation != self._screen_generation
                or self._closed
                or not self._system_connected
                or not self._system_trusted
            ):
                raise RuntimeError("stale_screen_attestation")
            self._screen_owner, self._screen_per_user = owner, per_user
            compatible = per_user and self._lock_contract_verifier(peer.pid)
            compatibility_changed = compatible != self._screen_history_compatible
            self._screen_history_compatible = compatible
            self._status(
                SessionWatchState.READY,
                "watching_per_user" if per_user else "watching",
                system=True,
                screen=True,
            )
            if compatibility_changed and self._on_status is not None:
                self._on_status(self.status)
            if reply.body[0]:
                self._revoke(SessionSecurityEvent.SCREEN_LOCK)

    async def start(self) -> SessionWatchStatus:
        async with self._start_lock:
            if self._started or self._closed:
                return self.status
            self._started = True
            try:
                self._system, self._desktop = self._bus_factory()
                self._system_connected = True
                await self._system.add_match(
                    "type='signal',sender='org.freedesktop.DBus',"
                    "interface='org.freedesktop.DBus',member='NameOwnerChanged',"
                    "arg0='org.freedesktop.login1'"
                )
                await self._system.add_match(
                    "type='signal',sender='org.freedesktop.login1',"
                    "interface='org.freedesktop.login1.Manager'"
                )
                await self._refresh_system()
                for interface in (_SESSION, _PROPERTIES):
                    location = (
                        f"path='{self._session_path}'"
                        if interface == _SESSION
                        else f"path_namespace='{_LOGIN_PATH}'"
                    )
                    await self._system.add_match(
                        f"type='signal',sender='{_LOGIN}',{location},interface='{interface}'"
                    )
                # Re-read after AddMatch, before reporting any subscription ready.
                await self._refresh_system()
                if self._closed:
                    return self.status
                self._tasks.append(
                    asyncio.create_task(self._consume(self._system, system=True))
                )
                if self._desktop is not None:
                    try:
                        await self._desktop.add_match(
                            "type='signal',sender='org.freedesktop.DBus',"
                            "interface='org.freedesktop.DBus',member='NameOwnerChanged',"
                            "arg0='org.cinnamon.ScreenSaver'"
                        )
                        await self._desktop.add_match(
                            f"type='signal',sender='{_SCREEN}',path='{_SCREEN_PATH}',"
                            f"interface='{_SCREEN}',member='ActiveChanged'"
                        )
                    except Exception:
                        desktop, self._desktop = self._desktop, None
                        try:
                            await desktop.aclose()
                        except Exception:
                            pass
                    else:
                        self._screen_connected = True
                        self._tasks.append(
                            asyncio.create_task(
                                self._consume(self._desktop, system=False)
                            )
                        )
                if self._desktop is None:
                    self._invalidate_screen("screen_bus_unavailable")
                else:
                    await self._recheck_screen()
                    self._keepalive_task = asyncio.create_task(
                        self._keep_screen_service()
                    )
            except (Exception, asyncio.CancelledError) as error:
                self._system_owner = self._screen_owner = None
                self._revoke(SessionSecurityEvent.TRUST_LOST)
                self._status(
                    SessionWatchState.UNAVAILABLE,
                    "session_watch_unavailable",
                    system=False,
                    screen=False,
                )
                await self._stop_tasks()
                await self._close_buses()
                if isinstance(error, asyncio.CancelledError):
                    raise
            return self.status

    def _invalidate_screen(self, code: str, *, revoke: bool = True) -> None:
        self._screen_generation += 1
        self._screen_owner = None
        self._screen_per_user = False
        self._requested_lock = None
        self._bound_screen_test = None
        if revoke:
            self._revoke(SessionSecurityEvent.TRUST_LOST)
        self._status(
            SessionWatchState.UNAVAILABLE,
            code,
            system=self._system_trusted and self._system_connected,
            screen=False,
        )

    async def _recheck_screen(self) -> None:
        while not self._closed and self._system_connected and self._screen_connected:
            generation = self._screen_generation
            try:
                # Revalidate app/session metadata for both screen ownership models.
                # A stable attested logind consumer continues handling sleep events.
                await self._refresh_system()
                await self._refresh_screen()
            except asyncio.CancelledError:
                raise
            except Exception:
                if (
                    self._closed
                    or not self._system_connected
                    or not self._screen_connected
                ):
                    return
                if generation != self._screen_generation:
                    continue
                self._invalidate_screen("cinnamon_untrusted")
            if (
                generation == self._screen_generation
                or self.status.code == "cinnamon_untrusted"
            ):
                return

    def _check_display_namespace(self, *, force: bool = False) -> None:
        """Bounded polling covers X servers created without any logind event.

        The existing independent system consumer polls at most every 250 ms while
        this per-user display attestation is relevant, including on a busy bus.
        As with D-Bus delivery this is asynchronous detection, not a hard real-time
        guarantee. Recovery performs complete attestation and never opens access.
        """
        now = time.monotonic()
        if (
            self._display_target is None
            or not self._system_trusted
            or not self._screen_connected
            or (not force and now < self._next_display_check)
        ):
            return
        self._next_display_check = now + self._display_poll_interval
        try:
            valid = self._display_verifier(self._display_target, os.getuid())
        except Exception:
            valid = False
        if not valid and not self._display_failed:
            self._display_failed = True
            self._invalidate_screen("display_namespace_changed")
        elif valid and self._display_failed:
            self._display_failed = False
            self._invalidate_screen("display_namespace_rechecking", revoke=False)
            self._schedule_screen_check()

    def _schedule_screen_check(self) -> None:
        if (
            self._closed
            or not self._system_connected
            or not self._screen_connected
            or not self._system_trusted
        ):
            return
        # A single worker coalesces bursts; it never replaces the two consumers.
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._recheck_screen())

    @staticmethod
    def _name_change(reply: DBusReply, name: str) -> bool:
        return (
            reply.sender == _DBUS
            and reply.path == _DBUS_PATH
            and reply.interface == _DBUS
            and reply.member == "NameOwnerChanged"
            and reply.signature == "sss"
            and len(reply.body) == 3
            and reply.body[0] == name
            and all(isinstance(value, str) for value in reply.body)
        )

    async def _consume(self, bus: SessionBus, *, system: bool) -> None:
        try:
            while not self._closed and not self._failed:
                if system:
                    self._check_display_namespace()
                try:
                    # Keep the short timeout from startup, so the first accepted
                    # per-user attestation cannot inherit a previous 1 s wait.
                    timeout = self._display_poll_interval if system else 1
                    reply = await bus.next_signal(timeout=timeout)
                except TimeoutError:
                    continue
                if reply is None:
                    continue
                if self._name_change(reply, _LOGIN if system else _SCREEN):
                    if (
                        not system
                        and reply.body[1] == ""
                        and reply.body[2]
                        and self._screen_owner in {None, reply.body[2]}
                    ):
                        # The first lazy appearance is not a replacement or a
                        # trust loss. Re-attest it before exposing a context.
                        # Its NameOwnerChanged may be queued after our final read.
                        if self._screen_owner is None:
                            await self._recheck_screen()
                        continue
                    # Seal before the first await. A replacement owner never unlocks.
                    if system:
                        self._system_owner = None
                        self._system_trusted = False
                    self._invalidate_screen("service_owner_changed")
                    if system:
                        try:
                            await self._refresh_system()
                        except Exception:
                            self._system_owner = None
                            self._status(
                                SessionWatchState.UNAVAILABLE,
                                "service_untrusted",
                                system=False,
                                screen=False,
                            )
                        else:
                            self._status(
                                SessionWatchState.UNAVAILABLE,
                                "screen_rechecking"
                                if self._screen_connected
                                else "screen_bus_unavailable",
                                system=True,
                                screen=False,
                            )
                            self._schedule_screen_check()
                    else:
                        await self._recheck_screen()
                    continue
                if system:
                    self._system_signal(reply)
                else:
                    self._screen_signal(reply)
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closed:
                self._revoke(SessionSecurityEvent.TRUST_LOST)
                self._screen_generation += 1
                self._screen_owner = None
                if system:
                    # Screen trust relies on the application logind identity.
                    self._system_owner = None
                    self._system_trusted = False
                    self._failed = True
                    current = asyncio.current_task()
                    for task in self._tasks:
                        if task is not current:
                            task.cancel()
                    if self._refresh_task is not None:
                        self._refresh_task.cancel()
                    self._status(
                        SessionWatchState.DISCONNECTED,
                        "system_bus_disconnected",
                        system=False,
                        screen=False,
                    )
                    await self._close_buses()
                else:
                    # The connected, verified system consumer keeps sleep protection.
                    self._screen_connected = False
                    self._desktop = None
                    self._status(
                        SessionWatchState.DISCONNECTED,
                        "screen_bus_disconnected",
                        system=self._system_owner is not None
                        and self._system_connected,
                        screen=False,
                    )
                    try:
                        await bus.aclose()
                    except Exception:
                        pass
                    # Transport reconnect requires a new application lifetime. Owner
                    # reactivation on an intact bus is independently re-attested above.

    def _screen_signal(self, reply: DBusReply) -> None:
        if (
            self._screen_owner is not None
            and reply.sender == self._screen_owner
            and reply.path == _SCREEN_PATH
            and reply.interface == _SCREEN
            and reply.member == "ActiveChanged"
            and reply.signature == "b"
            and len(reply.body) == 1
            and type(reply.body[0]) is bool
        ):
            if reply.body[0]:
                self._revoke(SessionSecurityEvent.SCREEN_LOCK)
                cycle = self._requested_lock
                if (
                    cycle is not None
                    and cycle.context == self.screen_context
                    and self._serial_after(reply.serial, cycle.baseline_serial)
                ):
                    cycle.active_seen = True
                    cycle.active_serial = reply.serial
                    self._publish_requested_lock()
            else:
                cycle = self._requested_lock
                if (
                    cycle is not None
                    and cycle.context == self.screen_context
                    and cycle.active_seen
                    and self._serial_after(reply.serial, cycle.active_serial)
                ):
                    cycle.inactive_seen = True
                    cycle.inactive_serial = reply.serial
                    self._publish_requested_lock()
                self._observation("screen_inactive")

    async def _keep_screen_service(self) -> None:
        """GetActive's normal hold/release keeps the attested lazy owner alive.

        Cinnamon otherwise exits 30 seconds after idle, which would invalidate a
        successful context. No --hold flag, setting or OS lock is used here.
        """
        try:
            while (
                not self._closed and self._system_connected and self._screen_connected
            ):
                await asyncio.sleep(5)
                context = self.screen_context
                if context is None:
                    continue
                try:
                    await self.read_screen_state(context)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if self.screen_context == context:
                        self._invalidate_screen("cinnamon_untrusted")
        except asyncio.CancelledError:
            raise

    def _system_signal(self, reply: DBusReply) -> None:
        if (
            not self._system_trusted
            or self._system_owner is None
            or reply.sender != self._system_owner
        ):
            return
        if reply.path == _LOGIN_PATH and reply.interface == _MANAGER:
            if (
                reply.signature == "b"
                and len(reply.body) == 1
                and reply.body[0] is True
            ):
                if reply.member == "PrepareForSleep":
                    if not self._sleep_signal_pending:
                        self._sleep_signal_pending = True
                        bound = self._bound_sleep_test
                        self._active_sleep_test = (
                            bound[1]
                            if bound is not None
                            and self._bound_sleep_issued
                            and bound[0] == self.sleep_context
                            and self._serial_after(
                                reply.serial, self._bound_sleep_barrier
                            )
                            else None
                        )
                        self._bound_sleep_test = None
                        self._bound_sleep_issued = False
                        self._bound_sleep_barrier = 0
                        self._sleep_begin_serial = reply.serial
                        self._revoke(SessionSecurityEvent.SLEEP)
                        # A kernel gap must follow the synchronous ordinary
                        # revoke. Freezing before this handler sealed access
                        # cannot be turned into a successful protection check.
                        self._sleep_gap_before = self._sleep_gap()
                elif reply.member == "PrepareForShutdown":
                    self._revoke(SessionSecurityEvent.SHUTDOWN)
            elif (
                reply.member == "PrepareForSleep"
                and reply.signature == "b"
                and len(reply.body) == 1
                and reply.body[0] is False
            ):
                if self._sleep_signal_pending and not self._serial_after(
                    reply.serial, self._sleep_begin_serial
                ):
                    return
                before, self._sleep_gap_before = self._sleep_gap_before, None
                self._sleep_begin_serial = 0
                self._sleep_signal_pending = False
                after = self._sleep_gap()
                self._observation(
                    "sleep_resume",
                    actual_suspend=before is not None
                    and after is not None
                    and after - before > 0.01,
                    test_id=self._active_sleep_test,
                )
                self._active_sleep_test = None
            elif (
                reply.member == "SessionRemoved"
                and reply.signature == "so"
                and reply.body == [self._session_id, self._session_path]
            ):
                self._revoke(SessionSecurityEvent.SESSION_CHANGE)
                self._system_owner = self._screen_owner = None
                self._system_trusted = False
                self._screen_generation += 1
                self._status(
                    SessionWatchState.UNAVAILABLE,
                    "session_removed",
                    system=False,
                    screen=False,
                )
            elif (
                reply.member in {"SessionNew", "SessionRemoved"}
                and reply.signature == "so"
                and len(reply.body) == 2
            ):
                self._invalidate_screen("desktop_topology_changed")
                self._schedule_screen_check()
            return
        if reply.path != self._session_path:
            if (
                reply.interface == _PROPERTIES
                and reply.member == "PropertiesChanged"
                and reply.signature == "sa{sv}as"
                and len(reply.body) == 3
                and (reply.path == self._user_path or reply.path in self._desktop_paths)
            ):
                if reply.path == self._user_path and self._only_user_idle_metadata(
                    reply.body
                ):
                    # Idle accounting changes during a normal Cinnamon lock.
                    # It does not change User.Display, Sessions or ownership.
                    # Every other property/malformed frame remains fail-closed.
                    return
                self._invalidate_screen("desktop_metadata_changed")
                self._schedule_screen_check()
            return
        if reply.interface == _SESSION:
            if reply.member == "Lock" and reply.signature == "" and not reply.body:
                self._revoke(SessionSecurityEvent.SCREEN_LOCK)
            return
        if (
            reply.interface != _PROPERTIES
            or reply.member != "PropertiesChanged"
            or reply.signature != "sa{sv}as"
            or len(reply.body) != 3
            or reply.body[0] != _SESSION
        ):
            return
        try:
            changed = dict(reply.body[1])
            invalidated = reply.body[2]
            if any(
                name in changed or name in invalidated
                for name in ("User", "Id", "Remote", "Type", "Class")
            ):
                self._revoke(SessionSecurityEvent.TRUST_LOST)
                self._system_owner = self._screen_owner = None
                self._system_trusted = False
                self._screen_generation += 1
                self._status(
                    SessionWatchState.UNAVAILABLE,
                    "session_identity_changed",
                    system=False,
                    screen=False,
                )
                return
            if changed.get("LockedHint") is True:
                self._revoke(SessionSecurityEvent.SCREEN_LOCK)
            if changed.get("Active") is False or changed.get("State") == "closing":
                self._revoke(SessionSecurityEvent.SESSION_CHANGE)
            active_changed = (
                type(changed.get("Active")) is bool
                and changed["Active"] != self._session_active
            )
            if active_changed:
                self._session_active = changed["Active"]
                self._invalidate_screen("desktop_metadata_changed", revoke=False)
                self._schedule_screen_check()
            if any(
                name in changed or name in invalidated
                for name in ("Display", "Desktop", "Seat")
            ):
                self._invalidate_screen("desktop_metadata_changed")
                self._schedule_screen_check()
            if any(name in invalidated for name in ("Active", "LockedHint")):
                self._invalidate_screen("session_metadata_invalidated")
                self._schedule_screen_check()
        except (ValueError, TypeError):
            self._revoke(SessionSecurityEvent.TRUST_LOST)

    @staticmethod
    def _only_user_idle_metadata(body: list) -> bool:
        if len(body) != 3 or body[0] != _LOGIN + ".User":
            return False
        changed, invalidated = body[1:]
        if type(changed) is not dict or type(invalidated) is not list:
            return False
        idle = {"IdleHint", "IdleSinceHint", "IdleSinceHintMonotonic"}
        if any(type(name) is not str or name not in idle for name in changed):
            return False
        if any(type(name) is not str or name not in idle for name in invalidated):
            return False
        names = set(changed) | set(invalidated)
        if (
            not names
            or len(set(invalidated)) != len(invalidated)
            or set(changed) & set(invalidated)
        ):
            return False
        return all(
            type(value) is bool
            if name == "IdleHint"
            else type(value) is int and 0 <= value < 2**64
            for name, value in changed.items()
        )

    async def _close_buses(self) -> None:
        buses = self._system, self._desktop
        self._system = self._desktop = None
        self._system_connected = self._screen_connected = False
        self._system_trusted = False
        for bus in buses:
            if bus is not None:
                try:
                    await bus.aclose()
                except Exception:
                    pass

    async def _stop_tasks(self) -> None:
        tasks = list(self._tasks)
        if self._refresh_task is not None:
            tasks.append(self._refresh_task)
        if self._keepalive_task is not None:
            tasks.append(self._keepalive_task)
        current = asyncio.current_task()
        tasks = [task for task in tasks if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._refresh_task = None
        self._keepalive_task = None

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bound_sleep_test = None
        self._bound_sleep_issued = False
        self._bound_sleep_barrier = 0
        self._sleep_begin_serial = 0
        self._active_sleep_test = None
        self._sleep_signal_pending = False
        self._sleep_gap_before = None
        restore, self._saved_screen_task = self._saved_screen_task, None
        if restore is not None and restore is not asyncio.current_task():
            restore.cancel()
            await asyncio.gather(restore, return_exceptions=True)
        async with self._start_lock:
            await self._stop_tasks()
            self._system_owner = self._screen_owner = None
            await self._close_buses()
            self._status(SessionWatchState.CLOSED, "closed", system=False, screen=False)
