"""Synthetic local journals and unmounted controls, with no profile or HTTP use."""

from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.analytics import (  # noqa: E402
    AnalyticsFilter,
    RequestAttempt,
    build_analytics,
)
from i18n import configure_localization, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from providers.models import ProviderId  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui.analytics_pages import DailyTokenChart, TokenUsagePage  # noqa: E402

NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)


def _texts(control: ft.Control) -> str:
    return "\n".join(
        str(child.value) for child in walk(control) if isinstance(child, ft.Text)
    )


def _attempt(sequence: int, offset: int = 0, **values) -> RequestAttempt:
    return RequestAttempt(
        sequence,
        "same-turn",
        "same-chat",
        sent_at=NOW - timedelta(days=offset),
        chronology_known=True,
        **values,
    )


class DailyTokenChartTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.update = patch.object(ft.Control, "update", return_value=None)
        self.update.start()
        self.addCleanup(self.update.stop)

    async def test_touch_day_selection_exposes_partial_components_and_keyboard_navigation(
        self,
    ):
        snapshot = build_analytics(
            [
                _attempt(1, 2, prompt_tokens=9, total_tokens=None, usage_source="api"),
                _attempt(2, 1),
                _attempt(
                    3,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    usage_source="api",
                ),
            ],
            AnalyticsFilter(timezone_name="UTC"),
            NOW,
        )
        for language in ("en", "ru"):
            set_language(language)
            chart = DailyTokenChart(snapshot.daily_tokens)
            chart._tap(
                ft.TapEvent(
                    "tap_down", ft.GestureDetector(), local_position=ft.Offset(0, 3)
                )
            )
            self.assertEqual(chart.selected_day, snapshot.daily_tokens[0].day)
            self.assertIn(
                snapshot.daily_tokens[0].day.isoformat(), _texts(chart._details)
            )
            self.assertTrue(chart.previous.disabled)
            # The actual tap path and keyboard/touch buttons select the same day.
            chart.select_day(len(snapshot.daily_tokens) - 3)
            detail = _texts(chart._details)
            self.assertIn("9", detail)
            self.assertIn(str(tr("analytics.unknown")), detail)
            self.assertIn("incomplete" if language == "en" else "Неполные", detail)
            chart.select_day(len(snapshot.daily_tokens) - 2)
            detail = _texts(chart._details)
            self.assertIn(
                "Usage source unavailable"
                if language == "en"
                else "Источник данных недоступен",
                detail,
            )
            self.assertEqual(chart.days[-2].usage.requests, 1)
            chart.select_day(len(snapshot.daily_tokens) - 1)
            self.assertTrue(chart.next.disabled)
            self.assertEqual(chart.days[-1].usage.api.total_tokens, 0)

    async def test_long_history_bounds_canvas_and_controls_but_every_day_remains_selectable(
        self,
    ):
        snapshot = build_analytics(
            [
                _attempt(1, 5000, total_tokens=10, usage_source="api"),
                _attempt(2, total_tokens=20, usage_source="api"),
            ],
            AnalyticsFilter(period="all", timezone_name="UTC"),
            NOW,
        )
        chart = DailyTokenChart(snapshot.daily_tokens)
        control_count = len(list(walk(chart.control)))
        shape_limit = 1 + 31 * 4
        self.assertLess(len(chart.canvas.shapes), shape_limit)
        self.assertLess(control_count, 70)
        chart._slide(ft.Event("change", ft.Slider(value=0)))
        self.assertEqual(chart.selected_day, snapshot.start_date)
        self.assertIn("10", _texts(chart._details))
        chart.select_day(len(snapshot.daily_tokens) - 1)
        self.assertEqual(chart.selected_day, snapshot.end_date)
        self.assertIn("20", _texts(chart._details))
        self.assertLess(len(chart.canvas.shapes), shape_limit)
        self.assertEqual(len(list(walk(chart.control))), control_count)

    async def test_filter_reload_and_lock_erase_chart_and_reject_late_interaction(self):
        page = TokenUsagePage(on_filter=AsyncMock())
        initial = AnalyticsFilter(timezone_name="UTC")
        old = build_analytics(
            [_attempt(1, total_tokens=123456, usage_source="api")], initial, NOW
        )
        request = page.begin_load(initial)
        page.set_snapshot(old)
        chart = page._token_chart
        assert chart is not None
        self.assertIn("123", _texts(page._body))
        changed = replace(initial, provider_id=ProviderId.VSEGPT)
        page.begin_load(changed)
        self.assertFalse(page.is_current_load(request, initial))
        self.assertEqual(chart.days, ())
        self.assertEqual(chart.canvas.shapes, [])
        self.assertEqual(chart._details.controls, [])
        page.set_snapshot(build_analytics([], changed, NOW))
        current = page._token_chart
        assert current is not None
        page.clear_private()
        chart.select_day(3)
        current.select_day(3)
        page.set_snapshot(old)
        self.assertFalse(page.is_current_load(request, initial))
        self.assertEqual(page._body.controls, [])
        self.assertEqual(current.days, ())
        self.assertEqual(current.control.controls, [])
        self.assertIsNone(page._snapshot)

    async def test_language_sync_retains_filters_selected_day_and_separate_estimates(
        self,
    ):
        filters = AnalyticsFilter(
            period="30d", provider_id=ProviderId.VSEGPT, timezone_name="UTC"
        )
        snapshot = build_analytics(
            [
                _attempt(
                    1,
                    1,
                    provider_id=ProviderId.VSEGPT,
                    requested_model_id="same",
                    prompt_tokens=5,
                    completion_tokens=7,
                    total_tokens=12,
                    usage_source="estimated",
                ),
                _attempt(
                    2,
                    provider_id=ProviderId.VSEGPT,
                    requested_model_id="same",
                    prompt_tokens=1,
                    completion_tokens=2,
                    total_tokens=3,
                    usage_source="api",
                ),
            ],
            filters,
            NOW,
        )
        page = TokenUsagePage(on_filter=AsyncMock(), filters=filters)
        page.set_snapshot(snapshot)
        chart = page._token_chart
        assert chart is not None
        chart.select_day(28)
        selected = chart.selected_day
        for language, title in (("en", "Tokens by day"), ("ru", "Токены по дням")):
            set_language(language)
            page.sync_language()
            self.assertIn(title, _texts(page._body))
            self.assertEqual(page.filters, filters)
            self.assertEqual(page.provider.value, ProviderId.VSEGPT)
            current = page._token_chart
            assert current is not None
            self.assertEqual(current.selected_day, selected)
            self.assertEqual(current.days[28].usage.estimated.total_tokens, 12)
            self.assertIsNone(current.days[28].usage.api.total_tokens)

    async def test_unknown_only_day_does_not_present_a_zero_total(self):
        set_language("en")
        snapshot = build_analytics(
            [_attempt(1)], AnalyticsFilter(timezone_name="UTC"), NOW
        )
        chart = DailyTokenChart(snapshot.daily_tokens)
        self.assertIn("No known token totals", str(chart._scale.value))
        self.assertIn("Unavailable", _texts(chart._details))
        self.assertEqual(chart.days[-1].usage.requests, 1)
        self.assertNotIn("0 tokens", str(chart._scale.value))
        chart.select_day(0)
        self.assertIn("No requests on this day.", _texts(chart._details))
