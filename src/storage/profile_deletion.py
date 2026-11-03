"""Явное удаление одного профиля без разрешения читать его содержимое.

Локальный fsync intent предшествует удалению SecureStorage и SQLite. Его
наличие на startup имеет приоритет над обычным PIN/initialization reconcile.
Это протокол возобновления, а не транзакция двух разных хранилищ.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import secrets
import sqlite3
import stat
import sys
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import BuiltinFunctionType
from typing import Any

from storage.data_protection import (
    DATA_BINDING_ALIAS,
    DATA_INITIALIZATION_ALIAS,
    DATA_KEY_ALIAS,
)
from storage.database_connections import (
    DatabaseOwnershipError,
    database_lock,
    owned_database_identity,
    retire_database,
)
from storage.request_attempts import (
    TABLE as REQUEST_ATTEMPTS_TABLE,
)
from storage.request_attempts import validate_request_attempts_schema
from storage.secure_credentials import (
    API_KEY_STORAGE_NAME,
    REGISTRATION_ID_STORAGE_NAME,
    SecureStorageBackend,
)

PROFILE_ALIASES = (
    API_KEY_STORAGE_NAME,
    DATA_KEY_ALIAS,
    DATA_BINDING_ALIAS,
    DATA_INITIALIZATION_ALIAS,
    REGISTRATION_ID_STORAGE_NAME,
)
_MAX_METADATA_BYTES = 128 * 1024


def _json(raw: bytes | str) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ProfileDeletionError("metadata_invalid")
            value[key] = item
        return value

    def invalid(_constant: str) -> Any:
        raise ProfileDeletionError("metadata_invalid")

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


@dataclass(frozen=True)
class DeletionDiagnostic:
    """Только безопасная стадия и код, без paths, identities и backend errors."""

    stage: str
    code: str
    prepared: bool = False
    intent_pending: bool = False


class ProfileDeletionError(RuntimeError):
    """Безопасный отказ без содержимого базы или сообщения native backend."""

    def __init__(
        self, code: str = "path_unsafe", *, diagnostic: DeletionDiagnostic | None = None
    ) -> None:
        self.diagnostic = diagnostic or DeletionDiagnostic("inspect", code)
        super().__init__("profile_deletion.unavailable")


def _local_profile_account():
    import pwd

    return pwd.getpwuid(os.getuid())


def _authority_file(path: Path) -> bytes:
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ProfileDeletionError("directory_shared")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or info.st_nlink != 1
        ):
            raise ProfileDeletionError("directory_shared")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            value = stream.read(1024 * 1024 + 1)
        if len(value) > 1024 * 1024:
            raise ProfileDeletionError("directory_shared")
        return value
    finally:
        os.close(descriptor)


def _private_group_authority(account) -> str:
    """Finite local files/systemd policy. Unknown NSS/userdb is unsupported."""
    import grp
    import pwd

    if account.pw_uid != os.getuid() or account.pw_gid != account.pw_uid:
        raise ProfileDeletionError("directory_shared")
    config = _authority_file(Path("/etc/nsswitch.conf"))
    local_passwd = _authority_file(Path("/etc/passwd"))
    local_group = _authority_file(Path("/etc/group"))
    sources = {}
    for raw in config.decode("utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            name, values = line.split(":", 1)
            if name in {"passwd", "group", "initgroups"}:
                if name in sources:
                    raise ProfileDeletionError("directory_shared")
                sources[name] = values.split()
    accepted = (["files"], ["files", "systemd"])
    if (
        sources.get("passwd") not in accepted
        or sources.get("group") not in accepted
        or ("initgroups" in sources and sources["initgroups"] not in accepted)
    ):
        raise ProfileDeletionError("directory_shared")
    digest = hashlib.sha256(config + b"\0" + local_passwd + b"\0" + local_group)
    for name in (
        "/etc/userdb",
        "/run/userdb",
        "/run/host/userdb",
        "/usr/local/lib/userdb",
        "/usr/lib/userdb",
        "/run/systemd/userdb",
    ):
        directory = Path(name)
        if not directory.exists() and not directory.is_symlink():
            digest.update(name.encode() + b"absent")
            continue
        for parent in (directory, *directory.parents):
            info = parent.lstat()
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & 0o022
            ):
                raise ProfileDeletionError("directory_shared")
        children = list(directory.iterdir())
        if name == "/run/systemd/userdb":
            if any(child.name != "io.systemd.DynamicUser" for child in children):
                raise ProfileDeletionError("directory_shared")
            for child in children:
                info = child.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != 0:
                    raise ProfileDeletionError("directory_shared")
                digest.update(f"{name}:{info.st_dev}:{info.st_ino}".encode())
        elif children:
            raise ProfileDeletionError("directory_shared")
        info = directory.lstat()
        digest.update(f"{name}:{info.st_dev}:{info.st_ino}".encode())
    local_users = [
        line.split(":")
        for line in local_passwd.decode("utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    local_groups = [
        line.split(":")
        for line in local_group.decode("utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    if not any(
        len(row) == 7
        and row[0] == account.pw_name
        and int(row[2]) == account.pw_uid
        and int(row[3]) == account.pw_gid
        for row in local_users
    ):
        raise ProfileDeletionError("directory_shared")
    private = [
        row for row in local_groups if len(row) == 4 and int(row[2]) == account.pw_gid
    ]
    if len(private) != 1 or set(filter(None, private[0][3].split(","))) - {
        account.pw_name
    }:
        raise ProfileDeletionError("directory_shared")
    group = grp.getgrgid(account.pw_gid)
    if set(group.gr_mem) - {account.pw_name}:
        raise ProfileDeletionError("directory_shared")
    users = pwd.getpwall()
    if len(users) > 16384 or len(grp.getgrall()) > 16384:
        raise ProfileDeletionError("directory_shared")
    for peer in users:
        if peer.pw_uid == account.pw_uid:
            continue
        if peer.pw_gid == account.pw_gid or account.pw_gid in os.getgrouplist(
            peer.pw_name, peer.pw_gid
        ):
            raise ProfileDeletionError("directory_shared")
    # Root can assign supplementary groups outside NSS. Existing foreign
    # non-root peers with such a grant make the directory genuinely shared.
    mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    proc_mount = []
    for line in mounts:
        before, separator, after = line.partition(" - ")
        if separator:
            fields, detail = before.split(), after.split()
            if (
                len(fields) >= 6
                and len(detail) >= 3
                and fields[4] == "/proc"
                and detail[0] == "proc"
            ):
                proc_mount.append(fields[5] + "," + detail[2])
    if len(proc_mount) != 1 or any(
        option.startswith("hidepid=") and option != "hidepid=0"
        for option in proc_mount[0].split(",")
    ):
        raise ProfileDeletionError("directory_shared")
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            fields = {}
            for line in (process / "status").read_text().splitlines():
                if line.startswith(("Uid:", "Gid:", "Groups:")):
                    key, values = line.split(":", 1)
                    fields[key] = [int(value) for value in values.split()]
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError:
            raise ProfileDeletionError("directory_shared") from None
        if "Uid" not in fields or "Gid" not in fields or "Groups" not in fields:
            raise ProfileDeletionError("directory_shared")
        if (
            any(uid not in {0, account.pw_uid} for uid in fields["Uid"])
            and account.pw_gid in fields["Gid"] + fields["Groups"]
        ):
            raise ProfileDeletionError("directory_shared")
    return digest.hexdigest()


def _local_filesystem(descriptor: int) -> None:
    import ctypes

    class _StatFs(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_long),
            ("bsize", ctypes.c_long),
            ("blocks", ctypes.c_ulong),
            ("bfree", ctypes.c_ulong),
            ("bavail", ctypes.c_ulong),
            ("files", ctypes.c_ulong),
            ("ffree", ctypes.c_ulong),
            ("fsid", ctypes.c_int * 2),
            ("namelen", ctypes.c_long),
            ("frsize", ctypes.c_long),
            ("flags", ctypes.c_long),
            ("spare", ctypes.c_long * 4),
        ]

    if ctypes.sizeof(ctypes.c_void_p) != 8:
        raise ProfileDeletionError("filesystem_unsupported")
    info = _StatFs()
    library = ctypes.CDLL(None, use_errno=True)
    call = library.fstatfs
    call.argtypes = [ctypes.c_int, ctypes.POINTER(_StatFs)]
    call.restype = ctypes.c_int
    if call(descriptor, ctypes.byref(info)) != 0 or info.type not in {
        0xEF53,
        0x58465342,
        0x9123683E,
        0x01021994,
    }:
        raise ProfileDeletionError("filesystem_unsupported")
    if os.fstatvfs(descriptor).f_flag & os.ST_RDONLY:
        raise ProfileDeletionError("filesystem_readonly")


def _no_acl(descriptor: int) -> None:
    for name in (
        "system.posix_acl_access",
        "system.posix_acl_default",
        "system.nfs4_acl",
    ):
        try:
            os.getxattr(descriptor, name)
        except OSError as error:
            if error.errno == errno.ENODATA or (
                name == "system.nfs4_acl"
                and error.errno in {errno.ENOTSUP, errno.EOPNOTSUPP}
            ):
                continue
            raise ProfileDeletionError("acl_unsupported") from None
        raise ProfileDeletionError("acl_unsupported")


@contextmanager
def _legacy_chain(path: Path):
    """Linux-only canonical path walk pins every inode without following links."""
    if sys.platform != "linux" or _android_application_runtime():
        raise ProfileDeletionError("directory_not_dedicated")
    account = _local_profile_account()
    expected = (
        Path(account.pw_dir)
        / ".local/share/io.github.umichata.tokenlogue/data/tokenlogue.sqlite3"
    )
    if path != expected or Path(account.pw_dir) == Path("/"):
        raise ProfileDeletionError("directory_not_dedicated")
    authority = _private_group_authority(account)
    descriptors = []
    identities = []
    try:
        descriptor = os.open(
            "/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        descriptors.append(descriptor)
        for part in path.parent.parts[1:]:
            descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            descriptors.append(descriptor)
        for index, descriptor in enumerate(descriptors):
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid not in {0, account.pw_uid}:
                raise ProfileDeletionError("directory_shared")
            sticky_root = info.st_uid == 0 and bool(info.st_mode & stat.S_ISVTX)
            if (info.st_mode & 0o002 and not sticky_root) or (
                info.st_mode & 0o020
                and info.st_gid != account.pw_gid
                and not sticky_root
            ):
                raise ProfileDeletionError("directory_shared")
            if index == len(descriptors) - 1 and (
                info.st_uid != account.pw_uid
                or info.st_mode & (stat.S_ISVTX | stat.S_ISUID | stat.S_ISGID)
            ):
                raise ProfileDeletionError("directory_shared")
            _local_filesystem(descriptor)
            _no_acl(descriptor)
            identities.append(
                [
                    info.st_dev,
                    info.st_ino,
                    info.st_uid,
                    info.st_gid,
                    stat.S_IMODE(info.st_mode),
                ]
            )
        leaf = descriptors[-1]
        database = os.stat(path.name, dir_fd=leaf, follow_symlinks=False)
        if (
            not stat.S_ISREG(database.st_mode)
            or database.st_uid != account.pw_uid
            or database.st_nlink != 1
        ):
            raise ProfileDeletionError("path_unsafe")
        try:
            lock = os.stat(
                "." + path.name + ".owner.lock", dir_fd=leaf, follow_symlinks=False
            )
        except OSError:
            raise ProfileDeletionError("ownership_busy") from None
        held = owned_database_identity(path)
        if (
            not stat.S_ISREG(lock.st_mode)
            or lock.st_uid != account.pw_uid
            or lock.st_nlink != 1
            or (lock.st_dev, lock.st_ino) != held
        ):
            raise ProfileDeletionError("ownership_busy")
        yield (
            leaf,
            dict(
                chain=identities,
                authority=authority,
                database=[database.st_dev, database.st_ino],
                lock=list(held),
            ),
        )
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _android_application_runtime() -> bool:
    """Compiled Android Python marker, never environment or a platform label."""
    marker = getattr(sys, "getandroidapilevel", None)
    if (
        not isinstance(marker, BuiltinFunctionType)
        or marker.__module__ != "sys"
        or marker.__name__ != "getandroidapilevel"
    ):
        return False
    try:
        api = marker()
        return (
            type(api) is int
            and api >= 24
            and os.getuid() >= 10000
            and os.getgid() >= 10000
            and 1000 not in os.getgroups()
        )
    except Exception:
        return False


def _android_system_link(component: Path) -> bool:
    """Only the evidenced OS alias /data/user/0 -> /data/data gets AID_SYSTEM."""
    if component != Path("/data/user/0") or not _android_application_runtime():
        return False
    link = component.lstat()
    if (
        not stat.S_ISLNK(link.st_mode)
        or link.st_uid != 0
        or link.st_gid != 0
        or component.readlink() != Path("/data/data")
        or component.resolve(strict=True) != Path("/data/data")
    ):
        return False
    for path in (Path("/"), Path("/data"), Path("/data/user"), Path("/data/data")):
        owner = path.stat(follow_symlinks=False)
        if not stat.S_ISDIR(owner.st_mode) or owner.st_mode & 0o002:
            return False
        if owner.st_uid == 0 and owner.st_gid == 0 and not owner.st_mode & 0o022:
            continue
        # AID_SYSTEM is an OS authority on Android, not Unix UID 1000 on Linux.
        # Group write is allowed only to SYSTEM, which this app cannot join.
        if path != Path("/data") or owner.st_uid != 1000 or owner.st_gid != 1000:
            return False
    return True


def _validate_profile_ancestors(parent: Path) -> None:
    for component in (parent, *parent.parents):
        if not component.exists() and not component.is_symlink():
            continue
        if not component.is_symlink():
            if not component.is_dir():
                raise ProfileDeletionError()
            continue
        if component == parent or component.lstat().st_uid != 0:
            raise ProfileDeletionError()
        if _android_system_link(component):
            continue
        # Native Android paths may contain OS links. A user-owned profile link
        # never establishes scope, even if it points to a safe directory.
        for ancestor in (component.parent, *component.parent.parents):
            owner = ancestor.stat(follow_symlinks=False)
            if (
                owner.st_uid != 0
                or owner.st_mode & 0o022
                or not stat.S_ISDIR(owner.st_mode)
            ):
                raise ProfileDeletionError()
        target = component.resolve(strict=True)
        target_info = target.stat(follow_symlinks=False)
        if (
            target_info.st_uid != 0
            or target_info.st_mode & 0o022
            or not stat.S_ISDIR(target_info.st_mode)
        ):
            raise ProfileDeletionError()


def validate_profile_path(
    path: str | Path, *, create_parent: bool = True, require_private: bool = True
) -> Path:
    """Проверяет filesystem scope до flock, SQLite и SecureStorage.

    При необходимости создаёт только недостающие private каталоги после
    проверки уже существующей цепочки. Ни базу, ни owner-lock не создаёт.
    """
    try:
        database = Path(path).absolute()
        parent = database.parent
        if any(part == ".." for part in database.parts):
            raise ProfileDeletionError()
        _validate_profile_ancestors(parent)
        if not parent.exists():
            if not create_parent:
                raise ProfileDeletionError()
            missing = []
            existing = parent
            while not existing.exists():
                missing.append(existing)
                existing = existing.parent
            owner = existing.stat(follow_symlinks=False)
            if (
                owner.st_uid != os.getuid()
                or (require_private and owner.st_mode & 0o022)
                or not stat.S_ISDIR(owner.st_mode)
            ):
                raise ProfileDeletionError()
            for directory in reversed(missing):
                directory.mkdir(mode=0o700)
            _validate_profile_ancestors(parent)
        info = parent.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or (require_private and info.st_mode & 0o022)
        ):
            raise ProfileDeletionError()
        try:
            leaf = database.stat(follow_symlinks=False)
        except FileNotFoundError:
            leaf = None
        if leaf is not None and (
            not stat.S_ISREG(leaf.st_mode)
            or leaf.st_uid != os.getuid()
            or leaf.st_nlink != 1
        ):
            raise ProfileDeletionError()
        return database
    except Exception:
        raise ProfileDeletionError() from None


@dataclass(frozen=True)
class DeletionScope:
    """Одно подтверждение связано с конкретным экземпляром и snapshot."""

    nonce: str = field(repr=False)
    metadata: str = field(repr=False)
    preparation_required: bool = False
    preparation_metadata: str = field(default="", repr=False)


class ProfileDeletion:
    """Удаляет только подтверждённые файлы и пять точных aliases профиля."""

    def __init__(
        self,
        path: str | Path,
        storage: SecureStorageBackend,
        *,
        durable_write: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.path = Path(path).absolute()
        self.storage = storage
        self.intent_path = self.path.with_name(
            self.path.name + ".profile-deletion.json"
        )
        self._durable_write = durable_write
        self._confirmation: DeletionScope | None = None
        self._generation = 0
        self._operation = asyncio.Lock()
        self._prepared = False
        self._stage = "inspect"
        self.diagnostic: DeletionDiagnostic | None = None

    def _failure(self, error: BaseException) -> ProfileDeletionError:
        code = (
            error.diagnostic.code
            if isinstance(error, ProfileDeletionError)
            else (
                "ownership_busy"
                if isinstance(error, DatabaseOwnershipError)
                else "deletion_incomplete"
                if self._stage == "finish"
                else "preparation_failed"
                if self._stage == "prepare"
                else "intent_write_failed"
                if self._stage == "accept"
                else "metadata_invalid"
            )
        )
        self.diagnostic = DeletionDiagnostic(
            self._stage, code, self._prepared, self.pending()
        )
        return ProfileDeletionError(diagnostic=self.diagnostic)

    def _legacy_proof(self) -> dict[str, Any]:
        with _legacy_chain(self.path) as (_descriptor, proof):
            return proof

    def cancel(self) -> None:
        """Не отменяет уже принятое намерение, не изменяет файлы и aliases."""
        self._generation += 1
        self._confirmation = None

    def pending(self) -> bool:
        """Не создаёт базу. Повреждённый intent также блокирует обычный startup."""
        temporary = self.intent_path.with_name(self.intent_path.name + ".write")
        return any(
            path.exists() or path.is_symlink() for path in (self.intent_path, temporary)
        )

    def _directory(self, *, require_private: bool = True) -> tuple[int, int]:
        validate_profile_path(
            self.path, create_parent=False, require_private=require_private
        )
        info = self.path.parent.stat(follow_symlinks=False)
        return info.st_dev, info.st_ino

    def _preferences(self) -> dict[str, Any] | None:
        preferences = self.path.parent / "tokenlogue-preferences.json"
        identity = self._identity(preferences)
        if identity is None:
            return None
        value = self._read_json(preferences)
        retained: dict[str, str | bool] = {}
        if value.get("language") in {"ru", "en"}:
            retained["language"] = value["language"]
        if type(value.get("wide_sidebar_visible")) is bool:
            retained["wide_sidebar_visible"] = value["wide_sidebar_visible"]
        return dict(identity=identity, retained=retained)

    def _identity(self, path: Path) -> list[int] | None:
        try:
            info = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            return None
        if (
            path.parent != self.path.parent
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_nlink != 1
        ):
            raise ProfileDeletionError()
        return [info.st_dev, info.st_ino]

    def _read_json(self, path: Path) -> dict[str, Any]:
        identity = self._identity(path)
        if identity is None:
            raise ProfileDeletionError()
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (
                [opened.st_dev, opened.st_ino] != identity
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or not stat.S_ISREG(opened.st_mode)
            ):
                raise ProfileDeletionError()
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                data = stream.read(_MAX_METADATA_BYTES + 1)
            if len(data) > _MAX_METADATA_BYTES:
                raise ProfileDeletionError("metadata_invalid")
            value = _json(data)
            if not isinstance(value, dict):
                raise ProfileDeletionError("metadata_invalid")
            return value
        finally:
            os.close(descriptor)

    @staticmethod
    def _coordinates(raw: str | None) -> dict[str, str] | None:
        # The native plugin transports a whole value (on Linux a whole plugin
        # blob). Only ownership coordinates are interpreted here. In particular
        # pending PIN records, code verifiers and DEK/API slots are not queried.
        if raw is None:
            return None
        if not isinstance(raw, str) or len(raw) > _MAX_METADATA_BYTES:
            raise ProfileDeletionError("metadata_invalid")
        value = _json(raw)
        if (
            not isinstance(value, dict)
            or type(value.get("version")) is not int
            or value["version"] != 1
            or any(
                not isinstance(value.get(key), str)
                or not value[key]
                or len(value[key]) > 256
                for key in ("database_id", "key_id")
            )
        ):
            raise ProfileDeletionError("metadata_invalid")
        return {key: value[key] for key in ("database_id", "key_id")}

    def _files(self, coordinates: dict[str, str] | None) -> dict[str, list[int]]:
        names = [self.path.name + suffix for suffix in ("", "-wal", "-shm", "-journal")]
        journal = self.path.with_name(self.path.name + ".protection-migration.json")
        names += [journal.name, journal.name + ".write"]
        temporary_names: set[str] = set()
        for candidate in (journal, journal.with_name(journal.name + ".write")):
            if self._identity(candidate) is None:
                continue
            state = self._read_json(candidate)
            name = state.get("temporary")
            if (
                state.get("version") != 1
                or state.get("stage") not in {"copying", "validated"}
                or not isinstance(name, str)
                or Path(name).name != name
                or not name.startswith("." + self.path.name + ".protected-")
                or coordinates is None
                or any(state.get(key) != value for key, value in coordinates.items())
            ):
                raise ProfileDeletionError()
            temporary_names.add(name)
            names += [name + suffix for suffix in ("", "-wal", "-shm", "-journal")]
        # Never infer ownership merely from a wildcard prefix. An orphan without
        # an identity-bearing migration journal needs a separate repair audit.
        for candidate in self.path.parent.glob("." + self.path.name + ".protected-*"):
            if not any(
                candidate.name == name + suffix
                for name in temporary_names
                for suffix in ("", "-wal", "-shm", "-journal")
            ):
                raise ProfileDeletionError()
        return {
            name: identity
            for name in names
            if (identity := self._identity(self.path.parent / name)) is not None
        }

    def _database_metadata(self) -> dict[str, Any]:
        identity = self._identity(self.path)
        if identity is None:
            raise ProfileDeletionError("metadata_invalid")
        connection = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA temp_store=MEMORY")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            expected = {
                "auth_state",
                "chats",
                "chat_budgets",
                "turns",
                "messages",
                "chat_drafts",
            }
            if version == 7:
                expected.add("content_protection")
            if REQUEST_ATTEMPTS_TABLE in tables:
                try:
                    validate_request_attempts_schema(connection)
                except (ValueError, sqlite3.Error):
                    raise ProfileDeletionError("metadata_invalid") from None
                expected.add(REQUEST_ATTEMPTS_TABLE)
            if (
                version not in {6, 7}
                or tables != expected
                or connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger')"
                ).fetchone()
            ):
                raise ProfileDeletionError("metadata_invalid")
            registration = connection.execute(
                "SELECT registration_id FROM auth_state"
            ).fetchall()
            if (
                len(registration) != 1
                or not isinstance(registration[0][0], str)
                or not registration[0][0]
                or len(registration[0][0]) > 256
            ):
                raise ProfileDeletionError("metadata_invalid")
            coordinates = None
            if version == 7:
                rows = connection.execute(
                    "SELECT database_id,key_id,format_version FROM content_protection"
                ).fetchall()
                if (
                    len(rows) != 1
                    or rows[0][2] != 1
                    or any(
                        not isinstance(value, str) or not value or len(value) > 256
                        for value in rows[0][:2]
                    )
                ):
                    raise ProfileDeletionError("metadata_invalid")
                coordinates = dict(database_id=rows[0][0], key_id=rows[0][1])
            if self._identity(self.path) != identity:
                raise ProfileDeletionError("identity_mismatch")
            return dict(
                schema=version,
                registration_id=registration[0][0],
                database=identity,
                coordinates=coordinates,
            )
        finally:
            connection.close()

    async def _snapshot(self, *, require_private: bool = True) -> dict[str, Any]:
        directory = self._directory(require_private=require_private)
        if self._identity(self.path) is None:
            raise ProfileDeletionError()
        self._identity(self.path.with_name("." + self.path.name + ".owner.lock"))
        with database_lock(self.path):
            # Validate potential SQLite sidecars before SQLite may inspect them.
            for suffix in ("-wal", "-shm", "-journal"):
                self._identity(self.path.with_name(self.path.name + suffix))
            metadata = self._database_metadata()
        try:
            registration = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
            binding_raw = await self.storage.get(DATA_BINDING_ALIAS)
            initialization_raw = await self.storage.get(DATA_INITIALIZATION_ALIAS)
        except Exception:
            raise ProfileDeletionError("backend_unavailable") from None
        if registration != metadata["registration_id"]:
            raise ProfileDeletionError("identity_mismatch")
        try:
            binding = self._coordinates(binding_raw)
            initialization = self._coordinates(initialization_raw)
        except Exception:
            raise ProfileDeletionError("metadata_invalid") from None
        coordinates = metadata["coordinates"]
        if metadata["schema"] == 7 and (binding is None or binding != coordinates):
            raise ProfileDeletionError("identity_mismatch")
        if (
            binding is not None
            and initialization is not None
            and binding != initialization
        ):
            raise ProfileDeletionError("identity_mismatch")
        if coordinates is None:
            coordinates = binding or initialization
        try:
            unidentified_key = coordinates is None and await self.storage.contains_key(
                DATA_KEY_ALIAS
            )
        except Exception:
            raise ProfileDeletionError("backend_unavailable") from None
        if unidentified_key:
            # An unbound key from the shared namespace might belong to another
            # profile. Missing DEK is safe, an unidentified present DEK is not.
            raise ProfileDeletionError("identity_mismatch")
        if initialization is not None and initialization != coordinates:
            raise ProfileDeletionError("identity_mismatch")
        with database_lock(self.path):
            if (
                self._database_metadata() != metadata
                or self._directory(require_private=require_private) != directory
            ):
                raise ProfileDeletionError("identity_mismatch")
            files = self._files(coordinates)
            preferences = self._preferences()
        return dict(
            metadata=metadata,
            coordinates=coordinates,
            directory=list(directory),
            files=files,
            preferences=preferences,
        )

    async def capture(self) -> DeletionScope:
        """Не принимает намерение и не извлекает секретные ключи или историю."""
        generation = self._generation
        self._stage = "inspect"
        self.diagnostic = None
        try:
            if self.pending() or self._operation.locked():
                raise ProfileDeletionError()
            async with self._operation:
                self._directory(require_private=False)
                needs_preparation = bool(
                    self.path.parent.stat(follow_symlinks=False).st_mode & 0o022
                )
                proof = self._legacy_proof() if needs_preparation else None
                snapshot = await self._snapshot(require_private=not needs_preparation)
                if generation != self._generation:
                    raise ProfileDeletionError("stale_confirmation")
                if proof is not None and self._legacy_proof() != proof:
                    raise ProfileDeletionError("identity_mismatch")
                scope = DeletionScope(
                    secrets.token_hex(16),
                    json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                    needs_preparation,
                    json.dumps(proof, sort_keys=True, separators=(",", ":"))
                    if proof is not None
                    else "",
                )
                self._confirmation = scope
                return scope
        except Exception as error:
            raise self._failure(error) from None

    def _sync_directory(self) -> None:
        descriptor = os.open(
            self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _write_intent(self, value: dict[str, Any]) -> None:
        temporary = self.intent_path.with_name(self.intent_path.name + ".write")
        if temporary.exists() or temporary.is_symlink():
            raise ProfileDeletionError()
        if self.pending():
            self._identity(self.intent_path)
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            with os.fdopen(descriptor, "w", closefd=False, encoding="utf-8") as stream:
                json.dump(value, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.intent_path)
            self._sync_directory()
        finally:
            os.close(descriptor)
            temporary.unlink(missing_ok=True)

    def _scope_current(self, scope: DeletionScope, generation: int) -> None:
        if generation != self._generation or scope is not self._confirmation:
            raise ProfileDeletionError("stale_confirmation")

    def _prepare_directory(self, scope: DeletionScope, generation: int) -> None:
        self._stage = "prepare"
        expected = _json(scope.preparation_metadata)
        with _legacy_chain(self.path) as (descriptor, proof):
            if proof != expected or self._legacy_proof() != expected:
                raise ProfileDeletionError("identity_mismatch")
            self._scope_current(scope, generation)
            # No await between the last scope check and this inode-bound change.
            # Only the confirmed data leaf changes, never its ancestors.
            os.fchmod(descriptor, 0o700)
            self._prepared = True
            self.diagnostic = DeletionDiagnostic("prepare", "prepared", True, False)
            os.fsync(descriptor)
            changed = _json(scope.preparation_metadata)
            changed["chain"][-1][-1] = 0o700
            try:
                current = self._legacy_proof()
            except (OSError, DatabaseOwnershipError):
                raise ProfileDeletionError("identity_mismatch") from None
            if current != changed:
                raise ProfileDeletionError("identity_mismatch")
            self._directory()

    async def accept(self, scope: DeletionScope) -> None:
        """Последняя проверка до fsync. После возврата UI отмена не останавливает intent."""
        generation = self._generation
        self._stage = "accept"
        try:
            if (
                self._operation.locked()
                or scope is not self._confirmation
                or self.pending()
            ):
                raise ProfileDeletionError("stale_confirmation")
            async with self._operation:
                self._scope_current(scope, generation)
                if scope.preparation_required and self._legacy_proof() != _json(
                    scope.preparation_metadata
                ):
                    raise ProfileDeletionError("identity_mismatch")
                snapshot = await self._snapshot(
                    require_private=not scope.preparation_required
                )
                original = _json(scope.metadata)
                # The dialog selects a profile, not a frozen WAL generation.
                # Quiescing a legitimate writer may remove/checkpoint sidecars
                # or sanitize preferences. Bind the confirmation to stable
                # identity and capture current exact file inodes into the intent.
                stable = ("metadata", "coordinates", "directory")
                if (
                    generation != self._generation
                    or scope is not self._confirmation
                    or any(snapshot[key] != original[key] for key in stable)
                ):
                    raise ProfileDeletionError("identity_mismatch")
                if scope.preparation_required:
                    with database_lock(self.path):
                        self._prepare_directory(scope, generation)
                    self._stage = "accept"
                    # Rights preparation grants no data access. Re-run all of the
                    # existing strict metadata/storage checks after that change.
                    snapshot = await self._snapshot()
                    self._scope_current(scope, generation)
                    if any(snapshot[key] != original[key] for key in stable):
                        raise ProfileDeletionError("identity_mismatch")
                    expected = _json(scope.preparation_metadata)
                    expected["chain"][-1][-1] = 0o700
                    if self._legacy_proof() != expected:
                        raise ProfileDeletionError("identity_mismatch")
                # No await between final callback/identity check and durable intent.
                with database_lock(self.path):
                    preference_write = self.path.parent / (
                        ".tokenlogue-preferences.json.deletion-" + scope.nonce
                    )
                    if preference_write.exists() or preference_write.is_symlink():
                        raise ProfileDeletionError()
                    retire_database(self.path)
                    self._write_intent(
                        dict(version=1, nonce=scope.nonce, scope=snapshot, removed=[])
                    )
                self._confirmation = None
        except Exception as error:
            raise self._failure(error) from None

    def _validate_intent(self, intent: dict[str, Any]) -> dict[str, Any]:
        if (
            set(intent) != {"version", "nonce", "scope", "removed"}
            or type(intent["version"]) is not int
            or intent["version"] != 1
            or not isinstance(intent["nonce"], str)
            or len(intent["nonce"]) != 32
            or any(character not in "0123456789abcdef" for character in intent["nonce"])
            or not isinstance(intent["scope"], dict)
            or not isinstance(intent["removed"], list)
        ):
            raise ProfileDeletionError()
        scope = intent["scope"]
        if (
            set(scope)
            != {"metadata", "coordinates", "directory", "files", "preferences"}
            or scope["directory"] != list(self._directory())
            or not isinstance(scope["files"], dict)
            or not isinstance(scope["metadata"], dict)
        ):
            raise ProfileDeletionError()
        preferences = scope["preferences"]
        if preferences is not None:
            if (
                not isinstance(preferences, dict)
                or set(preferences) != {"identity", "retained"}
                or not isinstance(preferences["identity"], list)
                or len(preferences["identity"]) != 2
                or any(
                    type(value) is not int or value < 0
                    for value in preferences["identity"]
                )
                or not isinstance(preferences["retained"], dict)
                or set(preferences["retained"]) - {"language", "wide_sidebar_visible"}
            ):
                raise ProfileDeletionError()
            retained = preferences["retained"]
            if (
                "language" in retained and retained["language"] not in {"en", "ru"}
            ) or (
                "wide_sidebar_visible" in retained
                and type(retained["wide_sidebar_visible"]) is not bool
            ):
                raise ProfileDeletionError()
        removed = intent["removed"]
        if removed != list(PROFILE_ALIASES[: len(removed)]):
            raise ProfileDeletionError()
        metadata = scope["metadata"]
        if (
            set(metadata) != {"schema", "registration_id", "database", "coordinates"}
            or type(metadata["schema"]) is not int
            or metadata["schema"] not in {6, 7}
            or not isinstance(metadata["registration_id"], str)
            or not metadata["registration_id"]
            or len(metadata["registration_id"]) > 256
            or metadata["database"] != scope["files"].get(self.path.name)
        ):
            raise ProfileDeletionError()
        for coordinates in (metadata["coordinates"], scope["coordinates"]):
            if coordinates is not None and (
                not isinstance(coordinates, dict)
                or set(coordinates) != {"database_id", "key_id"}
                or any(
                    not isinstance(value, str) or not value or len(value) > 256
                    for value in coordinates.values()
                )
            ):
                raise ProfileDeletionError()
        if metadata["schema"] == 7 and (
            metadata["coordinates"] is None
            or metadata["coordinates"] != scope["coordinates"]
        ):
            raise ProfileDeletionError()
        allowed = {
            self.path.name + suffix
            for suffix in (
                "",
                "-wal",
                "-shm",
                "-journal",
                ".protection-migration.json",
                ".protection-migration.json.write",
            )
        }
        for name, identity in scope["files"].items():
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or (
                    name not in allowed
                    and not name.startswith("." + self.path.name + ".protected-")
                )
                or not isinstance(identity, list)
                or len(identity) != 2
                or any(type(value) is not int or value < 0 for value in identity)
            ):
                raise ProfileDeletionError()
        if self.path.name not in scope["files"]:
            raise ProfileDeletionError()
        return intent

    def _intent(self) -> dict[str, Any]:
        self._directory()
        temporary = self.intent_path.with_name(self.intent_path.name + ".write")
        main_exists = self._identity(self.intent_path) is not None
        writing_exists = self._identity(temporary) is not None
        main = (
            self._validate_intent(self._read_json(self.intent_path))
            if main_exists
            else None
        )
        writing = (
            self._validate_intent(self._read_json(temporary))
            if writing_exists
            else None
        )
        if writing is not None:
            if main is None:
                # A fully written initial intent left before rename is the same
                # explicit confirmation. Make it durable before any destruction.
                descriptor = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(temporary, self.intent_path)
                self._sync_directory()
                main = writing
            elif (
                writing["nonce"] != main["nonce"]
                or writing["scope"] != main["scope"]
                or writing["removed"][: len(main["removed"])] != main["removed"]
            ):
                raise ProfileDeletionError()
            else:
                # The accepted main intent dominates. Repeating removals is safe
                # even if an ACK-progress replacement was interrupted.
                temporary.unlink()
                self._sync_directory()
        if main is None:
            raise ProfileDeletionError()
        return main

    async def _namespace(self, intent: dict[str, Any]) -> None:
        registration = await self.storage.get(REGISTRATION_ID_STORAGE_NAME)
        expected = intent["scope"]["metadata"].get("registration_id")
        if registration != expected:
            # Registration is removed last. A crash after that removal is safe
            # only if every other exact alias is already absent.
            if registration is not None or any(
                [await self.storage.contains_key(key) for key in PROFILE_ALIASES[:-1]]
            ):
                raise ProfileDeletionError()
        for key in (DATA_BINDING_ALIAS, DATA_INITIALIZATION_ALIAS):
            coordinates = self._coordinates(await self.storage.get(key))
            if (
                coordinates is not None
                and coordinates != intent["scope"]["coordinates"]
            ):
                raise ProfileDeletionError()

    def _validate_files(self, intent: dict[str, Any]) -> None:
        if list(self._directory()) != intent["scope"]["directory"]:
            raise ProfileDeletionError()
        for name, identity in intent["scope"]["files"].items():
            current = self._identity(self.path.parent / name)
            if current is not None and current != identity:
                raise ProfileDeletionError()
        # Newly appeared SQLite/migration files cannot silently escape the intent.
        known = set(intent["scope"]["files"])
        for candidate in self.path.parent.iterdir():
            if candidate.name in {
                self.path.name + suffix
                for suffix in (
                    "",
                    "-wal",
                    "-shm",
                    "-journal",
                    ".protection-migration.json",
                    ".protection-migration.json.write",
                )
            } or candidate.name.startswith("." + self.path.name + ".protected-"):
                if candidate.name not in known:
                    raise ProfileDeletionError()

    def _unlink(self, name: str, identity: list[int]) -> None:
        path = self.path.parent / name
        current = self._identity(path)
        if current is not None:
            if current != identity:
                raise ProfileDeletionError()
            path.unlink()
            self._sync_directory()

    def _sanitize_preferences(self, intent: dict[str, Any]) -> None:
        captured = intent["scope"]["preferences"]
        preferences = self.path.parent / "tokenlogue-preferences.json"
        current = self._identity(preferences)
        if current is not None and (
            captured is None or current != captured["identity"]
        ):
            value = self._read_json(preferences)
            if (
                set(value) - {"language", "wide_sidebar_visible"}
                or ("language" in value and value["language"] not in {"ru", "en"})
                or (
                    "wide_sidebar_visible" in value
                    and type(value["wide_sidebar_visible"]) is not bool
                )
            ):
                raise ProfileDeletionError()
            # A queued old language selector uses PreferencesStore's atomic
            # whitelist writer. Its new nonsensitive choice is already clean.
            # Preserve it without widening the scope to any other file/field.
            return
        if captured is None:
            return
        encoded = (
            json.dumps(
                captured["retained"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if current is None:
            raise ProfileDeletionError()
        temporary = self.path.parent / (
            ".tokenlogue-preferences.json.deletion-" + intent["nonce"]
        )
        self._identity(temporary)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, preferences)
            self._sync_directory()
        finally:
            os.close(descriptor)

    async def finish(self) -> None:
        """Идемпотентное завершение. Любой отказ оставляет startup заблокированным."""
        self._stage = "finish"
        try:
            if self._operation.locked():
                raise ProfileDeletionError()
            async with self._operation:
                self._directory()
                self._identity(self.path)
                self._identity(
                    self.path.with_name("." + self.path.name + ".owner.lock")
                )
                with database_lock(self.path):
                    intent = self._intent()
                    self._validate_files(intent)
                    retire_database(self.path)
                await self._namespace(intent)
                for key in PROFILE_ALIASES:
                    await self._namespace(intent)
                    await self.storage.remove(key)
                    if self._durable_write is not None:
                        await self._durable_write()
                    if await self.storage.contains_key(key):
                        raise ProfileDeletionError()
                    if key not in intent["removed"]:
                        intent["removed"].append(key)
                        self._write_intent(intent)
                # All plugin aliases are absent before any file is removed.
                if any(
                    [await self.storage.contains_key(key) for key in PROFILE_ALIASES]
                ):
                    raise ProfileDeletionError()
                with database_lock(self.path):
                    self._validate_files(intent)
                    self._sanitize_preferences(intent)
                    # Sidecars first. The main file remains a startup barrier
                    # until aliases and their durable acknowledgements are gone.
                    names = sorted(
                        intent["scope"]["files"],
                        key=lambda name: name == self.path.name,
                    )
                    for name in names:
                        self._unlink(name, intent["scope"]["files"][name])
                    if any(
                        self._identity(self.path.parent / name) is not None
                        for name in names
                    ):
                        raise ProfileDeletionError()
                    self.intent_path.unlink()
                    self._sync_directory()
                    self.diagnostic = DeletionDiagnostic(
                        "finish", "complete", self._prepared, False
                    )
        except Exception as error:
            raise self._failure(error) from None
