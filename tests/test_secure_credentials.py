"""Офлайн-тесты адаптера платформенного защищённого хранилища."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from storage.secure_credentials import (  # noqa: E402
    API_KEY_STORAGE_NAME,
    REGISTRATION_ID_STORAGE_NAME,
    SECURE_STORAGE_NAMESPACE,
    FletSecureCredentials,
    SecureCredentialsError,
)


class FakeSecureStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.read_keys: list[str] = []
        self.fail_set_key: str | None = None

    async def contains_key(self, key: str) -> bool:
        return key in self.values

    async def get(self, key: str) -> str | None:
        self.read_keys.append(key)
        return self.values.get(key)

    async def set(self, key: str, value: Any) -> None:
        if key == self.fail_set_key:
            raise RuntimeError("injected set failure")
        self.values[key] = str(value)

    async def remove(self, key: str) -> None:
        self.values.pop(key, None)


class SecureCredentialsTests(unittest.IsolatedAsyncioTestCase):
    def test_storage_keys_use_tokenlogue_namespace(self) -> None:
        self.assertEqual(
            SECURE_STORAGE_NAMESPACE,
            "io.github.umichata.tokenlogue",
        )
        self.assertTrue(API_KEY_STORAGE_NAME.startswith(SECURE_STORAGE_NAMESPACE))
        self.assertTrue(
            REGISTRATION_ID_STORAGE_NAME.startswith(SECURE_STORAGE_NAMESPACE)
        )

    async def test_inspection_does_not_read_api_key(self) -> None:
        storage = FakeSecureStorage()
        storage.values[API_KEY_STORAGE_NAME] = "test-value"
        storage.values[REGISTRATION_ID_STORAGE_NAME] = "registration-id"
        credentials = FletSecureCredentials(storage)

        state = await credentials.inspect_state()

        self.assertTrue(state.complete)
        self.assertNotIn(API_KEY_STORAGE_NAME, storage.read_keys)
        self.assertIn(REGISTRATION_ID_STORAGE_NAME, storage.read_keys)

    async def test_partial_save_removes_both_records(self) -> None:
        storage = FakeSecureStorage()
        storage.fail_set_key = API_KEY_STORAGE_NAME
        credentials = FletSecureCredentials(storage)

        with self.assertRaises(SecureCredentialsError):
            await credentials.save_credentials("test-value", "registration-id")

        self.assertEqual(storage.values, {})

    async def test_delete_removes_key_and_registration_id(self) -> None:
        storage = FakeSecureStorage()
        storage.values[API_KEY_STORAGE_NAME] = "test-value"
        storage.values[REGISTRATION_ID_STORAGE_NAME] = "registration-id"
        credentials = FletSecureCredentials(storage)

        await credentials.delete_credentials()

        self.assertEqual(storage.values, {})


if __name__ == "__main__":
    unittest.main()
