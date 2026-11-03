"""Глобальное удаление привязано к текущей сессии и сохраняет отменённый чат."""

from __future__ import annotations

import asyncio
import sys
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import tr  # noqa: E402
from storage.profile_deletion import PROFILE_ALIASES, ProfileDeletion  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402


class ProfileDeletionMenuTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.app = self.fx.controller
        self.chat = self.app._chat_controller
        self.deleted = AsyncMock()
        self.app._on_profile_deleted = self.deleted
        self.fx.auth._profile_deletion = ProfileDeletion(
            self.fx.fixture.database.path, self.fx.fixture.storage
        )
        await self.app.submit_pin("0123")
        self.assertTrue(self.chat.session_active)

    async def open_deletion(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        await workspace.open_menu()
        button = workspace.delete_profile_button
        assert button is not None and button.on_click is not None
        await cast(Callable[[ft.Event], Awaitable[None]], button.on_click)(
            ft.Event(name="click", control=button)
        )
        return self.app._profile_deletion_view

    async def wait_resume(self):
        for _ in range(100):
            await asyncio.sleep(0.01)
            if self.chat.workspace_visible:
                break
        self.assertTrue(self.chat.workspace_visible)

    async def test_global_action_exists_for_both_platforms_and_empty_workspace(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        selected, state = workspace._selected_chat, workspace._interaction_state
        for platform in (ft.PagePlatform.LINUX, ft.PagePlatform.ANDROID):
            for empty in (False, True):
                self.fx.page.platform = platform
                workspace = self.chat._workspace_view
                assert workspace is not None
                workspace._selected_chat = None if empty else selected
                workspace._interaction_state = None if empty else state
                await workspace.open_menu()
                button = workspace.delete_profile_button
                assert button is not None and workspace._menu_list is not None
                self.assertIs(workspace._menu_list.controls[-1], button)
                self.assertFalse(button.disabled)
                workspace.close_menu()

    async def test_cancel_restores_exact_chat_and_draft_without_deletion(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        exact = "  synthetic draft\n🙂\n "
        workspace.restore_editor(exact)
        selected = self.chat.selected_chat_id
        aliases = dict(self.fx.fixture.storage.values)
        dialog = await self.open_deletion()
        assert dialog is not None
        self.assertFalse(self.chat.workspace_visible)
        self.assertTrue(self.chat.session_active)
        generation = self.chat.session_generation
        await self.chat._refresh_after_key_validation(generation)
        await self.chat._show_workspace(expected_generation=generation)
        self.assertIs(self.app._profile_deletion_view, dialog)
        dialog._on_cancel()
        await self.wait_resume()
        restored = self.chat._workspace_view
        assert restored is not None
        self.assertEqual(restored.editor_value, exact)
        self.assertEqual(self.chat.selected_chat_id, selected)
        self.assertEqual(self.fx.fixture.storage.values, aliases)
        dialog.phrase_field.value = dialog.phrase
        await dialog._confirm(None)
        self.assertTrue(self.fx.fixture.database.path.exists())

    async def test_menu_confirmation_uses_strict_existing_deletion(self):
        neighbor = self.fx.fixture.database.path.parent / "synthetic-export.txt"
        neighbor.write_text("preserve")
        self.fx.fixture.storage.values["foreign.alias"] = "preserve"
        dialog = await self.open_deletion()
        assert dialog is not None
        dialog.phrase_field.value = dialog.phrase
        await dialog._confirm(None)
        self.assertFalse(self.fx.fixture.database.path.exists())
        self.assertTrue(
            all(k not in self.fx.fixture.storage.values for k in PROFILE_ALIASES)
        )
        self.assertEqual(neighbor.read_text(), "preserve")
        self.assertEqual(self.fx.fixture.storage.values["foreign.alias"], "preserve")
        self.assertFalse(self.chat.session_active)
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.deleted.assert_awaited_once()
        await dialog._confirm(None)
        self.deleted.assert_awaited_once()

    async def test_old_cancel_and_confirmation_cannot_affect_new_menu_dialog(self):
        old = await self.open_deletion()
        assert old is not None
        old._on_cancel()
        await self.wait_resume()
        current = await self.open_deletion()
        assert current is not None
        old._on_cancel()
        old.phrase_field.value = old.phrase
        await old._confirm(None)
        self.assertIs(self.app._profile_deletion_view, current)
        self.assertTrue(self.fx.fixture.database.path.exists())

    async def test_capture_error_returns_draft_and_explains_deletion_not_started(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        workspace.restore_editor("synthetic retained draft")
        with patch.object(
            self.fx.auth,
            "capture_profile_deletion",
            new=AsyncMock(side_effect=OSError("synthetic")),
        ):
            await self.open_deletion()
        restored = self.chat._workspace_view
        assert restored is not None
        self.assertEqual(restored.editor_value, "synthetic retained draft")
        self.assertIsNone(self.app._profile_deletion_view)
        assert restored.composer is not None
        self.assertEqual(
            restored.composer.status.value, tr("profile_deletion.not_started")
        )

    async def test_stale_workspace_callback_cannot_open_new_session_dialog(self):
        workspace = self.chat._workspace_view
        assert workspace is not None and workspace._on_delete_profile is not None
        stale = workspace._on_delete_profile
        await self.app.lock_application()
        await self.app.submit_pin("0123")
        await stale()
        self.assertIsNone(self.app._profile_deletion_view)
        self.assertTrue(self.chat.workspace_visible)

    async def test_stale_menu_event_after_refresh_is_rejected(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        await workspace.open_menu()
        button = workspace.delete_profile_button
        assert button is not None and button.on_click is not None
        stale = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
        workspace._refresh_menu()
        await stale(ft.Event(name="click", control=button))
        self.assertIsNone(self.app._profile_deletion_view)
        self.assertTrue(self.chat.workspace_visible)

    async def test_language_change_rebinds_open_menu_and_rejects_old_event(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        await workspace.open_menu()
        button = workspace.delete_profile_button
        assert button is not None and button.on_click is not None
        stale = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
        self.app.handle_language_change()
        await stale(ft.Event(name="click", control=button))
        self.assertIsNone(self.app._profile_deletion_view)
        current = workspace.delete_profile_button
        assert current is not None and current.on_click is not None
        await cast(Callable[[ft.Event], Awaitable[None]], current.on_click)(
            ft.Event(name="click", control=current)
        )
        self.assertIsNotNone(self.app._profile_deletion_view)

    async def test_language_change_cancels_old_confirmation_and_resumes(self):
        dialog = await self.open_deletion()
        assert dialog is not None
        self.app.handle_language_change()
        await self.wait_resume()
        dialog.phrase_field.value = dialog.phrase
        await dialog._confirm(None)
        self.assertTrue(self.fx.fixture.database.path.exists())

    async def test_system_lock_revokes_dialog_without_resuming_workspace(self):
        dialog = await self.open_deletion()
        assert dialog is not None
        self.app.prepare_system_lock("screen_lock")
        await self.app.wait_system_lock()
        dialog.phrase_field.value = dialog.phrase
        await dialog._confirm(None)
        self.assertFalse(self.chat.session_active)
        self.assertFalse(self.chat.workspace_visible)
        self.assertIsNotNone(self.app._pin_login_view)
        self.assertTrue(self.fx.fixture.database.path.exists())

    async def test_close_revokes_dialog_without_resuming_workspace(self):
        dialog = await self.open_deletion()
        assert dialog is not None
        self.app.prepare_close()
        await asyncio.sleep(0)
        dialog.phrase_field.value = dialog.phrase
        await dialog._confirm(None)
        self.assertFalse(self.chat.session_active)
        self.assertTrue(self.fx.fixture.database.path.exists())

    async def test_busy_or_conflicting_modal_rejects_action(self):
        workspace = self.chat._workspace_view
        assert workspace is not None and workspace._on_delete_profile is not None
        with patch.object(
            self.chat._workspace_controller, "has_dialog", return_value=True
        ):
            await workspace._on_delete_profile()
        self.assertIsNone(self.app._profile_deletion_view)
        workspace._sending = True
        await workspace._on_delete_profile()
        workspace._sending = False
        self.app._reset_dialog_open = True
        await workspace._on_delete_profile()
        self.app._reset_dialog_open = False
        self.assertIsNone(self.app._profile_deletion_view)
        self.assertTrue(self.chat.workspace_visible)

    async def test_language_change_during_scope_capture_cancels_pending_origin(self):
        capture = self.fx.auth.capture_profile_deletion
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed():
            entered.set()
            await release.wait()
            return await capture()

        with patch.object(self.fx.auth, "capture_profile_deletion", delayed):
            opening = asyncio.create_task(self.open_deletion())
            await entered.wait()
            self.app.handle_language_change()
            release.set()
            await opening
        await self.wait_resume()
        self.assertIsNone(self.app._profile_deletion_view)
        self.assertTrue(self.fx.fixture.database.path.exists())

    async def test_language_change_during_initial_draft_flush_cancels_and_resumes(self):
        workspace = self.chat._workspace_view
        assert workspace is not None
        workspace.restore_editor("synthetic draft during flush")
        selected = self.chat.selected_chat_id
        flush = self.chat.flush_drafts
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed():
            entered.set()
            await release.wait()
            return await flush()

        with patch.object(self.chat, "flush_drafts", delayed):
            opening = asyncio.create_task(self.open_deletion())
            await entered.wait()
            self.app.handle_language_change()
            # A scheduled cancellation must not resume ahead of the pending flush.
            await asyncio.sleep(0)
            release.set()
            await opening
        self.assertIsNone(self.app._profile_deletion_view)
        await self.wait_resume()
        restored = self.chat._workspace_view
        assert restored is not None
        self.assertEqual(restored.editor_value, "synthetic draft during flush")
        self.assertEqual(self.chat.selected_chat_id, selected)
        self.assertTrue(self.fx.fixture.database.path.exists())
