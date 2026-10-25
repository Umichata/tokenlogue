"""Проверки аутентифицированного формата локального содержимого."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.field_cipher import CiphertextError, FieldCipher  # noqa: E402


class FieldCipherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cipher = FieldCipher(bytes(range(32)), "database-a", "key-a")
        self.aad: dict[str, Any] = dict(
            table="messages",
            field="content",
            record_id="message-a",
            chat_id="chat-a",
            role="user",
            revision=0,
        )

    def test_unicode_empty_long_and_new_nonce(self) -> None:
        for text in ("", "История 🔐\n日本語", "длинное сообщение " * 10000):
            with self.subTest(length=len(text)):
                one = self.cipher.encrypt(text, **self.aad)
                two = self.cipher.encrypt(text, **self.aad)
                self.assertNotEqual(one, two)
                self.assertEqual(self.cipher.decrypt(one, **self.aad), text)
                self.assertEqual(self.cipher.decrypt(two, **self.aad), text)

    def test_wrong_key_and_every_aad_coordinate_rejected(self) -> None:
        encrypted = self.cipher.encrypt("SYNTHETIC SENTINEL", **self.aad)
        for field in self.aad:
            changed = dict(self.aad)
            changed[field] = (
                1 if field == "revision" else str(changed[field]) + "-other"
            )
            with self.subTest(field=field), self.assertRaises(CiphertextError):
                self.cipher.decrypt(encrypted, **changed)
        for cipher in (
            FieldCipher(bytes(reversed(range(32))), "database-a", "key-a"),
            FieldCipher(bytes(range(32)), "database-b", "key-a"),
            FieldCipher(bytes(range(32)), "database-a", "key-b"),
        ):
            with self.assertRaises(CiphertextError):
                cipher.decrypt(encrypted, **self.aad)

    def test_envelope_corruption_never_returns_plaintext(self) -> None:
        encrypted = self.cipher.encrypt("SYNTHETIC SENTINEL", **self.aad)
        payload = json.loads(encrypted)
        for index in range(6):
            changed = list(payload)
            changed[index] = 2 if index == 1 else "corrupted"
            with self.subTest(index=index), self.assertRaises(CiphertextError):
                self.cipher.decrypt(json.dumps(changed), **self.aad)
        for invalid in ("plaintext", "", "null", "[]", "{}", "[true]"):
            with self.assertRaises(CiphertextError):
                self.cipher.decrypt(invalid, **self.aad)

    def test_size_limit_and_repr_do_not_expose_key(self) -> None:
        with self.assertRaises(CiphertextError):
            self.cipher.encrypt("x" * (16 * 1024 * 1024 + 1), **self.aad)
        self.assertNotIn(repr(bytes(range(32))), repr(self.cipher))
