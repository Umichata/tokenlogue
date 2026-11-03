"""Device history uses synthetic identities and temporary files only."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.device_protection_store import (  # noqa: E402
    DeviceProtectionStore,
    ProtectionStoreError,
)
from platform_security.local_protection import (  # noqa: E402
    SCREEN_CONTRACT,
    SLEEP_CONTRACT,
    CheckState,
    DeviceCheckRecord,
    DeviceProtectionHistory,
)
from preferences import PreferencesStore  # noqa: E402
from storage.access_context import finish_worker  # noqa: E402


def success(mechanism="screen", when=100):
    return DeviceCheckRecord(
        CheckState.CONFIRMED,
        when,
        when,
        SCREEN_CONTRACT if mechanism == "screen" else SLEEP_CONTRACT,
    )


class DeviceProtectionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.path = self.base / "device"
        self.store = self.make_store()

    def make_store(self, *, machine=b"a" * 32, uid=1001, path=None):
        return DeviceProtectionStore(
            path or self.path, machine_identity=machine, user_id=uid
        )

    def history_path(self):
        return next(self.path.glob("history-*.json"))

    def test_empty_restart_and_reboot_binding(self):
        self.assertEqual(self.store.load(), DeviceProtectionHistory())
        self.store.save("screen", success())
        self.store.save("sleep", success("sleep", 101))
        self.assertEqual(self.make_store().load(), self.store.load())
        self.assertEqual(self.store.load().screen, success())
        self.assertEqual(self.store.load().sleep, success("sleep", 101))

    def test_preferences_and_chat_profile_copy_do_not_transfer_results(self):
        self.store.save("screen", success())
        profile = self.base / "profile"
        prefs = PreferencesStore(profile / "tokenlogue-preferences.json")
        prefs.set_language("en")
        prefs.set_local_protection_onboarding("done")
        shutil.copytree(profile, self.base / "other-profile")
        target = self.make_store(path=self.base / "other-device", machine=b"b" * 32)
        self.assertEqual(target.load(), DeviceProtectionHistory())
        assert prefs.path is not None
        self.assertNotIn("confirmed", prefs.path.read_text())

    def test_even_copied_device_directory_does_not_transfer_to_other_machine_or_user(
        self,
    ):
        self.store.save("screen", success())
        copied = self.base / "copied-device"
        shutil.copytree(self.path, copied)
        for target in (
            self.make_store(path=copied, machine=b"b" * 32),
            self.make_store(path=copied, uid=1002),
        ):
            self.assertEqual(target.load(), DeviceProtectionHistory())
            target.save("sleep", success("sleep"))
            self.assertIsNone(target.load().screen)
        self.assertEqual(self.store.load().screen, success())

    def test_independent_concurrent_merges_and_preferences(self):
        prefs = PreferencesStore(self.base / "profile/preferences.json")
        other = self.make_store()
        self.store.load()
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(self.store.save, "screen", success()),
                pool.submit(other.save, "sleep", success("sleep", 101)),
                pool.submit(prefs.set_language, "en"),
                pool.submit(prefs.set_local_protection_onboarding, "done"),
                pool.submit(prefs.set_wide_sidebar_visible, False),
            ]
            for future in futures:
                future.result(timeout=3)
        result = self.make_store().load()
        self.assertEqual(result.screen, success())
        self.assertEqual(result.sleep, success("sleep", 101))
        reloaded = PreferencesStore(prefs.path)
        self.assertEqual(reloaded.language, "en")
        self.assertFalse(reloaded.wide_sidebar_visible)
        self.assertEqual(reloaded.local_protection_onboarding, "done")

    def test_failure_retains_last_success_and_other_mechanism(self):
        self.store.save("screen", success())
        self.store.save("sleep", success("sleep"))
        failure = DeviceCheckRecord(CheckState.PROBLEM, 101, None, SLEEP_CONTRACT)
        self.store.save("sleep", failure)
        result = self.store.load().sleep
        assert result is not None
        self.assertEqual(result.last_success_at, 100)
        self.assertEqual(result.state, CheckState.PROBLEM)
        self.assertEqual(self.store.load().screen, success())

    def test_late_older_write_does_not_replace_newer_result(self):
        self.store.save("screen", success(when=101))
        with self.assertRaises(ProtectionStoreError):
            self.store.save("screen", success(when=100))
        result = self.store.load().screen
        assert result is not None
        self.assertEqual(result.checked_at, 101)

    def test_delayed_same_second_success_cannot_hide_new_failure(self):
        self.store.save("screen", success(when=100))
        failure = DeviceCheckRecord(CheckState.PROBLEM, 101, 100, SCREEN_CONTRACT)
        self.store.save("screen", failure)
        with self.assertRaises(ProtectionStoreError):
            self.make_store().save("screen", success(when=101))
        self.assertEqual(self.make_store().load().screen, failure)

    def test_later_genuine_success_can_replace_a_failure(self):
        self.store.save(
            "screen", DeviceCheckRecord(CheckState.PROBLEM, 100, None, SCREEN_CONTRACT)
        )
        self.store.save("screen", success(when=101))
        self.assertEqual(self.make_store().load().screen, success(when=101))

    def test_atomic_replace_failure_preserves_previous_durable_record(self):
        self.store.save("screen", success())
        before = self.history_path().read_bytes()
        with patch(
            "platform_security.device_protection_store.os.replace", side_effect=OSError
        ):
            with self.assertRaises(ProtectionStoreError):
                self.store.save("sleep", success("sleep"))
        self.assertEqual(self.history_path().read_bytes(), before)
        self.assertIsNone(self.store.load().sleep)
        self.assertFalse(list(self.path.glob(".pending-*")))

    def test_corrupt_or_future_schema_never_loads_success(self):
        self.store.save("screen", success())
        path = self.history_path()
        original = path.read_text()
        for content in ("{", "[]", original.replace('"version":1', '"version":2')):
            with self.subTest(content=content[:20]):
                path.write_text(content)
                with self.assertRaises(ProtectionStoreError):
                    self.make_store().load()
        path.write_text(original)

    def test_strict_fields_types_and_incomplete_attempt_rejected(self):
        self.store.save("screen", success())
        path = self.history_path()
        original = json.loads(path.read_text())
        mutations = (
            {"checked_at": True},
            {"state": "running"},
            {"state": "untested"},
            {"origin": "unknown"},
            {"last_success_at": 101},
            {"checked_at": -1},
            {"contract": "raw:private:value"},
            {"extra": "private"},
        )
        for mutation in mutations:
            value = json.loads(json.dumps(original))
            value["screen"].update(mutation)
            path.write_text(json.dumps(value))
            with self.subTest(fields=list(mutation)):
                with self.assertRaises(ProtectionStoreError):
                    self.make_store().load()

    def test_future_contract_preserves_history_for_stale_ui(self):
        result = DeviceCheckRecord(CheckState.CONFIRMED, 100, 100, "linux-screen-v999")
        self.store.save("screen", result)
        self.assertEqual(self.store.load().screen, result)

    def test_duplicate_json_fields_cannot_create_success(self):
        self.store.save("screen", success())
        path = self.history_path()
        path.write_text(
            path.read_text().replace('"version":1', '"version":2,"version":1')
        )
        with self.assertRaises(ProtectionStoreError):
            self.store.load()

    def test_no_raw_binding_or_profile_secrets_in_persisted_metadata(self):
        self.store.save("screen", success())
        data = "".join(p.read_text() for p in self.path.glob("*.json"))
        self.assertNotIn("a" * 32, data)
        self.assertNotIn('"uid"', data)
        self.assertNotIn('"username"', data)
        value = json.loads(self.history_path().read_text())
        self.assertEqual(set(value), {"version", "binding", "screen", "sleep"})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o700)
        for path in self.path.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_symlink_or_public_directory_is_rejected(self):
        target = self.base / "target"
        target.mkdir(mode=0o700)
        self.path.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ProtectionStoreError):
            self.store.load()
        self.path.unlink()
        self.path.mkdir(mode=0o755)
        with self.assertRaises(ProtectionStoreError):
            self.store.load()

    def test_symlink_or_hardlinked_history_is_rejected(self):
        self.store.save("screen", success())
        path = self.history_path()
        backup = self.base / "backup"
        path.rename(backup)
        path.symlink_to(backup)
        with self.assertRaises(ProtectionStoreError):
            self.store.load()
        path.unlink()
        os.link(backup, path)
        with self.assertRaises(ProtectionStoreError):
            self.store.load()

    def test_invalid_or_missing_machine_identity_cannot_create_pass(self):
        for machine in (b"", b"a" * 31, b"z" * 32, b"a" * 33):
            with self.assertRaises(ProtectionStoreError):
                self.make_store(machine=machine)


class HistoryWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_thread_is_drained_before_owner_returns(self):
        import threading

        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def write():
            entered.set()
            release.wait(2)
            finished.set()

        task = asyncio.create_task(finish_worker(asyncio.to_thread(write)))
        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
        task.cancel()
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())
