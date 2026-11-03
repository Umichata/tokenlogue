"""Composition forwards trusted screen evidence after the ordinary safety seal."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app import AppController  # noqa: E402
from main import start_linux_session_watch  # noqa: E402
from platform_security.linux_session import (  # noqa: E402
    SessionObservation,
    SessionSecurityEvent,
    SessionWatchState,
    SessionWatchStatus,
)
from platform_security.local_protection import (  # noqa: E402
    AppLockState,
    ObserverContext,
)

CONTEXT = ObserverContext("linux", "synthetic", 1, "synthetic-source")


class FakeController:
    def __init__(self):
        self.state = AppLockState(9, True, True, False)
        self.events = []
        self.transitions = []
        self.resumes = []

    def protection_app_state(self):
        return self.state

    def set_session_watch_status(self, **_status):
        pass

    def set_screen_lock_adapter(self, _adapter, _sleep_context):
        pass

    def set_sleep_adapter(self, _adapter):
        pass

    def prepare_system_lock(self, event):
        self.events.append(("seal", event))
        self.state = AppLockState(10, False, False, False)

    def record_normal_protection(self, mechanism, context, before):
        self.events.append(("receipt", mechanism, context, before, self.state))

    def record_screen_transition(self, context, locked, *, test_id=None):
        self.transitions.append((context, locked, test_id))

    def record_sleep_resume(self, context, suspended, *, test_id=None):
        self.resumes.append((context, suspended, test_id))


class FakeWatcher:
    screen_context = CONTEXT
    sleep_context = CONTEXT

    def __init__(self, event, *, on_status, on_observation):
        self.event = event
        self.status = on_status
        self.observation = on_observation

    async def start(self):
        self.status(SessionWatchStatus(SessionWatchState.READY, "ready", True, True))

    async def aclose(self):
        pass


class SessionWatchCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FakeController()
        with patch("platform_security.linux_session.LinuxSessionWatcher", FakeWatcher):
            self.watcher = await start_linux_session_watch(
                cast(AppController, self.app)
            )

    async def test_trusted_screen_events_are_not_dropped_or_used_to_unlock_app(self):
        watcher = cast(FakeWatcher, self.watcher)
        watcher.observation(SessionObservation("screen_locked", CONTEXT, test_id=7))
        watcher.observation(SessionObservation("screen_inactive", CONTEXT, test_id=7))
        self.assertEqual(
            self.app.transitions, [(CONTEXT, True, 7), (CONTEXT, False, 7)]
        )
        self.assertEqual(self.app.events, [])
        self.assertEqual(self.app.state, AppLockState(9, True, True, False))

    async def test_ordinary_handler_revokes_before_recording_its_receipt(self):
        watcher = cast(FakeWatcher, self.watcher)
        watcher.event(SessionSecurityEvent.SCREEN_LOCK)
        self.assertEqual(self.app.events[0], ("seal", SessionSecurityEvent.SCREEN_LOCK))
        receipt = self.app.events[1]
        self.assertEqual(receipt[:3], ("receipt", "screen", CONTEXT))
        self.assertTrue(receipt[3].opened)
        self.assertTrue(receipt[4].revoked)

    async def test_screen_observations_do_not_claim_sleep(self):
        watcher = cast(FakeWatcher, self.watcher)
        watcher.observation(SessionObservation("screen_inactive", CONTEXT))
        self.assertEqual(self.app.resumes, [])
        watcher.observation(SessionObservation("sleep_resume", CONTEXT, True))
        self.assertEqual(self.app.resumes, [(CONTEXT, True, None)])

    async def test_sleep_trial_tag_is_forwarded_without_granting_access(self):
        watcher = cast(FakeWatcher, self.watcher)
        watcher.observation(
            SessionObservation("sleep_resume", CONTEXT, True, test_id=23)
        )
        self.assertEqual(self.app.resumes, [(CONTEXT, True, 23)])
        self.assertEqual(self.app.state, AppLockState(9, True, True, False))
        self.assertEqual(self.app.events, [])

    async def test_ordinary_sleep_handler_revokes_before_its_receipt(self):
        watcher = cast(FakeWatcher, self.watcher)
        watcher.event(SessionSecurityEvent.SLEEP)
        self.assertEqual(self.app.events[0], ("seal", SessionSecurityEvent.SLEEP))
        receipt = self.app.events[1]
        self.assertEqual(receipt[:3], ("receipt", "sleep", CONTEXT))
        self.assertTrue(receipt[3].opened)
        self.assertTrue(receipt[4].revoked)
