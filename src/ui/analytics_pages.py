"""Local request analytics, native Flet bars and accessible responsive tables."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

import flet as ft
import flet.canvas as cv

from chat.analytics import (
    AnalyticsFilter,
    AnalyticsSnapshot,
    CurrencySpending,
    DailySpending,
    DailyTokenUsage,
    ModelChoice,
    ModelUsage,
    TokenUsageSummary,
    TokenUsageTotals,
)
from i18n import localize_tree, number, tr
from providers.models import ProviderId, provider_spec
from ui.language_selector import LanguageSelector
from ui.provider_filter import ProviderFilter
from ui.styles import (
    BORDER_COLOR,
    ERROR_COLOR,
    MUTED_COLOR,
    PRIMARY_COLOR,
    WARNING_COLOR,
    dropdown_style,
    surface,
)

FilterCallback = Callable[[AnalyticsFilter], Awaitable[None]]


def _provider_name(provider_id: str) -> str:
    try:
        return provider_spec(provider_id).name
    except ValueError:
        return provider_id


def _model_key(choice: ModelChoice) -> str:
    return json.dumps([choice.provider_id, choice.model_id], ensure_ascii=True)


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


def _token_summary_controls(summary: TokenUsageSummary) -> list[ft.Control]:
    controls: list[ft.Control] = [
        _metric(tr("analytics.requests"), number(summary.requests))
    ]
    if not summary.requests:
        controls.append(ft.Text(tr("analytics.day_no_requests"), color=MUTED_COLOR))
        return controls
    unknown_source = (
        summary.requests - summary.api.requests - summary.estimated.requests
    )
    for source, values, color in (
        ("api", summary.api, PRIMARY_COLOR),
        ("estimate", summary.estimated, WARNING_COLOR),
        (
            "unknown",
            TokenUsageTotals(unknown_source, None, None, None, unknown_source),
            MUTED_COLOR,
        ),
    ):
        if not values.requests:
            continue
        controls.extend(
            [
                ft.Text(tr(f"analytics.token_source.{source}"), color=color),
                ft.Row(
                    wrap=True,
                    spacing=20,
                    controls=[
                        _metric(
                            tr("analytics.token_input"), _tokens(values.prompt_tokens)
                        ),
                        _metric(
                            tr("analytics.token_output"),
                            _tokens(values.completion_tokens),
                        ),
                        _metric(
                            tr("analytics.token_total"), _tokens(values.total_tokens)
                        ),
                    ],
                ),
            ]
        )
        if values.partial_requests:
            controls.append(
                ft.Text(
                    tr(
                        "analytics.token_partial_source",
                        count=number(values.partial_requests),
                    ),
                    color=WARNING_COLOR,
                    size=12,
                )
            )
    if summary.unknown_usage_requests:
        controls.append(
            ft.Text(
                tr(
                    "analytics.token_partial_day",
                    count=number(summary.unknown_usage_requests),
                ),
                color=WARNING_COLOR,
            )
        )
    return controls


class DailyTokenChart:
    """A bounded canvas window with tap and keyboard-accessible day selection."""

    _WINDOW_DAYS = 31

    def __init__(self, days: tuple[DailyTokenUsage, ...]) -> None:
        self.days: tuple[DailyTokenUsage, ...] = days
        self._width = 560.0
        self._selected = next(
            (
                index
                for index in range(len(days) - 1, -1, -1)
                if days[index].usage.requests
            ),
            max(0, len(days) - 1),
        )
        self.canvas = cv.Canvas(width=float("inf"), height=180, on_resize=self._resize)
        self._range = ft.Text("", size=12, color=MUTED_COLOR)
        self._scale = ft.Text("", size=12, color=MUTED_COLOR)
        self._details = ft.Column(tight=True, spacing=8)
        self.previous = ft.TextButton(
            tr("analytics.previous_day"),
            icon=ft.Icons.CHEVRON_LEFT,
            on_click=lambda _event: self.select_day(self._selected - 1),
        )
        self.next = ft.TextButton(
            tr("analytics.next_day"),
            icon=ft.Icons.CHEVRON_RIGHT,
            on_click=lambda _event: self.select_day(self._selected + 1),
        )
        self.selector = ft.Slider(
            min=0,
            max=max(1, len(days) - 1),
            divisions=max(1, len(days) - 1),
            value=self._selected,
            on_change=self._slide,
            disabled=len(days) < 2,
        )
        self.control = ft.Column(
            tight=True,
            spacing=8,
            controls=[
                ft.Row(
                    wrap=True,
                    controls=[
                        ft.Text(tr("analytics.token_source.api"), color=PRIMARY_COLOR),
                        ft.Text(
                            tr("analytics.token_source.estimate"), color=WARNING_COLOR
                        ),
                    ],
                ),
                ft.Text(tr("analytics.token_chart_help"), size=12, color=MUTED_COLOR),
                self._scale,
                ft.Semantics(
                    label=tr("analytics.token_chart_accessible"),
                    content=ft.GestureDetector(
                        content=self.canvas, on_tap_down=self._tap
                    ),
                ),
                self._range,
                ft.Semantics(
                    label=tr("analytics.token_day_select"), content=self.selector
                ),
                ft.Row(wrap=True, controls=[self.previous, self.next]),
                self._details,
            ],
        )
        self.select_day(self._selected, update=False)

    @property
    def selected_day(self) -> date | None:
        return self.days[self._selected].day if self.days else None

    def _window(self) -> tuple[int, tuple[DailyTokenUsage, ...]]:
        start = max(
            0,
            min(
                self._selected - self._WINDOW_DAYS // 2,
                len(self.days) - self._WINDOW_DAYS,
            ),
        )
        return start, self.days[start : start + self._WINDOW_DAYS]

    def _resize(self, event: cv.CanvasResizeEvent) -> None:
        self._width = max(1.0, event.width)
        self._draw()
        self._update()

    def _tap(self, event: ft.TapEvent) -> None:
        if not self.days or event.local_position is None:
            return
        start, days = self._window()
        offset = int(max(0, event.local_position.x) / self._width * len(days))
        self.select_day(start + min(len(days) - 1, offset))

    def _slide(self, event: ft.Event[ft.Slider]) -> None:
        if event.control.value is not None:
            self.select_day(round(event.control.value))

    def select_day(self, index: int, *, update: bool = True) -> None:
        if not self.days:
            return
        self._selected = min(max(index, 0), len(self.days) - 1)
        selected = self.days[self._selected]
        self.selector.value = self._selected
        self.previous.disabled = self._selected == 0
        self.next.disabled = self._selected == len(self.days) - 1
        self._details.controls = [
            ft.Text(selected.day.isoformat(), size=18, selectable=True),
            *_token_summary_controls(selected.usage),
        ]
        self._draw()
        if update:
            self._update()

    def _draw(self) -> None:
        start, days = self._window()
        if not days:
            self.canvas.shapes = []
            return
        width = self._width
        baseline = 174.0
        slot = width / len(days)
        maximum = max(
            (
                max(
                    day.usage.api.total_tokens or 0,
                    day.usage.estimated.total_tokens or 0,
                )
                for day in days
            ),
            default=0,
        )
        shapes: list[cv.Shape] = [
            cv.Line(0, baseline, width, baseline, paint=ft.Paint(color=BORDER_COLOR))
        ]
        for index, day in enumerate(days):
            if start + index == self._selected:
                shapes.append(
                    cv.Rect(
                        x=index * slot,
                        y=0,
                        width=slot,
                        height=baseline,
                        paint=ft.Paint(
                            color=ft.Colors.with_opacity(0.12, PRIMARY_COLOR)
                        ),
                    )
                )
            for values, color, offset in (
                (day.usage.api, PRIMARY_COLOR, 0.08),
                (day.usage.estimated, WARNING_COLOR, 0.52),
            ):
                # A missing total is not derived from its input/output components.
                if values.total_tokens is None:
                    continue
                height = values.total_tokens / maximum * 164 if maximum else 0
                shapes.append(
                    cv.Rect(
                        x=(index + offset) * slot,
                        y=baseline - max(height, 2),
                        width=max(0.1, slot * 0.36),
                        height=max(height, 2),
                        paint=ft.Paint(color=color),
                    )
                )
            if day.usage.unknown_usage_requests:
                shapes.append(
                    cv.Circle(
                        x=(index + 0.5) * slot,
                        y=5,
                        radius=2,
                        paint=ft.Paint(color=WARNING_COLOR),
                    )
                )
        self.canvas.shapes = shapes
        self._range.value = tr(
            "analytics.token_chart_range",
            start=days[0].day.isoformat(),
            end=days[-1].day.isoformat(),
        )
        any_total = any(
            values.total_tokens is not None
            for day in days
            for values in (day.usage.api, day.usage.estimated)
        )
        self._scale.value = (
            tr("analytics.token_chart_scale", maximum=number(maximum))
            if any_total
            else tr("analytics.token_chart_no_totals")
        )

    def clear(self) -> None:
        self.days = ()
        self.canvas.shapes = []
        self._details.controls = []
        self._range.value = ""
        self._scale.value = ""
        self.selector.value = 0
        self.selector.disabled = True
        self.previous.disabled = self.next.disabled = True
        self.control.controls = []

    def _update(self) -> None:
        try:
            self.control.update()
        except (RuntimeError, AssertionError):
            pass


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
        self._model_choices: dict[str, ModelChoice] = {}
        self._filter_generation = 0
        self._load_generation = 0
        self._cleared = False
        self._charts: list[DailyBarChart] = []
        self._token_chart: DailyTokenChart | None = None
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
            **dropdown_style(),
        )
        self.provider = ProviderFilter(
            on_change=self._provider_changed,
            value=ProviderId(self.filters.provider_id)
            if self.filters.provider_id is not None
            else None,
        )
        self.model = ft.Dropdown(
            label=tr("analytics.model"),
            value=self.filters.model_id or "",
            options=[ft.DropdownOption(key="", text=str(tr("analytics.all_models")))],
            on_select=self._filters_changed,
            col={"xs": 12, "md": 4},
            **dropdown_style(),
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
                ft.ResponsiveRow(
                    controls=[self.provider.control, self.period, self.model]
                ),
                self.progress,
                self.error,
                self._body,
            ],
        )

    async def _provider_changed(self, provider: ProviderId | None) -> None:
        self.provider.set_value(provider)
        await self._filters_changed(None)

    async def _filters_changed(self, _event: ft.Event | None) -> None:
        if self._cleared:
            return
        period = self.period.value
        if period not in ("7d", "30d", "all"):
            return
        choice = self._model_choices.get(self.model.value or "")
        provider = self.provider.value
        if (
            choice is not None
            and provider is not None
            and choice.provider_id != provider
        ):
            choice = None
        self.filters = replace(
            self.filters,
            period=period,
            provider_id=provider.value if provider is not None else None,
            model_id=choice.model_id if choice else None,
            model_provider_id=choice.provider_id.value if choice else None,
        )
        self._set_model_choices(
            tuple(
                choice
                for choice in self._model_choices.values()
                if provider is None or choice.provider_id == provider
            )
        )
        self._filter_generation += 1
        generation = self._filter_generation
        filters = self.filters
        self._usage_limit = 100
        self._day_limits.clear()
        self._snapshot = None
        self.error.value = ""
        self._render()
        self._update()
        try:
            await self._on_filter(filters)
        except Exception:
            if generation == self._filter_generation and filters == self.filters:
                self.show_error(tr("analytics.load_failed"))

    def begin_load(self, filters: AnalyticsFilter) -> int:
        """A retained page owns its requests independently of the other page."""
        self._load_generation += 1
        if self._snapshot is not None and self._snapshot.filters != filters:
            self._snapshot = None
            self._render()
        self.filters = filters
        self.period.value = filters.period
        self.provider.set_value(
            ProviderId(filters.provider_id) if filters.provider_id is not None else None
        )
        self._set_model_choices(
            tuple(
                choice
                for choice in self._model_choices.values()
                if filters.provider_id is None
                or choice.provider_id == filters.provider_id
            )
        )
        self.error.value = ""
        self.set_loading(True)
        return self._load_generation

    def is_current_load(self, generation: int, filters: AnalyticsFilter) -> bool:
        return (
            not self._cleared
            and generation == self._load_generation
            and filters == self.filters
        )

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
        self.provider.set_value(
            ProviderId(snapshot.filters.provider_id)
            if snapshot.filters.provider_id is not None
            else None
        )
        self._set_model_choices(snapshot.models)
        self.error.value = ""
        self.progress.visible = False
        self._render()
        self._update()

    def _set_model_choices(self, choices: tuple[ModelChoice, ...]) -> None:
        self._model_choices = {
            _model_key(choice): choice
            for choice in choices
            if choice.model_id is not None
        }
        self.model.options = [
            ft.DropdownOption(key="", text=str(tr("analytics.all_models"))),
            *[
                ft.DropdownOption(
                    key=key,
                    text=str(
                        tr(
                            "analytics.model_label",
                            provider=_provider_name(choice.provider_id),
                            model=choice.model_id,
                        )
                    ),
                )
                for key, choice in self._model_choices.items()
            ],
        ]
        self.model.value = next(
            (
                key
                for key, choice in self._model_choices.items()
                if choice.model_id == self.filters.model_id
                and (
                    self.filters.model_provider_id is None
                    or choice.provider_id == self.filters.model_provider_id
                )
            ),
            "",
        )

    def _render(self) -> None:
        selected_day = self._token_chart.selected_day if self._token_chart else None
        if self._token_chart is not None:
            self._token_chart.clear()
            self._token_chart = None
        for chart in self._charts:
            chart.clear()
        self._charts = []
        snapshot = self._snapshot
        if snapshot is None:
            self._body.controls = []
            return
        if self._kind == "tokens":
            self._render_usage(snapshot, selected_day=selected_day)
        else:
            self._render_spending(snapshot)

    def _render_usage(
        self, snapshot: AnalyticsSnapshot, *, selected_day: date | None = None
    ) -> None:
        rows = sorted(
            snapshot.usage_rows,
            key=lambda row: (
                -(row.total_tokens if row.total_tokens is not None else -1),
                row.provider_id,
                row.model_id or "",
            ),
        )
        self._token_chart = DailyTokenChart(snapshot.daily_tokens)
        if selected_day is not None:
            for index, day in enumerate(snapshot.daily_tokens):
                if day.day == selected_day:
                    self._token_chart.select_day(index, update=False)
                    break
        controls: list[ft.Control] = [
            ft.Text(
                tr("analytics.timezone", timezone=snapshot.timezone_name),
                color=MUTED_COLOR,
            ),
            surface(
                ft.Column(
                    tight=True,
                    spacing=12,
                    controls=[
                        ft.Text(tr("analytics.tokens_by_day"), size=21),
                        self._token_chart.control,
                    ],
                ),
                padding=16,
            ),
        ]
        if snapshot.undated_tokens.requests:
            controls.append(
                surface(
                    ft.Column(
                        tight=True,
                        spacing=8,
                        controls=[
                            ft.Text(tr("analytics.token_undated_summary"), size=18),
                            *_token_summary_controls(snapshot.undated_tokens),
                        ],
                    ),
                    padding=16,
                )
            )
        for provider in ProviderId:
            provider_rows = [row for row in rows if row.provider_id == provider]
            if not provider_rows:
                continue
            api_totals = [
                row.total_tokens
                for row in provider_rows
                if row.total_tokens is not None
            ]
            controls.append(
                surface(
                    ft.Column(
                        tight=True,
                        spacing=8,
                        controls=[
                            ft.Text(provider_spec(provider).name, size=18),
                            ft.Row(
                                wrap=True,
                                spacing=24,
                                controls=[
                                    _metric(
                                        tr("analytics.requests"),
                                        number(
                                            sum(row.requests for row in provider_rows)
                                        ),
                                    ),
                                    _metric(
                                        tr("analytics.api_total"),
                                        _tokens(
                                            sum(api_totals) if api_totals else None
                                        ),
                                    ),
                                    _metric(
                                        tr("analytics.api_requests"),
                                        number(
                                            sum(
                                                row.api_usage_requests
                                                for row in provider_rows
                                            )
                                        ),
                                    ),
                                    _metric(
                                        tr("analytics.unknown_requests"),
                                        number(
                                            sum(
                                                row.unknown_usage_requests
                                                for row in provider_rows
                                            )
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    padding=16,
                )
            )
        controls.append(ft.Text(tr("analytics.token_sources"), color=MUTED_COLOR))
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
            ft.Text(
                tr(
                    "analytics.currency_panel",
                    currency=currency,
                    provider=next(
                        spec.name
                        for provider in ProviderId
                        if (spec := provider_spec(provider)).currency == panel.currency
                    ),
                ),
                size=21,
            ),
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
            self.provider.sync_language()
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
        self._filter_generation += 1
        self._load_generation += 1
        self._snapshot = None
        self._model_choices.clear()
        if self._token_chart is not None:
            self._token_chart.clear()
            self._token_chart = None
        for chart in self._charts:
            chart.clear()
        self._charts = []
        self._body.controls = []
        self.model.options = []
        self.model.value = ""
        self.provider.set_value(None)
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
