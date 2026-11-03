"""Синтетические проверки формата и разделения домена резервного кода."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.recovery_code import (  # noqa: E402
    RecoveryCodeIssue,
    code_digest,
    generate_code,
    normalize_code,
)


class RecoveryCodeTests(unittest.TestCase):
    def test_generation_uses_twenty_random_bytes_and_fixed_groups(self):
        with patch(
            "storage.recovery_code.secrets.token_bytes", return_value=bytes(20)
        ) as random_bytes:
            code = generate_code()
        random_bytes.assert_called_once_with(20)
        self.assertEqual([len(group) for group in code.split("-")], [4] * 8)
        self.assertEqual(normalize_code(code), "A" * 32)
        self.assertNotIn(code, repr(RecoveryCodeIssue("synthetic-attempt", code)))

    def test_normalization_accepts_only_documented_ascii_forms(self):
        self.assertEqual(
            normalize_code(" aaaa-aaaa aaaa-aaaa aaaa-aaaa aaaa-aaaa "), "A" * 32
        )
        for invalid in (
            "A" * 31,
            "A" * 33,
            "0" * 32,
            "1" * 32,
            "A" * 31 + "Ａ",
            "А" * 32,
            "A" * 16 + "\u00a0" + "A" * 16,
            "A" * 16 + "–" + "A" * 16,
            "A" * 16 + "\n" + "A" * 16,
            "A" * 16 + "\t" + "A" * 16,
            "-" * 100 + "A" * 32,
        ):
            with self.subTest(kind="malformed_ascii_or_unicode", length=len(invalid)):
                self.assertIsNone(normalize_code(invalid))

    def test_digest_binds_every_context_coordinate_and_full_code(self):
        context: dict[str, Any] = dict(
            database_id="database",
            key_id="key",
            registration_id="registration",
            generation=1,
        )
        original = code_digest("A" * 32, **context)
        self.assertEqual(len(original), 64)
        for field, value in (
            ("database_id", "other"),
            ("key_id", "other"),
            ("registration_id", "other"),
            ("generation", 2),
        ):
            changed = dict(context, **{field: value})
            self.assertNotEqual(original, code_digest("A" * 32, **changed))
        self.assertNotEqual(original, code_digest("A" * 31 + "B", **context))


if __name__ == "__main__":
    unittest.main()
