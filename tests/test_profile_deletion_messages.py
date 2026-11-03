"""Отказ до принятия удаления не выдаётся за частичное уничтожение профиля."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthResult, AuthStatus  # noqa: E402
from auth.service import deletion_error_message  # noqa: E402
from i18n import set_language  # noqa: E402
from storage.profile_deletion import DeletionDiagnostic, ProfileDeletion  # noqa: E402
from tests import test_linux_parity as fixtures  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui.profile_deletion_view import ProfileDeletionDialog  # noqa: E402


class ProfileDeletionMessageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.controller = self.fx.controller
        self.deletion = ProfileDeletion(
            self.fx.fixture.database.path, self.fx.fixture.storage
        )
        self.fx.auth._profile_deletion = self.deletion
        self.controller._show_pin_login()

    async def test_unknown_capture_failure_says_not_started_in_both_platforms(self):
        for platform in (ft.PagePlatform.LINUX, ft.PagePlatform.ANDROID):
            for language in ("en", "ru"):
                with self.subTest(platform=platform, language=language):
                    set_language(language)
                    self.fx.page.platform = platform
                    self.controller._show_pin_login()
                    old = self.fx.fixture.database.path.read_bytes()
                    aliases = dict(self.fx.fixture.storage.values)
                    with patch.object(
                        self.deletion, "capture", side_effect=OSError("private detail")
                    ):
                        await self.controller.request_profile_deletion()
                    view = self.controller._pin_login_view
                    assert view is not None
                    self.assertEqual(
                        getattr(view.message.value, "key", None),
                        "profile_deletion.not_started",
                    )
                    self.assertNotIn("private detail", str(view.message.value))
                    self.assertIsNone(self.controller._profile_deletion_view)
                    self.assertFalse(self.deletion.pending())
                    self.assertEqual(self.fx.fixture.database.path.read_bytes(), old)
                    self.assertEqual(self.fx.fixture.storage.values, aliases)

    async def test_preparation_explanation_is_in_the_same_confirmation(self):
        for language in ("en", "ru"):
            set_language(language)
            confirm, cancel = AsyncMock(), AsyncMock()
            view = ProfileDeletionDialog(confirm, cancel, preparation_required=True)
            keys = [
                getattr(c.value, "key", None)
                for c in walk(view.dialog)
                if isinstance(c, ft.Text)
            ]
            self.assertIn("profile_deletion.preparation_notice", keys)
            self.assertEqual(len(view.dialog.actions), 2)
            view.phrase_field.value = view.phrase
            await view._confirm(None)
            confirm.assert_awaited_once_with(view.phrase)
            cancel.assert_not_called()

    async def test_private_profile_does_not_claim_a_permission_change(self):
        view = ProfileDeletionDialog(AsyncMock(), lambda: None)
        keys = [
            getattr(c.value, "key", None)
            for c in walk(view.dialog)
            if isinstance(c, ft.Text) and c.visible
        ]
        self.assertNotIn("profile_deletion.preparation_notice", keys)

    async def test_lock_after_preparation_does_not_hide_the_kept_profile_message(self):
        reloaded, deleted = AsyncMock(), AsyncMock()
        self.controller._on_profile_reload = reloaded
        self.controller._on_profile_deleted = deleted
        await self.controller.request_profile_deletion()
        dialog = self.controller._profile_deletion_view
        assert dialog is not None
        before = self.fx.fixture.database.path.read_bytes()
        aliases = dict(self.fx.fixture.storage.values)

        async def prepared_then_cancelled(_scope):
            self.deletion.diagnostic = DeletionDiagnostic(
                "prepare", "preparation_failed", prepared=True, intent_pending=False
            )
            self.controller.prepare_system_lock("sleep")
            return AuthResult(
                AuthStatus.STORAGE_ERROR,
                deletion_error_message(self.deletion.diagnostic),
            )

        with patch.object(
            self.fx.auth, "confirm_profile_deletion", prepared_then_cancelled
        ):
            dialog.phrase_field.value = dialog.phrase
            await dialog._confirm(None)
        progress = self.controller._profile_deletion_progress
        assert progress is not None
        self.assertEqual(
            getattr(progress.message.value, "key", None),
            "profile_deletion.prepared_before",
        )
        self.assertFalse(self.deletion.pending())
        reloaded.assert_not_called()
        deleted.assert_not_called()
        self.assertEqual(self.fx.fixture.database.path.read_bytes(), before)
        self.assertEqual(self.fx.fixture.storage.values, aliases)
        await progress._retry(None)
        reloaded.assert_awaited_once_with()

    async def test_native_ack_failure_explains_accepted_deletion_and_keeps_retry(self):
        await self.controller.request_profile_deletion()
        dialog = self.controller._profile_deletion_view
        assert dialog is not None
        with patch.object(
            self.fx.fixture.storage, "remove", side_effect=OSError("private detail")
        ):
            dialog.phrase_field.value = dialog.phrase
            await dialog._confirm(None)
        self.assertTrue(self.deletion.pending())
        progress = self.controller._profile_deletion_progress
        assert progress is not None
        self.assertEqual(
            getattr(progress.message.value, "key", None),
            "profile_deletion.unavailable",
        )
        self.assertNotIn("private detail", str(progress.message.value))
        self.assertEqual(
            getattr(progress.retry_button.content, "key", None),
            "profile_deletion.retry",
        )
