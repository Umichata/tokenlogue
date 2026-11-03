"""Real protected controllers never replace an explicit per-chat decision globally."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import Chat, ModelCatalog  # noqa: E402
from chat_controller import ChatSessionController  # noqa: E402
from i18n import configure_localization, set_language  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests import test_chat_ui_integration as ui  # noqa: E402
from tests import test_message_sending as fx  # noqa: E402
from tests import test_paid_chat_policy as policy_fixtures  # noqa: E402


class PaidChatUiPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.fx = policy_fixtures.PaidChatPolicyTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        self.page = ui.FakePage()
        self.client = fx.FakeCompletionClient(
            [fx._success(cost="0.01") for _ in range(5)]
        )
        self.controller = ChatSessionController(
            cast(ft.Page, self.page),
            self.fx.validator,
            self.fx.service,
            cast(
                ModelCatalogService,
                ui.FakeCatalogService(
                    ModelCatalog(
                        free_models=(),
                        paid_models=(self.fx.model,),
                        available=True,
                    )
                ),
            ),
            self.fx.budgets,
            self.fx.sender(self.client),
            ChatDraftService(self.fx.drafts),
            on_lock=AsyncMock(),
            on_replace_key=AsyncMock(),
            on_storage_error=lambda _message: None,
            data_access=self.fx.access,
        )
        self.addCleanup(self.controller.dispose)
        self.control_updates = patch.object(ft.Control, "update")
        self.control_updates.start()
        self.addCleanup(self.control_updates.stop)
        await self.controller.activate(
            fx.TEST_CREDENTIAL,
            fx.KeyValidityState.VALID,
            fx.KeyLimitInfo.from_validated_remaining(None),
        )

    def view(self):
        value = self.controller._workspace_view
        assert value is not None
        return value

    def selected(self) -> Chat:
        result = self.view()._selected_chat
        assert result is not None
        return result

    async def checkbox(self, enabled: bool):
        view = self.view()
        box = view.paid_confirmation_checkbox
        assert box is not None and box.on_change is not None
        self.assertIsNone(view._menu_dialog)
        box.value = enabled
        await cast(Callable[[ft.Event], Awaitable[None]], box.on_change)(
            ft.Event(name="change", control=box)
        )

    async def test_checkbox_before_first_message_sends_nothing_and_first_submit_has_no_warning(
        self,
    ):
        self.assertEqual(self.fx.messages.list_turns("a"), [])
        await self.checkbox(True)
        self.assertEqual(self.client.calls, [])
        self.assertTrue(self.selected().paid_without_confirmation)
        await self.controller.submit_message("first paid request")
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(self.page.dialogs, [])
        await self.controller.submit_message("second paid request")
        self.assertEqual(len(self.client.calls), 2)
        self.assertEqual(self.page.dialogs, [])

    async def test_default_off_requires_new_confirmation_each_submit(self):
        await self.controller.submit_message("first")
        self.assertEqual(len(self.client.calls), 0)
        self.assertEqual(len(self.page.dialogs), 1)
        await self.controller.confirm_paid_request()
        self.assertEqual(len(self.client.calls), 1)
        await self.controller.submit_message("second")
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(len(self.page.dialogs), 1)

    async def test_price_change_and_retry_remain_warning_free_with_opt_in(self):
        self.client.results = [
            fx._known_error(ChatErrorType.RATE_LIMIT_EXCEEDED),
            fx._success(cost="0.5"),
        ]
        await self.checkbox(True)
        self.fx.catalog.models = (replace(self.fx.model, request_price=Decimal("0.5")),)
        await self.controller.submit_message("first with a new price")
        self.assertEqual(self.page.dialogs, [])
        turn = self.fx.messages.list_turns("a")[0]
        await self.controller.request_retry_turn(turn.id)
        self.assertEqual(self.page.dialogs, [])
        self.assertEqual(len(self.client.calls), 2)

    async def test_language_navigation_and_lock_preserve_only_this_chat_choice(self):
        await self.checkbox(True)
        set_language("ru")
        self.controller.handle_language_change()
        self.assertTrue(self.selected().paid_without_confirmation)
        await self.controller.select_chat("b")
        self.assertFalse(self.selected().paid_without_confirmation)
        await self.controller.select_chat("a")
        self.assertTrue(self.selected().paid_without_confirmation)
        await self.controller.lock_application()
        self.fx.access.open(self.fx.cipher)
        await self.controller.activate(
            fx.TEST_CREDENTIAL,
            fx.KeyValidityState.VALID,
            fx.KeyLimitInfo.from_validated_remaining(None),
        )
        self.assertTrue(self.selected().paid_without_confirmation)
        self.assertEqual(self.client.calls, [])

    async def test_checkbox_label_wraps_and_remains_accessible_in_both_languages(self):
        labels = []
        for language in ("en", "ru"):
            with self.subTest(language=language):
                set_language(language)
                self.controller.handle_language_change()
                await self.view().open_menu()
                box = self.view().paid_confirmation_checkbox
                assert box is not None
                self.assertIsInstance(box.label, ft.Text)
                label = cast(ft.Text, box.label)
                self.assertFalse(label.no_wrap)
                self.assertIsNotNone(label.width)
                self.assertEqual(box.semantics_label, label.value)
                self.assertFalse(box.value)
                labels.append(label.value)
                self.view().close_menu()
        self.assertNotEqual(*labels)
        self.assertEqual(self.client.calls, [])

    async def test_failed_save_rolls_checkbox_back_and_keeps_exact_draft(self):
        exact = "  synthetic preserved editor\n🙂 "
        self.view().restore_editor(exact)
        with patch.object(
            self.fx.chats,
            "set_paid_without_confirmation",
            side_effect=OSError("synthetic"),
        ):
            await self.checkbox(True)
        view = self.view()
        self.assertFalse(self.selected().paid_without_confirmation)
        self.assertEqual(view.editor_value, exact)
        assert view.composer is not None
        self.assertTrue(view.composer.status.visible)
        self.assertEqual(self.client.calls, [])

    async def test_old_paid_dialog_cannot_confirm_new_request_after_permission_changes(
        self,
    ):
        await self.controller.submit_message("old")
        old = self.page.dialogs[-1]
        assert isinstance(old, ft.AlertDialog)
        confirm_button, cancel_button = old.actions[-1], old.actions[0]
        assert isinstance(confirm_button, (ft.Button, ft.TextButton))
        assert isinstance(cancel_button, (ft.Button, ft.TextButton))
        old_confirm = confirm_button.on_click
        old_cancel = cancel_button.on_click
        assert old_confirm is not None and old_cancel is not None
        await self.controller.set_paid_without_confirmation("a", True)
        await self.controller.set_paid_without_confirmation("a", False)
        await self.controller.submit_message("new")
        current = self.page.dialogs[-1]
        self.assertIsNot(current, old)
        await cast(Callable[[ft.Event], Awaitable[None]], old_confirm)(
            ft.Event(name="click", control=old.actions[-1])
        )
        cast(Callable[[ft.Event], None], old_cancel)(
            ft.Event(name="click", control=old.actions[0])
        )
        self.assertEqual(self.client.calls, [])
        self.assertIn(current, self.page.dialogs)
        await self.controller.confirm_paid_request()
        self.assertEqual(len(self.client.calls), 1)

    async def test_opt_out_during_preflight_invalidates_pending_and_retains_draft(self):
        await self.checkbox(True)
        entered, release = asyncio.Event(), asyncio.Event()
        validate = self.fx.validator.validate_key

        async def delayed(value):
            entered.set()
            await release.wait()
            return await validate(value)

        exact = "  synthetic queued text\n🙂 "
        self.view().restore_editor(exact)
        with patch.object(self.fx.validator, "validate_key", delayed):
            pending = asyncio.create_task(self.controller.submit_message(exact))
            await entered.wait()
            await self.controller.set_paid_without_confirmation("a", False)
            release.set()
            await pending
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.view().editor_value, exact)
        self.assertFalse(self.selected().paid_without_confirmation)

    async def test_old_workspace_setting_callback_cannot_change_reopened_session(self):
        old = self.view()._on_paid_confirmation_changed
        assert old is not None
        await self.controller.lock_application()
        self.fx.access.open(self.fx.cipher)
        await self.controller.activate(
            fx.TEST_CREDENTIAL,
            fx.KeyValidityState.VALID,
            fx.KeyLimitInfo.from_validated_remaining(None),
        )
        await old("a", True)
        self.assertFalse(self.fx.chat("a").paid_without_confirmation)

    async def test_pending_setting_write_never_opens_first_paid_warning_or_dispatches(
        self,
    ):
        exact = "synthetic first request after setting save"
        self.view().restore_editor(exact)
        entered, release = threading.Event(), threading.Event()
        save = self.fx.chats.set_paid_without_confirmation

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("synthetic setting write timeout")
            return save(*args, **kwargs)

        with patch.object(self.fx.chats, "set_paid_without_confirmation", delayed):
            changing = asyncio.create_task(self.checkbox(True))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            try:
                composer = self.view().composer
                assert composer is not None
                self.assertTrue(composer.send_button.disabled)
                await self.controller.submit_message(exact)
                self.assertIsNone(self.controller._workspace_controller.pending_preview)
                self.assertEqual(self.client.calls, [])
            finally:
                release.set()
            await changing
        self.assertTrue(self.selected().paid_without_confirmation)
        self.view().close_menu()
        composer = self.view().composer
        assert composer is not None
        self.assertFalse(composer.send_button.disabled)
        await self.controller.submit_message(exact)
        self.assertEqual(len(self.client.calls), 1)

    async def test_lock_during_paid_preflight_never_dispatches_or_reopens_old_workspace(
        self,
    ):
        await self.checkbox(True)
        entered, release = asyncio.Event(), asyncio.Event()
        validate = self.fx.validator.validate_key

        async def delayed(value):
            entered.set()
            await release.wait()
            return await validate(value)

        exact = "synthetic draft before system lock"
        self.view().restore_editor(exact)
        with patch.object(self.fx.validator, "validate_key", delayed):
            pending = asyncio.create_task(self.controller.submit_message(exact))
            await entered.wait()
            await self.controller.lock_application()
            release.set()
            await pending
        self.assertFalse(self.controller.workspace_visible)
        self.assertFalse(self.controller.session_active)
        self.assertEqual(self.client.calls, [])
        self.fx.access.open(self.fx.cipher)
        self.assertEqual(self.fx.drafts.get_draft("a").text, exact)
