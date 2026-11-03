"""Device history stays independent of ephemeral observer and trial lifetimes."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from platform_security.local_protection import (  # noqa: E402
    SCREEN_CONTRACT,
    SLEEP_CONTRACT,
    AppLockState,
    CheckState,
    DeviceCheckRecord,
    DeviceProtectionHistory,
    LocalProtectionChecks,
    ObserverContext,
    ScreenLockUnavailable,
    ScreenState,
)


class Adapter:
    def __init__(self, screen: ObserverContext, sleep: ObserverContext):
        self.screen_context, self.sleep_context = screen, sleep
        self.requests = 0
        self.unbound = []
        self.identifier: int | None = None
        self.error: Exception | None = None
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None

    async def prepare_sleep_test(self, *, timeout: float = 8.0):
        if self.error:
            raise self.error
        return self.sleep_context

    def bind_sleep_test(self, context, test_id):
        self.identifier = test_id

    def unbind_sleep_test(self, context, test_id):
        self.unbound.append((context, test_id))

    async def request_sleep(self, context):
        self.requests += 1
        self.entered.set()
        if self.release:
            await self.release.wait()
        if self.error:
            raise self.error

    async def read_screen_state(self, context):
        return ScreenState(context, False)

    async def request_screen_lock(self, context):
        pass


class DeviceProtectionTrials(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.screen = ObserverContext("linux", "fake", 1, "fake-screen")
        self.sleep = ObserverContext("linux", "fake", 1, "fake-system")
        self.state = AppLockState(1, True, True, False)
        self.now = 0.0
        self.wall_now = 1234567890
        self.completed = []
        self.emergencies = 0
        self.checks = self.create()
        self.adapter = Adapter(self.screen, self.sleep)

    def create(self, history=None, **kwargs):
        checks = LocalProtectionChecks(
            lambda: self.state,
            self.emergency,
            clock=lambda: self.now,
            wall_clock=lambda: self.wall_now,
            history=history,
            on_completed=lambda *args: self.completed.append(args),
            poll_interval=0.001,
            reaction_grace=0,
            **kwargs,
        )
        checks.update_observers(self.screen, self.sleep)
        self.addAsyncCleanup(checks.aclose)
        return checks

    def require_record(self, record: DeviceCheckRecord | None) -> DeviceCheckRecord:
        self.assertIsNotNone(record)
        assert record is not None
        return record

    def emergency(self):
        self.emergencies += 1
        self.state = AppLockState(2, False, False, True)

    async def screen_pass(self):
        self.state = AppLockState(1, True, True, False)
        self.assertTrue(await self.checks.start_screen_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("screen", self.screen, 1, True)
        self.checks.observe_screen_transition(self.screen, True)
        self.checks.observe_screen_transition(self.screen, False)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)

    def observed_sleep(self, *, sealed=True, actual=True, pin=True):
        self.state = AppLockState(2, not sealed, not sealed, pin and sealed)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.checks.observe_sleep_resume(self.sleep, actual)

    async def test_screen_then_observed_sleep_preserves_both_after_reconnect_and_pin(
        self,
    ):
        await self.screen_pass()
        self.observed_sleep()
        self.checks.update_observers(None, self.sleep)
        self.assertFalse(self.checks.snapshot.screen_connected)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        replacement = ObserverContext(
            "linux", "new-session-after-reboot", 7, "new-owner"
        )
        self.checks.update_observers(replacement, self.sleep)
        self.state = AppLockState(3, True, True, False)
        self.checks.app_state_changed()
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(
            self.require_record(self.checks.history.sleep).origin, "observed"
        )

    async def test_sleep_then_screen_does_not_overwrite_sleep(self):
        self.observed_sleep()
        before = self.checks.history.sleep
        await self.screen_pass()
        self.assertEqual(self.checks.history.sleep, before)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_restart_loaded_history_has_no_active_trial_or_auto_request(self):
        await self.screen_pass()
        self.observed_sleep()
        fresh = self.create(self.checks.history)
        fresh.update_observers(None, None)
        self.assertFalse(fresh.snapshot.screen_connected)
        self.assertFalse(fresh.snapshot.test_running)
        self.assertEqual(fresh.snapshot.screen.state, CheckState.CONFIRMED)
        fresh.update_observers(self.screen, self.sleep)
        self.assertEqual(fresh.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(fresh.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(self.adapter.requests, 0)

    async def test_contract_mismatch_is_stale_not_pass_and_retains_record(self):
        old = DeviceCheckRecord(CheckState.CONFIRMED, 12, 12, "old-contract")
        fresh = self.create(DeviceProtectionHistory(old, None))
        self.assertTrue(fresh.snapshot.screen_stale)
        self.assertEqual(fresh.snapshot.screen.code, "contract_changed")
        self.assertEqual(fresh.snapshot.screen_history, old)

    async def test_runtime_contract_change_hides_current_green_but_not_history(self):
        await self.screen_pass()
        self.checks.update_observers(self.screen, self.sleep, screen_compatible=False)
        self.assertTrue(self.checks.snapshot.screen_stale)
        self.assertEqual(self.checks.snapshot.screen.code, "contract_changed")
        self.assertEqual(
            self.require_record(self.checks.snapshot.screen_history).state,
            CheckState.CONFIRMED,
        )
        self.checks.update_observers(self.screen, self.sleep, screen_compatible=True)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)

    async def test_new_sleep_fail_retains_screen_and_previous_success_time(self):
        await self.screen_pass()
        self.observed_sleep()
        self.observed_sleep(sealed=False)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.PROBLEM)
        self.assertEqual(
            self.require_record(self.checks.snapshot.sleep_history).last_success_at,
            1234567890,
        )
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.emergencies, 2)

    async def test_pair_without_kernel_suspend_cannot_create_fail_or_erase_pass(self):
        self.observed_sleep()
        previous = self.checks.history.sleep
        self.observed_sleep(sealed=False, actual=False)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(
            self.checks.snapshot.sleep_attempt.code, "actual_suspend_unproven"
        )
        self.assertEqual(self.checks.history.sleep, previous)

    async def test_manual_request_keeps_app_open_until_normal_handler_then_long_sleep(
        self,
    ):
        await self.screen_pass()
        self.state = AppLockState(1, True, True, False)
        self.adapter.release = asyncio.Event()
        pending = asyncio.create_task(self.checks.start_sleep_test(self.adapter, 1))
        await self.adapter.entered.wait()
        self.assertTrue(self.state.opened)
        self.assertEqual(self.emergencies, 0)
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.assertTrue(await pending)
        # Arbitrary BOOTTIME can pass during actual suspend, while monotonic
        # request/unlock deadlines do not. Delayed RPC is still pending.
        self.now = 10
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(
            self.require_record(self.checks.history.sleep).origin, "manual"
        )

    async def test_rpc_ack_without_sleep_is_not_pass_and_times_out(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.assertTrue(self.state.opened)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)
        self.now = 10
        await asyncio.sleep(0.01)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.UNTESTED)
        self.assertEqual(self.completed, [])

    async def test_unavailable_and_cancel_do_not_erase_prior_success(self):
        self.observed_sleep()
        previous = self.checks.history.sleep
        self.state = AppLockState(1, True, True, False)
        self.adapter.error = ScreenLockUnavailable("sleep_permission_required")
        self.assertFalse(await self.checks.start_sleep_test(self.adapter, 1))
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(
            self.checks.snapshot.sleep_attempt.code, "sleep_permission_required"
        )
        self.checks.cancel_sleep_test()
        self.assertEqual(self.checks.history.sleep, previous)

    async def test_duplicate_and_cross_mechanism_click_cannot_issue_second_request(
        self,
    ):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.assertFalse(await self.checks.start_sleep_test(self.adapter, 1))
        self.assertFalse(await self.checks.start_screen_test(self.adapter, 1))
        self.assertEqual(self.adapter.requests, 1)

    async def test_old_or_missing_sleep_identifier_cannot_complete_manual_trial(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.checks.observe_sleep_resume(self.sleep, True, test_id=None)
        assert self.adapter.identifier is not None
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier + 1
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_resume_before_prepare_or_after_cancel_cannot_complete(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.completed, [])
        self.checks.cancel_sleep_test()
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.completed, [])

    async def test_pin_not_yet_built_waits_then_finishes(self):
        self.state = AppLockState(2, False, False, False)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.checks.observe_sleep_resume(self.sleep, True)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)
        self.state = AppLockState(2, False, False, True)
        self.checks.app_state_changed()
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_incomplete_trial_is_not_persisted_after_restart(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        fresh = self.create(self.checks.history)
        self.assertEqual(fresh.snapshot.sleep.state, CheckState.UNTESTED)
        self.assertFalse(fresh.snapshot.test_running)

    async def test_completion_callback_failure_reports_unsaved_current_pass(self):
        def broken(*_):
            raise OSError("private detail")

        self.checks.set_completion_callback(broken)
        self.observed_sleep()
        self.assertTrue(self.checks.snapshot.persistence_error)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        fresh = self.create(DeviceProtectionHistory())
        self.assertEqual(fresh.snapshot.sleep.state, CheckState.UNTESTED)

    async def test_loaded_fail_remains_red_during_unavailable_retry(self):
        record = DeviceCheckRecord(CheckState.PROBLEM, 23, 12, SLEEP_CONTRACT)
        fresh = self.create(DeviceProtectionHistory(None, record))
        fresh.sleep_preparation_unavailable("sleep_inhibited")
        self.assertEqual(fresh.snapshot.sleep.state, CheckState.PROBLEM)
        self.assertEqual(
            self.require_record(fresh.snapshot.sleep_history).last_success_at, 12
        )

    async def test_histories_are_stable_contracts_not_process_metadata(self):
        await self.screen_pass()
        self.observed_sleep()
        self.assertEqual(
            self.require_record(self.checks.history.screen).contract, SCREEN_CONTRACT
        )
        self.assertEqual(
            self.require_record(self.checks.history.sleep).contract, SLEEP_CONTRACT
        )
        self.assertEqual(len(self.completed), 2)

    async def test_cold_sleep_preparation_can_publish_new_context_without_cancelling_itself(
        self,
    ):
        self.checks.update_observers(self.screen, None)
        original = self.adapter.prepare_sleep_test

        async def cold_prepare(*, timeout: float = 8.0):
            self.checks.update_observers(self.screen, self.sleep)
            return await original(timeout=timeout)

        self.adapter.prepare_sleep_test = cold_prepare
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.assertEqual(self.adapter.requests, 1)

    async def test_very_fast_sleep_before_rpc_returns_still_confirms_once(self):
        async def immediate(context):
            self.adapter.requests += 1
            self.state = AppLockState(2, False, False, True)
            self.checks.normal_reaction("sleep", context, 1, True)
            self.checks.observe_sleep_resume(
                context, True, test_id=self.adapter.identifier
            )

        self.adapter.request_sleep = immediate
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(len(self.completed), 1)

    async def test_cancel_retry_same_context_rejects_old_identifier(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        old = self.adapter.identifier
        self.checks.cancel_sleep_test()
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.checks.observe_sleep_resume(self.sleep, True, test_id=old)
        self.assertEqual(self.completed, [])
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_owner_loss_cancels_waiting_request_and_preserves_completed_sibling(
        self,
    ):
        await self.screen_pass()
        self.state = AppLockState(1, True, True, False)
        self.adapter.release = asyncio.Event()
        pending = asyncio.create_task(self.checks.start_sleep_test(self.adapter, 1))
        await self.adapter.entered.wait()
        self.checks.update_observers(self.screen, None)
        self.assertFalse(await pending)
        self.adapter.release.set()
        await asyncio.sleep(0)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.UNTESTED)

    async def test_new_screen_fail_does_not_erase_sleep_or_old_screen_success(self):
        await self.screen_pass()
        self.observed_sleep()
        self.state = AppLockState(1, True, True, False)
        self.assertTrue(await self.checks.start_screen_test(self.adapter, 1))
        self.checks.observe_screen_transition(self.screen, True)
        self.checks.observe_screen_transition(self.screen, False)
        self.assertEqual(self.checks.snapshot.screen.state, CheckState.PROBLEM)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertEqual(
            self.require_record(self.checks.history.screen).last_success_at, 1234567890
        )

    async def test_normal_screen_seal_before_sleep_prepare_is_valid_bound_chain(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("screen", self.screen, 1, True)
        self.checks.normal_reaction("sleep", self.sleep, 2, False)
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_manual_preseal_or_foreign_screen_receipt_cannot_confirm_sleep(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        wrong = ObserverContext("linux", "other-session", 1, "other-source")
        self.checks.normal_reaction("screen", wrong, 1, True)
        self.checks.normal_reaction("sleep", self.sleep, 2, False)
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.completed, [])
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)

    async def test_screen_receipt_from_old_epoch_cannot_chain_after_owner_change(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, True)
        self.checks.normal_reaction("screen", self.screen, 1, True)
        new = ObserverContext("linux", "fake", 2, "replacement")
        self.checks.update_observers(new, self.sleep)
        self.checks.normal_reaction("sleep", self.sleep, 2, False)
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.completed, [])

    async def test_sleep_cannot_be_started_from_already_sealed_profile(self):
        self.state = AppLockState(2, False, False, True)
        self.assertFalse(await self.checks.start_sleep_test(self.adapter, 2))
        self.assertEqual(self.adapter.requests, 0)

    async def test_late_failed_rpc_after_real_resume_cannot_replace_actual_proof(self):
        self.adapter.release = asyncio.Event()
        pending = asyncio.create_task(self.checks.start_sleep_test(self.adapter, 1))
        await self.adapter.entered.wait()
        self.state = AppLockState(2, False, False, False)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.assertTrue(await pending)
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)
        self.adapter.error = ScreenLockUnavailable("sleep_unavailable")
        self.adapter.release.set()
        await asyncio.sleep(0.005)
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)
        self.state = AppLockState(2, False, False, True)
        self.checks.app_state_changed()
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_pin_observed_before_late_resume_survives_ordinary_pin_login(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, False)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.state = AppLockState(2, False, False, True)
        self.checks.app_state_changed()
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.RUNNING)
        self.state = AppLockState(3, True, True, False)
        self.checks.app_state_changed()
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.CONFIRMED)
        self.assertTrue(self.state.opened)
        self.assertEqual(self.emergencies, 0)

    async def test_early_pin_without_actual_sleep_still_cannot_pass(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.state = AppLockState(2, False, False, False)
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.state = AppLockState(2, False, False, True)
        self.checks.app_state_changed()
        self.checks.observe_sleep_resume(
            self.sleep, False, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.UNTESTED)
        self.assertEqual(self.completed, [])

    async def test_early_emergency_pin_does_not_replace_missing_normal_receipt(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.checks.normal_reaction("sleep", self.sleep, 1, True)
        self.assertTrue(self.state.sealed_pin)
        self.checks.app_state_changed()
        self.checks.observe_sleep_resume(
            self.sleep, True, test_id=self.adapter.identifier
        )
        self.assertEqual(self.checks.snapshot.sleep.state, CheckState.PROBLEM)

    async def test_clock_rollback_cannot_put_new_failure_before_previous_success(self):
        await self.screen_pass()
        self.wall_now = 1234567800
        self.state = AppLockState(1, True, True, False)
        self.assertTrue(await self.checks.start_screen_test(self.adapter, 1))
        self.checks.observe_screen_transition(self.screen, True)
        self.checks.observe_screen_transition(self.screen, False)
        record = self.require_record(self.checks.history.screen)
        self.assertEqual(record.state, CheckState.PROBLEM)
        self.assertEqual(record.checked_at, 1234567890)
        self.assertEqual(record.last_success_at, 1234567890)
        self.assertEqual(self.completed[-1], ("screen", record))
        self.wall_now = 1234567891
        await self.screen_pass()
        self.assertEqual(
            self.require_record(self.checks.history.screen).checked_at, 1234567891
        )

    async def test_cancel_and_close_unbind_exact_sleep_trial_once(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        first = self.adapter.identifier
        self.checks.cancel_sleep_test()
        self.assertEqual(self.adapter.unbound, [(self.sleep, first)])
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        second = self.adapter.identifier
        await self.checks.aclose()
        self.assertEqual(
            self.adapter.unbound, [(self.sleep, first), (self.sleep, second)]
        )

    async def test_restored_history_attach_and_idle_reconnect_do_not_invent_attempts(
        self,
    ):
        screen = DeviceCheckRecord(CheckState.CONFIRMED, 100, 100, SCREEN_CONTRACT)
        for history in (
            DeviceProtectionHistory(screen, None),
            DeviceProtectionHistory(
                screen,
                DeviceCheckRecord(CheckState.CONFIRMED, 101, 101, SLEEP_CONTRACT),
            ),
        ):
            with self.subTest(sleep_checked=history.sleep is not None):
                fresh = self.create(history)
                self.assertEqual(fresh.snapshot.screen_attempt.code, "not_checked")
                self.assertEqual(fresh.snapshot.sleep_attempt.code, "not_checked")
                fresh.update_observers(None, None)
                self.assertEqual(fresh.snapshot.screen_attempt.code, "not_checked")
                self.assertEqual(fresh.snapshot.sleep_attempt.code, "not_checked")
                new_screen = ObserverContext("linux", "restored", 7, "new-screen")
                new_sleep = ObserverContext("linux", "restored", 8, "new-system")
                fresh.update_observers(new_screen, new_sleep)
                self.assertEqual(fresh.history, history)
                self.assertEqual(fresh.snapshot.screen.state, CheckState.CONFIRMED)
                self.assertEqual(fresh.snapshot.screen_attempt.code, "not_checked")
                self.assertEqual(fresh.snapshot.sleep_attempt.code, "not_checked")

    async def test_real_failed_attempt_survives_idle_reconnect(self):
        self.checks.sleep_preparation_unavailable("sleep_permission_required")
        self.checks.preparation_unavailable("request_unavailable")
        self.checks.update_observers(None, None)
        self.checks.update_observers(self.screen, self.sleep)
        self.assertEqual(
            self.checks.snapshot.screen_attempt.code, "request_unavailable"
        )
        self.assertEqual(
            self.checks.snapshot.sleep_attempt.code, "sleep_permission_required"
        )

    async def test_actual_trial_context_loss_remains_unconfirmed_attempt(self):
        self.assertTrue(await self.checks.start_sleep_test(self.adapter, 1))
        self.checks.update_observers(self.screen, None)
        self.assertEqual(self.checks.snapshot.sleep_attempt.code, "observer_changed")
        self.assertEqual(self.checks.snapshot.screen_attempt.code, "not_checked")
        self.checks.update_observers(self.screen, self.sleep)
        self.assertEqual(self.checks.snapshot.sleep_attempt.code, "observer_changed")
