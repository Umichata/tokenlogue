"""Общая блокировка соединений и граница защищённого содержимого."""

from __future__ import annotations

import os
import sqlite3
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, ContextManager, Protocol

from i18n import tr
from storage.field_cipher import CiphertextError, FieldCipher

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux и Android используют POSIX flock.
    fcntl = None

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
_OWNERS: dict[str, tuple[int, int, int]] = {}


class DatabaseOwnershipError(RuntimeError):
    """Другой клиент владеет базой или владение нельзя безопасно подтвердить."""

    def __init__(self) -> None:
        super().__init__(tr("service.database_in_use"))


def _after_fork() -> None:
    global _LOCKS, _LOCKS_GUARD, _OWNERS
    # Унаследованный FD не означает, что дочерний клиент получил владение.
    # Не вызываем LOCK_UN, который снял бы блокировку родительского процесса.
    for descriptor, _device, _inode in _OWNERS.values():
        os.close(descriptor)
    _OWNERS = {}
    _LOCKS = {}
    _LOCKS_GUARD = threading.Lock()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork)


def _claim_database(database: Path) -> None:
    name = str(database)
    lock_file = database.with_name("." + database.name + ".owner.lock")
    owned = _OWNERS.get(name)
    if owned is not None:
        try:
            current = lock_file.stat(follow_symlinks=False)
        except OSError:
            raise DatabaseOwnershipError() from None
        if (current.st_dev, current.st_ino) != owned[1:] or current.st_nlink != 1:
            raise DatabaseOwnershipError()
        return
    if fcntl is None:
        raise DatabaseOwnershipError()
    descriptor = None
    try:
        descriptor = os.open(
            lock_file,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise DatabaseOwnershipError()
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = lock_file.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise DatabaseOwnershipError()
        # FD живёт до выхода процесса, а не до конца SQLite connection или rename.
        # Файл нельзя удалять при закрытии, иначе появятся независимые lock inode.
        _OWNERS[name] = (descriptor, opened.st_dev, opened.st_ino)
        descriptor = None
    except OSError:
        raise DatabaseOwnershipError() from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


class ContentAccess(Protocol):
    """Координатор проверяет сессию или ограниченный lease завершения."""

    def authorize(
        self,
        operation: str,
        *,
        chat_id: str = "",
        record_id: str = "",
    ) -> ContextManager[FieldCipher]: ...


class ProtectedConnection(sqlite3.Connection):
    cipher: FieldCipher | None = None


def database_lock(path: str | Path) -> threading.RLock:
    database = Path(path).resolve()
    name = str(database)
    with _LOCKS_GUARD:
        _claim_database(database)
        return _LOCKS.setdefault(name, threading.RLock())


def encrypt_value(
    connection: sqlite3.Connection,
    value: str | None,
    *,
    table: str,
    field: str,
    record_id: str,
    chat_id: str = "",
    role: str = "",
    revision: int = 0,
) -> str | None:
    cipher = getattr(connection, "cipher", None)
    if cipher is None or value is None:
        return value
    return cipher.encrypt(
        value,
        table=table,
        field=field,
        record_id=record_id,
        chat_id=chat_id,
        role=role,
        revision=revision,
    )


def _row_factory(cipher: FieldCipher | None):
    def decode(cursor: sqlite3.Cursor, values: tuple[object, ...]) -> sqlite3.Row:
        row = sqlite3.Row(cursor, values)
        if cipher is None:
            return row
        names = row.keys()
        clear = list(values)
        fields: list[tuple[str, str, dict[str, Any]]] = []
        if "title" in names and "id" in names:
            fields.append(("chats", "title", {"record_id": str(row["id"])}))
        if "content" in names and "role" in names:
            fields.append(
                (
                    "messages",
                    "content",
                    {
                        "record_id": str(row["id"]),
                        "chat_id": str(row["chat_id"]),
                        "role": str(row["role"]),
                    },
                )
            )
        elif "content" in names and "revision" in names and row["revision"] is not None:
            fields.append(
                (
                    "chat_drafts",
                    "content",
                    {
                        "record_id": str(row["chat_id"]),
                        "chat_id": str(row["chat_id"]),
                        "revision": int(row["revision"]),
                    },
                )
            )
        if "accounting_status" in names and "id" in names:
            for name in ("generation_id", "finish_reason"):
                if name in names:
                    fields.append(
                        (
                            "turns",
                            name,
                            {
                                "record_id": str(row["id"]),
                                "chat_id": str(row["chat_id"]),
                            },
                        )
                    )
        for table, name, metadata in fields:
            value = row[name]
            if value is not None:
                clear[names.index(name)] = cipher.decrypt(
                    value,
                    table=table,
                    field=name,
                    **metadata,
                )
        return sqlite3.Row(cursor, tuple(clear))

    return decode


@contextmanager
def connection(
    path: str | Path,
    access: ContentAccess | None = None,
    operation: str = "read",
    *,
    chat_id: str = "",
    record_id: str = "",
    auth_only: bool = False,
    allow_create: bool = False,
) -> Iterator[ProtectedConnection]:
    with database_lock(path):
        authorization = (
            access.authorize(operation, chat_id=chat_id, record_id=record_id)
            if access is not None and not auth_only
            else nullcontext(None)
        )
        with authorization as cipher:
            database = Path(path)
            if access is not None and not database.is_file():
                raise CiphertextError()
            raw = sqlite3.connect(
                database if allow_create else database.resolve().as_uri() + "?mode=rw",
                uri=not allow_create,
                timeout=5.0,
                factory=ProtectedConnection,
            )
            try:
                raw.execute("PRAGMA foreign_keys = ON")
                raw.execute("PRAGMA temp_store = MEMORY")
                version = int(raw.execute("PRAGMA user_version").fetchone()[0])
                protected = (
                    raw.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_protection'"
                    ).fetchone()
                    is not None
                )
                if not auth_only and (
                    (cipher is None and (version >= 7 or protected))
                    or (cipher is not None and (version != 7 or not protected))
                ):
                    raise CiphertextError()
                if cipher is not None:
                    metadata = raw.execute(
                        "SELECT database_id,key_id,marker FROM content_protection WHERE singleton_id=1"
                    ).fetchone()
                    if (
                        metadata is None
                        or metadata[0] != cipher.database_id
                        or metadata[1] != cipher.key_id
                    ):
                        raise CiphertextError()
                    if (
                        cipher.decrypt(
                            metadata[2],
                            table="content_protection",
                            field="marker",
                            record_id="1",
                        )
                        != "tokenlogue-protected-content"
                    ):
                        raise CiphertextError()
                raw.cipher = cipher
                raw.row_factory = _row_factory(cipher)
                with raw:
                    yield raw
            finally:
                raw.close()
