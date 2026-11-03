"""Наблюдение за Linux-сессией проверяется на отдельном D-Bus double."""

from __future__ import annotations

import asyncio
import os
import socket
import stat
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import platform_security.linux_session as session_module  # noqa: E402
from platform_security.linux_dbus import DBusError, DBusReply  # noqa: E402
from platform_security.linux_session import (  # noqa: E402
    LinuxSessionWatcher,
    SessionSecurityEvent,
    SessionWatchState,
    trusted_session_process,
)

DBUS = "org.freedesktop.DBus"
DBUS_PATH = "/org/freedesktop/DBus"
LOGIN = "org.freedesktop.login1"
LOGIN_PATH = "/org/freedesktop/login1"
SESSION_PATH = LOGIN_PATH + "/session/test"
SESSION = LOGIN + ".Session"
MANAGER = LOGIN + ".Manager"
PROPERTIES = "org.freedesktop.DBus.Properties"
SCREEN = "org.cinnamon.ScreenSaver"
SCREEN_PATH = "/org/cinnamon/ScreenSaver"


class FakeBus:
    def __init__(self, *, system: bool) -> None:
        self.system = system
        self.owner: str | None = ":1.10" if system else ":1.20"
        self.screen_active = False
        self.calls: list[tuple] = []
        self.matches: list[str] = []
        self.closed = 0
        self.signals: asyncio.Queue[DBusReply | Exception] = asyncio.Queue()
        self.properties = {
            "User": [os.getuid(), "/users/test"],
            "Id": "test",
            "Remote": False,
            "Type": "x11",
            "Class": "user",
            "Active": True,
            "LockedHint": False,
            "Display": ":0",
            "Desktop": "cinnamon",
            "Seat": ["seat0", "/org/freedesktop/login1/seat/seat0"],
        }
        self.session_for_screen = SESSION_PATH
        self.screen_pid_error: Exception | None = None
        self.user_properties = {
            "Display": ["test", SESSION_PATH],
            "Sessions": [["test", SESSION_PATH]],
        }
        self.session_properties: dict[str, dict] = {}
        self.reply_sender: str | None = None
        self.daemon_sender = DBUS
        self.has_owner_override: list | None = None

    async def call(
        self,
        destination: str,
        path: str,
        interface: str,
        member: str,
        signature: str = "",
        body: list | None = None,
        *,
        timeout: float = 10,
    ) -> DBusReply:
        self.calls.append((destination, path, interface, member, signature, body))
        if destination == DBUS:
            if member == "NameHasOwner":
                result = (
                    self.has_owner_override
                    if self.has_owner_override is not None
                    else [self.owner is not None]
                )
                return DBusReply(self.daemon_sender, "b", result)
            if member == "GetNameOwner":
                return DBusReply(self.daemon_sender, "s", [self.owner])
            if member == "GetConnectionUnixUser":
                return DBusReply(
                    self.daemon_sender, "u", [0 if self.system else os.getuid()]
                )
            if member == "GetConnectionUnixProcessID":
                return DBusReply(self.daemon_sender, "u", [123 if self.system else 456])
        sender = self.reply_sender or self.owner or ":1.999"
        if member == "GetSessionByPID":
            if body != [os.getpid()] and self.screen_pid_error is not None:
                raise self.screen_pid_error
            path = SESSION_PATH if body == [os.getpid()] else self.session_for_screen
            return DBusReply(sender, "o", [path])
        if member == "GetUser":
            return DBusReply(sender, "o", ["/org/freedesktop/login1/user/_1000"])
        if member == "GetAll":
            properties = (
                self.user_properties
                if body == [LOGIN + ".User"]
                else self.session_properties.get(path, self.properties)
            )
            return DBusReply(sender, "a{sv}", [properties])
        if member == "GetActive":
            return DBusReply(sender, "b", [self.screen_active])
        raise AssertionError(member)

    async def add_match(self, rule: str) -> None:
        self.matches.append(rule)

    async def next_signal(self, *, timeout: float = 1) -> DBusReply | None:
        # Ровно такой timeout использует настоящий transport.
        value = await asyncio.wait_for(self.signals.get(), min(timeout, 0.02))
        if isinstance(value, Exception):
            raise value
        return value

    async def aclose(self) -> None:
        self.closed += 1


def signal(sender, path, interface, member, signature="", body=None) -> DBusReply:
    return DBusReply(sender, signature, body or [], path, interface, member)


class LinuxSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.system, self.desktop = FakeBus(system=True), FakeBus(system=False)
        self.events: list[SessionSecurityEvent] = []
        self.statuses = []
        self.identities: list[tuple] = []

        def verify(role, pid, uid):
            self.identities.append((role, pid, uid))
            return True

        async def service_verify(_bus, name, owner, uid):
            self.assertEqual((name, owner, uid), (LOGIN, ":1.10", 0))

        self.activation_verifier = AsyncMock()
        self.watcher = LinuxSessionWatcher(
            self.events.append,
            on_status=self.statuses.append,
            bus_factory=lambda: (self.system, self.desktop),
            process_verifier=verify,
            process_snapshot=lambda pid: pid,
            display_verifier=lambda _display, _uid: True,
            activation_verifier=self.activation_verifier,
            service_verifier=service_verify,
        )
        self.addAsyncCleanup(self.watcher.aclose)

    async def wait_for(self, predicate) -> None:
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.001)
        self.fail("watcher did not consume synthetic event")

    async def emit(self, bus: FakeBus, value: DBusReply) -> None:
        bus.signals.put_nowait(value)
        await self.wait_for(lambda: bus.signals.empty())
        await asyncio.sleep(0)

    async def test_legitimate_per_user_activation_without_session_scope_is_ready(self):
        self.system.screen_pid_error = DBusError(
            "org.freedesktop.login1.NoSessionForPID", sender=":1.10"
        )
        await self.watcher.start()
        self.assertEqual(self.watcher.status.state, SessionWatchState.READY)
        self.assertTrue(self.watcher.status.system_events)
        self.assertTrue(self.watcher.status.screen_events)
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SCREEN_LOCK])

    async def test_unsupported_screen_retains_trusted_suspend_monitoring(self):
        self.watcher._process_verifier = lambda role, _pid, _uid: role == "logind"
        await self.watcher.start()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.events.clear()
        await self.emit(
            self.system,
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])
        self.watcher._system_signal(
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False])
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])

    async def use_per_user(self):
        self.system.screen_pid_error = DBusError(
            LOGIN + ".NoSessionForPID", sender=":1.10"
        )
        await self.watcher.start()

    async def test_no_session_fallback_accepts_only_exact_error_from_pinned_logind(
        self,
    ):
        for error in (
            DBusError(LOGIN + ".NoSessionForPID"),
            DBusError(LOGIN + ".NoSessionForPID", sender=":1.999"),
            DBusError("org.freedesktop.DBus.Error.AccessDenied", sender=":1.10"),
            RuntimeError(LOGIN + ".NoSessionForPID"),
            TimeoutError("transport unavailable"),
        ):
            with self.subTest(kind=type(error), sender=getattr(error, "sender", "")):
                self.system.screen_pid_error = error
                await self.watcher.start()
                self.assertFalse(self.watcher.status.screen_events)
                self.assertTrue(self.watcher.status.system_events)
                self.activation_verifier.assert_not_awaited()
                # A fresh watcher lifetime is required, not a modified active one.
                await self.watcher.aclose()
                await self.asyncSetUp()

    async def test_per_user_requires_loaded_activation_origin(self):
        self.watcher._activation_verifier = AsyncMock(
            side_effect=RuntimeError("user override or unknown process")
        )
        await self.use_per_user()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])

    async def test_per_user_rejects_user_display_for_another_desktop(self):
        self.system.user_properties["Display"] = [
            "other",
            LOGIN_PATH + "/session/other",
        ]
        await self.use_per_user()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)

    async def test_per_user_rejects_second_inactive_local_graphical_session(self):
        path = LOGIN_PATH + "/session/other"
        self.system.user_properties["Sessions"].append(["other", path])
        self.system.session_properties[path] = {
            **self.system.properties,
            "Id": "other",
            "Active": False,
            "Display": ":1",
        }
        await self.use_per_user()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)

    async def test_runtime_extra_display_without_logind_event_seals_and_recovers(self):
        available = True
        self.watcher._display_poll_interval = 0.01
        self.watcher._display_verifier = lambda _display, _uid: available
        await self.use_per_user()
        self.assertEqual(self.watcher.status.state, SessionWatchState.READY)
        available = False
        await self.wait_for(lambda: not self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)
        before = len(self.events)
        available = True
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.READY
        )
        self.assertTrue(self.watcher.status.system_events)
        self.assertEqual(len(self.events), before)
        self.assertGreaterEqual(self.activation_verifier.await_count, 2)

    async def test_runtime_display_check_runs_even_with_busy_signal_queue(self):
        available = True
        self.watcher._display_poll_interval = 0.005
        self.watcher._display_verifier = lambda _display, _uid: available
        await self.use_per_user()
        queued_at_loss = []
        original_status = self.watcher._on_status

        def observe_status(status):
            if status.code == "display_namespace_changed":
                queued_at_loss.append(self.system.signals.qsize())
            if original_status is not None:
                original_status(status)

        self.watcher._on_status = observe_status
        for _ in range(10000):
            self.system.signals.put_nowait(
                signal(":1.999", "/ignored", "ignored", "ignored")
            )
        available = False
        await self.wait_for(lambda: not self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.assertTrue(queued_at_loss)
        self.assertGreater(queued_at_loss[0], 0)
        self.assertIn(SessionSecurityEvent.TRUST_LOST, self.events)

    async def test_all_current_session_identity_invalidations_fail_closed(self):
        for name in ("Id", "Remote", "Type", "Class", "User"):
            with self.subTest(name=name):
                await self.watcher.start()
                self.watcher._system_signal(
                    signal(
                        ":1.10",
                        SESSION_PATH,
                        PROPERTIES,
                        "PropertiesChanged",
                        "sa{sv}as",
                        [SESSION, {}, [name]],
                    )
                )
                self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
                self.assertFalse(self.watcher.status.screen_events)
                self.assertFalse(self.watcher.status.system_events)
                self.assertEqual(self.watcher.status.code, "session_identity_changed")
                await self.watcher.aclose()
                await self.asyncSetUp()

    async def test_first_per_user_walk_observes_previously_read_tty_becoming_graphical(
        self,
    ):
        tty = LOGIN_PATH + "/session/tty"
        self.system.user_properties["Sessions"] = [["tty", tty], ["test", SESSION_PATH]]
        self.system.session_properties[tty] = {
            **self.system.properties,
            "Id": "tty",
            "Type": "tty",
            "Remote": False,
            "Display": "",
            "Seat": ["", "/"],
        }
        original = self.system.call
        transitioned = False
        registered_before_transition = False

        async def race(*args, **kwargs):
            nonlocal transitioned, registered_before_transition
            reply = await original(*args, **kwargs)
            if (
                args[1] == SESSION_PATH
                and args[3] == "GetAll"
                and args[5] == [SESSION]
                and any(call[3] == "GetUser" for call in self.system.calls)
                and not transitioned
            ):
                transitioned = True
                registered_before_transition = tty in self.watcher._desktop_paths
                self.system.session_properties[tty]["Type"] = "x11"
                self.system.session_properties[tty]["Display"] = ":1"
                self.watcher._system_signal(
                    signal(
                        ":1.10",
                        tty,
                        PROPERTIES,
                        "PropertiesChanged",
                        "sa{sv}as",
                        [SESSION, {"Type": "x11", "Display": ":1"}, []],
                    )
                )
            return reply

        self.system.call = race
        await self.use_per_user()
        self.assertTrue(transitioned)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(
            any(item.state == SessionWatchState.READY for item in self.statuses)
        )
        self.assertTrue(registered_before_transition)

    async def test_first_walk_rereads_all_sessions_even_without_change_signal(self):
        tty = LOGIN_PATH + "/session/tty"
        self.system.user_properties["Sessions"] = [["tty", tty], ["test", SESSION_PATH]]
        self.system.session_properties[tty] = {
            **self.system.properties,
            "Id": "tty",
            "Type": "tty",
            "Remote": False,
            "Display": "",
            "Seat": ["", "/"],
        }
        original = self.system.call
        transitioned = False

        async def race(*args, **kwargs):
            nonlocal transitioned
            reply = await original(*args, **kwargs)
            if (
                args[1] == SESSION_PATH
                and args[3] == "GetAll"
                and args[5] == [SESSION]
                and any(call[3] == "GetUser" for call in self.system.calls)
                and not transitioned
            ):
                transitioned = True
                self.system.session_properties[tty]["Type"] = "x11"
                self.system.session_properties[tty]["Display"] = ":1"
            return reply

        self.system.call = race
        await self.use_per_user()
        self.assertTrue(transitioned)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(
            any(item.state == SessionWatchState.READY for item in self.statuses)
        )

    async def test_per_user_rejects_extra_display_even_with_one_logind_session(self):
        self.watcher._display_verifier = lambda _display, _uid: False
        await self.use_per_user()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)

    async def test_per_user_allows_remote_tty_without_claiming_other_graphical_desktop(
        self,
    ):
        path = LOGIN_PATH + "/session/ssh"
        self.system.user_properties["Sessions"].append(["ssh", path])
        self.system.session_properties[path] = {
            **self.system.properties,
            "Id": "ssh",
            "Remote": True,
            "Type": "tty",
            "Display": "",
            "Seat": ["", "/"],
        }
        await self.use_per_user()
        self.assertEqual(self.watcher.status.code, "watching_per_user")

    async def test_per_user_rejects_missing_unsupported_or_multiscreen_desktop(self):
        for changed in (
            {"Display": ":0.1"},
            {"Display": "remote:0"},
            {"Display": ""},
            {"Desktop": "unknown"},
            {"Seat": ["", "/"]},
            {"Active": False},
        ):
            with self.subTest(changed=changed):
                self.system.properties.update(changed)
                await self.use_per_user()
                self.assertFalse(self.watcher.status.screen_events)
                await self.watcher.aclose()
                await self.asyncSetUp()

    async def test_owner_changes_during_get_active_do_not_publish_ready(self):
        original = self.desktop.call

        async def changed(*args, **kwargs):
            result = await original(*args, **kwargs)
            if args[3] == "GetActive":
                self.desktop.owner = ":1.21"
            return result

        self.desktop.call = changed
        await self.watcher.start()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(
            any(item.state == SessionWatchState.READY for item in self.statuses)
        )

    async def test_pid_reuse_after_async_verification_is_rejected(self):
        versions = {123: 1, 456: 1}
        self.watcher._process_snapshot = lambda pid: versions[pid]
        original = self.desktop.call

        async def replaced(*args, **kwargs):
            result = await original(*args, **kwargs)
            if args[3] == "GetActive":
                versions[456] += 1
            return result

        self.desktop.call = replaced
        await self.watcher.start()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)

    async def test_process_reuse_during_synchronous_entrypoint_verification_is_rejected(
        self,
    ):
        versions = {123: 1, 456: 1}
        self.watcher._process_snapshot = lambda pid: versions[pid]

        def changed(role, pid, uid):
            if role == "cinnamon":
                versions[pid] += 1
            return True

        self.watcher._process_verifier = changed
        await self.watcher.start()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)

    async def test_screen_daemon_uid_and_positive_pid_are_checked_independently(self):
        original = self.desktop.call
        for member, value in (
            ("GetConnectionUnixUser", os.getuid() + 1),
            ("GetConnectionUnixProcessID", 0),
        ):

            async def wrong(*args, **kwargs):
                if args[3] == member:
                    return DBusReply(DBUS, "u", [value])
                return await original(*args, **kwargs)

            self.desktop.call = wrong
            await self.watcher.start()
            self.assertFalse(self.watcher.status.screen_events)
            self.assertTrue(self.watcher.status.system_events)
            await self.watcher.aclose()
            await self.asyncSetUp()
            original = self.desktop.call

    async def test_exited_process_during_async_verification_is_rejected(self):
        exited = False

        def snapshot(pid):
            if pid == 456 and exited:
                raise ProcessLookupError("gone")
            return pid

        self.watcher._process_snapshot = snapshot
        original = self.desktop.call

        async def died(*args, **kwargs):
            nonlocal exited
            result = await original(*args, **kwargs)
            if args[3] == "GetActive":
                exited = True
            return result

        self.desktop.call = died
        await self.watcher.start()
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)

    async def test_late_signal_from_old_owner_and_duplicate_unlock_never_open(self):
        await self.watcher.start()
        self.desktop.owner = ":1.21"
        await self.emit(
            self.desktop,
            signal(
                DBUS,
                DBUS_PATH,
                DBUS,
                "NameOwnerChanged",
                "sss",
                [SCREEN, ":1.20", ":1.21"],
            ),
        )
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.READY
        )
        self.events.clear()
        for owner, active in ((":1.20", True), (":1.21", False), (":1.21", False)):
            self.watcher._screen_signal(
                signal(owner, SCREEN_PATH, SCREEN, "ActiveChanged", "b", [active])
            )
        self.assertEqual(self.events, [])
        for _ in range(2):
            self.watcher._screen_signal(
                signal(":1.21", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
            )
        self.assertEqual(self.events, [SessionSecurityEvent.SCREEN_LOCK] * 2)

    async def test_screen_disconnect_retains_live_system_consumer_and_no_hidden_ready(
        self,
    ):
        await self.watcher.start()
        self.desktop.signals.put_nowait(RuntimeError("disconnected"))
        await self.wait_for(
            lambda: self.watcher.status.code == "screen_bus_disconnected"
        )
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertEqual(self.desktop.closed, 1)
        self.assertEqual(self.system.closed, 0)
        self.events.clear()
        await self.emit(
            self.system,
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])
        self.assertEqual(self.watcher.status.state, SessionWatchState.DISCONNECTED)

    async def test_system_owner_recovery_restores_partial_status_after_screen_disconnect(
        self,
    ):
        await self.watcher.start()
        self.desktop.signals.put_nowait(RuntimeError("disconnected"))
        await self.wait_for(
            lambda: self.watcher.status.code == "screen_bus_disconnected"
        )
        self.system.owner = ":1.11"
        self.watcher._service_verifier = AsyncMock()
        await self.emit(
            self.system,
            signal(
                DBUS,
                DBUS_PATH,
                DBUS,
                "NameOwnerChanged",
                "sss",
                [LOGIN, ":1.10", ":1.11"],
            ),
        )
        await self.wait_for(
            lambda: self.watcher.status.code == "screen_bus_unavailable"
        )
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.events.clear()
        await self.emit(
            self.system,
            signal(":1.11", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])
        self.assertEqual(self.desktop.closed, 1)

    async def test_missing_session_transport_retains_system_sleep_subscription(self):
        self.watcher._bus_factory = lambda: (self.system, None)
        await self.watcher.start()
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.events.clear()
        await self.emit(
            self.system,
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])

    async def test_screen_add_match_failure_retains_verified_system_and_closes_screen(
        self,
    ):
        self.desktop.add_match = AsyncMock(side_effect=RuntimeError("no match"))
        await self.watcher.start()
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertEqual(self.desktop.closed, 1)
        self.assertEqual(len(self.watcher._tasks), 1)
        self.events.clear()
        await self.emit(
            self.system,
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SLEEP])

    async def test_topology_change_seals_before_async_check_without_delaying_suspend(
        self,
    ):
        await self.use_per_user()
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(*_args):
            started.set()
            await release.wait()

        self.watcher._activation_verifier = blocked
        await self.emit(
            self.system,
            signal(
                ":1.10",
                LOGIN_PATH,
                MANAGER,
                "SessionNew",
                "so",
                ["new", LOGIN_PATH + "/session/new"],
            ),
        )
        await asyncio.wait_for(started.wait(), 1)
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        await self.emit(
            self.system,
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True]),
        )
        self.assertEqual(self.events[-1], SessionSecurityEvent.SLEEP)
        release.set()
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.READY
        )
        self.assertEqual(self.events[-1], SessionSecurityEvent.SLEEP)

    async def test_user_display_change_revalidates_without_preserving_old_owner(self):
        await self.use_per_user()
        self.system.user_properties["Display"] = [
            "other",
            LOGIN_PATH + "/session/other",
        ]
        await self.emit(
            self.system,
            signal(
                ":1.10",
                "/org/freedesktop/login1/user/_1000",
                PROPERTIES,
                "PropertiesChanged",
                "sa{sv}as",
                [
                    LOGIN + ".User",
                    {"Display": self.system.user_properties["Display"]},
                    [],
                ],
            ),
        )
        await self.wait_for(lambda: self.watcher.status.code == "cinnamon_untrusted")
        self.assertFalse(self.watcher.status.screen_events)
        self.assertTrue(self.watcher.status.system_events)
        before = len(self.events)
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        )
        self.assertEqual(len(self.events), before)

    async def test_pending_verifier_cannot_replace_real_disconnect_status(self):
        await self.use_per_user()
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(*_args):
            started.set()
            await release.wait()
            raise RuntimeError("late failed verifier")

        self.watcher._activation_verifier = blocked
        await self.emit(
            self.system,
            signal(
                ":1.10",
                LOGIN_PATH,
                MANAGER,
                "SessionNew",
                "so",
                ["new", LOGIN_PATH + "/session/new"],
            ),
        )
        await asyncio.wait_for(started.wait(), 1)
        self.desktop.signals.put_nowait(RuntimeError("lost"))
        await self.wait_for(
            lambda: self.watcher.status.code == "screen_bus_disconnected"
        )
        release.set()
        await self.wait_for(
            lambda: (
                self.watcher._refresh_task is not None
                and self.watcher._refresh_task.done()
            )
        )
        self.assertEqual(self.watcher.status.code, "screen_bus_disconnected")
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)

    async def test_cancelled_startup_closes_both_buses_and_leaves_no_tasks(self):
        started, release = asyncio.Event(), asyncio.Event()
        original = self.system.call

        async def blocked(*args, **kwargs):
            started.set()
            await release.wait()
            return await original(*args, **kwargs)

        self.system.call = blocked
        startup = asyncio.create_task(self.watcher.start())
        await asyncio.wait_for(started.wait(), 1)
        startup.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await startup
        self.assertEqual(self.system.closed, 1)
        self.assertEqual(self.desktop.closed, 1)
        self.assertFalse(self.watcher._tasks)
        self.assertIsNone(self.watcher._refresh_task)
        self.assertFalse(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])

    async def test_pending_screen_worker_is_cancelled_and_buses_freed_at_close(self):
        await self.use_per_user()
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(*_args):
            started.set()
            await release.wait()

        self.watcher._activation_verifier = blocked
        await self.emit(
            self.system,
            signal(
                ":1.10",
                LOGIN_PATH,
                MANAGER,
                "SessionNew",
                "so",
                ["new", LOGIN_PATH + "/session/new"],
            ),
        )
        await asyncio.wait_for(started.wait(), 1)
        await self.watcher.aclose()
        self.assertIsNone(self.watcher._refresh_task)
        self.assertEqual(self.system.closed, 1)
        self.assertEqual(self.desktop.closed, 1)
        self.assertEqual(self.watcher.status.state, SessionWatchState.CLOSED)

    async def test_native_transport_timeout_is_not_a_disconnect(self):
        await self.watcher.start()
        await asyncio.sleep(0.06)
        self.assertEqual(self.watcher.status.state, SessionWatchState.READY)
        self.assertEqual(self.events, [])

    async def test_subscriptions_are_once_and_cleanup_is_idempotent(self):
        first, second = await asyncio.gather(self.watcher.start(), self.watcher.start())
        self.assertEqual(first, second)
        self.assertEqual(len(self.system.matches), 4)
        self.assertEqual(len(self.desktop.matches), 2)
        self.assertGreaterEqual(len(self.identities), 3)
        await self.watcher.aclose()
        await self.watcher.aclose()
        self.assertEqual(self.system.closed, 1)
        self.assertEqual(self.desktop.closed, 1)
        self.assertEqual(self.watcher.status.state, SessionWatchState.CLOSED)

    async def test_cinnamon_lock_revokes_synchronously_and_unlock_does_not_open(self):
        await self.watcher.start()
        locked = signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        self.watcher._screen_signal(locked)
        self.assertEqual(self.events, [SessionSecurityEvent.SCREEN_LOCK])
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [False])
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SCREEN_LOCK])

    async def test_forged_cinnamon_signal_and_malformed_true_are_ignored(self):
        await self.watcher.start()
        for value in (
            signal(":1.999", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True]),
            signal(":1.20", "/wrong", SCREEN, "ActiveChanged", "b", [True]),
            signal(":1.20", SCREEN_PATH, "other", "ActiveChanged", "b", [True]),
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "s", [True]),
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [1]),
        ):
            self.watcher._screen_signal(value)
        self.assertEqual(self.events, [])

    async def test_sleep_shutdown_and_session_lock_are_synchronous(self):
        await self.watcher.start()
        for member in ("PrepareForSleep", "PrepareForShutdown"):
            self.watcher._system_signal(
                signal(":1.10", LOGIN_PATH, MANAGER, member, "b", [True])
            )
        self.watcher._system_signal(signal(":1.10", SESSION_PATH, SESSION, "Lock"))
        self.assertEqual(
            self.events,
            [
                SessionSecurityEvent.SLEEP,
                SessionSecurityEvent.SHUTDOWN,
                SessionSecurityEvent.SCREEN_LOCK,
            ],
        )

    async def test_system_resume_and_unlock_never_unlock_application(self):
        await self.watcher.start()
        for value in (
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [False]),
            signal(":1.10", SESSION_PATH, SESSION, "Unlock"),
            signal(
                ":1.10",
                SESSION_PATH,
                PROPERTIES,
                "PropertiesChanged",
                "sa{sv}as",
                [SESSION, {"Active": True, "LockedHint": False}, []],
            ),
        ):
            self.watcher._system_signal(value)
        self.assertEqual(self.events, [])

    async def test_focus_minimization_and_prompt_are_not_device_lock(self):
        await self.watcher.start()
        for member in ("FocusOut", "Hidden", "Paused", "AuthenticationAgent"):
            self.watcher._screen_signal(
                signal(":1.20", SCREEN_PATH, SCREEN, member, "b", [True])
            )
            self.watcher._system_signal(
                signal(":1.10", SESSION_PATH, SESSION, member, "b", [True])
            )
        self.assertEqual(self.events, [])

    async def test_logind_event_requires_pinned_unique_owner_path_and_interface(self):
        await self.watcher.start()
        for owner, path, interface in (
            (":1.777", LOGIN_PATH, MANAGER),
            (LOGIN, LOGIN_PATH, MANAGER),
            (":1.10", "/wrong", MANAGER),
            (":1.10", LOGIN_PATH, "untrusted"),
        ):
            self.watcher._system_signal(
                signal(owner, path, interface, "PrepareForSleep", "b", [True])
            )
        self.assertEqual(self.events, [])

    async def test_current_session_properties_revoke_but_other_session_does_not(self):
        await self.watcher.start()
        for changes, expected in (
            ({"LockedHint": True}, SessionSecurityEvent.SCREEN_LOCK),
            ({"Active": False}, SessionSecurityEvent.SESSION_CHANGE),
            ({"State": "closing"}, SessionSecurityEvent.SESSION_CHANGE),
        ):
            message = signal(
                ":1.10",
                SESSION_PATH,
                PROPERTIES,
                "PropertiesChanged",
                "sa{sv}as",
                [SESSION, changes, []],
            )
            self.watcher._system_signal(message)
            self.assertEqual(self.events[-1], expected)
        before = list(self.events)
        self.watcher._system_signal(signal(":1.10", "/session/other", SESSION, "Lock"))
        self.assertEqual(self.events, before)

    async def test_invalidated_protected_properties_revoke(self):
        await self.watcher.start()
        self.watcher._system_signal(
            signal(
                ":1.10",
                SESSION_PATH,
                PROPERTIES,
                "PropertiesChanged",
                "sa{sv}as",
                [SESSION, {}, ["LockedHint"]],
            )
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])

    async def test_starting_locked_or_inactive_never_opens_application(self):
        self.system.properties["Active"] = False
        self.system.properties["LockedHint"] = True
        self.desktop.screen_active = True
        await self.watcher.start()
        self.assertIn(SessionSecurityEvent.SESSION_CHANGE, self.events)
        self.assertIn(SessionSecurityEvent.SCREEN_LOCK, self.events)

    async def test_cinnamon_transient_absence_is_explicit_partial_status(self):
        self.desktop.owner = None
        await self.watcher.start()
        self.assertEqual(
            self.watcher.status.state, SessionWatchState.WAITING_SCREEN_SERVICE
        )
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertFalse(any("StartService" in call for call in self.desktop.calls))

    async def test_owner_loss_seals_before_waiting_and_trusted_replacement_rearms(self):
        await self.watcher.start()
        self.desktop.owner = None
        await self.emit(
            self.desktop,
            signal(
                DBUS, DBUS_PATH, DBUS, "NameOwnerChanged", "sss", [SCREEN, ":1.20", ""]
            ),
        )
        await self.wait_for(
            lambda: (
                self.watcher.status.state == SessionWatchState.WAITING_SCREEN_SERVICE
            )
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.desktop.owner = ":1.21"
        self.desktop.screen_active = True
        await self.emit(
            self.desktop,
            signal(
                DBUS, DBUS_PATH, DBUS, "NameOwnerChanged", "sss", [SCREEN, "", ":1.21"]
            ),
        )
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.READY
        )
        self.assertEqual(self.events[-1], SessionSecurityEvent.SCREEN_LOCK)

    async def test_fake_bus_owner_change_is_ignored(self):
        await self.watcher.start()
        await self.emit(
            self.desktop,
            signal(
                ":1.999",
                DBUS_PATH,
                DBUS,
                "NameOwnerChanged",
                "sss",
                [SCREEN, ":1.20", ""],
            ),
        )
        self.assertEqual(self.events, [])
        self.assertEqual(self.watcher.status.state, SessionWatchState.READY)

    async def test_untrusted_screensaver_never_becomes_ready(self):
        self.watcher._process_verifier = lambda role, _pid, _uid: role == "logind"
        await self.watcher.start()
        self.assertEqual(self.watcher.status.state, SessionWatchState.UNAVAILABLE)
        self.assertTrue(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.watcher._screen_signal(
            signal(":1.20", SCREEN_PATH, SCREEN, "ActiveChanged", "b", [True])
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])

    async def test_untrusted_logind_fails_closed_and_closes_connections(self):
        self.watcher._process_verifier = lambda *_args: False
        await self.watcher.start()
        self.assertEqual(self.watcher.status.state, SessionWatchState.UNAVAILABLE)
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.assertEqual(self.system.closed, 1)
        self.assertEqual(self.desktop.closed, 1)

    async def test_screen_service_in_other_session_is_rejected(self):
        self.system.session_for_screen = LOGIN_PATH + "/session/other"
        await self.watcher.start()
        self.assertEqual(self.watcher.status.state, SessionWatchState.UNAVAILABLE)
        self.assertFalse(self.watcher.status.screen_events)

    async def test_logind_session_comes_from_pid_and_not_environment(self):
        with patch.dict(os.environ, {"XDG_SESSION_ID": "spoofed"}):
            await self.watcher.start()
        calls = [call for call in self.system.calls if call[3] == "GetSessionByPID"]
        self.assertIn([os.getpid()], [call[5] for call in calls])
        self.assertNotIn(["spoofed"], [call[5] for call in self.system.calls])

    async def test_remote_wayland_and_wrong_uid_are_explicitly_unsupported(self):
        for changes in (
            {"Remote": True},
            {"Type": "wayland"},
            {"Class": "greeter"},
            {"User": [os.getuid() + 1, "/other"]},
        ):
            with self.subTest(changes=changes):
                system, desktop = FakeBus(system=True), FakeBus(system=False)
                system.properties.update(changes)

                async def service_verify(*_args):
                    pass

                watcher = LinuxSessionWatcher(
                    self.events.append,
                    bus_factory=lambda: (system, desktop),
                    process_verifier=lambda *_args: True,
                    process_snapshot=lambda pid: pid,
                    display_verifier=lambda _display, _uid: True,
                    activation_verifier=AsyncMock(),
                    service_verifier=service_verify,
                )
                await watcher.start()
                self.assertEqual(watcher.status.state, SessionWatchState.UNAVAILABLE)
                await watcher.aclose()

    async def test_disconnect_seals_and_marks_automatic_protection_unavailable(self):
        await self.watcher.start()
        self.system.signals.put_nowait(RuntimeError("private transport details"))
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.DISCONNECTED
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.assertFalse(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)
        self.assertNotIn("private", self.watcher.status.code)

    async def test_session_removal_does_not_monitor_or_unlock_another_session(self):
        await self.watcher.start()
        self.watcher._system_signal(
            signal(
                ":1.10",
                LOGIN_PATH,
                MANAGER,
                "SessionRemoved",
                "so",
                ["test", SESSION_PATH],
            )
        )
        self.assertEqual(self.events, [SessionSecurityEvent.SESSION_CHANGE])
        self.assertEqual(self.watcher.status.code, "session_removed")
        self.watcher._system_signal(signal(":1.10", SESSION_PATH, SESSION, "Lock"))
        self.assertEqual(self.events, [SessionSecurityEvent.SESSION_CHANGE])

    async def test_nonboolean_daemon_has_owner_reply_is_rejected(self):
        self.system.has_owner_override = [1]
        await self.watcher.start()
        self.assertEqual(self.watcher.status.state, SessionWatchState.UNAVAILABLE)

    async def test_forged_daemon_reply_is_rejected(self):
        self.system.daemon_sender = ":1.999"
        await self.watcher.start()
        self.assertEqual(self.watcher.status.state, SessionWatchState.UNAVAILABLE)

    async def test_root_managed_service_attestation_is_mandatory(self):
        verify = AsyncMock(side_effect=RuntimeError("wrong MainPID"))
        self.watcher._service_verifier = verify
        await self.watcher.start()
        verify.assert_awaited_once_with(self.system, LOGIN, ":1.10", 0)
        self.assertEqual(self.watcher.status.state, SessionWatchState.UNAVAILABLE)
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])

    async def test_logind_replacement_is_rechecked_and_never_unlocks(self):
        await self.watcher.start()
        self.system.owner = ":1.11"
        self.watcher._service_verifier = AsyncMock()
        await self.emit(
            self.system,
            signal(
                DBUS,
                DBUS_PATH,
                DBUS,
                "NameOwnerChanged",
                "sss",
                [LOGIN, ":1.10", ":1.11"],
            ),
        )
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.READY
        )
        self.watcher._service_verifier.assert_awaited_with(
            self.system, LOGIN, ":1.11", 0
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.watcher._system_signal(
            signal(":1.10", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.watcher._system_signal(
            signal(":1.11", LOGIN_PATH, MANAGER, "PrepareForSleep", "b", [True])
        )
        self.assertEqual(self.events[-1], SessionSecurityEvent.SLEEP)

    async def test_owner_change_revokes_before_waiting_for_new_identity(self):
        await self.watcher.start()
        original = self.desktop.call
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(*args, **kwargs):
            if args[3] == "NameHasOwner":
                started.set()
                await release.wait()
            return await original(*args, **kwargs)

        self.desktop.call = blocked
        self.desktop.owner = ":1.21"
        self.desktop.signals.put_nowait(
            signal(
                DBUS,
                DBUS_PATH,
                DBUS,
                "NameOwnerChanged",
                "sss",
                [SCREEN, ":1.20", ":1.21"],
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.assertFalse(self.watcher.status.screen_events)
        release.set()
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.READY
        )

    async def test_disconnected_bus_cannot_be_rearmed_by_other_bus(self):
        await self.watcher.start()
        self.system.signals.put_nowait(RuntimeError("disconnected"))
        await self.wait_for(
            lambda: self.watcher.status.state == SessionWatchState.DISCONNECTED
        )
        self.desktop.signals.put_nowait(
            signal(
                DBUS, DBUS_PATH, DBUS, "NameOwnerChanged", "sss", [SCREEN, "", ":1.21"]
            )
        )
        await asyncio.sleep(0.03)
        self.assertEqual(self.watcher.status.state, SessionWatchState.DISCONNECTED)
        self.assertEqual(self.system.closed, 1)
        self.assertEqual(self.desktop.closed, 1)

    async def test_close_during_start_cannot_create_new_subscriptions(self):
        original = self.system.call
        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(*args, **kwargs):
            started.set()
            await release.wait()
            return await original(*args, **kwargs)

        self.system.call = blocked
        startup = asyncio.create_task(self.watcher.start())
        await asyncio.wait_for(started.wait(), 1)
        closing = asyncio.create_task(self.watcher.aclose())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(startup, closing)
        self.assertEqual(self.watcher.status.state, SessionWatchState.CLOSED)
        self.assertFalse(self.watcher._tasks)
        self.assertEqual(self.events, [])
        self.assertEqual(self.system.closed, 1)
        self.assertEqual(self.desktop.closed, 1)

    async def test_changed_session_identity_seals_and_disables_observation(self):
        await self.watcher.start()
        self.watcher._system_signal(
            signal(
                ":1.10",
                SESSION_PATH,
                PROPERTIES,
                "PropertiesChanged",
                "sa{sv}as",
                [SESSION, {"User": [os.getuid() + 1, "/other"]}, []],
            )
        )
        self.assertEqual(self.events, [SessionSecurityEvent.TRUST_LOST])
        self.assertEqual(self.watcher.status.code, "session_identity_changed")
        self.assertFalse(self.watcher.status.system_events)
        self.assertFalse(self.watcher.status.screen_events)

    async def test_production_process_validator_rejects_invalid_and_own_python(self):
        self.assertFalse(trusted_session_process("logind", -1, 0))
        self.assertFalse(trusted_session_process("unknown", os.getpid(), os.getuid()))
        self.assertFalse(trusted_session_process("cinnamon", os.getpid(), os.getuid()))


class ActivationBus:
    def __init__(self, *, system):
        self.system = system
        self.uid = os.getuid()
        self.prefix = f"/user.slice/user-{self.uid}.slice/user@{self.uid}.service"
        self.owner = ":1.1" if system else ":1.30"
        self.pid = 1 if system else 300
        self.reply_sender = self.owner
        self.fragment = (
            "/usr/lib/systemd/system/user@.service"
            if system
            else "/usr/lib/systemd/user/dbus.service"
        )
        self.drops = []
        self.unit_pid = 300 if system else 456
        self.executable = (
            "/usr/lib/systemd/systemd" if system else "/usr/bin/dbus-daemon"
        )
        self.group = (
            self.prefix if system else self.prefix + "/session.slice/dbus.service"
        )

    async def add_match(self, rule: str) -> None:
        raise AssertionError("not needed for metadata attestation")

    async def next_signal(self, *, timeout: float = 1) -> DBusReply | None:
        raise AssertionError("not needed for metadata attestation")

    async def aclose(self) -> None:
        pass

    async def call(
        self, destination, path, interface, member, signature="", body=None, **_kwargs
    ):
        if destination == DBUS:
            if member == "GetNameOwner":
                return DBusReply(DBUS, "s", [self.owner])
            if member == "GetConnectionUnixUser":
                return DBusReply(DBUS, "u", [0 if self.system else self.uid])
            if member == "GetConnectionUnixProcessID":
                return DBusReply(DBUS, "u", [456 if body == [DBUS] else self.pid])
        if member == "GetUnit":
            return DBusReply(
                self.reply_sender, "o", ["/org/freedesktop/systemd1/unit/checked"]
            )
        if member == "GetAll":
            if body == ["org.freedesktop.systemd1.Unit"]:
                properties = {
                    "FragmentPath": self.fragment,
                    "DropInPaths": self.drops,
                    "ControlGroup": self.group,
                }
            else:
                properties = {
                    "MainPID": self.unit_pid,
                    "ExecStart": [[self.executable]],
                }
            return DBusReply(self.reply_sender, "a{sv}", [properties])
        raise AssertionError(member)


class ActivationAttestationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.system, self.desktop = (
            ActivationBus(system=True),
            ActivationBus(system=False),
        )
        self.uid = os.getuid()
        prefix = self.system.prefix
        stamp = session_module._ProcessStamp
        self.stamps = {
            789: stamp(self.uid, 300, 900, f"0::{prefix}/session.slice/dbus.service\n"),
            456: stamp(self.uid, 300, 800, f"0::{prefix}/session.slice/dbus.service\n"),
            300: stamp(self.uid, 1, 700, f"0::{prefix}/init.scope\n"),
        }
        self.argv = b"/usr/bin/dbus-daemon\0--session\0--address=systemd:\0--nofork\0--nopidfile\0--systemd-activation\0--syslog-only\0"
        self.service = "[D-BUS Service]\nName=org.cinnamon.ScreenSaver\nExec=/usr/bin/cinnamon-screensaver\n"
        self.unit = "ExecStart=" + self.argv.rstrip(b"\0").decode().replace("\0", " ")
        self.root_files = True
        self.snapshot = lambda pid: self.stamps[pid]
        self.patches = [
            patch.object(
                session_module,
                "process_stamp",
                side_effect=lambda pid: self.snapshot(pid),
            ),
            patch.object(session_module, "trusted_session_process", return_value=True),
            patch.object(
                session_module,
                "_root_file",
                side_effect=lambda path: (
                    self.root_files and not str(path).startswith("/home/")
                ),
            ),
            patch.object(session_module, "_no_activation_shadow"),
            patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=lambda path, **_kw: (
                    Path("/usr/bin/dbus-daemon")
                    if str(path) == "/proc/456/exe"
                    else path
                ),
            ),
            patch.object(
                Path, "read_bytes", autospec=True, side_effect=lambda path: self.argv
            ),
            patch.object(
                Path,
                "read_text",
                autospec=True,
                side_effect=lambda path: (
                    self.service
                    if str(path).endswith("ScreenSaver.service")
                    else self.unit
                ),
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    async def attest(self):
        await session_module.verify_cinnamon_activation(
            self.system, self.desktop, 789, self.uid
        )

    async def test_daemonized_package_process_with_loaded_root_units_is_supported(self):
        await self.attest()

    async def test_direct_child_of_same_daemon_is_supported_before_daemonization(self):
        stamp = self.stamps[789]
        self.stamps[789] = session_module._ProcessStamp(
            stamp.uid, 456, stamp.start, stamp.cgroup
        )
        await self.attest()

    async def test_unknown_parent_same_uid_is_rejected(self):
        stamp = self.stamps[789]
        self.stamps[789] = session_module._ProcessStamp(
            stamp.uid, 999, stamp.start, stamp.cgroup
        )
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_origin"):
            await self.attest()

    async def test_session_cgroup_cannot_masquerade_as_user_activation(self):
        stamp = self.stamps[789]
        self.stamps[789] = session_module._ProcessStamp(
            stamp.uid, 300, stamp.start, "0::/session-other.scope\n"
        )
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_origin"):
            await self.attest()

    async def test_wrong_process_uid_is_rejected(self):
        stamp = self.stamps[789]
        self.stamps[789] = session_module._ProcessStamp(
            self.uid + 1, stamp.parent, stamp.start, stamp.cgroup
        )
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_origin"):
            await self.attest()

    async def test_wrong_root_manager_pid_is_rejected(self):
        self.system.pid = 999
        with self.assertRaisesRegex(RuntimeError, "untrusted_system_manager"):
            await self.attest()

    async def test_wrong_user_manager_pid_is_rejected(self):
        self.desktop.pid = 999
        with self.assertRaisesRegex(RuntimeError, "untrusted_user_manager"):
            await self.attest()

    async def test_loaded_user_unit_override_is_rejected(self):
        self.desktop.fragment = "/home/user/.config/systemd/user/dbus.service"
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_unit"):
            await self.attest()

    async def test_loaded_user_dropin_is_rejected(self):
        self.desktop.drops = [
            "/home/user/.config/systemd/user/dbus.service.d/override.conf"
        ]
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_unit"):
            await self.attest()

    async def test_loaded_main_pid_and_execstart_must_match_bus_daemon(self):
        self.desktop.unit_pid = 999
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_unit"):
            await self.attest()
        self.desktop.unit_pid = 456
        self.desktop.executable = "/home/user/dbus-daemon"
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_unit"):
            await self.attest()

    async def test_forged_systemd_reply_is_rejected(self):
        self.system.reply_sender = ":1.999"
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_unit"):
            await self.attest()

    async def test_custom_daemon_config_or_entrypoint_is_rejected(self):
        self.argv = b"/usr/bin/dbus-daemon\0--config-file=/home/user/session.conf\0"
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_metadata"):
            await self.attest()
        self.argv = b"/usr/bin/dbus-daemon\0--session\0--address=systemd:\0--nofork\0--nopidfile\0--systemd-activation\0--syslog-only\0"
        self.service = (
            "[D-BUS Service]\nName=org.cinnamon.ScreenSaver\nExec=/home/user/fake\n"
        )
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_metadata"):
            await self.attest()

    async def test_root_owned_package_files_are_required(self):
        self.root_files = False
        with self.assertRaisesRegex(RuntimeError, "untrusted_activation_metadata"):
            await self.attest()

    async def test_process_reuse_during_async_loaded_unit_checks_is_rejected(self):
        original = self.desktop.call

        async def changed(*args, **kwargs):
            result = await original(*args, **kwargs)
            if args[3] == "GetAll":
                stamp = self.stamps[789]
                self.stamps[789] = session_module._ProcessStamp(
                    stamp.uid, stamp.parent, stamp.start + 1, stamp.cgroup
                )
            return result

        self.desktop.call = changed
        with self.assertRaisesRegex(RuntimeError, "activation_process_changed"):
            await self.attest()


class ActivationMetadataTests(unittest.TestCase):
    def test_cinnamon_maps_require_exact_library_path_and_installed_entrypoint(self):
        original_path = Path
        library = "/usr/libexec/cinnamon-screensaver/libcscreensaver.so"
        mapped = library
        command = b"cinnamon-screensaver\0"

        def read_text(path):
            self.assertEqual(str(path), "/proc/456/maps")
            return "1000-2000 r-xp 0000 00:01 1 " + mapped + "\n"

        with (
            patch.object(session_module, "_root_file", return_value=True),
            patch.object(
                Path,
                "stat",
                autospec=True,
                return_value=SimpleNamespace(st_uid=os.getuid()),
            ),
            patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=lambda path, **_kw: (
                    original_path("/usr/bin/python3.12")
                    if str(path) == "/proc/456/exe"
                    else path
                ),
            ),
            patch.object(
                Path, "read_bytes", autospec=True, side_effect=lambda _path: command
            ),
            patch.object(Path, "read_text", autospec=True, side_effect=read_text),
        ):
            self.assertTrue(trusted_session_process("cinnamon", 456, os.getuid()))
            mapped = "/home/user/forged" + library
            self.assertFalse(trusted_session_process("cinnamon", 456, os.getuid()))
            mapped = library
            command = b"/usr/bin/python3\0/home/user/fake.py\0"
            self.assertFalse(trusted_session_process("cinnamon", 456, os.getuid()))

    def test_activation_requires_exact_installed_name_and_exec(self):
        good = "[D-BUS Service]\nName=org.cinnamon.ScreenSaver\nExec=/usr/bin/cinnamon-screensaver\n"
        self.assertTrue(session_module._activation_file_matches(good))
        for invalid in (
            good.replace(
                "/usr/bin/cinnamon-screensaver", "/home/user/cinnamon-screensaver"
            ),
            good + "SystemdService=user-controlled.service\n",
            good.replace("org.cinnamon.ScreenSaver", "org.evil.ScreenSaver"),
            good + "Exec=/usr/bin/cinnamon-screensaver\n",
        ):
            self.assertFalse(session_module._activation_file_matches(invalid))

    def test_user_activation_shadow_and_alternate_filename_are_rejected(self):
        with TemporaryDirectory() as name:
            base = Path(name)
            services = base / "data/dbus-1/services"
            services.mkdir(parents=True)
            expected = base / "root/org.cinnamon.ScreenSaver.service"
            env = base / "env"
            env.write_bytes(
                os.fsencode(f"XDG_DATA_HOME={base}/data\0XDG_DATA_DIRS={base}/none\0")
            )
            runtime = base / "runtime"
            runtime.mkdir()
            real_path = Path

            def fixture_path(value):
                if str(value) == "/proc/456/environ":
                    return env
                if str(value) == f"/run/user/{os.getuid()}":
                    return runtime
                return real_path(value)

            with (
                patch.object(session_module, "Path", side_effect=fixture_path),
                patch.object(
                    session_module, "_configured_service_dirs", return_value=set()
                ),
                patch.object(
                    session_module.pwd,
                    "getpwuid",
                    return_value=SimpleNamespace(pw_dir=str(base / "home")),
                ),
            ):
                session_module._no_activation_shadow(456, os.getuid(), expected)
                shadow = services / "org.cinnamon.ScreenSaver.service"
                shadow.write_text(
                    "[D-BUS Service]\nName=org.cinnamon.ScreenSaver\nExec=/home/user/fake\n"
                )
                with self.assertRaisesRegex(
                    RuntimeError, "overridden_activation_metadata"
                ):
                    session_module._no_activation_shadow(456, os.getuid(), expected)
                shadow.rename(services / "alternate-name.service")
                with self.assertRaisesRegex(
                    RuntimeError, "overridden_activation_metadata"
                ):
                    session_module._no_activation_shadow(456, os.getuid(), expected)

    def test_single_display_rejects_second_filesystem_or_abstract_server(self):
        with TemporaryDirectory() as name:
            base = Path(name)
            directory = base / "sockets"
            directory.mkdir()
            net = base / "unix"
            net.write_text("header\n000: 0 0 00010000 0001 01 123 /tmp/.X11-unix/X0\n")
            real_path, real_lstat = Path, Path.lstat

            def fixture_path(value):
                return {"/tmp/.X11-unix": directory, "/proc/net/unix": net}.get(
                    str(value), real_path(value)
                )

            def fixture_stat(path):
                item = real_lstat(path)
                if path == directory:
                    return SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=0)
                return item

            with (
                socket.socket(socket.AF_UNIX) as first,
                socket.socket(socket.AF_UNIX) as second,
            ):
                first.bind(str(directory / "X0"))
                with (
                    patch.object(session_module, "Path", side_effect=fixture_path),
                    patch.object(
                        Path, "lstat", autospec=True, side_effect=fixture_stat
                    ),
                ):
                    self.assertTrue(
                        session_module.single_x11_display(":0", os.getuid())
                    )
                    second.bind(str(directory / "X1"))
                    self.assertFalse(
                        session_module.single_x11_display(":0", os.getuid())
                    )
                    (directory / "X1").unlink()
                    net.write_text(
                        "header\n000: 0 0 00010000 0001 01 123 @/tmp/.X11-unix/X1\n"
                    )
                    self.assertFalse(
                        session_module.single_x11_display(":0", os.getuid())
                    )

    def test_user_file_and_user_symlink_to_root_package_are_not_root_metadata(self):
        with TemporaryDirectory() as name:
            path = Path(name) / "service"
            path.write_text("[D-BUS Service]\nName=org.cinnamon.ScreenSaver\n")
            self.assertFalse(session_module._root_file(path))
            path.unlink()
            path.symlink_to("/usr/bin/python3")
            self.assertFalse(session_module._root_file(path))


if __name__ == "__main__":
    unittest.main()
