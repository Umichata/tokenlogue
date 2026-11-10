"""Account API states render in both chat modes without inventing money."""

import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
