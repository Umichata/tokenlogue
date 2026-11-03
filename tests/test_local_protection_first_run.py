"""Cold preparation and real event ordering keep a protection trial scoped."""

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


class PreparedScreen:
    def __init__(self, context, publish):
        self.screen_context = None
        self.context = context
        self.publish = publish
        self.prepare_calls = 0
        self.requests = 0
        self.locked = False
        self.prepare_release: asyncio.Event | None = None
        self.prepare_entered = asyncio.Event()

    async def prepare_screen_test(self, *, timeout=8):
        self.prepare_calls += 1
        self.prepare_entered.set()
        if self.prepare_release is not None:
            await self.prepare_release.wait()
        self.screen_context = self.context
        self.publish(self.context, None)
        return self.context

    async def read_screen_state(self, context):
        return ScreenState(context, self.locked)

    async def request_screen_lock(self, context):
        self.requests += 1


class TaggedPreparedScreen(PreparedScreen):
    def bind_screen_test(self, context, identifier):
        self.bound = (context, identifier)


class LocalProtectionFirstRunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.context = ObserverContext("linux", "qa", 2, "attested-locker")
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
            request_timeout=0.03,
        )
        self.addAsyncCleanup(self.model.aclose)
        self.screen = PreparedScreen(self.context, self.model.update_observers)

    def emergency(self):
        self.emergencies += 1
        self.state = AppLockState(6, False, False, True)

    async def settle(self):
        for _ in range(5):
            await asyncio.sleep(0.001)

    async def test_cold_context_is_prepared_before_binding_trial(self):
        self.assertIsNone(self.screen.screen_context)
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.assertEqual(self.screen.prepare_calls, 1)
        self.assertEqual(self.screen.requests, 1)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)

    async def test_quick_events_not_caught_by_poll_still_need_normal_seal_and_pin(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.state = AppLockState(6, False, False, False)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.model.observe_screen_transition(self.context, True)
        self.model.observe_screen_transition(self.context, False)
        self.assertNotEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.state = AppLockState(6, False, False, True)
        self.model.app_state_changed()
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.emergencies, 0)

    async def test_normal_slow_unlock_is_not_lost_at_short_acquisition_deadline(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.screen.locked = True
        self.model.observe_screen_transition(self.context, True)
        self.now = 120.0
        await self.settle()
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)
        self.screen.locked = False
        self.model.observe_screen_transition(self.context, False)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)

    async def test_late_old_context_events_cannot_confirm_another_trial(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.model.observe_screen_transition(self.context, True)
        changed = ObserverContext("linux", "qa", 3, "replacement-locker")
        self.model.update_observers(changed, None)
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.model.observe_screen_transition(self.context, False)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)

    async def test_duplicate_and_cancel_during_bootstrap_never_issue_request(self):
        self.screen.prepare_release = asyncio.Event()
        starting = asyncio.create_task(self.model.start_screen_test(self.screen, 5))
        await asyncio.wait_for(self.screen.prepare_entered.wait(), 0.2)
        self.assertTrue(self.model.snapshot.screen_test_running)
        self.assertFalse(await self.model.start_screen_test(self.screen, 5))
        self.model.cancel_screen_test()
        self.screen.prepare_release.set()
        self.assertFalse(await starting)
        self.assertEqual(self.screen.requests, 0)

    async def test_bootstrap_timeout_can_retry_without_issuing_old_lock(self):
        self.model._preparation_timeout = 0.01
        self.screen.prepare_release = asyncio.Event()
        self.assertFalse(await self.model.start_screen_test(self.screen, 5))
        self.assertEqual(self.model.snapshot.screen.code, "preparation_timeout")
        self.assertFalse(self.model.snapshot.screen_test_running)
        self.assertEqual(self.screen.requests, 0)
        self.screen.prepare_release.set()
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.assertEqual(self.screen.requests, 1)

    async def test_long_unlock_timeout_is_bounded_and_late_return_cannot_confirm(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.screen.locked = True
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.model.observe_screen_transition(self.context, True)
        self.now = 901
        await self.settle()
        self.assertEqual(self.model.snapshot.screen.code, "unlock_timeout")
        self.screen.locked = False
        self.model.observe_screen_transition(self.context, False)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)

    async def test_result_survives_normal_pin_login_and_translation(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.model.observe_screen_transition(self.context, True)
        self.model.observe_screen_transition(self.context, False)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.state = AppLockState(7, True, True, False)
        self.model.app_state_changed()
        self.model.update_observers(self.context, None)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)

    async def test_screen_unlock_without_visible_pin_never_confirms(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.state = AppLockState(6, False, False, False)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.model.observe_screen_transition(self.context, True)
        self.model.observe_screen_transition(self.context, False)
        self.now = 6
        await self.settle()
        self.assertEqual(self.model.snapshot.screen.code, "pin_timeout")
        self.state = AppLockState(6, False, False, True)
        self.model.app_state_changed()
        self.assertEqual(self.model.snapshot.screen.state, CheckState.UNTESTED)

    async def test_trace_contains_no_context_or_exception_content(self):
        trace = []
        self.model.set_trace(trace.append)

        async def unavailable(**_kwargs):
            raise ScreenLockUnavailable("private_exception_secret_not_a_code")

        self.screen.prepare_screen_test = unavailable
        self.assertFalse(await self.model.start_screen_test(self.screen, 5))
        self.assertEqual(self.model.snapshot.screen.code, "request_unavailable")
        self.assertTrue(trace)
        self.assertNotIn("private_exception_secret", repr(trace))
        self.assertNotIn(self.context.source, repr(trace))
        self.assertTrue(all("test" in item and "generation" in item for item in trace))

    async def test_readback_unlock_before_dispatch_waits_bounded_normal_receipt(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.model.observe_screen_transition(self.context, True)
        self.model.observe_screen_transition(self.context, False)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)
        self.assertEqual(self.emergencies, 0)
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)

    async def test_readback_unlock_without_later_normal_seal_becomes_red(self):
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        self.model.observe_screen_transition(self.context, True)
        self.model.observe_screen_transition(self.context, False)
        self.now = 2
        await self.settle()
        self.assertEqual(self.model.snapshot.screen.state, CheckState.PROBLEM)
        self.assertEqual(self.emergencies, 1)

    async def test_same_context_late_tagged_and_untagged_events_cannot_confirm_retry(
        self,
    ):
        self.screen = TaggedPreparedScreen(self.context, self.model.update_observers)
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        assert self.model._trial is not None
        old_id = self.model._trial.identifier
        self.model.cancel_screen_test()
        self.assertTrue(await self.model.start_screen_test(self.screen, 5))
        assert self.model._trial is not None
        new_id = self.model._trial.identifier
        self.assertNotEqual(old_id, new_id)
        self.state = AppLockState(6, False, False, True)
        self.model.normal_reaction("screen", self.context, 5, True)
        self.model.observe_screen_transition(self.context, True, test_id=old_id)
        self.model.observe_screen_transition(self.context, False, test_id=old_id)
        self.model.observe_screen_transition(self.context, True)
        self.model.observe_screen_transition(self.context, False)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.RUNNING)
        self.model.observe_screen_transition(self.context, True, test_id=new_id)
        self.model.observe_screen_transition(self.context, False, test_id=new_id)
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
