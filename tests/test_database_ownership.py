"""Межпроцессное владение общей SQLite на всём сроке работы клиента."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.encrypted_migration import migrate_database  # noqa: E402
from storage.field_cipher import FieldCipher  # noqa: E402
from tests.test_chat_repository import _chat  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_CLIENT = """
import json,sys
from datetime import UTC,datetime
from storage.database import AuthDatabase
from storage.chat_repository import SqliteChatRepository
from tests.test_chat_repository import _chat
try:
    if sys.argv[2] == 'auth':
        database = AuthDatabase(sys.argv[1])
        result = {'opened': True, 'registered': database.get_auth_state() is not None}
    else:
        repository = SqliteChatRepository(sys.argv[1])
        repository.create_chat(_chat('concurrent',datetime.now(UTC)))
        result = {'saved': True, 'ids': sorted(chat.id for chat in repository.list_chats())}
    print(json.dumps(result))
except Exception as error:
    print(json.dumps({'error_type': type(error).__name__}))
    sys.exit(23)
"""


class DatabaseOwnershipTests(unittest.TestCase):
    def client(self, path: Path, action: str = "write") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", _CLIENT, str(path), action],
            cwd=_ROOT,
            env=dict(
                os.environ, PYTHONPATH=str(_ROOT / "src") + os.pathsep + str(_ROOT)
            ),
            capture_output=True,
            text=True,
            timeout=15,
        )

    def assert_refused(self, path: Path, action: str = "write") -> None:
        result = self.client(path, action)
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertEqual(
            json.loads(result.stdout), {"error_type": "DatabaseOwnershipError"}
        )

    def test_other_auth_process_is_refused_before_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = AuthDatabase(directory)
            before = database.path.read_bytes()
            self.assert_refused(Path(directory), "auth")
            self.assertEqual(database.path.read_bytes(), before)

    def test_repository_only_process_is_refused_between_connections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = AuthDatabase(directory).path
            repository = SqliteChatRepository(path)
            repository.create_chat(_chat("original", datetime.now(UTC)))
            self.assert_refused(path)
            self.assertEqual(
                [chat.id for chat in repository.list_chats()], ["original"]
            )

    def test_current_writer_is_refused_before_and_after_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = AuthDatabase(directory).path
            SqliteChatRepository(path).create_chat(_chat("original", datetime.now(UTC)))
            stages = []

            def hit(stage: str) -> None:
                if stage in {"before_replace", "after_replace"}:
                    stages.append(stage)
                    self.assert_refused(path)

            cipher = FieldCipher(bytes(range(32)), "fixture-db", "fixture-key")
            migrate_database(path, cipher, failpoint=hit)
            self.assertEqual(stages, ["before_replace", "after_replace"])
            # Владение не заканчивается после rename и проверки нового файла.
            self.assert_refused(Path(directory), "auth")
            with sqlite3.connect(path) as raw:
                self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], 7)
                self.assertEqual(
                    raw.execute("SELECT id FROM chats ORDER BY id").fetchall(),
                    [("original",)],
                )

    def test_current_migrator_is_refused_while_other_process_owns_database(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = AuthDatabase(directory).path
            code = """
import sys
from storage.encrypted_migration import migrate_database
from storage.field_cipher import FieldCipher
try:
    migrate_database(sys.argv[1], FieldCipher(bytes(32), 'other-db', 'other-key'))
except Exception as error:
    print(type(error).__name__)
    sys.exit(23)
"""
            result = subprocess.run(
                [sys.executable, "-c", code, str(path)],
                cwd=_ROOT,
                env=dict(os.environ, PYTHONPATH=str(_ROOT / "src")),
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 23, result.stderr)
            self.assertEqual(result.stdout.strip(), "DatabaseOwnershipError")
            with sqlite3.connect(path) as raw:
                self.assertEqual(raw.execute("PRAGMA user_version").fetchone()[0], 6)

    def test_ownership_survives_auth_object_collection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = AuthDatabase(directory).path
            # Конструктор может использоваться без сохранения объекта AuthDatabase.
            self.assert_refused(path)
            self.assertIsNone(AuthDatabase(directory).get_auth_state())

    def test_second_process_can_open_after_owner_exits_normally(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            code = """
import sys
from storage.database import AuthDatabase
from storage.chat_repository import SqliteChatRepository
from tests.test_chat_repository import _chat
from datetime import UTC,datetime
path=AuthDatabase(sys.argv[1]).path
SqliteChatRepository(path).create_chat(_chat('original',datetime.now(UTC)))
print('READY',flush=True)
sys.stdin.readline()
"""
            with subprocess.Popen(
                [sys.executable, "-c", code, directory],
                cwd=_ROOT,
                env=dict(
                    os.environ,
                    PYTHONPATH=str(_ROOT / "src") + os.pathsep + str(_ROOT),
                ),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ) as owner:
                assert owner.stdout is not None
                self.assertEqual(owner.stdout.readline().strip(), "READY")
                self.assert_refused(Path(directory), "auth")
                _, stderr = owner.communicate("finish\n", timeout=15)
                self.assertEqual(owner.returncode, 0, stderr)
            result = self.client(Path(directory) / "tokenlogue.sqlite3")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["ids"], ["concurrent", "original"]
            )

    def test_alias_path_uses_same_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "data"
            path = AuthDatabase(data).path
            alias = Path(directory) / "alias"
            alias.symlink_to(data, target_is_directory=True)
            self.assert_refused(alias / path.name)

    @unittest.skipUnless(hasattr(os, "fork"), "Нужен POSIX fork")
    def test_fork_does_not_treat_inherited_descriptor_as_own_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = AuthDatabase(directory).path
            reading, writing = os.pipe()
            child = os.fork()
            if child == 0:
                os.close(reading)
                try:
                    AuthDatabase(directory)
                    observed = b"opened"
                except Exception as error:
                    observed = type(error).__name__.encode("ascii")
                os.write(writing, observed)
                os.close(writing)
                os._exit(0)
            os.close(writing)
            try:
                observed = os.read(reading, 200)
                _, status = os.waitpid(child, 0)
            finally:
                os.close(reading)
            self.assertEqual(status, 0)
            self.assertEqual(observed, b"DatabaseOwnershipError")
            # Закрытие копии FD в дочернем процессе не снимает lock родителя.
            self.assert_refused(path)

    def test_lock_file_replacement_is_refused_instead_of_splitting_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = AuthDatabase(directory).path
            lock_file = path.with_name("." + path.name + ".owner.lock")
            if not lock_file.exists():
                self.fail("Отсутствует стабильный файл межпроцессного владения")
            lock_file.unlink()
            lock_file.write_bytes(b"")
            with self.assertRaisesRegex(RuntimeError, ".+"):
                AuthDatabase(directory)


if __name__ == "__main__":
    unittest.main()
