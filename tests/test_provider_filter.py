"""Provider view choices stay local to their own page and survive localization."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo  # noqa: E402
from i18n import configure_localization, set_language  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from providers.models import ProviderId  # noqa: E402
from providers.quota import DailyRequestQuota  # noqa: E402
from ui.provider_filter import ProviderFilter  # noqa: E402
from ui.provider_page import ProviderPage, ProviderPresentation  # noqa: E402


class ProviderFilterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        set_language("ru")

    async def test_three_independent_selectors_notify_only_their_owner(self):
        callbacks = [AsyncMock() for _ in range(3)]
        filters = [ProviderFilter(on_change=callback) for callback in callbacks]
        filters[0].control.value = "vsegpt"
        await filters[0]._changed(ft.Event(name="select", control=filters[0].control))
        callbacks[0].assert_awaited_once_with(ProviderId.VSEGPT)
        for other, callback in zip(filters[1:], callbacks[1:], strict=True):
            self.assertIsNone(other.value)
            callback.assert_not_awaited()
        filters[1].set_value(ProviderId.OPENROUTER)
        filters[2].set_value(None)
        for language, all_label in (("en", "All"), ("ru", "Все")):
            for selector in filters:
                for option in selector.control.options:
                    object.__setattr__(option, "_frozen", True)
            set_language(language)
            for selector in filters:
                selector.sync_language()
                self.assertEqual(selector.control.options[0].text, all_label)
                self.assertEqual(
                    [option.key for option in selector.control.options],
                    ["all", "openrouter", "vsegpt"],
                )
            self.assertEqual(
                [selector.value for selector in filters],
                [ProviderId.VSEGPT, ProviderId.OPENROUTER, None],
            )
        callbacks[0].assert_awaited_once()
        callbacks[1].assert_not_awaited()
        callbacks[2].assert_not_awaited()

    async def test_daily_quota_is_optional_provider_confirmed_and_scrubbed(self):
        page = ProviderPage(
            on_check=AsyncMock(),
            on_save=AsyncMock(),
            on_refresh=AsyncMock(),
            on_default=AsyncMock(),
        )
        card = page.cards[ProviderId.OPENROUTER]
        self.assertFalse(card.daily_quota.visible)
        presentation = ProviderPresentation(
            ProviderId.OPENROUTER,
            has_saved_key=True,
            key_limit=replace(
                KeyLimitInfo.unknown(), daily_request_quota=DailyRequestQuota(3, 12, 9)
            ),
        )
        page.set_provider(presentation)
        self.assertTrue(card.daily_quota.visible)
        self.assertIn("9", str(card.daily_quota.value))
        self.assertIn("12", str(card.daily_quota.value))
        self.assertIn("UTC", str(card.daily_quota.value))
        # Losing the optional field cannot turn unknown into a zero allowance.
        page.set_provider(ProviderPresentation(ProviderId.OPENROUTER))
        self.assertFalse(card.daily_quota.visible)
        self.assertEqual(card.daily_quota.value, "")
        page.set_provider(presentation)
        page.clear_private()
        self.assertEqual(card.daily_quota.value, "")
