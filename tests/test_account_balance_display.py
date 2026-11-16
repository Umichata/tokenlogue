"""Account API states render in both chat modes without inventing money."""

import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import flet as ft
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.provider_router import ProviderRouter  # noqa: E402
from app import AppController  # noqa: E402
from auth.models import KeyLimitInfo  # noqa: E402
from chat.account_balance import (  # noqa: E402
    AccountBalanceSnapshot,
    AccountBalanceState,
)
from chat.accounting import RemainingBudget  # noqa: E402
from chat.metrics import (  # noqa: E402
    ChatMetricsSnapshot,
    LastRequestMetrics,
    LastRequestState,
)
from chat.models import ChatMode  # noqa: E402
from i18n import money, set_language  # noqa: E402
from providers.creation import NewChatPolicy  # noqa: E402
from providers.models import Currency, ProviderId  # noqa: E402
from providers.session import ProviderState  # noqa: E402
from ui.chat_metrics import ChatMetricsStrip  # noqa: E402


class AccountBalanceDisplayTests(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def snapshot(self, mode, balance):
        return ChatMetricsSnapshot(
            chat_id="synthetic",
            mode=mode,
            remaining=RemainingBudget(100, Decimal("0.73"), False),
            last_request=LastRequestMetrics(LastRequestState.NONE),
            key_limit=KeyLimitInfo.from_validated_remaining(Decimal("7.12")),
            account_balance=balance,
        )

    def test_signed_api_values_are_visible_in_both_modes_and_languages(self):
        for language in ("en", "ru"):
            set_language(language)
            for mode in ChatMode:
                for value in ("2.5", "0", "-0.000123", "-0.0000001"):
                    with self.subTest(language=language, mode=mode, value=value):
                        amount = Decimal(value)
                        strip = ChatMetricsStrip()
                        strip.set_metrics(
                            self.snapshot(
                                mode,
                                AccountBalanceSnapshot(
                                    AccountBalanceState.CURRENT,
                                    amount,
                                    datetime(2026, 11, 10, tzinfo=UTC),
                                ),
                            )
                        )
                        self.assertIn("OpenRouter", strip.account.value)
                        if amount < 0:
                            self.assertIn("-", strip.account.value)
                            self.assertNotIn(
                                str(money(Decimal("0"))), strip.account.value
                            )
                        elif amount == 0:
                            self.assertIn(str(money(0)), strip.account.value)
                        self.assertNotIn("2.5", str(strip.metadata.value))
                        self.assertNotIn("2.5", str(strip.values.value))

    def test_loading_stale_and_unavailable_never_present_previous_as_current(self):
        for language in ("en", "ru"):
            set_language(language)
            strip = ChatMetricsStrip()
            snapshot = self.snapshot(ChatMode.FREE, AccountBalanceSnapshot())
            strip.set_metrics(snapshot)
            unavailable = str(strip.account.value)
            self.assertNotIn("0", unavailable)
            strip.set_metrics(
                replace(
                    snapshot,
                    account_balance=AccountBalanceSnapshot(AccountBalanceState.LOADING),
                )
            )
            self.assertNotEqual(strip.account.value, unavailable)
            current = AccountBalanceSnapshot(
                AccountBalanceState.CURRENT, Decimal("12.34")
            )
            strip.set_metrics(replace(snapshot, account_balance=current))
            current_text = str(strip.account.value)
            for state in (AccountBalanceState.STALE, AccountBalanceState.LOADING):
                strip.set_metrics(
                    replace(snapshot, account_balance=replace(current, state=state))
                )
                self.assertNotEqual(str(strip.account.value), current_text)
                self.assertIn("12", strip.account.value)

    def test_vsegpt_states_and_tooltips_never_borrow_openrouter_or_key_limits(self):
        for language in ("en", "ru"):
            set_language(language)
            for state, amount in (
                (AccountBalanceState.CURRENT, Decimal("987.65")),
                (AccountBalanceState.CURRENT, Decimal("0")),
                (AccountBalanceState.CURRENT, Decimal("-0.2")),
                (AccountBalanceState.LOADING, None),
                (AccountBalanceState.LOADING, Decimal("987.65")),
                (AccountBalanceState.STALE, Decimal("987.65")),
                (AccountBalanceState.UNAVAILABLE, None),
            ):
                with self.subTest(language=language, state=state, amount=amount):
                    strip = ChatMetricsStrip()
                    strip.set_metrics(
                        replace(
                            self.snapshot(ChatMode.PAID, AccountBalanceSnapshot()),
                            remaining=RemainingBudget(100, Decimal("12.34"), False),
                            provider_id=ProviderId.VSEGPT,
                            currency=Currency.RUB,
                            account_balance=AccountBalanceSnapshot(
                                state,
                                balance_amount=amount,
                                provider_id=ProviderId.VSEGPT,
                                currency=Currency.RUB,
                            ),
                        )
                    )
                    self.assertIn("VSEGPT", strip.account.value)
                    help_text = cast(ft.Tooltip, strip.account.tooltip).message
                    self.assertIn("VSEGPT", help_text)
                    self.assertNotIn("OpenRouter", help_text)
                    self.assertNotIn("OpenRouter", strip.account.value)
                    self.assertIn(
                        str(money(Decimal("12.34"), Currency.RUB)), strip.values.value
                    )
                    self.assertFalse(strip.metadata.visible)
                    self.assertEqual(strip.metadata.value, "")
                    self.assertIsNone(strip.metadata.tooltip)
                    if amount is not None:
                        self.assertIn(
                            str(money(amount, Currency.RUB)), strip.account.value
                        )
                    else:
                        self.assertNotIn(
                            str(money(0, Currency.RUB)), strip.account.value
                        )

    def test_foreign_provider_snapshot_cannot_supply_amount_timestamp_or_loading(self):
        for language in ("en", "ru"):
            set_language(language)
            strip = ChatMetricsStrip()
            foreign = AccountBalanceSnapshot(
                AccountBalanceState.LOADING,
                Decimal("123.45"),
                datetime(2026, 11, 10, tzinfo=UTC),
            )
            strip.set_metrics(
                replace(
                    self.snapshot(ChatMode.PAID, foreign),
                    provider_id=ProviderId.VSEGPT,
                    currency=Currency.RUB,
                )
            )
            unavailable_text = str(strip.account.value)
            self.assertIn("VSEGPT", unavailable_text)
            self.assertNotIn("123", unavailable_text)
            self.assertNotIn("2026", cast(ft.Tooltip, strip.account.tooltip).message)
            assert strip._snapshot is not None
            strip.set_metrics(
                replace(
                    strip._snapshot,
                    account_balance=replace(foreign, state=AccountBalanceState.CURRENT),
                )
            )
            self.assertEqual(strip.account.value, unavailable_text)


class MoneySourceToPresentationTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        set_language("en")

    def test_app_passes_full_key_cap_state_without_substituting_account_amount(self):
        presented = []
        states = {
            provider: ProviderState(
                provider,
                has_saved_key=True,
                balance=AccountBalanceSnapshot(
                    AccountBalanceState.CURRENT,
                    balance_amount=Decimal("123.45")
                    if provider is ProviderId.OPENROUTER
                    else Decimal("987.65"),
                    provider_id=provider,
                    currency=Currency.USD
                    if provider is ProviderId.OPENROUTER
                    else Currency.RUB,
                ),
            )
            for provider in ProviderId
        }
        app = SimpleNamespace(
            _private_pages_available=lambda: True,
            _provider_profiles=SimpleNamespace(
                default_provider=ProviderId.OPENROUTER,
                creation_policy=NewChatPolicy.OPENROUTER,
                state=lambda provider: states[provider],
            ),
            _provider_page=SimpleNamespace(
                set_default=lambda _provider: None,
                set_provider=presented.append,
            ),
        )
        for key_limit in (
            KeyLimitInfo.unknown(),
            KeyLimitInfo.from_validated_remaining(None),
            KeyLimitInfo.from_validated_remaining(Decimal("7.89")),
            KeyLimitInfo.from_validated_remaining(Decimal("0")),
            KeyLimitInfo.from_validated_remaining(Decimal("-1.2")),
        ):
            states[ProviderId.OPENROUTER] = replace(
                states[ProviderId.OPENROUTER], key_limit=key_limit
            )
            presented.clear()
            AppController._refresh_provider_presentations(cast(AppController, app))
            openrouter, vsegpt = presented
            self.assertIs(openrouter.key_limit, key_limit)
            self.assertEqual(openrouter.balance_amount, Decimal("123.45"))
            self.assertEqual(vsegpt.balance_amount, Decimal("987.65"))
            self.assertEqual(vsegpt.key_limit, KeyLimitInfo.unknown())

    async def test_api_account_key_and_local_chat_values_keep_distinct_sources(self):
        requests = []

        def handler(request):
            requests.append((request.url.host, request.url.path))
            if request.url.path.endswith("/key"):
                return httpx.Response(200, json={"data": {"limit_remaining": 7.89}})
            if request.url.path.endswith("/credits"):
                return httpx.Response(
                    200, json={"data": {"total_credits": 150, "total_usage": 26.55}}
                )
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "credits": "987.65",
                        "subscription_status": "ok",
                        "user_status": 0,
                    },
                },
            )

        router = ProviderRouter(transport=httpx.MockTransport(handler))
        key = await router.validate_key("sk-or-v1-local-money-fixture")
        account = await router.get_credits("sk-or-v1-local-money-fixture")
        vsegpt = await router.get_credits("sk-or-visLOCAL_MONEY")
        self.assertEqual(account.balance_amount, Decimal("123.45"))
        self.assertEqual(key.limit_remaining, Decimal("7.89"))
        self.assertEqual(vsegpt.balance_amount, Decimal("987.65"))
        self.assertEqual(
            requests,
            [
                ("openrouter.ai", "/api/v1/key"),
                ("openrouter.ai", "/api/v1/credits"),
                ("api.vsegpt.ru", "/v1/balance"),
            ],
        )
        snapshot = ChatMetricsSnapshot(
            "local",
            ChatMode.PAID,
            RemainingBudget(100, Decimal("0.67"), False),
            LastRequestMetrics(LastRequestState.FINAL, cost=Decimal("0.0123")),
            key_limit=KeyLimitInfo.from_validated_remaining(key.limit_remaining),
            account_balance=AccountBalanceSnapshot(
                AccountBalanceState.CURRENT, balance_amount=account.balance_amount
            ),
        )
        for language in ("en", "ru"):
            set_language(language)
            strip = ChatMetricsStrip()
            strip.set_metrics(snapshot)
            self.assertIn(str(money(Decimal("123.45"))), strip.account.value)
            self.assertIn(str(money(Decimal("7.89"))), strip.metadata.value)
            self.assertIn(str(money(Decimal("0.67"))), strip.values.value)
            self.assertIn(str(money(Decimal("0.0123"))), strip.values.value)
            account_text, key_text = str(strip.account.value), str(strip.metadata.value)
            strip.set_metrics(
                replace(
                    snapshot, remaining=RemainingBudget(100, Decimal("12.34"), False)
                )
            )
            self.assertEqual(strip.account.value, account_text)
            self.assertEqual(strip.metadata.value, key_text)
            strip.set_metrics(
                replace(
                    snapshot,
                    key_limit=KeyLimitInfo.from_validated_remaining(Decimal("0")),
                )
            )
            self.assertEqual(strip.account.value, account_text)
            self.assertIn(str(money(Decimal("0.67"))), strip.values.value)
