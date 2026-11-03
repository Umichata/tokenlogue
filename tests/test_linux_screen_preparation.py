"""Lazy Cinnamon activation is attested before launch and does not pre-seal."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.linux_dbus import DBusError, DBusReply  # noqa: E402
from platform_security.linux_session import LinuxSessionWatcher  # noqa: E402
from platform_security.local_protection import ScreenLockUnavailable  # noqa: E402
from tests.test_linux_screen_lock_adapter import LockBus  # noqa: E402
from tests.test_linux_session import (  # noqa: E402
    DBUS,
    DBUS_PATH,
    LOGIN,
    SCREEN,
    SCREEN_PATH,
    FakeBus,
    signal,
)


class LazyBus(LockBus):
    def __init__(self, actions):
        super().__init__(system=False)
        self.owner = None
        self.actions = actions
        self.activation_allowed = True
        self.lock_cycle = False
        self.serial = 100

    async def call(
        self,
        destination,
        path,
        interface,
        member,
        signature="",
        body=None,
        *,
        timeout: float = 10,
    ):
        if member == "StartServiceByName":
            self.calls.append((destination, path, interface, member, signature, body))
            self.actions.append("activate")
            if self.activation_allowed:
                await asyncio.sleep(0.001)
                self.owner = ":1.20"
                self.signals.put_nowait(
                    signal(
                        DBUS,
                        DBUS_PATH,
                        DBUS,
                        "NameOwnerChanged",
                        "sss",
                        [SCREEN, "", self.owner],
                    )
                )
            return DBusReply(DBUS, "u", [1])
        if member == "Lock":
            self.serial += 1
            acknowledgement = self.serial
            if self.lock_cycle:
                self.screen_active = True
                self.serial += 1
                self.signals.put_nowait(
                    replace(
                        signal(
                            self.owner,
                            SCREEN_PATH,
                            SCREEN,
                            "ActiveChanged",
                            "b",
                            [True],
                        ),
                        serial=self.serial,
                    )
                )
                await asyncio.sleep(0.005)
            result = await super().call(
                destination, path, interface, member, signature, body, timeout=timeout
            )
            return replace(result, serial=acknowledgement)
        result = await super().call(
            destination, path, interface, member, signature, body, timeout=timeout
        )
        if member == "GetActive":
            self.serial += 1
            return replace(result, serial=self.serial)
        return result


class LinuxScreenPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.actions = []
        self.system = FakeBus(system=True)
        self.system.screen_pid_error = DBusError(
            LOGIN + ".NoSessionForPID", sender=":1.10"
        )
        self.desktop = LazyBus(self.actions)
        self.events = []
        self.observations = []
        self.capable = True
        self.preparer = AsyncMock(
            side_effect=lambda *_: self.actions.append("attest_activation")
        )
        self.watcher = LinuxSessionWatcher(
            self.events.append,
            on_observation=self.observations.append,
            bus_factory=lambda: (self.system, self.desktop),
            process_verifier=lambda *_: True,
            process_snapshot=lambda pid: pid,
            display_verifier=lambda *_: True,
            activation_verifier=AsyncMock(),
            activation_preparer=self.preparer,
            lock_contract_verifier=lambda *_: self.capable,
            service_verifier=AsyncMock(),
        )
        self.addAsyncCleanup(self.watcher.aclose)
        await self.watcher.start()
        self.events.clear()

    async def test_cold_activation_is_attested_first_without_app_seal(self):
        self.assertIsNone(self.watcher.screen_context)
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertEqual(context, self.watcher.screen_context)
        self.assertEqual(self.actions[:2], ["attest_activation", "activate"])
        self.assertIn(
            (DBUS, DBUS_PATH, DBUS, "StartServiceByName", "su", [SCREEN, 0]),
            self.desktop.calls,
        )
        self.assertEqual(self.events, [])

    async def test_saved_history_restores_lazy_owner_with_activation_only(self):
        self.watcher._saved_screen_interval = 0.001
        self.watcher._saved_screen_retry = 0.001
        self.assertIsNone(self.watcher._saved_screen_task)
        self.assertNotIn("activate", self.actions)
        self.watcher.enable_saved_screen_monitoring()
        task = self.watcher._saved_screen_task
        self.watcher.enable_saved_screen_monitoring()
        self.assertIs(self.watcher._saved_screen_task, task)
        for _ in range(100):
            if self.watcher.screen_context is not None:
                break
            await asyncio.sleep(0.001)
        self.assertIsNotNone(self.watcher.screen_context)
        self.assertTrue(self.watcher.screen_history_compatible)
        self.assertEqual(self.events, [])
        self.assertFalse(
            any(
                call[3] in {"Lock", "Suspend", "SuspendWithFlags"}
                for bus in (self.desktop, self.system)
                for call in bus.calls
            )
        )

    async def test_saved_monitoring_reconnects_after_lazy_owner_exit(self):
        self.watcher._saved_screen_interval = 0.001
        self.watcher._saved_screen_retry = 0.001
        await self.watcher.prepare_screen_test(timeout=0.1)
        old = self.watcher.screen_context
        self.desktop.owner = None
        await self.watcher._refresh_screen()
        self.assertIsNone(self.watcher.screen_context)
        self.watcher.enable_saved_screen_monitoring()
        for _ in range(100):
            if self.watcher.screen_context is not None:
                break
            await asyncio.sleep(0.001)
        self.assertIsNotNone(self.watcher.screen_context)
        self.assertNotEqual(old, self.watcher.screen_context)
        self.assertFalse(any(call[3] == "Lock" for call in self.desktop.calls))

    async def test_unknown_runtime_contract_is_reported_on_same_owner_refresh(self):
        await self.watcher.prepare_screen_test(timeout=0.1)
        statuses = []
        self.watcher._on_status = statuses.append
        self.assertTrue(self.watcher.screen_history_compatible)
        self.capable = False
        await self.watcher._refresh_screen()
        self.assertFalse(self.watcher.screen_history_compatible)
        self.assertTrue(statuses)
        self.assertIsNotNone(self.watcher.screen_context)

    async def test_saved_contract_is_revalidated_during_readback_without_new_trial(
        self,
    ):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertIsNone(self.watcher._requested_lock)
        statuses = []
        self.watcher._on_status = statuses.append
        self.capable = False
        await self.watcher.read_screen_state(context)
        self.assertFalse(self.watcher.screen_history_compatible)
        self.assertTrue(statuses)
        self.assertIsNotNone(self.watcher.screen_context)

    async def test_untrusted_restore_is_bounded_and_drained_on_close(self):
        self.watcher._saved_screen_retry = 0.001
        self.preparer.side_effect = RuntimeError("private detail")
        self.watcher.enable_saved_screen_monitoring()
        await asyncio.sleep(0.01)
        task = self.watcher._saved_screen_task
        self.assertFalse(
            any(
                call[3] in {"StartServiceByName", "Lock"} for call in self.desktop.calls
            )
        )
        await self.watcher.aclose()
        assert task is not None
        self.assertTrue(task.done())
        self.assertIsNone(self.watcher._saved_screen_task)

    async def test_untrusted_activation_never_issues_activation_or_lock(self):
        self.preparer.side_effect = RuntimeError("untrusted private detail")
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertFalse(
            any(
                call[3] in {"StartServiceByName", "Lock"} for call in self.desktop.calls
            )
        )

    async def test_missing_owner_times_out_without_lock_or_false_ready(self):
        self.desktop.activation_allowed = False
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.prepare_screen_test(timeout=0.02)
        self.assertIsNone(self.watcher.screen_context)
        self.assertFalse(any(call[3] == "Lock" for call in self.desktop.calls))

    async def test_same_owner_async_refresh_keeps_existing_attestation(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.watcher._identity

        async def delayed(bus, owner, role):
            if role == "cinnamon":
                entered.set()
                await release.wait()
            return await original(bus, owner, role)

        self.watcher._identity = delayed
        task = asyncio.create_task(self.watcher._refresh_screen())
        await entered.wait()
        self.assertEqual(self.watcher.screen_context, context)
        release.set()
        await task
        self.assertEqual(self.watcher.screen_context, context)

    async def test_own_lock_cycle_with_capability_does_not_require_locked_hint(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.desktop.lock_cycle = True
        await self.watcher.request_screen_lock(context)
        self.assertFalse(self.system.properties["LockedHint"])
        self.assertTrue((await self.watcher.read_screen_state(context)).locked)
        self.assertIn("screen_locked", [item.kind for item in self.observations])

    async def test_visible_screensaver_without_own_request_is_not_lock_proof(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.desktop.screen_active = True
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        )
        self.assertIsNone((await self.watcher.read_screen_state(context)).locked)
        self.assertNotIn("screen_locked", [item.kind for item in self.observations])

    async def test_capability_loss_prevents_requested_cycle_proof(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.capable = False
        self.desktop.lock_cycle = True
        await self.watcher.request_screen_lock(context)
        self.assertIsNone((await self.watcher.read_screen_state(context)).locked)
        self.assertNotIn("screen_locked", [item.kind for item in self.observations])

    async def test_other_desktop_is_rejected_before_any_service_activation(self):
        self.system.properties["Desktop"] = "other-desktop"
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertFalse(
            any(call[3] == "StartServiceByName" for call in self.desktop.calls)
        )

    async def test_ambiguous_graphical_session_is_rejected_before_activation(self):
        path = LOGIN + "/session/another"
        self.system.user_properties["Sessions"].append(["another", path])
        self.system.session_properties[path] = {
            **self.system.properties,
            "Id": "another",
            "Display": ":1",
        }
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertFalse(
            any(call[3] == "StartServiceByName" for call in self.desktop.calls)
        )

    async def test_queued_old_activation_frame_is_not_this_request_evidence(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.watcher.bind_screen_test(context, 7)
        await self.watcher.request_screen_lock(context)
        self.desktop.screen_active = True
        self.watcher._screen_signal(
            replace(
                signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True]),
                serial=50,
            )
        )
        self.assertNotIn("screen_locked", [item.kind for item in self.observations])
        self.assertIsNone((await self.watcher.read_screen_state(context)).locked)

    async def test_activation_older_than_lock_ack_is_not_current_proof(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        await self.watcher.request_screen_lock(context)
        cycle = self.watcher._requested_lock
        assert cycle is not None
        self.desktop.screen_active = True
        self.watcher._screen_signal(
            replace(
                signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True]),
                serial=cycle.baseline_serial,
            )
        )
        self.assertNotIn("screen_locked", [item.kind for item in self.observations])

    async def test_zero_serial_never_creates_composite_proof(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        await self.watcher.request_screen_lock(context)
        self.desktop.screen_active = True
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        )
        self.assertNotIn("screen_locked", [item.kind for item in self.observations])

    async def test_fresh_transition_carries_bound_trial_id(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.watcher.bind_screen_test(context, 7)
        self.desktop.lock_cycle = True
        await self.watcher.request_screen_lock(context)
        locked = next(
            item for item in self.observations if item.kind == "screen_locked"
        )
        self.assertEqual(locked.test_id, 7)
        self.desktop.screen_active = False
        self.desktop.serial += 1
        self.watcher._screen_signal(
            replace(
                signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [False]),
                serial=self.desktop.serial,
            )
        )
        inactive = [
            item
            for item in self.observations
            if item.kind == "screen_inactive" and item.test_id is not None
        ]
        self.assertEqual(inactive[-1].test_id, 7)

    def test_sender_serial_half_range_rejects_old_and_ambiguous_wrap(self):
        self.assertTrue(self.watcher._serial_after(2, 0xFFFFFFFE))
        self.assertFalse(self.watcher._serial_after(0xFFFFFFFE, 2))
        self.assertFalse(self.watcher._serial_after(0x80000002, 2))
        self.assertFalse(self.watcher._serial_after(0, 2))
        self.assertFalse(self.watcher._serial_after(True, 2))

    async def test_desktop_bus_retry_keeps_independent_system_subscription(self):
        old_context = await self.watcher.prepare_screen_test(timeout=0.1)
        sleep_context = self.watcher.sleep_context
        self.desktop.signals.put_nowait(RuntimeError("synthetic disconnect"))
        for _ in range(100):
            if self.watcher._desktop is None:
                break
            await asyncio.sleep(0.001)
        self.assertIsNone(self.watcher._desktop)
        new_desktop = LazyBus(self.actions)
        self.watcher._bus_factory = lambda: (self.system, new_desktop)
        new_context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertNotEqual(new_context, old_context)
        self.assertEqual(self.watcher.sleep_context, sleep_context)
        self.assertEqual(self.system.closed, 0)
        self.assertFalse(any(call[3] == "Lock" for call in new_desktop.calls))

    async def test_system_bus_retry_rebuilds_attested_connections_and_generation(self):
        old_context = await self.watcher.prepare_screen_test(timeout=0.1)
        old_sleep = self.watcher.sleep_context
        self.system.signals.put_nowait(RuntimeError("synthetic disconnect"))
        for _ in range(100):
            if self.watcher._system is None:
                break
            await asyncio.sleep(0.001)
        self.assertIsNone(self.watcher._system)
        new_system = FakeBus(system=True)
        new_system.screen_pid_error = DBusError(
            LOGIN + ".NoSessionForPID", sender=":1.10"
        )
        new_desktop = LazyBus(self.actions)
        self.watcher._bus_factory = lambda: (new_system, new_desktop)
        new_context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.assertNotEqual(new_context, old_context)
        self.assertNotEqual(self.watcher.sleep_context, old_sleep)
        self.assertFalse(any(call[3] == "Lock" for call in new_desktop.calls))

    async def test_lost_package_contract_invalidates_already_published_context(self):
        context = await self.watcher.prepare_screen_test(timeout=0.1)
        self.desktop.lock_cycle = True
        await self.watcher.request_screen_lock(context)
        self.assertIn("screen_locked", [item.kind for item in self.observations])
        self.capable = False
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.read_screen_state(context)
        self.assertIsNone(self.watcher.screen_context)


if __name__ == "__main__":
    unittest.main()
