"""Выдача кода не теряет черновик и не оживляет закрытую чат-сессию."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tests.test_chat_controller as fixtures  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import KeyValidityState  # noqa: E402
from chat.drafts import DraftStorageError  # noqa: E402
from i18n import configure_localization  # noqa: E402
from preferences import PreferencesStore  # noqa: E402


class RecoveryCodeChatRouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.fixture = fixtures.ChatControllerTests()
        self.fixture.setUp()
        self.fixture.chat_service.chats = [fixtures._existing_chat()]
        self.controller = self.fixture._controller()
        self.addCleanup(self.controller.dispose)

    async def activate(self) -> None:
        await self.controller.activate(
            "synthetic-session", KeyValidityState.VALID, self.fixture.available_limit
        )

    async def test_route_flushes_draft_and_ignores_workspace_refresh_until_return(self):
        await self.activate()
        view = self.controller._workspace_view
        assert view is not None
        selected = self.controller.selected_chat_id
        exact = "  Последняя строка\n🙂\n "
        view.restore_editor(exact)
        generation = self.controller.session_generation
        self.assertTrue(await self.controller.suspend_for_security())
        self.assertTrue(self.controller.session_active)
        self.assertFalse(self.controller.workspace_visible)
        self.assertEqual(self.controller.selected_chat_id, selected)
        screen = ft.Text("SYNTHETIC_SECURITY_SCREEN")
        self.fixture.page.controls = [screen]
        await self.controller._show_workspace(expected_generation=generation)
        await self.controller._refresh_after_key_validation(generation)
        await self.controller.request_new_chat()
        await self.controller.select_chat("another-chat")
        self.assertEqual(self.fixture.page.controls, [screen])
        self.assertEqual(self.fixture.catalog_service.get_calls, 0)
        self.assertEqual(self.controller.selected_chat_id, selected)
        await self.controller.resume_after_security()
        restored = self.controller._workspace_view
        assert restored is not None
        self.assertIsNot(restored, view)
        self.assertEqual(restored.editor_value, exact)
        self.assertEqual(self.controller.selected_chat_id, selected)

    async def test_system_lock_prevents_resume_from_reopening_chat(self):
        await self.activate()
        self.assertTrue(await self.controller.suspend_for_security())
        self.controller.begin_lock()
        await self.controller.resume_after_security()
        self.assertFalse(self.controller.session_active)
        self.assertFalse(self.controller.workspace_visible)

    async def test_pending_key_check_does_not_block_or_replace_security_screen(self):
        blocking = fixtures.BlockingKeyValidator(fixtures._available_key())
        self.controller._key_validator = cast(KeyValidator, blocking)
        await self.controller.activate(
            "synthetic-session", KeyValidityState.UNKNOWN, self.fixture.available_limit
        )
        await asyncio.wait_for(blocking.started.wait(), timeout=1)
        try:
            self.assertTrue(await self.controller.suspend_for_security())
            screen = ft.Text("SYNTHETIC_SECURITY_SCREEN")
            self.fixture.page.controls = [screen]
            blocking.release.set()
            await fixtures._wait_for_key_validation(self.controller)
            self.assertEqual(self.controller.key_validity, KeyValidityState.VALID)
            self.assertEqual(self.fixture.page.controls, [screen])
            await self.controller.resume_after_security()
            self.assertTrue(self.controller.workspace_visible)
        finally:
            blocking.release.set()

    async def test_failed_draft_save_keeps_workspace_and_rejects_security_route(self):
        await self.activate()
        view = self.controller._workspace_view
        assert view is not None
        view.restore_editor("SYNTHETIC_PENDING_DRAFT")
        with (
            patch.object(
                self.controller._drafts,
                "flush",
                new=AsyncMock(side_effect=DraftStorageError()),
            ),
            patch.object(ft.Control, "update"),
        ):
            self.assertFalse(await self.controller.suspend_for_security())
        self.assertTrue(self.controller.session_active)
        self.assertIs(self.controller._workspace_view, view)
        self.assertEqual(view.editor_value, "SYNTHETIC_PENDING_DRAFT")
        self.assertTrue(self.controller.draft_save_failed)


if __name__ == "__main__":
    unittest.main()
