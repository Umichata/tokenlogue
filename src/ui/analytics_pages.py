"""Local request analytics, native Flet bars and accessible responsive tables."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

import flet as ft
import flet.canvas as cv

from chat.analytics import (
    AnalyticsFilter,
    AnalyticsSnapshot,
    CurrencySpending,
    DailySpending,
    ModelUsage,
)
from i18n import localize_tree, number, tr
from providers.models import ProviderId, provider_spec
from ui.language_selector import LanguageSelector
from ui.styles import (
    BORDER_COLOR,
    ERROR_COLOR,
    MUTED_COLOR,
    PRIMARY_COLOR,
    WARNING_COLOR,
    surface,
)

FilterCallback = Callable[[AnalyticsFilter], Awaitable[None]]


def _provider_name(provider_id: str) -> str:
    try:
        return provider_spec(provider_id).name
    except ValueError:
        return provider_id


def _tokens(value: int | None) -> str:
    return number(value) if value is not None else tr("analytics.unknown")


def _amount(value: Decimal, currency: str) -> str:
    return tr("analytics.amount", amount=_monetary_number(value), currency=currency)


def _monetary_number(value: Decimal) -> str:
    minimum = Decimal("0.000001")
    if value != 0 and abs(value) < minimum:
        return tr(
            "analytics.tiny_positive" if value > 0 else "analytics.tiny_negative",
            amount=number(minimum),
        )
    with localcontext() as context:
        context.prec = max(context.prec, value.adjusted() + 8)
        rounded = value.quantize(minimum, rounding=ROUND_HALF_UP)
    return number(rounded)


def _metric(label: str, value: str) -> ft.Column:
    return ft.Column(
        tight=True,
        spacing=2,
        controls=[ft.Text(label, size=12, color=MUTED_COLOR), ft.Text(value)],
    )


class DailyBarChart:
    """Money is Decimal until normalized bar geometry reaches the draw boundary."""

    def __init__(self, days: tuple[DailySpending, ...], currency: str) -> None:
        self.days = days
        self.currency = currency
        maximum = max(
            (max(day.confirmed, day.estimated) for day in days), default=Decimal(0)
        )
        self._width = 560.0
        self.canvas = cv.Canvas(width=float("inf"), height=180, on_resize=self._resize)
        self.control = ft.Semantics(
            label=tr("analytics.chart_accessible", currency=currency),
            image=True,
            content=ft.Column(
                tight=True,
                spacing=4,
                controls=[
                    ft.Row(
                        wrap=True,
                        controls=[
                            ft.Text(tr("analytics.actual"), color=PRIMARY_COLOR),
                            ft.Text(tr("analytics.estimated"), color=WARNING_COLOR),
                        ],
                    ),
                    ft.Text(
                        tr("analytics.chart_scale", maximum=_amount(maximum, currency)),
                        size=12,
                        color=MUTED_COLOR,
                    ),
                    self.canvas,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(days[0].day.isoformat() if days else "", size=11),
                            ft.Text(days[-1].day.isoformat() if days else "", size=11),
                        ],
                    ),
                ],
            ),
        )
        self._draw()

    def _resize(self, event: cv.CanvasResizeEvent) -> None:
        self._width = max(1.0, event.width)
        self._draw()
        try:
            self.canvas.update()
        except (RuntimeError, AssertionError):
            pass

    def _draw(self) -> None:
        width = self._width
        baseline = 174.0
        shapes: list[cv.Shape] = [
            cv.Line(0, baseline, width, baseline, paint=ft.Paint(color=BORDER_COLOR))
        ]
        maximum = max(
            (max(day.confirmed, day.estimated) for day in self.days),
            default=Decimal(0),
        )
        if self.days:
            slot = width / len(self.days)
            for index, day in enumerate(self.days):
                for series, color, offset in (
                    (day.confirmed, PRIMARY_COLOR, 0.08),
                    (day.estimated, WARNING_COLOR, 0.52),
                ):
                    height = (
                        float(max(Decimal(0), series) / maximum) * 164
                        if maximum > 0
                        else 0
                    )
                    shapes.append(
                        cv.Rect(
                            x=(index + offset) * slot,
                            y=baseline - max(height, 1),
                            width=max(0.1, slot * 0.36),
                            height=max(height, 1),
                            paint=ft.Paint(color=color if height else BORDER_COLOR),
                        )
                    )
        self.canvas.shapes = shapes

    def clear(self) -> None:
        self.days = ()
        self.canvas.shapes = []
        self.control.label = ""
        self.control.content = ft.Container()


class _AnalyticsPage:
    def __init__(
        self,
        page_kind: Literal["tokens", "spending"],
        *,
        on_filter: FilterCallback,
        filters: AnalyticsFilter | None = None,
    ) -> None:
        self.filters = filters or AnalyticsFilter()
        self._kind = page_kind
        self._on_filter = on_filter
        self._snapshot: AnalyticsSnapshot | None = None
        self._cleared = False
        self._charts: list[DailyBarChart] = []
        self._usage_limit = 100
        self._day_limits: dict[str, int] = {}
        self.period = ft.Dropdown(
            label=tr("analytics.period"),
            value=self.filters.period,
            options=[
                ft.DropdownOption(key=value, text=str(tr(f"analytics.period.{value}")))
                for value in ("7d", "30d", "all")
            ],
            on_select=self._filters_changed,
            col={"xs": 12, "md": 4},
        )
        self.provider = ft.Dropdown(
            label=tr("analytics.provider"),
            value=self.filters.provider_id or "",
            options=[
                ft.DropdownOption(key="", text=str(tr("analytics.all_providers"))),
                *[
                    ft.DropdownOption(key=p.value, text=provider_spec(p).name)
                    for p in ProviderId
                ],
            ],
            on_select=self._filters_changed,
            col={"xs": 12, "md": 4},
        )
        self.model = ft.Dropdown(
            label=tr("analytics.model"),
            value=self.filters.model_id or "",
            options=[ft.DropdownOption(key="", text=str(tr("analytics.all_models")))],
            on_select=self._filters_changed,
            col={"xs": 12, "md": 4},
        )
        self.progress = ft.ProgressBar(visible=False, color=PRIMARY_COLOR)
        self.error = ft.Text("", color=ERROR_COLOR)
        self._body = ft.Column(tight=True, spacing=16)
        self.control = ft.ListView(
            expand=True,
            spacing=16,
            padding=16,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            tr(f"analytics.title.{page_kind}"), size=26, expand=True
                        ),
                        LanguageSelector(compact=True),
                    ],
                ),
                ft.Text(tr("analytics.scope"), color=MUTED_COLOR),
                ft.ResponsiveRow(controls=[self.period, self.provider, self.model]),
                self.progress,
                self.error,
                self._body,
            ],
        )

    async def _filters_changed(self, _event: ft.Event) -> None:
        if self._cleared:
            return
        period = self.period.value
        if period not in ("7d", "30d", "all"):
            return
        self.filters = replace(
            self.filters,
            period=period,
            provider_id=self.provider.value or None,
            model_id=self.model.value or None,
        )
        self._usage_limit = 100
        self._day_limits.clear()
        self.set_loading(True)
        try:
            await self._on_filter(self.filters)
        except Exception:
            self.show_error(tr("analytics.load_failed"))
        finally:
            self.set_loading(False)

    def set_loading(self, loading: bool) -> None:
        if not self._cleared:
            self.progress.visible = loading
            self._update()

    def show_error(self, message: str) -> None:
        if not self._cleared:
            self.error.value = message
            self._update()

    def set_snapshot(self, snapshot: AnalyticsSnapshot) -> None:
        if self._cleared:
            return
        self._snapshot = snapshot
        self.filters = snapshot.filters
        self.period.value = snapshot.filters.period
        self.provider.value = snapshot.filters.provider_id or ""
        self.model.value = snapshot.filters.model_id or ""
        model_ids = sorted(
            {choice.model_id for choice in snapshot.models if choice.model_id}
        )
        self.model.options = [
            ft.DropdownOption(key="", text=str(tr("analytics.all_models"))),
            *[ft.DropdownOption(key=model, text=model) for model in model_ids],
        ]
        self.error.value = ""
        self.progress.visible = False
        self._render()
        self._update()

    def _render(self) -> None:
        for chart in self._charts:
            chart.clear()
        self._charts = []
        snapshot = self._snapshot
        if snapshot is None:
            self._body.controls = []
            return
        if self._kind == "tokens":
            self._render_usage(snapshot)
        else:
            self._render_spending(snapshot)

    def _render_usage(self, snapshot: AnalyticsSnapshot) -> None:
        rows = sorted(
            snapshot.usage_rows,
            key=lambda row: (
                -(row.total_tokens if row.total_tokens is not None else -1),
                row.provider_id,
                row.model_id or "",
            ),
        )
        requests = sum(row.requests for row in rows)
        api_requests = sum(row.api_usage_requests for row in rows)
        unknown = sum(row.unknown_usage_requests for row in rows)
        api_totals = [row.total_tokens for row in rows if row.total_tokens is not None]
        controls: list[ft.Control] = [
            surface(
                ft.Row(
                    wrap=True,
                    spacing=24,
                    controls=[
                        _metric(tr("analytics.requests"), number(requests)),
                        _metric(
                            tr("analytics.api_total"),
                            _tokens(sum(api_totals) if api_totals else None),
                        ),
                        _metric(tr("analytics.api_requests"), number(api_requests)),
                        _metric(tr("analytics.unknown_requests"), number(unknown)),
                    ],
                ),
                padding=16,
            ),
            ft.Text(tr("analytics.token_sources"), color=MUTED_COLOR),
        ]
        if snapshot.undated_requests:
            controls.append(
                ft.Text(
                    tr("analytics.undated", count=number(snapshot.undated_requests)),
                    color=WARNING_COLOR,
                )
            )
        if not rows:
            controls.append(ft.Text(tr("analytics.empty")))
        else:
            known = [row for row in rows if row.total_tokens is not None]
            if known:
                maximum = max(row.total_tokens or 0 for row in known)
                controls.append(ft.Text(tr("analytics.top_models"), size=20))
                for row in known[:5]:
                    label = tr(
                        "analytics.model_usage",
                        provider=_provider_name(row.provider_id),
                        model=row.model_id or tr("analytics.unknown_model"),
                        tokens=_tokens(row.total_tokens),
                    )
                    controls.append(
                        ft.Semantics(
                            label=label,
                            content=ft.Column(
                                tight=True,
                                spacing=4,
                                controls=[
                                    ft.Text(label, selectable=True),
                                    ft.ProgressBar(
                                        value=(row.total_tokens or 0) / maximum
                                        if maximum
                                        else 0,
                                        color=PRIMARY_COLOR,
                                    ),
                                ],
                            ),
                        )
                    )
            else:
                controls.append(
                    ft.Text(tr("analytics.no_confirmed_tokens"), color=WARNING_COLOR)
                )
            controls.append(ft.Text(tr("analytics.usage_table"), size=20))
            controls.extend(self._usage_row(row) for row in rows[: self._usage_limit])
            if len(rows) > self._usage_limit:

                async def more(_event: ft.Event) -> None:
                    self._usage_limit += 100
                    self._render()
                    self._update()

                controls.append(ft.TextButton(tr("analytics.show_more"), on_click=more))
        self._body.controls = controls

    def _usage_row(self, row: ModelUsage) -> ft.Control:
        heading = tr(
            "analytics.model_label",
            provider=_provider_name(row.provider_id),
            model=row.model_id or tr("analytics.unknown_model"),
        )
        controls: list[ft.Control] = [
            ft.Text(heading, size=16, selectable=True),
            ft.Row(
                wrap=True,
                spacing=20,
                controls=[
                    _metric(tr("analytics.requests"), number(row.requests)),
                    _metric(tr("analytics.input"), _tokens(row.prompt_tokens)),
                    _metric(tr("analytics.output"), _tokens(row.completion_tokens)),
                    _metric(tr("analytics.api_total"), _tokens(row.total_tokens)),
                ],
            ),
            ft.Text(
                tr(
                    "analytics.usage_coverage",
                    api=number(row.api_usage_requests),
                    estimated=number(row.estimated_usage_requests),
                    unknown=number(row.unknown_usage_requests),
                ),
                size=12,
                color=MUTED_COLOR,
            ),
        ]
        if row.estimated_usage_requests:
            controls.append(
                ft.Text(
                    tr(
                        "analytics.estimated_tokens",
                        input=_tokens(row.estimated_prompt_tokens),
                        output=_tokens(row.estimated_completion_tokens),
                        total=_tokens(row.estimated_total_tokens),
                    ),
                    color=WARNING_COLOR,
                )
            )
        if row.undated_requests:
            controls.append(
                ft.Text(
                    tr("analytics.undated", count=number(row.undated_requests)),
                    color=WARNING_COLOR,
                )
            )
        return surface(ft.Column(tight=True, spacing=10, controls=controls), padding=16)

    def _render_spending(self, snapshot: AnalyticsSnapshot) -> None:
        controls: list[ft.Control] = [
            ft.Text(
                tr("analytics.timezone", timezone=snapshot.timezone_name),
                color=MUTED_COLOR,
            ),
            ft.Text(tr("analytics.spending_sources"), color=MUTED_COLOR),
        ]
        if not snapshot.spending:
            controls.append(ft.Text(tr("analytics.empty")))
        for panel in snapshot.spending:
            controls.append(self._spending_panel(panel))
        self._body.controls = controls

    def _spending_panel(self, panel: CurrencySpending) -> ft.Control:
        currency = str(panel.currency)
        chart = DailyBarChart(panel.days, currency)
        self._charts.append(chart)
        controls: list[ft.Control] = [
            ft.Text(tr("analytics.currency_panel", currency=currency), size=21),
            ft.Row(
                wrap=True,
                spacing=24,
                controls=[
                    _metric(
                        tr("analytics.actual_total"),
                        _amount(panel.confirmed_total, currency),
                    ),
                    _metric(
                        tr("analytics.daily_average"),
                        _amount(panel.average_per_day, currency),
                    ),
                    _metric(
                        tr("analytics.estimated_total"),
                        _amount(panel.estimated_total, currency),
                    ),
                ],
            ),
            chart.control,
        ]
        if panel.unknown_cost_requests:
            controls.append(
                ft.Text(
                    tr(
                        "analytics.unknown_costs",
                        count=number(panel.unknown_cost_requests),
                    ),
                    color=WARNING_COLOR,
                )
            )
        if panel.undated_requests:
            controls.append(
                ft.Text(
                    tr(
                        "analytics.undated_spending",
                        count=number(panel.undated_requests),
                        actual=_amount(panel.undated_confirmed_total, currency),
                        estimated=_amount(panel.undated_estimated_total, currency),
                    ),
                    color=WARNING_COLOR,
                )
            )
        controls.append(ft.Text(tr("analytics.daily_table"), size=18))
        controls.append(
            ft.Row(
                controls=[
                    ft.Text(tr("analytics.date"), expand=3, weight=ft.FontWeight.BOLD),
                    ft.Text(
                        tr("analytics.amount_header"),
                        expand=4,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        tr("analytics.currency"), expand=2, weight=ft.FontWeight.BOLD
                    ),
                ],
            )
        )
        limit = self._day_limits.get(currency, 60)
        for day in panel.days[:limit]:
            notes: list[ft.Control] = [
                ft.Text(_monetary_number(day.confirmed), selectable=True)
            ]
            if day.estimated:
                notes.append(
                    ft.Text(
                        tr(
                            "analytics.day_estimate",
                            amount=_monetary_number(day.estimated),
                        ),
                        size=12,
                        color=WARNING_COLOR,
                    )
                )
            if day.unknown_requests:
                notes.append(
                    ft.Text(
                        tr("analytics.day_unknown", count=number(day.unknown_requests)),
                        size=12,
                        color=WARNING_COLOR,
                    )
                )
            controls.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Text(day.day.isoformat(), expand=3, selectable=True),
                        ft.Column(tight=True, spacing=2, expand=4, controls=notes),
                        ft.Text(currency, expand=2),
                    ],
                )
            )
        if len(panel.days) > limit:

            async def more(_event: ft.Event) -> None:
                self._day_limits[currency] = limit + 60
                self._render()
                self._update()

            controls.append(ft.TextButton(tr("analytics.show_more"), on_click=more))
        return surface(ft.Column(tight=True, spacing=12, controls=controls), padding=16)

    def sync_language(self) -> None:
        if not self._cleared:
            localize_tree(self.control)
            # Mounted DropdownOption controls are frozen by Flet 0.86.5.
            # Replace translated options instead of mutating their text.
            self.period.options = [
                ft.DropdownOption(key=value, text=str(tr(f"analytics.period.{value}")))
                for value in ("7d", "30d", "all")
            ]
            self.provider.options = [
                ft.DropdownOption(key="", text=str(tr("analytics.all_providers"))),
                *[
                    ft.DropdownOption(key=p.value, text=provider_spec(p).name)
                    for p in ProviderId
                ],
            ]
            self.model.options = [
                ft.DropdownOption(
                    key=option.key,
                    text=str(tr("analytics.all_models"))
                    if not option.key
                    else option.text,
                )
                for option in self.model.options
            ]
            self._render()

    def clear_private(self) -> None:
        self._cleared = True
        self._snapshot = None
        for chart in self._charts:
            chart.clear()
        self._charts = []
        self._body.controls = []
        self.model.options = []
        self.model.value = ""
        self.provider.value = ""
        self.error.value = ""
        self.progress.visible = False
        self.filters = AnalyticsFilter()

    def _update(self) -> None:
        try:
            self.control.update()
        except (RuntimeError, AssertionError):
            pass


class TokenUsagePage(_AnalyticsPage):
    def __init__(
        self, *, on_filter: FilterCallback, filters: AnalyticsFilter | None = None
    ) -> None:
        super().__init__("tokens", on_filter=on_filter, filters=filters)


class SpendingPage(_AnalyticsPage):
    def __init__(
        self, *, on_filter: FilterCallback, filters: AnalyticsFilter | None = None
    ) -> None:
        super().__init__("spending", on_filter=on_filter, filters=filters)
