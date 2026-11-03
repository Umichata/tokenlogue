"""Cinnamon lock changes idle metadata without changing the trusted user session."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.linux_dbus import DBusError  # noqa: E402
from platform_security.linux_session import (  # noqa: E402
    LinuxSessionWatcher,
    SessionSecurityEvent,
)
from platform_security.local_protection import (  # noqa: E402
    AppLockState,
    CheckState,
    LocalProtectionChecks,
)
from tests.test_linux_screen_preparation import LazyBus  # noqa: E402
from tests.test_linux_session import (  # noqa: E402
    LOGIN,
    PROPERTIES,
    SCREEN,
    SCREEN_PATH,
    SESSION,
    SESSION_PATH,
    FakeBus,
    signal,
)

IDLE = {"IdleHint": True, "IdleSinceHint": 123456, "IdleSinceHintMonotonic": 654321}


class LinuxIdleMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.system = FakeBus(system=True)
        self.system.screen_pid_error = DBusError(
            LOGIN + ".NoSessionForPID", sender=":1.10"
        )
        self.desktop = LazyBus([])
        self.state = AppLockState(5, True, True, False)
        self.events = []
        self.emergencies = 0
        self.model = LocalProtectionChecks(
            lambda: self.state, self.emergency, poll_interval=0.001
        )

        def revoke(event):
            before = self.state
            self.events.append(event)
            self.state = AppLockState(
                before.application_session + 1, False, False, True
            )
            if event is SessionSecurityEvent.SCREEN_LOCK:
                self.model.normal_reaction(
                    "screen",
                    self.watcher.screen_context,
                    before.application_session,
                    before.opened,
                )

        def observe(event):
            if event.kind in {"screen_locked", "screen_inactive"}:
                self.model.observe_screen_transition(
                    event.context, event.kind == "screen_locked", test_id=event.test_id
                )

        self.watcher = LinuxSessionWatcher(
            revoke,
            on_status=lambda _: self.model.update_observers(
                self.watcher.screen_context, self.watcher.sleep_context
            ),
            on_observation=observe,
            bus_factory=lambda: (self.system, self.desktop),
            process_verifier=lambda *_: True,
            process_snapshot=lambda pid: pid,
            display_verifier=lambda *_: True,
            activation_verifier=AsyncMock(),
            activation_preparer=AsyncMock(),
            lock_contract_verifier=lambda *_: True,
            service_verifier=AsyncMock(),
        )
        self.addAsyncCleanup(self.watcher.aclose)
        self.addAsyncCleanup(self.model.aclose)
        await self.watcher.start()
        self.context = await self.watcher.prepare_screen_test(timeout=0.2)
        assert self.watcher._user_path is not None
        self.user_path = self.watcher._user_path
        self.events.clear()

    def emergency(self):
        self.emergencies += 1
        self.state = AppLockState(6, False, False, True)

    def properties(
        self,
        changed,
        invalidated=None,
        *,
        interface=LOGIN + ".User",
        sender=":1.10",
        signature="sa{sv}as",
        path=None,
    ):
        return signal(
            sender,
            path or self.user_path,
            PROPERTIES,
            "PropertiesChanged",
            signature,
            [interface, changed, invalidated or []],
        )

    async def test_native_lock_idle_metadata_unlock_and_pin_keep_same_trial(self):
        self.desktop.lock_cycle = True
        self.assertTrue(await self.model.start_screen_test(self.watcher, 5))
        self.assertTrue(self.state.sealed_pin)
        self.assertTrue(
            self.model._trial is not None and self.model._trial.normal_receipt
        )
        self.watcher._system_signal(
            self.properties(IDLE, interface=SESSION, path=SESSION_PATH)
        )
        self.watcher._system_signal(self.properties(IDLE))
        self.assertEqual(self.watcher.screen_context, self.context)
        self.assertNotIn(SessionSecurityEvent.TRUST_LOST, self.events)
        self.desktop.screen_active = False
        self.desktop.serial += 1
        self.watcher._screen_signal(
            replace(
                signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [False]),
                serial=self.desktop.serial,
            )
        )
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(self.model.snapshot.sleep.state, CheckState.UNTESTED)
        self.state = AppLockState(7, True, True, False)
        self.model.app_state_changed()
        self.assertEqual(self.model.snapshot.screen.state, CheckState.CONFIRMED)

    async def test_only_user_idle_changed_and_invalidated_are_harmless(self):
        for changed, invalidated in [
            (IDLE, []),
            ({"IdleHint": False}, []),
            ({}, list(IDLE)),
            ({"IdleHint": False}, ["IdleSinceHint"]),
        ]:
            with self.subTest(changed=changed, invalidated=invalidated):
                self.watcher._system_signal(self.properties(changed, invalidated))
                self.assertEqual(self.watcher.screen_context, self.context)
        self.assertEqual(self.events, [])

    async def test_display_sessions_identity_unknown_or_mixed_changes_still_revoke(
        self,
    ):
        for changed in [
            {"Display": ["other", "/other"]},
            {"Sessions": []},
            {"UID": 1002},
            {"Unknown": True},
            {**IDLE, "Display": []},
        ]:
            with self.subTest(changed=changed):
                self.events.clear()
                self.watcher._system_signal(self.properties(changed))
                self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)
                await self.watcher._recheck_screen()

    async def test_invalidated_display_sessions_unknown_still_revoke(self):
        for names in [["Display"], ["Sessions"], ["Unknown"], ["IdleHint", "Sessions"]]:
            with self.subTest(names=names):
                self.events.clear()
                self.watcher._system_signal(self.properties({}, names))
                self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)
                await self.watcher._recheck_screen()

    async def test_malformed_idle_values_do_not_get_exception(self):
        for changed in [
            {"IdleHint": 1},
            {"IdleHint": "true"},
            {"IdleSinceHint": True},
            {"IdleSinceHint": -1},
            {"IdleSinceHintMonotonic": 2**64},
            {"IdleSinceHint": "123"},
        ]:
            with self.subTest(changed=changed):
                self.events.clear()
                self.watcher._system_signal(self.properties(changed))
                self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)
                await self.watcher._recheck_screen()

    async def test_wrong_sender_or_signature_does_not_enter_trusted_property_path(self):
        for message in [
            self.properties(IDLE, sender=":1.99"),
            self.properties(IDLE, signature="s"),
        ]:
            self.watcher._system_signal(message)
        self.assertEqual(self.watcher.screen_context, self.context)
        self.assertEqual(self.events, [])

    async def test_malformed_changed_invalidations_and_wrong_inner_interface_revoke(
        self,
    ):
        for changed, invalidated, interface in [
            ([("IdleHint", True)], [], LOGIN + ".User"),
            ({}, "IdleHint", LOGIN + ".User"),
            ({}, ["IdleHint", "IdleHint"], LOGIN + ".User"),
            ({"IdleHint": True}, ["IdleHint"], LOGIN + ".User"),
            (IDLE, [], SESSION),
            ({}, [], LOGIN + ".User"),
        ]:
            with self.subTest(
                changed=changed, invalidated=invalidated, interface=interface
            ):
                self.events.clear()
                self.watcher._system_signal(
                    self.properties(changed, invalidated, interface=interface)
                )
                self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)
                await self.watcher._recheck_screen()

    async def test_idle_exception_does_not_apply_to_another_monitored_session(self):
        other = LOGIN + "/session/other"
        self.watcher._desktop_paths.add(other)
        self.watcher._system_signal(
            self.properties(IDLE, interface=SESSION, path=other)
        )
        self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)


if __name__ == "__main__":
    unittest.main()
