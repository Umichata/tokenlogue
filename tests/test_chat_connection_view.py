"""Provider choice and confirmation remain public, explicit and one-shot."""

from __future__ import annotations

import inspect
import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.models import CatalogModel, ChatMode  # noqa: E402
from i18n import configure_localization, money, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from providers.models import Currency, PriceUnit, ProviderId  # noqa: E402
from tests.test_chat_menu import texts  # noqa: E402
from tests.test_chat_view import _chat, _state  # noqa: E402
from ui.chat_connection_view import (  # noqa: E402
    ProviderSwitchDialog,
    build_connection_confirmation,
    build_missing_provider_key_dialog,
)
from ui.chat_limits_view import NewChatLimitsView  # noqa: E402


class ChatConnectionViewTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.calls = []
        self.chat = _chat()
        self.model = CatalogModel(
            id="shared/model",
            name="A target model",
            prompt_price_per_token=Decimal(0),
            completion_price_per_token=Decimal(0),
            context_length=8192,
            pricing_is_complete=False,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
        )

    async def click(self, button):
        result = button.on_click(ft.Event(name="click", control=button))
        if inspect.isawaitable(result):
            await result

    async def dismiss(self, dialog):
        handler = dialog.on_dismiss
        assert handler is not None
        result = handler(ft.Event(name="dismiss", control=dialog))
        if inspect.isawaitable(result):
            await result

    async def select(self, provider):
        self.calls.append(provider)

    async def cancel(self):
        self.calls.append("cancel")

    async def confirm(self):
        self.calls.append("confirm")

    async def test_choice_has_two_services_and_old_selection_is_inert(self):
        dialog = ProviderSwitchDialog(ProviderId.OPENROUTER, self.select, self.cancel)
        self.assertEqual(set(dialog.provider_buttons), set(ProviderId))
        self.assertNotIn("All", texts(dialog.control))
        self.assertNotIn("Все", texts(dialog.control))
        await self.click(dialog.provider_buttons[ProviderId.VSEGPT])
        await self.click(dialog.provider_buttons[ProviderId.OPENROUTER])
        await self.dismiss(dialog.control)
        self.assertEqual(self.calls, [ProviderId.VSEGPT])

    async def test_cancel_or_dispose_prevents_queued_selection(self):
        for action in ("cancel", "dispose"):
            self.calls.clear()
            dialog = ProviderSwitchDialog(ProviderId.VSEGPT, self.select, self.cancel)
            if action == "cancel":
                await self.click(dialog.cancel_button)
            else:
                dialog.dispose()
            await self.click(dialog.provider_buttons[ProviderId.OPENROUTER])
            self.assertEqual(self.calls, ["cancel"] if action == "cancel" else [])

    async def test_missing_key_routes_only_chosen_service_and_dismiss_is_not_cancel(
        self,
    ):
        for language in ("en", "ru"):
            set_language(language)
            self.calls.clear()
            dialog = build_missing_provider_key_dialog(
                ProviderId.VSEGPT, self.select, self.cancel
            )
            self.assertNotIn("OpenRouter", " ".join(texts(dialog)))
            await self.click(dialog.actions[1])
            await self.dismiss(dialog)
            self.assertEqual(self.calls, [ProviderId.VSEGPT])

    async def test_confirmation_names_target_money_and_exact_context_scope(self):
        budget = replace(
            _state(self.chat).budget,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            cost_limit_usd=None,
            cost_used_usd=Decimal(0),
            cost_reserved_usd=Decimal(0),
            cost_limit=Decimal("180"),
            cost_used=Decimal("9.66"),
        )
        for language in ("en", "ru"):
            set_language(language)
            dialog = build_connection_confirmation(
                self.chat,
                self.model,
                ChatMode.PAID,
                Currency.RUB,
                Decimal("180"),
                self.confirm,
                self.cancel,
                token_limit=1000,
                budget=budget,
            )
            values = texts(dialog)
            self.assertIn("VSEGPT", values)
            self.assertNotIn("USD", " ".join(values))
            self.assertIn(money(Decimal("170.34"), Currency.RUB), values)
            self.assertIn(tr("connection.context_warning", provider="VSEGPT"), values)
            self.assertIn(tr("connection.no_send"), values)
            self.assertEqual(self.calls, [])
        await self.click(dialog.actions[1])
        await self.click(dialog.actions[1])
        await self.dismiss(dialog)
        self.assertEqual(self.calls, ["confirm"])

    async def test_restored_target_budget_form_keeps_shared_tokens_readonly(self):
        budget = replace(
            _state(self.chat).budget,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            cost_limit_usd=None,
            cost_used_usd=Decimal(0),
            cost_reserved_usd=Decimal(0),
            cost_limit=Decimal("180"),
            cost_used=Decimal("9.66"),
        )

        async def submit(tokens, completion, cost):
            self.calls.append((tokens, completion, cost))

        view = NewChatLimitsView(
            ChatMode.PAID,
            self.model,
            submit,
            self.cancel,
            initial_budget=budget,
            preserve_tokens=True,
            submit_label=tr("connection.review"),
        )
        self.assertTrue(view.form.token_limit.read_only)
        self.assertFalse(view.form.max_completion_tokens.read_only)
        self.assertEqual(view.form.token_limit.value, "1000")
        assert view.form.cost_limit is not None
        self.assertEqual(view.form.cost_limit.value, "180")
        view.form.max_completion_tokens.value = "128"
        view.form.cost_limit.value = "200"
        await view.form._submit_values()
        self.assertEqual(self.calls, [("1000", "128", "200")])
        self.assertEqual(budget.cost_used, Decimal("9.66"))
