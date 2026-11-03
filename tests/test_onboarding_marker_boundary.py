"""A cancelled preferences worker cannot outlive its profile operation boundary."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.local_protection import CheckResult, CheckState  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402


class OnboardingMarkerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fx = fixtures.LinuxRecoveryIntegrationTests()
        await fx.asyncSetUp()
        self.addCleanup(fx.doCleanups)
        self.app = fx.controller
        self.addAsyncCleanup(self.app.close_protection_checks)
        await self.app.submit_pin("0123")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.preferences = PreferencesStore(Path(temporary.name) / "preferences.json")
        self.preferences.set_local_protection_onboarding("pending")
        self.app._preferences = self.preferences
        checks = self.app._local_protection
        assert checks is not None
        checks._screen = CheckResult(CheckState.CONFIRMED, "screen_confirmed")

    async def exercise(self, *, cancel: bool):
        entered, release, finished = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        save = self.preferences.set_local_protection_onboarding

        def delayed(state):
            entered.set()
            if not release.wait(2):
                raise TimeoutError("synthetic worker was not released")
            save(state)
            finished.set()

        with patch.object(self.preferences, "set_local_protection_onboarding", delayed):
            task = asyncio.create_task(self.app._resume_protection_setup())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                if cancel:
                    task.cancel()
                    await asyncio.sleep(0.01)
                    self.assertFalse(task.done())
                self.assertTrue(self.app._operation_lock.locked())
                self.assertFalse(finished.is_set())
                self.assertEqual(
                    self.preferences.local_protection_onboarding, "pending"
                )
            finally:
                release.set()
                if cancel:
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    await task
                self.assertTrue(await asyncio.to_thread(finished.wait, 1))
        self.assertFalse(self.app._operation_lock.locked())
        self.assertEqual(
            PreferencesStore(self.preferences.path).local_protection_onboarding,
            "done",
        )

    async def test_resume_marker_write_serializes_with_other_profile_operations(self):
        await self.exercise(cancel=False)

    async def test_cancelled_owner_drains_marker_before_releasing_profile_operation(
        self,
    ):
        await self.exercise(cancel=True)
