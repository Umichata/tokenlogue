"""Real encrypted controllers route every paid entry through one budget decision."""

from __future__ import annotations

import inspect
import sys
import unittest
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import ModelCatalog  # noqa: E402
from chat_controller import ChatSessionController  # noqa: E402
from i18n import configure_localization, set_language  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests import test_chat_ui_integration as ui  # noqa: E402
from tests import test_message_sending as sending  # noqa: E402
from tests import test_paid_chat_policy as policy  # noqa: E402


class UiHarness:
    async def setup(self, case: unittest.TestCase, *, credits_reader=None, client=None):
        configure_localization(PreferencesStore())
        case.addCleanup(configure_localization, PreferencesStore())
        self.fx = policy.PaidChatPolicyTests()
        await self.fx.asyncSetUp()
        # This fixture was initialized directly, without its own unittest runner.
        case.addCleanup(self.fx.temp.cleanup)
        await self.fx.budgets.update_chat_limits(
            "a",
            token_limit=100_000,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("0.011"),
        )
        self.page = ui.FakePage()
        self.client = client or sending.FakeCompletionClient(
            [sending._success(cost="0.01") for _ in range(5)]
        )
        self.drafts = ChatDraftService(self.fx.drafts)
        self.controller = ChatSessionController(
            cast(ft.Page, self.page),
            self.fx.validator,
            self.fx.service,
            cast(
                ModelCatalogService,
                ui.FakeCatalogService(
                    ModelCatalog(
                        free_models=(), paid_models=(self.fx.model,), available=True
                    )
                ),
            ),
            self.fx.budgets,
            self.fx.sender(self.client),
            self.drafts,
            on_lock=AsyncMock(),
            on_replace_key=AsyncMock(),
            on_storage_error=lambda _message: None,
            data_access=self.fx.access,
            credits_reader=credits_reader,
        )
        case.addCleanup(self.controller.dispose)
        updater = patch.object(ft.Control, "update")
        updater.start()
        case.addCleanup(updater.stop)
        await self.controller.activate(
            sending.TEST_CREDENTIAL,
            sending.KeyValidityState.VALID,
            sending.KeyLimitInfo.from_validated_remaining(None),
        )
        return self

    def view(self):
        result = self.controller._workspace_view
        assert result is not None
        return result

    def dialog(self):
        result = self.page.dialogs[-1]
        assert isinstance(result, ft.AlertDialog)
        return result

    def budget(self, chat_id="a"):
        value = self.fx.messages.get_chat_budget(chat_id)
        assert value is not None
        return value

    def warning_buttons(self):
        column = self.dialog().actions[0]
        assert isinstance(column, ft.Column)
        buttons = column.controls
        assert len(buttons) == 3
        assert all(isinstance(button, (ft.Button, ft.TextButton)) for button in buttons)
        return buttons

    async def click(self, control):
        callback = control.on_click
        assert callback is not None
        result = callback(ft.Event(name="click", control=control))
        if inspect.isawaitable(result):
            await result


class BudgetWarningUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = await UiHarness().setup(self)

    async def test_automatic_paid_choice_still_warns_and_double_confirmation_sends_once(
        self,
    ):
        h = self.h
        await h.controller.set_paid_without_confirmation("a", True)
        h.view().restore_editor("synthetic budget request")
        await h.controller.submit_message("synthetic budget request")
        buttons = h.warning_buttons()
        self.assertEqual(h.client.calls, [])
        self.assertEqual(h.fx.messages.list_turns("a"), [])
        old = buttons[1]
        await h.click(old)
        await h.click(old)
        self.assertEqual(len(h.client.calls), 1)
        self.assertEqual(h.budget("a").cost_limit_usd, Decimal("0.011"))
        self.assertEqual(h.page.dialogs, [])

    async def test_cancel_and_system_dismiss_preserve_draft_without_reservation(self):
        h = self.h
        for language, action in (("en", "cancel"), ("ru", "dismiss")):
            with self.subTest(language=language, action=action):
                set_language(language)
                h.controller.handle_language_change()
                exact = "  synthetic draft\n🙂 "
                h.view().restore_editor(exact)
                await h.controller.submit_message(exact)
                dialog = h.dialog()
                if action == "cancel":
                    await h.click(h.warning_buttons()[0])
                else:
                    callback = dialog.on_dismiss
                    assert callback is not None
                    h.page.pop_dialog()
                    cast(Callable[[ft.Event], None], callback)(
                        ft.Event(name="dismiss", control=dialog)
                    )
                self.assertEqual(h.client.calls, [])
                self.assertEqual(h.fx.messages.list_turns("a"), [])
                self.assertEqual(h.fx.drafts.get_draft("a").text, exact)
                self.assertEqual(h.view().editor_value, exact)
                self.assertEqual(h.budget("a").cost_reserved_usd, Decimal("0"))

    async def test_edit_opens_originating_chat_and_never_sends_after_save(self):
        h = self.h
        exact = "synthetic unsent while changing limit"
        h.view().restore_editor(exact)
        await h.controller.submit_message(exact)
        await h.click(h.warning_buttons()[2])
        self.assertEqual(h.controller._workspace_controller._limits_chat_id, "a")
        self.assertEqual(h.fx.drafts.get_draft("a").text, exact)
        await h.controller.submit_existing_chat_limits("100000", "64", "0.02")
        await h.controller.confirm_cost_increase()
        self.assertEqual(h.budget("a").cost_limit_usd, Decimal("0.02"))
        self.assertEqual(h.budget("b").cost_limit_usd, Decimal("10"))
        self.assertEqual(h.client.calls, [])
        self.assertEqual(h.fx.messages.list_turns("a"), [])
        self.assertEqual(h.view().editor_value, exact)

    async def test_old_warning_after_chat_change_and_lock_cannot_send(self):
        h = self.h
        await h.controller.submit_message("synthetic old request")
        old = h.warning_buttons()[1]
        await h.controller.select_chat("b")
        await h.click(old)
        self.assertEqual(h.client.calls, [])
        await h.controller.select_chat("a")
        await h.controller.submit_message("synthetic second request")
        second = h.warning_buttons()[1]
        await h.controller.lock_application()
        await h.click(second)
        self.assertEqual(h.client.calls, [])

    async def test_editing_draft_invalidates_confirm_and_keeps_new_text(self):
        h = self.h
        await h.controller.submit_message("synthetic old text")
        old = h.warning_buttons()[1]
        h.drafts.record_edit("a", "synthetic changed text")
        h.view().restore_editor("synthetic changed text")
        await h.click(old)
        self.assertEqual(h.client.calls, [])
        self.assertEqual(h.fx.messages.list_turns("a"), [])
        self.assertEqual(h.drafts.current("a").text, "synthetic changed text")

    async def test_retry_always_gets_the_required_warning(self):
        h = self.h
        h.client.results = [
            sending._known_error(ChatErrorType.RATE_LIMIT_EXCEEDED),
            sending._success(cost="0.01"),
        ]
        await h.controller.set_paid_without_confirmation("a", True)
        await h.controller.submit_message("synthetic retry request")
        await h.click(h.warning_buttons()[1])
        turn = h.fx.messages.list_turns("a")[0]
        self.assertEqual(len(h.client.calls), 1)
        await h.controller.request_retry_turn(turn.id)
        self.assertEqual(len(h.client.calls), 1)
        await h.click(h.warning_buttons()[1])
        self.assertEqual(len(h.client.calls), 2)
        self.assertEqual(len(h.fx.messages.list_turns("a")), 1)

    async def test_changed_limit_requires_new_dialog_and_old_callback_cannot_accept_it(
        self,
    ):
        h = self.h
        await h.controller.submit_message("synthetic changed limit")
        first_dialog = h.dialog()
        old_confirm = h.warning_buttons()[1]
        await h.fx.budgets.update_chat_limits(
            "a",
            token_limit=100_000,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("0.0109"),
        )
        await h.click(old_confirm)
        self.assertEqual(h.client.calls, [])
        self.assertIsNot(h.dialog(), first_dialog)
        self.assertEqual(h.fx.messages.list_turns("a"), [])
        await h.click(old_confirm)
        self.assertEqual(h.client.calls, [])
        await h.click(h.warning_buttons()[1])
        self.assertEqual(len(h.client.calls), 1)
