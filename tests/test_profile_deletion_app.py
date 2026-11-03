"""Закрытый профиль удаляется только по отдельному подтверждению намерения."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthStatus  # noqa: E402
from storage.data_protection import DATA_KEY_ALIAS  # noqa: E402
from storage.profile_deletion import PROFILE_ALIASES, ProfileDeletion  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402


class ProfileDeletionAppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.controller = self.fx.controller
        self.storage = self.fx.fixture.storage
        self.deletion = ProfileDeletion(self.fx.fixture.database.path, self.storage)
        self.fx.auth._profile_deletion = self.deletion
        self.completed = AsyncMock()
        self.controller._on_profile_deleted = self.completed
        self.reloaded = AsyncMock()
        self.controller._on_profile_reload = self.reloaded
        self.controller._show_pin_login()
        self.storage.read_keys.clear()

    async def test_locked_linux_and_android_offer_deletion_without_dek(self):
        for platform in (ft.PagePlatform.LINUX, ft.PagePlatform.ANDROID):
            self.fx.page.platform = platform
            self.controller._show_pin_login(lock_seconds=0)
            view = self.controller._pin_login_view
            assert view is not None
            view.set_locked(30)
            self.assertIsNotNone(view.delete_profile_button)
            assert view.delete_profile_button is not None
            self.assertFalse(view.delete_profile_button.disabled)
            await self.controller.request_profile_deletion()
            self.assertIsNotNone(self.controller._profile_deletion_view)
            self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
            self.controller.cancel_profile_deletion()

    async def test_wrong_phrase_cancel_and_old_dialog_do_not_delete(self):
        before = self.fx.fixture.database.path.read_bytes()
        aliases = dict(self.storage.values)
        await self.controller.request_profile_deletion()
        view = self.controller._profile_deletion_view
        assert view is not None
        view.phrase_field.value = "wrong"
        await view._confirm(None)
        self.controller.cancel_profile_deletion()
        view.phrase_field.value = view.phrase
        await view._confirm(None)
        self.assertEqual(self.fx.fixture.database.path.read_bytes(), before)
        self.assertEqual(self.storage.values, aliases)
        self.assertFalse(self.completed.called)

    async def test_real_pin_lock_allows_deletion_dialog_and_cancel_resumes_countdown(
        self,
    ):
        self.fx.auth._clock = lambda: 1000.0
        self.fx.auth._pin_elapsed_clock = lambda: 1000.0
        self.fx.auth._pin_boot_token = lambda: "synthetic-pin-dialog-boot"
        results = [await self.fx.auth.login("9999") for _ in range(3)]
        self.assertEqual(results[-1].status, AuthStatus.LOCKED)
        self.controller._show_pin_login(lock_seconds=300)
        await asyncio.sleep(0.02)
        self.storage.read_keys.clear()
        await self.controller.request_profile_deletion()
        dialog = self.controller._profile_deletion_view
        assert dialog is not None
        self.assertIsNone(self.controller._lock_task)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        dialog._on_cancel()
        for _ in range(100):
            await asyncio.sleep(0.01)
            if self.controller._lock_task is not None:
                break
        self.assertIsNotNone(self.controller._lock_task)
        view = self.controller._pin_login_view
        assert view is not None
        self.assertTrue(view._locked)
        self.assertIn("05:00", view.message.value)
        self.assertEqual(await self.fx.auth.pin_lock_seconds_remaining(), 300)

    async def test_confirmed_deletion_revokes_old_access_and_runs_once(self):
        neighbor = self.fx.fixture.database.path.parent / "user-export.json"
        neighbor.write_text("synthetic-external-export")
        self.storage.values["foreign.application.alias"] = "synthetic-neighbor"
        await self.controller.request_profile_deletion()
        view = self.controller._profile_deletion_view
        assert view is not None
        view.phrase_field.value = view.phrase
        await view._confirm(None)
        self.assertFalse(self.fx.fixture.database.path.exists())
        self.assertTrue(all(key not in self.storage.values for key in PROFILE_ALIASES))
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.assertEqual(neighbor.read_text(), "synthetic-external-export")
        self.assertEqual(
            self.storage.values["foreign.application.alias"], "synthetic-neighbor"
        )
        self.completed.assert_awaited_once()
        view.phrase_field.value = view.phrase
        await view._confirm(None)
        self.completed.assert_awaited_once()

    async def cancel_before_intent(self, *, language=False, android=False):
        before = self.fx.fixture.database.path.read_bytes()
        aliases = dict(self.storage.values)
        await self.controller.request_profile_deletion()
        view = self.controller._profile_deletion_view
        assert view is not None
        entered, release = asyncio.Event(), asyncio.Event()

        async def quiesce():
            entered.set()
            await release.wait()

        with patch.object(
            self.controller._chat_controller, "wait_profile_deletion", quiesce
        ):
            view.phrase_field.value = view.phrase
            deleting = asyncio.create_task(view._confirm(None))
            await entered.wait()
            self.assertFalse(self.fx.fixture.access.unlocked)
            if language:
                self.controller.handle_language_change()
            elif android:
                self.fx.page.platform = ft.PagePlatform.ANDROID
                from tests.test_app_lifecycle import lifecycle

                await self.controller.handle_lifecycle_change(
                    lifecycle(ft.AppLifecycleState.PAUSE)
                )
            else:
                self.controller.prepare_system_lock("screen_lock")
            release.set()
            await deleting
        self.assertFalse(self.deletion.pending())
        self.assertEqual(self.fx.fixture.database.path.read_bytes(), before)
        self.assertEqual(self.storage.values, aliases)
        self.completed.assert_not_awaited()
        self.reloaded.assert_awaited_once()

    async def test_system_lock_cancels_during_quiesce_before_intent(self):
        await self.cancel_before_intent()

    async def test_language_change_cancels_during_quiesce_before_intent(self):
        await self.cancel_before_intent(language=True)

    async def test_android_pause_cancels_during_quiesce_before_intent(self):
        await self.cancel_before_intent(android=True)

    async def test_language_change_and_old_cancel_cannot_affect_new_dialog(self):
        await self.controller.request_profile_deletion()
        old = self.controller._profile_deletion_view
        assert old is not None
        self.controller.handle_language_change()
        await self.controller.request_profile_deletion()
        current = self.controller._profile_deletion_view
        assert current is not None
        self.assertIsNot(old, current)
        old._on_cancel()
        current.phrase_field.value = current.phrase
        await current._confirm(None)
        self.completed.assert_awaited_once()

    async def test_lost_removal_ack_stays_closed_until_retry_finishes(self):
        await self.controller.request_profile_deletion()
        view = self.controller._profile_deletion_view
        assert view is not None
        remove = self.storage.remove
        raised = False

        async def lost_ack(key):
            nonlocal raised
            await remove(key)
            if not raised:
                raised = True
                raise OSError("synthetic-lost-removal-ack")

        with patch.object(self.storage, "remove", side_effect=lost_ack):
            view.phrase_field.value = view.phrase
            await view._confirm(None)
        self.assertTrue(self.deletion.pending())
        self.assertFalse(self.fx.fixture.access.unlocked)
        self.completed.assert_not_awaited()
        self.assertIsNone(self.controller._key_view)
        progress = self.controller._profile_deletion_progress
        assert progress is not None
        self.assertTrue(progress.retry_button.visible)
        await progress._retry(None)
        self.assertFalse(self.deletion.pending())
        self.assertFalse(self.fx.fixture.database.path.exists())
        self.completed.assert_awaited_once()

    async def test_replaced_pin_screen_revokes_old_dialog_confirmation(self):
        before = self.fx.fixture.database.path.read_bytes()
        await self.controller.request_profile_deletion()
        old = self.controller._profile_deletion_view
        assert old is not None
        self.controller._show_pin_login()
        old.phrase_field.value = old.phrase
        await old._confirm(None)
        self.completed.assert_not_awaited()
        self.assertEqual(self.fx.fixture.database.path.read_bytes(), before)
