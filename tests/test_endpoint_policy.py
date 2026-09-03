"""Статические ограничения endpoint-ов и сохраняемых данных."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from storage.database import AuthDatabase  # noqa: E402


class EndpointPolicyTests(unittest.TestCase):
    def test_credits_is_absent_and_chat_endpoint_is_confined_to_client(self) -> None:
        source_files = {
            path.relative_to(SRC_ROOT): path.read_text(encoding="utf-8")
            for path in SRC_ROOT.rglob("*.py")
        }
        source = "\n".join(source_files.values())
        credits_endpoint = "/api/v1/" + "credits"
        completion_endpoint = "/api/v1/chat/" + "completions"

        self.assertNotIn(credits_endpoint, source)
        self.assertEqual(
            [
                str(path)
                for path, content in source_files.items()
                if completion_endpoint in content
            ],
            ["api/chat_completions.py"],
        )

    def test_key_limit_and_tier_are_not_persisted_in_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as data_dir:
            database = AuthDatabase(data_dir)
            with closing(sqlite3.connect(database.path)) as connection:
                columns = {
                    str(row[1])
                    for table in ("auth_state", "chats", "messages")
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }

        self.assertTrue(
            {"limit_remaining", "is_free_tier", "account_balance"}.isdisjoint(columns)
        )

    def test_completion_client_is_composed_once_and_not_created_in_ui(self) -> None:
        ui_sources = list((SRC_ROOT / "ui").glob("*.py"))
        for path in ui_sources:
            with self.subTest(path=path.name):
                content = path.read_text(encoding="utf-8")
                self.assertNotIn("ChatCompletionsClient(", content)
                self.assertNotIn("MessageSendingService(", content)

        main_source = (SRC_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertEqual(main_source.count("ChatCompletionsClient()"), 1)
        self.assertEqual(main_source.count("MessageSendingService("), 1)


if __name__ == "__main__":
    unittest.main()
