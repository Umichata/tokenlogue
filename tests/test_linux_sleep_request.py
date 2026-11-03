"""The explicit sleep adapter uses only attested ordinary logind requests."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from dataclasses import replace
from itertools import count
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from platform_security.linux_dbus import DBusError, DBusReply  # noqa: E402
from platform_security.linux_session import (  # noqa: E402
    LinuxSessionWatcher,
    SessionSecurityEvent,
)
from platform_security.local_protection import ScreenLockUnavailable  # noqa: E402
from tests.test_linux_session import (  # noqa: E402
    LOGIN_PATH,
    MANAGER,
    FakeBus,
)
from tests.test_linux_session import (
    signal as base_signal,
)

_SIGNAL_SERIALS = count(1000)


def signal(*args, serial: int | None = None, **kwargs):
    return replace(
        base_signal(*args, **kwargs),
        serial=next(_SIGNAL_SERIALS) if serial is None else serial,
    )


class SleepBus(FakeBus):
    def __init__(self):
        super().__init__(system=True)
        self.serial = 100
        self.capability = "yes"
        self.inhibitors = []
        self.suspend_error: DBusError | None = None
        self.suspend_reply_sender: str | None = None
        self.can_signature = "s"
        self.inhibitor_signature = "a(ssssuu)"

    async def call(
        self,
        destination,
        path,
        interface,
        member,
        signature="",
        body=None,
        *,
        timeout=10,
    ):
        if member in {"CanSuspend", "ListInhibitors", "Suspend"}:
            assert self.owner is not None
            self.serial += 1
            self.calls.append((destination, path, interface, member, signature, body))
            if member == "CanSuspend":
                return DBusReply(
                    self.owner,
                    self.can_signature,
                    [self.capability],
                    serial=self.serial,
                )
            if member == "ListInhibitors":
                return DBusReply(
                    self.owner,
                    self.inhibitor_signature,
                    [self.inhibitors],
                    serial=self.serial,
                )
            if self.suspend_error:
                raise self.suspend_error
            return DBusReply(
                self.suspend_reply_sender or self.owner, "", [], serial=self.serial
            )
        return await super().call(
            destination, path, interface, member, signature, body, timeout=timeout
        )


class LinuxSleepRequest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bus = SleepBus()
        self.desktop = FakeBus(system=False)
        self.events = []
        self.observations = []
        self.watcher = LinuxSessionWatcher(
            self.events.append,
            on_observation=self.observations.append,
            bus_factory=lambda: (self.bus, self.desktop),
            process_verifier=lambda *_: True,
            process_snapshot=lambda pid: pid,
            service_verifier=AsyncMock(),
            display_verifier=lambda *_: True,
            activation_verifier=AsyncMock(),
            lock_contract_verifier=lambda _: True,
        )
        self.addAsyncCleanup(self.watcher.aclose)
        await self.watcher.start()

    async def test_capability_and_inhibitors_precede_fixed_suspend_without_interactive(
        self,
    ):
        context = await self.watcher.prepare_sleep_test()
        self.assertFalse(any(call[3] == "Suspend" for call in self.bus.calls))
        self.watcher.bind_sleep_test(context, 4)
        await self.watcher.request_sleep(context)
        request = [call for call in self.bus.calls if call[3] == "Suspend"]
        self.assertEqual(
            request, [(":1.10", LOGIN_PATH, MANAGER, "Suspend", "b", [False])]
        )
        self.assertEqual(self.events, [])
        self.assertEqual(self.observations, [])

    async def test_unsupported_or_permission_challenge_never_requests_sleep(self):
        for capability, code in (
            ("no", "sleep_unavailable"),
            ("na", "sleep_unavailable"),
            ("challenge", "sleep_permission_required"),
            ("unexpected", "sleep_unavailable"),
        ):
            with self.subTest(capability=capability):
                self.bus.capability = capability
                with self.assertRaisesRegex(ScreenLockUnavailable, code):
                    await self.watcher.prepare_sleep_test()
        self.assertFalse(any(call[3] == "Suspend" for call in self.bus.calls))

    async def test_foreign_sleep_block_inhibitor_is_respected(self):
        self.bus.inhibitors = [
            ["sleep:shutdown", "other", "private reason", "block", os.getuid(), 999]
        ]
        with self.assertRaisesRegex(ScreenLockUnavailable, "sleep_inhibited"):
            await self.watcher.prepare_sleep_test()
        self.assertFalse(any(call[3] == "Suspend" for call in self.bus.calls))

    async def test_delay_and_unrelated_block_inhibitors_are_not_forced_or_changed(self):
        self.bus.inhibitors = [
            ["sleep", "other", "private reason", "delay", 0, 999],
            ["shutdown", "other", "private reason", "block", 0, 999],
        ]
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 1)
        await self.watcher.request_sleep(context)
        self.assertIn(
            (":1.10", LOGIN_PATH, MANAGER, "Suspend", "b", [False]), self.bus.calls
        )
        self.assertFalse(
            any(call[3] in {"Inhibit", "SuspendWithFlags"} for call in self.bus.calls)
        )

    async def test_new_inhibitor_between_prepare_and_request_prevents_suspend(self):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 1)
        self.bus.inhibitors = [["sleep", "other", "reason", "block", 0, 999]]
        with self.assertRaisesRegex(ScreenLockUnavailable, "sleep_inhibited"):
            await self.watcher.request_sleep(context)
        self.assertFalse(any(call[3] == "Suspend" for call in self.bus.calls))

    async def test_wrong_sender_signature_malformed_inhibitor_are_unavailable(self):
        for value in (
            ["sleep", "app", "why", "block", True, 2],
            ["sleep", "app"],
            ["sleep", "app", "why", "mystery", 0, 2],
        ):
            self.bus.inhibitors = [value]
            with self.assertRaises(ScreenLockUnavailable):
                await self.watcher.prepare_sleep_test()
        self.bus.inhibitors = []
        self.bus.can_signature = "b"
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.prepare_sleep_test()
        self.bus.can_signature = "s"
        self.bus.inhibitor_signature = "s"
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.prepare_sleep_test()

    async def test_permission_failure_and_bad_ack_are_safe_codes_without_details(self):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 1)
        assert self.bus.owner is not None
        self.bus.suspend_error = DBusError(
            "org.freedesktop.DBus.Error.AccessDenied", sender=self.bus.owner
        )
        with self.assertRaisesRegex(
            ScreenLockUnavailable, "^sleep_permission_required$"
        ):
            await self.watcher.request_sleep(context)
        self.bus.suspend_error = None
        self.bus.suspend_reply_sender = ":1.999"
        with self.assertRaisesRegex(ScreenLockUnavailable, "^sleep_unavailable$"):
            await self.watcher.request_sleep(context)

    async def test_unbound_request_and_changed_session_cannot_suspend(self):
        context = await self.watcher.prepare_sleep_test()
        with self.assertRaisesRegex(ScreenLockUnavailable, "observer_changed"):
            await self.watcher.request_sleep(context)
        self.watcher.bind_sleep_test(context, 1)
        self.bus.properties["Active"] = False
        with self.assertRaisesRegex(ScreenLockUnavailable, "session_changed"):
            await self.watcher.request_sleep(context)
        self.assertFalse(any(call[3] == "Suspend" for call in self.bus.calls))

    async def test_true_false_and_kernel_gap_are_scoped_and_one_shot(self):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 7)
        await self.watcher.request_sleep(context)
        with patch.object(self.watcher, "_sleep_gap", side_effect=[1.0, 121.0]):
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
            )
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
            )
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False])
            )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])
        self.assertTrue(self.observations[-1].actual_suspend)
        self.assertEqual(self.observations[-1].test_id, 7)
        with patch.object(self.watcher, "_sleep_gap", side_effect=[121.0, 122.0]):
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
            )
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False])
            )
        self.assertIsNone(self.observations[-1].test_id)

    async def test_no_gap_fake_pair_or_unpaired_false_never_proves_suspend(self):
        for values in ([1.0, 1.0], [None, None]):
            with patch.object(self.watcher, "_sleep_gap", side_effect=values):
                self.watcher._system_signal(
                    signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
                )
                self.watcher._system_signal(
                    signal(
                        ":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False]
                    )
                )
            self.assertFalse(self.observations[-1].actual_suspend)
        with patch.object(self.watcher, "_sleep_gap", return_value=999.0):
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False])
            )
        self.assertFalse(self.observations[-1].actual_suspend)

    async def test_untrusted_source_and_malformed_sleep_events_do_not_revoke_or_pass(
        self,
    ):
        for event in (
            signal(":1.99", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "s", [True]),
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [1]),
        ):
            self.watcher._system_signal(event)
        self.assertEqual(self.events, [])
        self.assertEqual(self.observations, [])

    async def test_external_prepare_before_own_suspend_cannot_claim_manual_identifier(
        self,
    ):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 7)
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.watcher._validate_sleep_request

        async def delayed(current):
            barrier = await original(current)
            entered.set()
            await release.wait()
            return barrier

        with patch.object(self.watcher, "_validate_sleep_request", side_effect=delayed):
            request = asyncio.create_task(self.watcher.request_sleep(context))
            await entered.wait()
            with patch.object(self.watcher, "_sleep_gap", side_effect=[1.0, 2.0]):
                self.watcher._system_signal(
                    signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
                )
                self.watcher._system_signal(
                    signal(
                        ":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False]
                    )
                )
            self.assertIsNone(self.observations[-1].test_id)
            release.set()
            with self.assertRaisesRegex(ScreenLockUnavailable, "observer_changed"):
                await request
        self.assertFalse(any(call[3] == "Suspend" for call in self.bus.calls))

    async def test_kernel_gap_baseline_follows_synchronous_normal_seal(self):
        gap = [1.0]

        def normal_seal(event):
            self.events.append(event)
            gap[0] = 121.0

        self.watcher._on_revoke = normal_seal
        with patch.object(self.watcher, "_sleep_gap", side_effect=lambda: gap[0]):
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
            )
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False])
            )
            self.assertFalse(self.observations[-1].actual_suspend)
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
            )
            gap[0] = 122.0
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False])
            )
            self.assertTrue(self.observations[-1].actual_suspend)

    async def test_exact_unbind_does_not_remove_newer_trial_binding(self):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 7)
        self.watcher.bind_sleep_test(context, 8)
        self.watcher.unbind_sleep_test(context, 7)
        self.assertEqual(self.watcher._bound_sleep_test, (context, 8))
        self.watcher.unbind_sleep_test(context, 8)
        self.assertIsNone(self.watcher._bound_sleep_test)
        self.assertFalse(self.watcher._bound_sleep_issued)

    async def test_queued_prepare_during_final_peer_check_is_older_than_send_barrier(
        self,
    ):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 7)
        queued = []
        original = self.watcher._same_peer

        async def queue_old_signal(*args):
            await original(*args)
            self.bus.serial += 1
            queued.append(
                signal(
                    ":1.10",
                    LOGIN_PATH,
                    MANAGER,
                    "PrepareForSleep",
                    "b",
                    [True],
                    serial=self.bus.serial,
                )
            )

        with patch.object(self.watcher, "_same_peer", side_effect=queue_old_signal):
            await self.watcher.request_sleep(context)
        self.assertTrue(self.watcher._bound_sleep_issued)
        barrier = self.watcher._bound_sleep_barrier
        self.assertLess(queued[0].serial, barrier)
        with patch.object(self.watcher, "_sleep_gap", side_effect=[1.0, 2.0]):
            self.watcher._system_signal(queued[0])
            self.watcher._system_signal(
                signal(
                    ":1.10",
                    LOGIN_PATH,
                    MANAGER,
                    "PrepareForSleep",
                    "b",
                    [False],
                    serial=barrier + 10,
                )
            )
        self.assertIsNone(self.observations[-1].test_id)
        self.assertTrue(self.observations[-1].actual_suspend)

    async def test_old_or_zero_resume_cannot_consume_current_trusted_sleep_cycle(self):
        context = await self.watcher.prepare_sleep_test()
        self.watcher.bind_sleep_test(context, 7)
        await self.watcher.request_sleep(context)
        begin = self.watcher._bound_sleep_barrier + 10
        with patch.object(self.watcher, "_sleep_gap", side_effect=[1.0, 2.0]):
            self.watcher._system_signal(
                signal(
                    ":1.10",
                    LOGIN_PATH,
                    MANAGER,
                    "PrepareForSleep",
                    "b",
                    [True],
                    serial=begin,
                )
            )
            for invalid in (0, begin, begin - 1):
                self.watcher._system_signal(
                    signal(
                        ":1.10",
                        LOGIN_PATH,
                        MANAGER,
                        "PrepareForSleep",
                        "b",
                        [False],
                        serial=invalid,
                    )
                )
            self.assertTrue(self.watcher._sleep_signal_pending)
            self.assertEqual(self.observations, [])
            self.watcher._system_signal(
                signal(
                    ":1.10",
                    LOGIN_PATH,
                    MANAGER,
                    "PrepareForSleep",
                    "b",
                    [False],
                    serial=begin + 1,
                )
            )
        self.assertTrue(self.observations[-1].actual_suspend)
        self.assertEqual(self.observations[-1].test_id, 7)
