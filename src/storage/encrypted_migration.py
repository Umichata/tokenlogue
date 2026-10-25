"""Переносит содержимое в новый зашифрованный файл без открытой копии."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from storage.database_connections import database_lock
from storage.field_cipher import FORMAT_VERSION, CiphertextError, FieldCipher

TABLES = ("auth_state", "chats", "chat_budgets", "turns", "messages", "chat_drafts")
MARKER = "tokenlogue-protected-content"


@dataclass(frozen=True)
class ProtectionMetadata:
    database_id: str
    key_id: str
    format_version: int = FORMAT_VERSION


def _existing(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA temp_store = MEMORY")
    return connection


def inspect_protection(path: str | Path) -> ProtectionMetadata | None:
    database = Path(path)
    if not database.exists():
        return None
    with database_lock(database):
        connection = None
        try:
            connection = _existing(database)
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            present = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='content_protection'"
            ).fetchone()
            if version <= 6 and present is None:
                return None
            if version != 7 or present is None:
                raise CiphertextError()
            rows = connection.execute("SELECT * FROM content_protection").fetchall()
            if len(rows) != 1 or rows[0]["format_version"] != FORMAT_VERSION:
                raise CiphertextError()
            row = rows[0]
            if not row["database_id"] or not row["key_id"]:
                raise CiphertextError()
            return ProtectionMetadata(row["database_id"], row["key_id"])
        except (sqlite3.Error, KeyError, TypeError, ValueError):
            raise CiphertextError() from None
        finally:
            if connection is not None:
                connection.close()


def _verify_protected_database(
    path: str | Path, cipher: FieldCipher
) -> ProtectionMetadata:
    metadata = inspect_protection(path)
    if metadata is None or metadata != ProtectionMetadata(
        cipher.database_id, cipher.key_id
    ):
        raise CiphertextError()
    connection = None
    try:
        connection = _existing(Path(path))
        marker = connection.execute("SELECT marker FROM content_protection").fetchone()[
            0
        ]
        if (
            cipher.decrypt(
                marker, table="content_protection", field="marker", record_id="1"
            )
            != MARKER
        ):
            raise CiphertextError()
        _integrity(connection)
        for table in TABLES:
            fields = _protected_fields(table)
            if fields:
                for row in connection.execute(f'SELECT * FROM "{table}"'):
                    for field in fields:
                        if row[field] is not None:
                            cipher.decrypt(
                                row[field], **_coordinates(table, field, row)
                            )
    except (sqlite3.Error, TypeError, ValueError):
        raise CiphertextError() from None
    finally:
        if connection is not None:
            connection.close()
    return metadata


def verify_protected_database(
    path: str | Path, cipher: FieldCipher
) -> ProtectionMetadata:
    """Проверяет весь формат под общей блокировкой файлового экземпляра."""
    with database_lock(path):
        return _verify_protected_database(path, cipher)


def _integrity(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise CiphertextError()
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise CiphertextError()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _journal_identity(value: Mapping[str, object]) -> str:
    return json.dumps(
        [value["version"], value["stage"], value["temporary"]], separators=(",", ":")
    )


def _journal(path: Path, value: Mapping[str, object], cipher: FieldCipher) -> None:
    value = dict(value)
    value["proof"] = cipher.encrypt(
        "tokenlogue-migration",
        table="migration_journal",
        field="proof",
        record_id=_journal_identity(value),
    )
    if path.is_symlink():
        raise CiphertextError()
    temporary = path.with_name(path.name + ".write")
    if temporary.is_symlink():
        raise CiphertextError()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _sync_directory(path.parent)


def _coordinates(table: str, field: str, row: sqlite3.Row | dict[str, object]) -> dict:
    if table == "chats":
        return dict(table=table, field=field, record_id=row["id"])
    if table == "messages":
        return dict(
            table=table,
            field=field,
            record_id=row["id"],
            chat_id=row["chat_id"],
            role=row["role"],
        )
    if table == "chat_drafts":
        return dict(
            table=table,
            field=field,
            record_id=row["chat_id"],
            chat_id=row["chat_id"],
            revision=row["revision"],
        )
    return dict(table=table, field=field, record_id=row["id"], chat_id=row["chat_id"])


def _protected_fields(table: str) -> tuple[str, ...]:
    return {
        "chats": ("title",),
        "messages": ("content",),
        "chat_drafts": ("content",),
        "turns": ("generation_id", "finish_reason"),
    }.get(table, ())


def _schema(connection: sqlite3.Connection) -> None:
    from storage import database

    for migration in (
        database._migrate_0_to_1,
        database._migrate_1_to_2,
        database._migrate_2_to_3,
        database._migrate_3_to_4,
        database._migrate_4_to_5,
        database._migrate_5_to_6,
    ):
        migration(connection)
    connection.execute(
        "ALTER TABLE chats ADD COLUMN title_origin TEXT NOT NULL DEFAULT 'legacy' "
        "CHECK (title_origin IN ('legacy','placeholder','manual','message'))"
    )
    connection.execute(
        "CREATE TABLE content_protection (singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),"
        "database_id TEXT NOT NULL,key_id TEXT NOT NULL,format_version INTEGER NOT NULL,marker TEXT NOT NULL)"
    )


def _cleanup_previous(journal: Path, database: Path, cipher: FieldCipher) -> None:
    if not journal.exists():
        return
    try:
        if journal.is_symlink():
            raise CiphertextError()
        state = json.loads(journal.read_text("utf-8"))
        if (
            not isinstance(state, dict)
            or type(state.get("version")) is not int
            or state["version"] != 1
            or state.get("stage") not in {"copying", "validated"}
        ):
            raise CiphertextError()
        if (
            state["database_id"] != cipher.database_id
            or state["key_id"] != cipher.key_id
        ):
            raise CiphertextError()
        if (
            cipher.decrypt(
                state["proof"],
                table="migration_journal",
                field="proof",
                record_id=_journal_identity(state),
            )
            != "tokenlogue-migration"
        ):
            raise CiphertextError()
        name = state["temporary"]
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.startswith("." + database.name + ".protected-")
        ):
            raise CiphertextError()
        temporary = database.parent / name
        if temporary.is_symlink():
            raise CiphertextError()
        if temporary.exists():
            cleanup = _existing(temporary)
            cleanup.close()
            temporary.unlink()
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        raise CiphertextError() from None


def migrate_database(
    path: str | Path,
    cipher: FieldCipher,
    failpoint: Callable[[str], None] | None = None,
) -> None:
    database = Path(path)
    journal = database.with_name(database.name + ".protection-migration.json")
    hit = failpoint or (lambda _stage: None)
    with database_lock(database):
        if not database.is_file() or database.is_symlink():
            raise CiphertextError()
        if inspect_protection(database) is not None:
            verify_protected_database(database, cipher)
            _cleanup_previous(journal, database, cipher)
            journal.unlink(missing_ok=True)
            _sync_directory(database.parent)
            return
        _cleanup_previous(journal, database, cipher)
        hit("after_key_saved")
        source = destination = None
        temporary: Path | None = None
        try:
            source = _existing(database)
            if source.execute("PRAGMA user_version").fetchone()[0] != 6:
                raise CiphertextError()
            checkpoint = source.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint[0] != 0:
                raise CiphertextError()
            if source.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
                raise CiphertextError()
            source.execute("BEGIN EXCLUSIVE")
            _integrity(source)
            actual_tables = {
                row[0]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if (
                actual_tables != set(TABLES)
                or source.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')"
                ).fetchone()
            ):
                raise CiphertextError()
            descriptor, name = tempfile.mkstemp(
                prefix="." + database.name + ".protected-", dir=database.parent
            )
            os.close(descriptor)
            temporary = Path(name)
            state = dict(
                database_id=cipher.database_id,
                key_id=cipher.key_id,
                temporary=temporary.name,
                stage="copying",
                version=1,
            )
            _journal(journal, state, cipher)
            destination = _existing(temporary)
            destination.execute("PRAGMA synchronous=FULL")
            destination.execute("BEGIN IMMEDIATE")
            _schema(destination)
            copied = 0
            for table in TABLES:
                for row in source.execute(
                    f'SELECT rowid AS _migration_rowid,* FROM "{table}" ORDER BY rowid'
                ):
                    values = dict(row)
                    rowid = values.pop("_migration_rowid")
                    for field in _protected_fields(table):
                        if values[field] is not None:
                            values[field] = cipher.encrypt(
                                values[field], **_coordinates(table, field, row)
                            )
                    if table == "chats":
                        values["title_origin"] = (
                            "manual" if row["title_is_manual"] else "legacy"
                        )
                    columns = ["rowid", *values]
                    quoted = ",".join('"' + column + '"' for column in columns)
                    placeholders = ",".join("?" for _ in columns)
                    destination.execute(
                        f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})',
                        (rowid, *values.values()),
                    )
                    copied += 1
                    if copied == 1:
                        hit("mid_copy")
            destination.execute(
                "INSERT INTO content_protection VALUES (1,?,?,?,?)",
                (
                    cipher.database_id,
                    cipher.key_id,
                    FORMAT_VERSION,
                    cipher.encrypt(
                        MARKER,
                        table="content_protection",
                        field="marker",
                        record_id="1",
                    ),
                ),
            )
            destination.execute("PRAGMA user_version=7")
            _integrity(destination)
            for table in TABLES:
                original = source.execute(
                    f'SELECT rowid AS _migration_rowid,* FROM "{table}" ORDER BY rowid'
                )
                encrypted = destination.execute(
                    f'SELECT rowid AS _migration_rowid,* FROM "{table}" ORDER BY rowid'
                )
                for old, new in zip(original, encrypted, strict=True):
                    for column in old.keys():
                        value = new[column]
                        if column in _protected_fields(table) and value is not None:
                            value = cipher.decrypt(
                                value, **_coordinates(table, column, old)
                            )
                        if value != old[column]:
                            raise CiphertextError()
            destination.commit()
            destination.close()
            destination = None
            source.rollback()
            source.close()
            source = None
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            state["stage"] = "validated"
            _journal(journal, state, cipher)
            hit("before_replace")
            os.replace(temporary, database)
            hit("after_replace")
            _sync_directory(database.parent)
            verify_protected_database(database, cipher)
            journal.unlink(missing_ok=True)
            _sync_directory(database.parent)
        except (sqlite3.Error, ValueError, KeyError, TypeError):
            raise CiphertextError() from None
        finally:
            if destination is not None:
                destination.close()
            if source is not None:
                source.close()
            if temporary is not None and not journal.exists():
                temporary.unlink(missing_ok=True)
