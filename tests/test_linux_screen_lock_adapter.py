"""Actual screen request/readback use trusted API and never synthesize revocation."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.linux_dbus import DBusReply  # noqa: E402
from platform_security.linux_session import (  # noqa: E402
    LinuxSessionWatcher,
    SessionSecurityEvent,
)
from platform_security.local_protection import (  # noqa: E402
    ObserverContext,
    ScreenLockUnavailable,
)
from tests.test_linux_session import (  # noqa: E402
    LOGIN_PATH,
    MANAGER,
    SCREEN,
    SCREEN_PATH,
    FakeBus,
    signal,
)


class LockBus(FakeBus):
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
        if member == "Lock":
            self.calls.append((destination, path, interface, member, signature, body))
            sender = self.reply_sender or self.owner
            assert sender is not None
            return DBusReply(sender, "", [])
        return await super().call(
            destination, path, interface, member, signature, body, timeout=timeout
        )


class LinuxScreenAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.system, self.desktop = FakeBus(system=True), LockBus(system=False)
        self.events = []
        self.observations = []
        self.statuses = []
        self.watcher = LinuxSessionWatcher(
            self.events.append,
            on_status=self.statuses.append,
            on_observation=self.observations.append,
            bus_factory=lambda: (self.system, self.desktop),
            process_verifier=lambda *_args: True,
            process_snapshot=lambda pid: pid,
            display_verifier=lambda *_args: True,
            activation_verifier=AsyncMock(),
            service_verifier=AsyncMock(),
        )
        self.addAsyncCleanup(self.watcher.aclose)
        await self.watcher.start()
        context = self.watcher.screen_context
        assert context is not None
        self.context: ObserverContext = context
        self.events.clear()

    async def test_request_uses_exact_cinnamon_method_and_never_prelocks_app(self):
        await self.watcher.request_screen_lock(self.context)
        self.assertIn(
            (":1.20", SCREEN_PATH, SCREEN, "Lock", "s", [""]), self.desktop.calls
        )
        self.assertEqual(self.events, [])

    async def test_actual_state_requires_locked_hint_and_screensaver_active(self):
        self.assertIs(
            (await self.watcher.read_screen_state(self.context)).locked, False
        )
        self.desktop.screen_active = True
        self.assertIsNone((await self.watcher.read_screen_state(self.context)).locked)
        self.system.properties["LockedHint"] = True
        self.assertIs((await self.watcher.read_screen_state(self.context)).locked, True)
        self.assertEqual(
            self.events, [], "readback must not synthesize an ordinary lock handler"
        )
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SCREEN_LOCK])

    async def test_lock_refused_when_already_locked_or_ambiguous(self):
        self.desktop.screen_active = True
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.request_screen_lock(self.context)
        self.assertFalse(any(c[3] == "Lock" for c in self.desktop.calls))

    async def test_cinnamon2d_is_valid_real_desktop_alias(self):
        self.system.properties["Desktop"] = "cinnamon2d"
        self.watcher._session_binding["Desktop"] = "cinnamon2d"
        self.assertIs(
            (await self.watcher.read_screen_state(self.context)).locked, False
        )

    async def test_source_owner_or_desktop_changed_cannot_confirm_old_context(self):
        self.desktop.owner = ":1.77"
        with self.assertRaises(RuntimeError):
            await self.watcher.read_screen_state(self.context)
        self.desktop.owner = ":1.20"
        self.system.properties["Desktop"] = "other"
        with self.assertRaises(ScreenLockUnavailable):
            await self.watcher.read_screen_state(self.context)

    async def test_callback_runs_on_context_change_even_same_status_booleans(self):
        before = len(self.statuses)
        self.watcher._screen_generation += 1
        status = self.watcher.status
        self.watcher._status(status.state, status.code, system=True, screen=True)
        self.assertEqual(len(self.statuses), before + 1)
        self.assertNotEqual(self.watcher.screen_context, self.context)

    async def test_sleep_pair_requires_actual_kernel_clock_gap(self):
        for end, expected in [(1.0, False), (1.2, True)]:
            with patch.object(self.watcher, "_sleep_gap", side_effect=[1.0, end]):
                self.watcher._system_signal(
                    replace(
                        signal(
                            ":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]
                        ),
                        serial=100,
                    )
                )
                self.watcher._system_signal(
                    replace(
                        signal(
                            ":1.10",
                            LOGIN_PATH,
                            MANAGER,
                            "PrepareForSleep",
                            "b",
                            [False],
                        ),
                        serial=101,
                    )
                )
            item = self.observations[-1]
            self.assertEqual(item.kind, "sleep_resume")
            self.assertEqual(item.actual_suspend, expected)
            self.assertEqual(item.context, self.watcher.sleep_context)

    async def test_inactive_signal_is_observation_only_and_never_unlocks_app(self):
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [False])
        )
        self.assertEqual(self.events, [])
        self.assertEqual(self.observations[-1].kind, "screen_inactive")

    async def test_wrong_sender_signature_and_integer_false_do_not_emit_resume(self):
        for sender, signature, body in [
            (":1.99", "b", [False]),
            (":1.10", "s", [False]),
            (":1.10", "b", [0]),
        ]:
            self.watcher._system_signal(
                signal(sender, LOGIN_PATH, MANAGER, "PrepareForSleep", signature, body)
            )
        self.assertEqual(self.observations, [])


if __name__ == "__main__":
    unittest.main()
