"""Замена ключа доступна только действующей чат-сессии."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import InitialRoute, KeyLimitInfo, KeyValidityState  # noqa: E402
from tests import test_app as fixtures  # noqa: E402


class PinReplacementBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_or_stale_pin_route_cannot_open_replacement(self):
        page, auth = (
            fixtures.FakePage(),
            fixtures.FakeAuthService(initial_route=InitialRoute.PIN),
        )
        app = fixtures._make_controller(page, auth)
        self.addCleanup(app.dispose)
        await app.start()
        stale = app.request_reset
        await stale()
        self.assertFalse(app._reset_dialog_open)
        self.assertEqual(page.dialogs, [])
        self.assertEqual(auth.reset_calls, 0)
        await app._activate_session(
            "synthetic-session", KeyValidityState.VALID, KeyLimitInfo.unknown()
        )
        await app.request_reset()
        self.assertTrue(app._reset_dialog_open)
        app.cancel_reset()
        await app.lock_application()
        await stale()
        self.assertFalse(app._reset_dialog_open)
        self.assertEqual(auth.reset_calls, 0)
