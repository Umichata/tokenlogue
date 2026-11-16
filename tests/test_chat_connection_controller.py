"""Explicit connection changes use real temporary repositories and offline catalogues."""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import ChatBudgetService, ChatLimitConfiguration  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    ChatMode,
    ModelCatalog,
)
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from chat_controller import ChatSessionController, ProviderProfiles  # noqa: E402
from i18n import configure_localization  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from providers.models import Currency, PriceUnit, ProviderId, detect_key  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests.test_chat_menu import texts, walk  # noqa: E402
from tests.test_chat_ui_integration import FakeKeyValidator, FakePage  # noqa: E402
from tests.test_provider_sending import FakeProviderProfiles  # noqa: E402


class _Catalogues:
    def __init__(self) -> None:
        self.vsegpt = CatalogModel(
            id="shared/model",
            name="Learning assistant",
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
            pricing_is_complete=False,
            context_length=8192,
            provider_max_completion_tokens=1024,
        )
        self.rows: dict[ProviderId, tuple[CatalogModel, ...]] = {
            ProviderId.OPENROUTER: (FREE_ROUTER_MODEL,),
            ProviderId.VSEGPT: (self.vsegpt,),
        }
        self.pause_provider: ProviderId | None = None
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[ProviderId] = []

    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...]:
        provider = detect_key(api_key)
        assert provider is not None
        self.calls.append(provider)
        if provider is self.pause_provider:
            self.entered.set()
            await self.release.wait()
        return self.rows[provider]


class _NoCompletion:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Configuring a connection must never generate")


class ChatConnectionControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = AuthDatabase(temporary.name)
        self.repo = SqliteChatRepository(database.path)
        self.messages = SqliteMessageRepository(database.path)
        self.drafts_repo = SqliteDraftRepository(database.path)
        self.chats = ChatService(self.repo)
        self.budgets = ChatBudgetService(self.messages)
        self.catalogues = _Catalogues()
        self.catalog = ModelCatalogService(self.catalogues)
        self.profiles = FakeProviderProfiles()
        self.profiles.keys[ProviderId.VSEGPT] = "sk-or-visLOCAL_SYNTHETIC_FIXTURE_7722"
        self.validator = FakeKeyValidator()
        self.completion = _NoCompletion()
        self.sender = MessageSendingService(
            self.chats, self.messages, self.completion, self.catalogues, self.validator
        )
        self.drafts = ChatDraftService(self.drafts_repo)
        catalog = await self.catalog.get_catalog(
            self.profiles.keys[ProviderId.OPENROUTER]
        )
        self.original = await self.chats.create_chat_with_limits(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            token_limit=8192,
            max_completion_tokens=512,
            cost_limit=Decimal("0"),
        )
        self.other = await self.chats.create_chat_with_limits(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            token_limit=8192,
            max_completion_tokens=512,
            cost_limit=Decimal("0"),
        )
        original = await self.chats.get_chat(self.original.id)
        other = await self.chats.get_chat(self.other.id)
        assert original is not None and other is not None
        self.original, self.other = original, other
        self.page = FakePage()
        self.settings: list[ProviderId] = []
        self.errors: list[str] = []

        async def noop() -> None:
            pass

        async def settings(provider: ProviderId) -> None:
            self.settings.append(provider)
            await self.controller.prepare_navigation()

        self.controller = ChatSessionController(
            cast(ft.Page, self.page),
            self.validator,
            self.chats,
            self.catalog,
            self.budgets,
            self.sender,
            self.drafts,
            on_lock=noop,
            on_replace_key=noop,
            on_storage_error=self.errors.append,
            provider_profiles=cast(ProviderProfiles, self.profiles),
            on_provider_settings_for=settings,
        )
        await self.controller.activate(
            self.profiles.keys[ProviderId.OPENROUTER],
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )
        await asyncio.gather(*tuple(self.controller._provider_tasks))
        await self.controller.select_chat(self.original.id)
        assert self.controller._workspace_view is not None
        assert self.controller._workspace_view.composer is not None
        assert self.controller._workspace_state is not None
        self.assertEqual(self.controller._workspace_state.chat.id, self.original.id)
        self.controller._workspace_view.composer.set_value("Keep this draft exact.  ")
        await self.controller.flush_drafts()

    async def asyncTearDown(self) -> None:
        self.catalogues.release.set()
        self.controller.dispose()
        await asyncio.sleep(0)

    async def click(self, control) -> None:
        result = control.on_click(ft.Event(name="click", control=control))
        if inspect.isawaitable(result):
            await result

    async def review(self, provider: ProviderId = ProviderId.VSEGPT) -> ft.AlertDialog:
        await self.controller.request_change_provider(self.original.id)
        selector = self.controller._provider_switch_dialog
        self.assertIsNotNone(
            selector,
            {
                "screen": self.controller._screen,
                "workspace": self.controller._workspace_view is not None,
                "busy": self.controller._workspace_controller.busy,
                "pending": self.controller._dialog_request_pending,
                "selected": self.controller.selected_chat_id == self.original.id,
                "change": self.controller._connection_change is not None,
                "errors": self.errors,
            },
        )
        assert selector is not None
        await self.click(selector.provider_buttons[provider])
        headings = [
            getattr(control.value, "key", None)
            for control in walk(self.page.controls[0])
            if isinstance(control, ft.Text)
            and control.theme_style is ft.TextThemeStyle.HEADLINE_MEDIUM
        ]
        if provider is ProviderId.VSEGPT:
            self.assertEqual(self.controller._screen.value, "model_selection")
            self.assertIs(self.controller._pending_mode, ChatMode.PAID)
        else:
            self.assertEqual(headings, ["connection.change_provider"])
        self.assertEqual(len(await self.chats.list_chats()), 2)
        mode = ChatMode.PAID if provider is ProviderId.VSEGPT else ChatMode.FREE
        await self.controller.select_chat_mode(mode)
        model = (
            self.catalogues.vsegpt
            if provider is ProviderId.VSEGPT
            else FREE_ROUTER_MODEL
        )
        await self.controller.select_chat_model(model)
        await self.controller.submit_new_chat_limits(
            "8192", "512", "120" if mode is ChatMode.PAID else None
        )
        dialog = self.controller._connection_dialog
        assert dialog is not None
        return dialog

    async def assert_original(self) -> None:
        current = await self.chats.get_chat(self.original.id)
        self.assertEqual(current, self.original)
        self.assertEqual(self.controller.selected_chat_id, self.original.id)
        self.assertEqual(self.completion.calls, 0)

    async def test_review_and_round_trip_preserve_identity_draft_and_default(
        self,
    ) -> None:
        dialog = await self.review()
        await self.assert_original()
        self.assertIn("VSEGPT", texts(dialog))
        self.assertNotIn(self.profiles.keys[ProviderId.VSEGPT], repr(dialog))
        await self.click(dialog.actions[-1])
        current = await self.chats.get_chat(self.original.id)
        assert current is not None
        self.assertEqual(
            (
                current.id,
                current.provider_id,
                current.currency,
                current.connection_revision,
            ),
            (self.original.id, ProviderId.VSEGPT, Currency.RUB, 1),
        )
        self.assertEqual(current.title, self.original.title)
        self.assertFalse(current.paid_without_confirmation)
        self.assertEqual(self.profiles.default_provider, ProviderId.OPENROUTER)
        self.assertEqual(await self.chats.get_chat(self.other.id), self.other)
        self.assertEqual(
            (await self.drafts.load(self.original.id)).text, "Keep this draft exact.  "
        )
        dialog = await self.review(ProviderId.OPENROUTER)
        await self.click(dialog.actions[-1])
        returned = await self.chats.get_chat(self.original.id)
        assert returned is not None
        self.assertEqual(
            (returned.provider_id, returned.connection_revision),
            (ProviderId.OPENROUTER, 2),
        )
        self.assertEqual(
            (
                await self.budgets.get_chat_budget(
                    self.original.id, provider_id=ProviderId.VSEGPT
                )
            ).cost_limit,
            Decimal("120"),
        )
        self.assertEqual(self.completion.calls, 0)

    async def test_cancel_at_each_stage_and_current_choice_do_not_change_chat(
        self,
    ) -> None:
        await self.controller.request_change_provider(self.original.id)
        await self.controller.select_connection_provider(ProviderId.OPENROUTER)
        await self.assert_original()
        await self.controller.request_change_provider(self.original.id)
        await self.controller.handle_application_back()
        await self.assert_original()
        await self.controller.request_change_provider(self.original.id)
        await self.controller.select_connection_provider(ProviderId.VSEGPT)
        await self.controller.cancel_new_chat()
        await self.assert_original()
        dialog = await self.review()
        await self.click(dialog.actions[0])
        await self.assert_original()

    async def test_missing_key_opens_only_target_card_and_return_needs_new_choice(
        self,
    ) -> None:
        old_key = self.profiles.keys.pop(ProviderId.VSEGPT)
        await self.controller.request_change_provider(self.original.id)
        await self.controller.select_connection_provider(ProviderId.VSEGPT)
        missing = self.controller._connection_dialog
        assert missing is not None
        await self.click(missing.actions[-1])
        self.assertEqual(self.settings, [ProviderId.VSEGPT])
        self.profiles.keys[ProviderId.VSEGPT] = old_key
        self.profiles.revisions[ProviderId.VSEGPT] += 1
        await self.controller.resume_home()
        self.assertIsNotNone(self.controller._provider_switch_dialog)
        await self.assert_original()
        await self.controller.cancel_connection_change()
        await self.assert_original()

    async def test_replaced_key_revokes_open_confirmation_without_resetting_profile(
        self,
    ) -> None:
        dialog = await self.review()
        self.profiles.keys[ProviderId.VSEGPT] = (
            "sk-or-visANOTHER_SYNTHETIC_FIXTURE_8822"
        )
        self.profiles.revisions[ProviderId.VSEGPT] += 1
        await self.controller.refresh_provider_state()
        await self.click(dialog.actions[-1])
        await self.assert_original()
        self.assertTrue(self.controller.session_active)

    async def test_late_catalogue_cannot_switch_newly_selected_chat(self) -> None:
        self.catalogues.pause_provider = ProviderId.VSEGPT
        await self.controller.request_change_provider(self.original.id)
        task = asyncio.create_task(
            self.controller.select_connection_provider(ProviderId.VSEGPT)
        )
        await asyncio.wait_for(self.catalogues.entered.wait(), timeout=2)
        await self.controller.select_chat(self.other.id)
        self.catalogues.release.set()
        await task
        self.assertEqual(self.controller.selected_chat_id, self.other.id)
        self.assertEqual(await self.chats.get_chat(self.original.id), self.original)
        self.assertEqual(await self.chats.get_chat(self.other.id), self.other)
        self.assertIsNone(self.controller._connection_change)
        self.assertEqual(self.completion.calls, 0)

    async def test_missing_model_or_transaction_failure_is_atomic(self) -> None:
        dialog = await self.review()
        self.catalogues.rows[ProviderId.VSEGPT] = ()
        await self.click(dialog.actions[-1])
        await self.assert_original()
        await self.controller.cancel_connection_change()
        self.catalogues.rows[ProviderId.VSEGPT] = (self.catalogues.vsegpt,)
        dialog = await self.review()
        with patch.object(
            self.repo,
            "switch_connection",
            side_effect=sqlite3.OperationalError("private fixture failure"),
        ):
            await self.click(dialog.actions[-1])
        await self.assert_original()
        self.assertNotIn(
            "private fixture failure", "\n".join(texts(self.page.controls[0]))
        )

    async def _assert_confirmation_catalogue_failure_is_atomic(
        self, catalogue: ModelCatalog, error_key: str
    ) -> None:
        dialog = await self.review()
        view = self.controller._new_limits_view
        assert view is not None
        draft_before = await self.drafts.load(self.original.id)
        budgets_before = {
            provider: await self.budgets.get_chat_budget(
                self.original.id, provider_id=provider
            )
            for provider in ProviderId
        }
        with (
            patch.object(self.catalog, "get_catalog", return_value=catalogue),
            patch.object(self.sender, "switch_chat_connection") as switch,
        ):
            await self.click(dialog.actions[-1])
        switch.assert_not_awaited()
        await self.assert_original()
        self.assertEqual(await self.drafts.load(self.original.id), draft_before)
        self.assertEqual(
            {
                provider: await self.budgets.get_chat_budget(
                    self.original.id, provider_id=provider
                )
                for provider in ProviderId
            },
            budgets_before,
        )
        self.assertIsNone(self.controller._connection_dialog)
        self.assertFalse(self.controller._workspace_controller.busy)
        self.assertFalse(self.controller._operation_lock.locked())
        self.assertFalse(view.form.submit_button.disabled)
        self.assertTrue(view.form.error.visible)
        self.assertEqual(getattr(view.form.error.value, "key", None), error_key)

    async def test_catalogue_unavailable_during_confirmation_keeps_connection(
        self,
    ) -> None:
        await self._assert_confirmation_catalogue_failure_is_atomic(
            ModelCatalog((), (), available=False), "connection.catalog_unavailable"
        )

    async def test_model_missing_from_available_confirmation_catalogue_keeps_connection(
        self,
    ) -> None:
        await self._assert_confirmation_catalogue_failure_is_atomic(
            ModelCatalog((), (), available=True), "service.model_missing"
        )

    async def test_lock_revokes_old_confirmation_and_reopen_keeps_original_draft(
        self,
    ) -> None:
        dialog = await self.review()
        self.controller.begin_lock()
        await self.click(dialog.actions[-1])
        self.assertIsNone(self.controller._connection_change)
        self.assertEqual(await self.chats.get_chat(self.original.id), self.original)
        await self.controller.activate(
            self.profiles.keys[ProviderId.OPENROUTER],
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )
        await self.controller.select_chat(self.original.id)
        self.assertEqual(
            (await self.drafts.load(self.original.id)).text, "Keep this draft exact.  "
        )
        self.assertEqual(self.completion.calls, 0)

    async def test_refresh_retries_a_connection_changed_between_chat_and_budget_reads(
        self,
    ) -> None:
        catalog = await self.catalog.get_catalog(self.profiles.keys[ProviderId.VSEGPT])
        original_read = self.budgets.get_chat_budget
        changed = False
        scopes: list[ProviderId | None] = []

        async def read(chat_id: str, *, provider_id: ProviderId | None = None):
            nonlocal changed
            scopes.append(provider_id)
            if not changed:
                changed = True
                await self.sender.switch_chat_connection(
                    chat_id,
                    expected_revision=0,
                    model=self.catalogues.vsegpt,
                    mode=ChatMode.PAID,
                    catalog=catalog,
                    key_validity=KeyValidityState.UNVERIFIED,
                    key_limit=KeyLimitInfo.unknown(),
                    configuration=ChatLimitConfiguration(
                        8192, 512, None, Decimal("120"), Currency.RUB
                    ),
                )
            return await original_read(chat_id, provider_id=provider_id)

        with patch.object(self.budgets, "get_chat_budget", side_effect=read):
            await self.controller._show_workspace(
                expected_generation=self.controller.session_generation
            )
        state = self.controller._workspace_state
        view = self.controller._workspace_view
        assert (
            state is not None and view is not None and view._selected_chat is not None
        )
        self.assertEqual(scopes, [ProviderId.OPENROUTER, ProviderId.VSEGPT])
        self.assertEqual(state.chat.provider_id, ProviderId.VSEGPT)
        self.assertEqual(state.budget.provider_id, ProviderId.VSEGPT)
        self.assertEqual(state.chat.connection_revision, 1)
        self.assertEqual(view._selected_chat, state.chat)
        self.assertEqual(self.controller.current_provider, ProviderId.VSEGPT)
        self.assertEqual(self.completion.calls, 0)


if __name__ == "__main__":
    unittest.main()
