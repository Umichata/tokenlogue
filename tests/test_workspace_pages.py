"""Offline UI checks; no Flet session, application profile or network access."""

import asyncio
import sys
import unittest
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.account_balance import (  # noqa: E402
    AccountBalanceSnapshot,
    AccountBalanceState,
)
from chat.accounting import AccountingStatus, BudgetState, RemainingBudget  # noqa: E402
from chat.analytics import (  # noqa: E402
    AnalyticsFilter,
    RequestAttempt,
    build_analytics,
)
from chat.budget_consent import BudgetWarning  # noqa: E402
from chat.metrics import (  # noqa: E402
    ChatMetricsSnapshot,
    LastRequestMetrics,
    LastRequestState,
)
from chat.models import (  # noqa: E402
    CatalogModel,
    ChatMode,
    MessageRole,
    MessageStatus,
    ModelCatalog,
)
from chat.sending import MessageSendPreview  # noqa: E402
from i18n import configure_localization, localize_tree, set_language  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from providers.models import Currency, PriceUnit, ProviderId  # noqa: E402
from tests import test_chat_menu as menu_fixtures  # noqa: E402
from tests.test_chat_components import _message, _turn  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from tests.test_chat_view import _state  # noqa: E402
from ui.analytics_pages import SpendingPage, TokenUsagePage, _amount  # noqa: E402
from ui.chat_limits_view import (  # noqa: E402
    ChatLimitsForm,
    build_budget_warning_dialog,
)
from ui.chat_metrics import ChatMetricsStrip  # noqa: E402
from ui.message_history import _message_metadata  # noqa: E402
from ui.model_selection_view import ModelSelectionView, ModeSelectionView  # noqa: E402
from ui.provider_page import (  # noqa: E402
    ProviderCheckResult,
    ProviderPage,
    ProviderPresentation,
)
from ui.workspace_shell import WorkspacePage, WorkspaceShell  # noqa: E402


class WorkspacePagesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.patch = patch.object(ft.Control, "update", return_value=None)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.check = AsyncMock(return_value=ProviderCheckResult(True, True))
        self.save = AsyncMock(return_value=True)
        self.providers = ProviderPage(
            on_check=self.check,
            on_save=self.save,
            on_refresh=AsyncMock(),
            on_default=AsyncMock(),
        )

    def type_key(self, provider, value):
        card = self.providers.cards[provider]
        card.key_field.value = value
        callback = cast(Callable[[ft.Event], None], card.key_field.on_change)
        callback(ft.Event(name="change", control=card.key_field))
        return card

    async def test_unknown_or_mismatched_prefix_never_reaches_callback(self):
        for candidate in ("sk-or-v1-", "sk-or-vv-fake-ui-candidate", "INVALID"):
            card = self.type_key(ProviderId.OPENROUTER, candidate)
            self.assertTrue(card.check.disabled)
            await self.providers.check_candidate(ProviderId.OPENROUTER)
            await self.providers.save_candidate(ProviderId.OPENROUTER)
        self.check.assert_not_awaited()
        self.save.assert_not_awaited()

    async def test_unverified_save_is_explicit_and_has_preserved_inner_content(self):
        self.check.return_value = ProviderCheckResult(True, False)
        key = "sk-or-vv-fake-ui-UNVERIFIED"
        card = self.type_key(ProviderId.VSEGPT, "  " + key + "  ")
        await self.providers.save_candidate(ProviderId.VSEGPT)
        self.save.assert_not_awaited()
        await self.providers.check_candidate(ProviderId.VSEGPT)
        self.assertFalse(card.save.disabled)
        await self.providers.save_candidate(ProviderId.VSEGPT)
        self.save.assert_awaited_once_with(ProviderId.VSEGPT, key, True)
        self.assertEqual(card.key_field.value, "")
        self.assertTrue(card.key_field.password)

    async def test_failed_candidate_keeps_saved_provider_presentation(self):
        saved = ProviderPresentation(
            ProviderId.OPENROUTER,
            True,
            "connected",
            balance_amount=Decimal("-0.5"),
            balance_status="stale",
        )
        self.providers.set_provider(saved)
        self.check.return_value = ProviderCheckResult(False, False, "safe failure")
        card = self.type_key(ProviderId.OPENROUTER, "sk-or-v1-fake-ui-candidate")
        await self.providers.check_candidate(ProviderId.OPENROUTER)
        await self.providers.save_candidate(ProviderId.OPENROUTER)
        self.assertIs(card.presentation, saved)
        self.assertTrue(card.save.disabled)
        self.save.assert_not_awaited()
        self.assertIn("-0,5", str(card.balance.value))

    async def test_private_clear_rejects_late_check_and_masks_revealed_key(self):
        started, finish = asyncio.Event(), asyncio.Event()

        async def delayed(*args):
            started.set()
            await finish.wait()
            return ProviderCheckResult(True, True, "late result")

        self.providers._on_check = delayed
        card = self.type_key(ProviderId.OPENROUTER, "sk-or-v1-fake-ui-candidate")
        reveal = cast(Callable[[ft.Event], None], card.reveal.on_click)
        reveal(ft.Event(name="click", control=card.reveal))
        self.assertFalse(card.key_field.password)
        task = asyncio.create_task(
            self.providers.check_candidate(ProviderId.OPENROUTER)
        )
        await started.wait()
        self.providers.clear_private()
        finish.set()
        await task
        self.assertEqual(card.key_field.value, "")
        self.assertEqual(card.message.value, "")
        self.assertIsNone(card.checked_value)
        self.assertIsNone(card.result)
        self.assertTrue(card.key_field.password)

    async def test_language_switch_preserves_candidate_and_mask(self):
        card = self.type_key(ProviderId.VSEGPT, "sk-or-vv-fake-ui-candidate")
        set_language("en")
        self.providers.sync_language()
        self.assertEqual(card.key_field.value, "sk-or-vv-fake-ui-candidate")
        self.assertTrue(card.key_field.password)
        self.assertIn("Detected VSEGPT", str(card.detected.value))

    async def test_shell_retains_home_and_does_not_steal_active_analytics(self):
        page = SimpleNamespace(
            platform=ft.PagePlatform.LINUX, width=1200, update=lambda: None
        )
        home, providers, tokens, spending = [ft.Container() for _ in range(4)]
        on_navigate = AsyncMock(return_value=True)
        shell = WorkspaceShell(
            cast(ft.Page, page),
            home,
            providers,
            tokens,
            spending,
            on_navigate=on_navigate,
        )
        self.assertTrue(shell.rail.visible)
        await shell.select(WorkspacePage.TOKENS)
        new_home = ft.Container()
        shell.set_home(new_home)
        self.assertIs(shell._content.content, tokens)
        await shell.select(WorkspacePage.HOME)
        self.assertIs(shell._content.content, new_home)
        shell.resize(360)
        self.assertTrue(shell.navigation.visible)
        self.assertFalse(shell.rail.visible)
        on_navigate.return_value = False
        await shell.select(WorkspacePage.PROVIDERS)
        self.assertEqual(shell.selected_page, WorkspacePage.HOME)
        shell.clear_private()
        self.assertFalse(await shell.select(WorkspacePage.SPENDING))

    async def test_analytics_separates_currencies_and_clears_all_snapshots(self):
        now = datetime(2026, 11, 15, 1, tzinfo=UTC)
        attempts = [
            RequestAttempt(
                1,
                "turn1",
                "chat1",
                requested_model_id="same/model",
                sent_at=now,
                chronology_known=True,
                prompt_tokens=3,
                total_tokens=4,
                usage_source="api",
                cost=Decimal("0.1"),
                cost_source="api",
            ),
            RequestAttempt(
                2,
                "turn2",
                "chat2",
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                requested_model_id="same/model",
                sent_at=now,
                chronology_known=True,
                prompt_tokens=3,
                total_tokens=4,
                usage_source="api",
            ),
            RequestAttempt(3, "turn3", "chat3", cost=Decimal("0.2"), cost_source="api"),
        ]
        snapshot = build_analytics(
            attempts, AnalyticsFilter(period="all", timezone_name="UTC"), now
        )
        tokens = TokenUsagePage(on_filter=AsyncMock())
        spending = SpendingPage(on_filter=AsyncMock())
        tokens.set_snapshot(snapshot)
        spending.set_snapshot(snapshot)
        self.assertEqual({c.currency for c in spending._charts}, {"USD", "RUB"})
        self.assertEqual(len(snapshot.usage_rows), 3)
        self.assertEqual(snapshot.undated_requests, 1)
        self.assertEqual(sum(p.unknown_cost_requests for p in snapshot.spending), 1)
        charts = list(spending._charts)
        tokens.clear_private()
        spending.clear_private()
        self.assertIsNone(tokens._snapshot)
        self.assertIsNone(spending._snapshot)
        self.assertEqual(tokens._body.controls, [])
        self.assertEqual(spending._body.controls, [])
        self.assertTrue(all(chart.canvas.shapes == [] for chart in charts))

    async def test_empty_snapshot_and_both_languages_build(self):
        for language in ("ru", "en"):
            set_language(language)
            for page_type in (TokenUsagePage, SpendingPage):
                page = page_type(on_filter=AsyncMock())
                page.set_snapshot(build_analytics([], AnalyticsFilter()))
                page.sync_language()
                self.assertTrue(page._body.controls)

    async def test_language_change_replaces_mounted_frozen_filter_options(self):
        page = SpendingPage(
            on_filter=AsyncMock(), filters=AnalyticsFilter(period="all")
        )
        for selector in (page.period, page.provider, page.model):
            for option in selector.options:
                object.__setattr__(option, "_frozen", True)
        set_language("en")
        localize_tree(page.control)
        page.sync_language()
        self.assertEqual(page.period.value, "all")
        self.assertEqual(page.period.options[0].text, "7 days")
        self.assertEqual(page.provider.options[0].text, "All providers")
        self.assertEqual(page.model.options[0].text, "All models")

    async def test_analytics_money_display_rounds_without_losing_nonzero_amounts(self):
        exact = Decimal("106.25") / Decimal(30)
        for language, expected in (("en", "3.541667 RUB"), ("ru", "3,541667 RUB")):
            set_language(language)
            self.assertEqual(_amount(exact, "RUB"), expected)
            self.assertIn("<", _amount(Decimal("0.0000000001"), "RUB"))
            self.assertNotEqual(
                _amount(Decimal("0.0000000001"), "RUB"), _amount(Decimal(0), "RUB")
            )
            self.assertEqual(_amount(Decimal(0), "RUB"), "0 RUB")
        self.assertEqual(exact, Decimal("106.25") / Decimal(30))

    async def test_rub_metrics_use_only_rub_and_keep_tokens_with_unknown_cost(self):
        for language in ("ru", "en"):
            set_language(language)
            strip = ChatMetricsStrip()
            strip.set_metrics(
                ChatMetricsSnapshot(
                    "chat",
                    ChatMode.PAID,
                    RemainingBudget(
                        None, None, False, cost=Decimal("50"), currency=Currency.RUB
                    ),
                    LastRequestMetrics(
                        LastRequestState.UNKNOWN,
                        prompt_tokens=3,
                        completion_tokens=2,
                        total_tokens=5,
                        currency=Currency.RUB,
                        provider_id=ProviderId.VSEGPT,
                        usage_source="api",
                    ),
                    currency=Currency.RUB,
                    provider_id=ProviderId.VSEGPT,
                    account_balance=AccountBalanceSnapshot(
                        AccountBalanceState.CURRENT,
                        balance_amount=Decimal("-2"),
                        currency=Currency.RUB,
                        provider_id=ProviderId.VSEGPT,
                    ),
                )
            )
            label = str(strip.values.value)
            self.assertIn("50 RUB", label)
            self.assertIn("5", label)
            self.assertIn("-2 RUB", str(strip.account.value))
            self.assertNotIn("USD", label + str(strip.account.value))
            self.assertEqual(strip.control.width, float("inf"))

    async def test_unknown_price_budget_dialog_has_three_actions_and_no_fake_zero(self):
        set_language("en")
        warning = BudgetWarning(
            None,
            None,
            None,
            None,
            None,
            currency=Currency.RUB,
            limit=Decimal("100"),
            remaining=Decimal("50"),
            unknown_pricing=True,
        )
        preview = MessageSendPreview(
            "chat",
            None,
            "model",
            "Model",
            10,
            20,
            30,
            None,
            None,
            None,
            None,
            None,
            currency=Currency.RUB,
            provider_id=ProviderId.VSEGPT,
            budget_warning=warning,
            unknown_pricing=True,
        )
        dialog = build_budget_warning_dialog(
            preview, AsyncMock(), lambda: None, AsyncMock()
        )
        buttons = cast(ft.Column, dialog.actions[0]).controls
        self.assertEqual(len(buttons), 3)
        assert dialog.content is not None
        labels = " ".join(
            str(item.value or "")
            for item in walk(dialog.content)
            if isinstance(item, ft.Text)
        )
        self.assertIn("50 RUB", labels)
        self.assertIn("Cost is unknown", labels)
        self.assertNotIn("0 RUB", labels.replace("50 RUB", ""))
        self.assertNotIn("USD", labels)
        form = ChatLimitsForm(ChatMode.PAID, AsyncMock(), currency=Currency.RUB)
        assert form.cost_limit is not None
        self.assertEqual(form.cost_limit.value, "")
        self.assertIn("RUB", str(form.cost_limit.label))

    async def test_model_unknown_unit_never_looks_free_and_usage_survives_unknown_cost(
        self,
    ):
        set_language("en")
        model = CatalogModel(
            "shared/model",
            "A long model name " * 15,
            Decimal(0),
            Decimal(0),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
            pricing_is_complete=False,
        )
        view = ModelSelectionView(ChatMode.PAID, (model,), AsyncMock(), AsyncMock())
        labels = " ".join(
            str(item.value or "")
            for item in walk(view.control)
            if isinstance(item, ft.Text)
        )
        self.assertIn("VSEGPT", labels)
        self.assertIn("not a free model", labels)
        self.assertNotIn("USD", labels)
        turn = replace(
            _turn(accounting_status=AccountingStatus.UNKNOWN, error_type=None),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            prompt_tokens=8,
            completion_tokens=3,
            total_tokens=11,
            usage_source="api",
        )
        message = _message(
            "id", MessageRole.ASSISTANT, MessageStatus.SENT, "fake answer"
        )
        metadata = _message_metadata(message, turn)
        self.assertIn(("Input tokens", "8"), metadata)
        self.assertIn(("Total", "11"), metadata)
        self.assertNotIn(
            "USD", " ".join(str(value) for pair in metadata for value in pair)
        )

    async def test_secret_field_repr_and_keyboard_settings_do_not_expose_candidate(
        self,
    ):
        candidate = "sk-or-vv-fake-ui-private-candidate"
        card = self.type_key(ProviderId.VSEGPT, candidate)
        self.assertNotIn(candidate, repr(card.key_field))
        self.assertNotIn(candidate, repr(self.providers.control))
        for name in (
            "enable_suggestions",
            "enable_ime_personalized_learning",
            "enable_stylus_handwriting",
            "smart_dashes_type",
            "smart_quotes_type",
        ):
            self.assertFalse(getattr(card.key_field, name))

    async def test_unverified_unknown_pricing_chat_can_reach_explicit_review(self):
        model = CatalogModel(
            "same/model",
            "Model",
            Decimal(0),
            Decimal(0),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_is_complete=False,
            pricing_unit=PriceUnit.UNKNOWN,
        )
        mode = ModeSelectionView(
            ModelCatalog((), (model,), True),
            KeyValidityState.UNVERIFIED,
            KeyLimitInfo.unknown(),
            AsyncMock(),
            AsyncMock(),
        )
        self.assertFalse(mode.paid_button.disabled)
        self.assertTrue(mode.free_button.disabled)
        fixture = menu_fixtures.ChatMenuTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        chat = replace(
            fixture.chat,
            mode=ChatMode.PAID,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
            pricing_snapshot_complete=False,
        )
        state = _state(chat)
        budget = replace(
            state.budget,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            cost_limit_usd=None,
            cost_limit=Decimal(100),
            state=BudgetState.ACCOUNTING_UNKNOWN,
        )
        state = replace(
            state,
            budget=budget,
            remaining=RemainingBudget(
                500, None, True, cost=Decimal(0), currency=Currency.RUB
            ),
        )
        view = fixture.view(
            chat,
            state,
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
        )
        self.addCleanup(view.dispose)
        self.assertTrue(view._sending_allowed(state))
        self.assertFalse(
            view._sending_allowed(
                replace(
                    state,
                    remaining=RemainingBudget(0, None, True, currency=Currency.RUB),
                )
            )
        )
        known_chat = replace(
            chat,
            provider_id=ProviderId.OPENROUTER,
            currency=Currency.USD,
            pricing_snapshot_complete=True,
            pricing_unit=PriceUnit.TOKEN,
        )
        self.assertFalse(view._sending_allowed(replace(state, chat=known_chat)))

    async def test_drawer_state_tracks_native_dismiss_select_and_explicit_close(self):
        fixture = menu_fixtures.ChatMenuTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        view = fixture.view()
        self.addCleanup(view.dispose)
        with patch.object(fixture.page, "show_drawer", new=AsyncMock()) as show:
            with patch.object(fixture.page, "close_drawer", new=AsyncMock()) as close:
                self.assertFalse(view.drawer_open)
                await view._toggle_sidebar(
                    ft.Event(name="click", control=view.sidebar_button)
                )
                self.assertTrue(view.drawer_open)
                show.assert_awaited_once()
                opened_drawer = fixture.page.drawer
                view._render_layout()
                self.assertIs(fixture.page.drawer, opened_drawer)
                self.assertTrue(view.drawer_open)
                await view.close_drawer()
                self.assertFalse(view.drawer_open)
                close.assert_awaited_once()
                await view.close_drawer()
                close.assert_awaited_once()
                await view._show_drawer()
                drawer = fixture.page.drawer
                assert drawer is not None
                dismissed = cast(Callable[[ft.Event], None], drawer.on_dismiss)
                dismissed(ft.Event(name="dismiss", control=drawer))
                self.assertFalse(view.drawer_open)
                await view._show_drawer()
                tile = view._build_chat_tile(fixture.chat)
                click = cast(Callable[[ft.Event], Awaitable[None]], tile.on_click)
                await click(ft.Event(name="click", control=tile))
                self.assertFalse(view.drawer_open)
                self.assertEqual(close.await_count, 2)
                self.assertIn(("select", (fixture.chat.id,)), fixture.calls)

    async def test_large_model_history_renders_in_bounded_pages(self):
        now = datetime(2026, 11, 15, 1, tzinfo=UTC)
        snapshot = build_analytics(
            [
                RequestAttempt(
                    index,
                    f"turn{index}",
                    "chat",
                    requested_model_id=f"model/{index}",
                    sent_at=now,
                    chronology_known=True,
                    total_tokens=index,
                    usage_source="api",
                    cost=Decimal("0"),
                    cost_source="api",
                )
                for index in range(250)
            ],
            AnalyticsFilter(timezone_name="UTC"),
            now,
        )
        page = TokenUsagePage(on_filter=AsyncMock())
        page.set_snapshot(snapshot)
        self.assertEqual(len(snapshot.usage_rows), 250)
        self.assertLess(len(page._body.controls), 120)
        self.assertTrue(
            any(isinstance(control, ft.TextButton) for control in page._body.controls)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
