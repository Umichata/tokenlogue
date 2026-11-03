"""Actual AppController metadata workers preserve sibling writes and drain."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization  # noqa: E402
from platform_security.device_protection_store import (
    DeviceProtectionStore,  # noqa: E402
)
from platform_security.local_protection import (  # noqa: E402
    SCREEN_CONTRACT,
    SLEEP_CONTRACT,
    CheckState,
    DeviceCheckRecord,
    DeviceProtectionHistory,
)
from preferences import PreferencesStore  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402


class ProtectionHistoryWorkersTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.fixture.temporary.cleanup)
        self.addCleanup(configure_localization, PreferencesStore())
        self.addCleanup(self.fx.updates.stop)
        self.addCleanup(self.fx.controller.dispose)
        self.app = self.fx.controller
        checks = self.app._local_protection
        assert checks is not None
        self.checks = checks
        self.addAsyncCleanup(self.app.close_protection_checks)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = DeviceProtectionStore(
            Path(temporary.name) / "device", machine_identity=b"a" * 32, user_id=1001
        )
        self.screen = DeviceCheckRecord(CheckState.CONFIRMED, 100, 100, SCREEN_CONTRACT)
        self.sleep = DeviceCheckRecord(CheckState.CONFIRMED, 101, 101, SLEEP_CONTRACT)

    async def drain(self):
        while self.app._history_save_tasks:
            await asyncio.gather(*tuple(self.app._history_save_tasks))

    async def test_loading_green_metadata_never_unlocks_auth_or_data(self):
        before = self.app.protection_app_state()
        self.app.configure_protection_history(
            DeviceProtectionHistory(self.screen, self.sleep), self.store.save
        )
        self.assertTrue(before.revoked)
        self.assertEqual(self.app.protection_app_state(), before)
        self.assertEqual(self.checks.history.screen, self.screen)

    async def test_sibling_success_cannot_hide_failed_screen_save(self):
        def writer(mechanism, record):
            if mechanism == "screen":
                raise OSError("synthetic disk failure")
            return self.store.save(mechanism, record)

        self.app.configure_protection_history(DeviceProtectionHistory(), writer)
        self.app._queue_protection_history("screen", self.screen)
        self.app._queue_protection_history("sleep", self.sleep)
        await self.drain()
        self.assertTrue(self.checks.snapshot.persistence_error)
        self.assertIsNone(self.store.load().screen)
        self.assertEqual(self.store.load().sleep, self.sleep)
        self.app._history_writer = self.store.save
        self.app._queue_protection_history("screen", self.screen)
        await self.drain()
        self.assertFalse(self.checks.snapshot.persistence_error)
        self.assertEqual(self.store.load().screen, self.screen)

    async def test_disk_reply_does_not_roll_back_newer_in_memory_sibling(self):
        entered, release = threading.Event(), threading.Event()

        def writer(mechanism, record):
            if mechanism == "screen":
                entered.set()
                if not release.wait(2):
                    raise TimeoutError("synthetic barrier")
            return self.store.save(mechanism, record)

        self.app.configure_protection_history(DeviceProtectionHistory(), writer)
        self.app._queue_protection_history("screen", self.screen)
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            self.checks.set_history(DeviceProtectionHistory(self.screen, self.sleep))
            self.app._queue_protection_history("sleep", self.sleep)
        finally:
            release.set()
        await self.drain()
        self.assertEqual(self.checks.history.sleep, self.sleep)
        self.assertEqual(self.store.load().sleep, self.sleep)

    async def test_cancelled_close_waits_for_real_metadata_worker(self):
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )

        def writer(mechanism, record):
            entered.set()
            if not release.wait(2):
                raise TimeoutError("synthetic barrier")
            result = self.store.save(mechanism, record)
            finished.set()
            return result

        self.app.configure_protection_history(DeviceProtectionHistory(), writer)
        self.app._queue_protection_history("screen", self.screen)
        task = None
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            task = asyncio.create_task(self.app.close_protection_checks())
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.sleep(0.01)
            self.assertFalse(task.done())
            self.assertFalse(finished.is_set())
        finally:
            release.set()
            if task is not None:
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertTrue(finished.is_set())
        self.assertEqual(self.store.load().screen, self.screen)
        self.assertFalse(self.app._history_save_tasks)
