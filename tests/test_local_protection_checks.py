"""Evidence must be a real same-context OS cycle plus the ordinary app seal."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.local_protection import (  # noqa: E402
    AppLockState,
    CheckState,
    LocalProtectionChecks,
    ObserverContext,
    ScreenLockUnavailable,
    ScreenState,
)
from platform_security.windows_session import WindowsSessionAdapter  # noqa: E402


class FakeScreen:
    def __init__(self, context: ObserverContext):
        self.screen_context = context
        self.locked: bool | None = False
        self.requests = 0
        self.failure: Exception | None = None
        self.request_entered = asyncio.Event()
        self.request_release: asyncio.Event | None = None

    async def read_screen_state(self, context):
        return ScreenState(self.screen_context, self.locked)

    async def request_screen_lock(self, context):
        self.requests += 1
        self.request_entered.set()
        if self.request_release is not None:
            await self.request_release.wait()
        if self.failure is not None:
            raise self.failure


class LocalProtectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.screen = ObserverContext("linux", "synthetic-session", 1, "locker-a")
        self.sleep = ObserverContext("linux", "synthetic-session", 1, "system-a")
        self.state = AppLockState(5, True, True, False)
        self.now = 0.0
        self.emergencies = 0
        self.changes = []
        self.model = LocalProtectionChecks(
            lambda: self.state,
            self.emergency,
            self.changes.append,
            clock=lambda: self.now,
            poll_interval=0.001,
            reaction_grace=0,
            request_timeout=0.05,
        )
        self.model.update_observers(self.screen, self.sleep)
        self.adapter = FakeScreen(self.screen)
        self.addAsyncCleanup(self.model.aclose)

    def emergency(self):
        self.emergencies += 1
        self.state = AppLockState(6, False, False, True)

    async def wait_for(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.001)
        self.fail("evidence model did not reach expected state")

    async def start(self):
        self.assertTrue(await self.model.start_screen_test(self.adapter, 5))

    def normal_screen_seal(self, *, pin=True):
        self.state = AppLockState(6, False, False, pin)
        self.model.normal_reaction("screen", self.screen, 5, True)

    async def complete_screen(self):
        await self.start()
        self.adapter.locked = True
        self.normal_screen_seal()
        await self.wait_for(
            lambda: (
                self.model._trial is not None
                and self.model._trial.locked_at is not None
            )
        )
        self.adapter.locked = False
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.CONFIRMED
        )

    async def test_subscriptions_start_untested_and_do_not_confirm_sleep(self):
        self.assertTrue(self.model.snapshot.screen_connected)
        self.assertTrue(self.model.snapshot.sleep_connected)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)
        self.assertEqual(self.model.snapshot.screen_attempt.code, "not_checked")
        await self.start()
        self.assertEqual(self.adapter.requests, 1)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)

    async def test_success_needs_locked_normal_seal_unlock_and_actual_pin(self):
        await self.start()
        self.adapter.locked = True
        self.normal_screen_seal(pin=False)
        await self.wait_for(
            lambda: (
                self.model._trial is not None
                and self.model._trial.locked_at is not None
            )
        )
        self.adapter.locked = False
        await asyncio.sleep(0.005)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)
        self.state = AppLockState(6, False, False, True)
        self.model.app_state_changed()
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.CONFIRMED
        )
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)

    async def test_known_os_lock_and_failed_ordinary_seal_is_red_after_emergency(self):
        await self.start()
        self.adapter.locked = True
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.PROBLEM
        )
        self.assertEqual(self.emergencies, 1)
        self.assertTrue(self.state.sealed_pin)
        self.adapter.locked = False
        await asyncio.sleep(0.005)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.PROBLEM)

    async def test_ui_pin_flag_with_open_data_is_never_success(self):
        await self.start()
        self.adapter.locked = True
        self.state = AppLockState(6, False, True, True)
        self.model.normal_reaction("screen", self.screen, 5, True)
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.PROBLEM
        )
        self.assertEqual(self.emergencies, 1)

    async def test_manual_app_seal_is_not_an_ordinary_watcher_receipt(self):
        await self.start()
        self.state = AppLockState(6, False, False, True)
        self.adapter.locked = True
        await self.wait_for(
            lambda: (
                self.model._trial is not None
                and self.model._trial.locked_at is not None
            )
        )
        self.adapter.locked = False
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.UNTESTED
        )
        self.assertEqual(self.model.snapshot.screen.code, "normal_reaction_unproven")
        self.assertEqual(self.emergencies, 0)

    async def test_visible_screensaver_without_lock_proof_is_unconfirmed(self):
        await self.start()
        self.adapter.locked = None
        self.normal_screen_seal()
        await self.wait_for(
            lambda: self.model._trial is not None and self.model._trial.ambiguous_seen
        )
        self.adapter.locked = False
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.UNTESTED
        )
        self.assertEqual(self.model.snapshot.screen.code, "locked_state_unproven")
        self.assertEqual(self.emergencies, 0)

    async def test_command_and_unlock_alone_are_not_proof_and_timeout_is_bounded(self):
        await self.start()
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)
        self.now = 91
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.UNTESTED
        )
        self.assertEqual(self.model.snapshot.screen.code, "timeout")
        self.assertTrue(await self.model.start_screen_test(self.adapter, 5))
        self.assertEqual(self.adapter.requests, 2)

    async def test_request_failure_and_hanging_request_never_confirm(self):
        self.adapter.failure = RuntimeError("private OS detail must not reach UI")
        self.assertFalse(await self.model.start_screen_test(self.adapter, 5))
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(self.model.snapshot.screen.code, "request_unavailable")
        self.adapter.failure = None
        release = asyncio.Event()
        self.adapter.request_release = release
        self.assertFalse(await self.model.start_screen_test(self.adapter, 5))
        self.assertFalse(self.model.snapshot.screen_test_running)

    async def test_request_failure_after_detected_problem_cannot_hide_red(self):
        self.adapter.request_release = asyncio.Event()
        self.adapter.failure = RuntimeError("synthetic")
        starting = asyncio.create_task(self.model.start_screen_test(self.adapter, 5))
        await self.adapter.request_entered.wait()
        self.adapter.locked = True
        await self.wait_for(
            lambda: self.model.snapshot.screen.state is CheckState.PROBLEM
        )
        assert self.adapter.request_release is not None
        self.adapter.request_release.set()
        self.assertFalse(await starting)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.PROBLEM)

    async def test_duplicate_click_and_already_closed_app_do_not_start_second_test(
        self,
    ):
        await self.start()
        self.assertFalse(await self.model.start_screen_test(self.adapter, 5))
        self.assertEqual(self.adapter.requests, 1)
        await self.model.aclose()
        self.assertFalse(await self.model.start_screen_test(self.adapter, 5))

    async def test_closed_or_wrong_application_session_cannot_begin(self):
        self.assertFalse(await self.model.start_screen_test(self.adapter, 4))
        self.state = AppLockState(6, False, False, True)
        self.assertFalse(await self.model.start_screen_test(self.adapter, 6))
        self.assertEqual(self.adapter.requests, 0)

    async def test_generation_loss_cancels_test_and_late_event_cannot_confirm(self):
        await self.start()
        old = self.screen
        self.screen = ObserverContext("linux", "synthetic-session", 2, "locker-b")
        self.adapter.screen_context = self.screen
        self.model.update_observers(self.screen, self.sleep)
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", old, 5, True)
        await asyncio.sleep(0.005)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)
        self.assertEqual(self.model.snapshot.screen_attempt.code, "observer_changed")

    async def test_observer_change_cancels_unissued_os_request(self):
        release = asyncio.Event()
        entered = asyncio.Event()
        issued = []

        async def delayed(context):
            entered.set()
            await release.wait()
            issued.append(context)

        self.adapter.request_screen_lock = delayed
        starting = asyncio.create_task(self.model.start_screen_test(self.adapter, 5))
        await entered.wait()
        self.model.update_observers(None, self.sleep)
        self.assertFalse(await starting)
        release.set()
        await asyncio.sleep(0)
        self.assertEqual(issued, [])
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)

    async def test_close_drains_pending_request_and_invalidates_prior_result(self):
        release = asyncio.Event()
        entered = asyncio.Event()
        issued = []

        async def delayed(context):
            entered.set()
            await release.wait()
            issued.append(context)

        self.adapter.request_screen_lock = delayed
        starting = asyncio.create_task(self.model.start_screen_test(self.adapter, 5))
        await entered.wait()
        await self.model.aclose()
        self.assertFalse(await starting)
        release.set()
        await asyncio.sleep(0)
        self.assertEqual(issued, [])
        self.assertFalse(self.model.snapshot.screen_connected)
        self.assertFalse(self.model.snapshot.screen_test_running)

    async def test_explicit_cancel_during_initial_read_does_not_issue_os_lock(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked(context):
            entered.set()
            await release.wait()
            return ScreenState(context, False)

        self.adapter.read_screen_state = blocked
        starting = asyncio.create_task(self.model.start_screen_test(self.adapter, 5))
        await entered.wait()
        self.model.cancel_screen_test()
        release.set()
        self.assertFalse(await starting)
        self.assertEqual(self.adapter.requests, 0)

    async def test_explicit_cancel_drains_pending_request_without_unhandled_cancellation(
        self,
    ):
        self.adapter.request_release = asyncio.Event()
        starting = asyncio.create_task(self.model.start_screen_test(self.adapter, 5))
        await self.adapter.request_entered.wait()
        self.model.cancel_screen_test()
        self.assertFalse(await starting)
        self.assertFalse(self.model.snapshot.screen_test_running)

    async def test_translation_same_context_preserves_confirmation(self):
        await self.complete_screen()
        before = self.model.snapshot
        self.model.update_observers(self.screen, self.sleep)
        self.assertEqual(self.model.snapshot, before)
        self.model.update_observers(None, self.sleep)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertFalse(self.model.snapshot.screen_connected)
        self.assertEqual(self.model.snapshot.screen_attempt.code, "not_checked")

    async def test_sleep_requires_ordinary_seal_real_kernel_sleep_and_returned_pin(
        self,
    ):
        self.state = AppLockState(6, False, False, False)
        self.model.normal_reaction("sleep", self.sleep, 5, True)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.RUNNING)
        self.model.observe_sleep_resume(self.sleep, suspended=True)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.RUNNING)
        self.state = AppLockState(6, False, False, True)
        self.model.app_state_changed()
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)

    async def test_prepare_sleep_pair_without_actual_suspend_is_not_green(self):
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("sleep", self.sleep, 5, True)
        self.model.observe_sleep_resume(self.sleep, suspended=False)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)
        self.assertEqual(self.model.snapshot.sleep.code, "actual_suspend_unproven")

    async def test_known_sleep_failure_cannot_be_hidden_by_screen_confirmation(self):
        await self.complete_screen()
        self.state = AppLockState(7, True, True, False)
        self.model.normal_reaction("sleep", self.sleep, 7, True)
        self.model.observe_sleep_resume(self.sleep, suspended=True)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.PROBLEM)
        self.assertTrue(self.model.snapshot.has_problem)

    async def test_new_model_without_loaded_history_cannot_invent_green_result(self):
        await self.complete_screen()
        new = LocalProtectionChecks(lambda: self.state, self.emergency)
        self.addAsyncCleanup(new.aclose)
        new.update_observers(self.screen, self.sleep)
        self.assertEqual(new.snapshot.screen.state, CheckState.UNTESTED)
        self.assertEqual(new.snapshot.sleep.state, CheckState.UNTESTED)

    async def test_windows_boundary_cannot_claim_linux_mock_as_native_success(self):
        adapter = WindowsSessionAdapter()
        self.assertIsNone(adapter.screen_context)
        self.assertIsNone(adapter.sleep_context)
        self.assertFalse(await self.model.start_screen_test(adapter, 5))
        with self.assertRaises(ScreenLockUnavailable):
            await adapter.request_screen_lock(self.screen)
        with self.assertRaises(ScreenLockUnavailable):
            await adapter.read_screen_state(self.screen)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)


if __name__ == "__main__":
    unittest.main()
