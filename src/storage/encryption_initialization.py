"""Доказывает незавершённую первичную настройку без чтения ключа данных."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from storage.database_connections import database_lock
from storage.field_cipher import CiphertextError


def _cell(value: object) -> object:
    if isinstance(value, bytes):
        return {"blob": base64.b64encode(value).decode("ascii")}
    return value


def plaintext_evidence(path: Path) -> str:
    """Связывает intent с целой исходной schema 6 без признаков шифрования."""
    from storage import database
    from storage.encrypted_migration import TABLES, _protected_fields

    with database_lock(path):
        if not path.is_file() or path.is_symlink():
            raise CiphertextError()
        journal = path.with_name(path.name + ".protection-migration.json")
        if (
            journal.exists()
            or journal.is_symlink()
            or journal.with_name(journal.name + ".write").exists()
            or journal.with_name(journal.name + ".write").is_symlink()
            or any(path.parent.glob("." + path.name + ".protected-*"))
        ):
            raise CiphertextError()
        expected = sqlite3.connect(":memory:")
        connection = None
        try:
            for migration in (
                database._migrate_0_to_1,
                database._migrate_1_to_2,
                database._migrate_2_to_3,
                database._migrate_3_to_4,
                database._migrate_4_to_5,
                database._migrate_5_to_6,
            ):
                migration(expected)
            connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA temp_store=MEMORY")
            connection.execute("BEGIN")
            if connection.execute("PRAGMA user_version").fetchone()[0] != 6:
                raise CiphertextError()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if (
                tables != set(TABLES)
                or connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger')"
                ).fetchone()
            ):
                raise CiphertextError()
            if (
                connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
                or connection.execute("PRAGMA foreign_key_check").fetchone()
            ):
                raise CiphertextError()
            digest = hashlib.sha256()

            def append(value: object) -> None:
                encoded = json.dumps(
                    value, ensure_ascii=True, separators=(",", ":"), allow_nan=False
                ).encode("ascii")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)

            append("tokenlogue-plaintext-initialization-v1")
            append(
                [
                    list(row)
                    for row in connection.execute(
                        "SELECT type,name,tbl_name,sql FROM sqlite_master "
                        "ORDER BY type,name"
                    )
                ]
            )
            for table in TABLES:
                columns = [
                    tuple(row)
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                ]
                if columns != list(expected.execute(f'PRAGMA table_info("{table}")')):
                    raise CiphertextError()
                append(table)
                count = 0
                for row in connection.execute(
                    f'SELECT rowid AS _initial_rowid,* FROM "{table}" ORDER BY rowid'
                ):
                    count += 1
                    for field in _protected_fields(table):
                        value = row[field]
                        if value is not None and (
                            not isinstance(value, str)
                            or re.match(r'\[\s*"TLG"', value.lstrip())
                        ):
                            raise CiphertextError()
                    # Счётчик неверных PIN меняется до разрешения доступа.
                    # Verifier и регистрация входят в digest и защищённую привязку.
                    append(
                        [
                            [name, _cell(row[name])]
                            for name in row.keys()
                            if table != "auth_state"
                            or name not in {"failed_attempts", "locked_until"}
                        ]
                    )
                if table == "auth_state" and count != 1:
                    raise CiphertextError()
            return digest.hexdigest()
        except (sqlite3.Error, TypeError, ValueError):
            raise CiphertextError() from None
        finally:
            expected.close()
            if connection is not None:
                connection.close()
