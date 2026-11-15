"""Local request-journal projections. Money never crosses currency boundaries."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from providers.models import Currency, ProviderId

ZERO = Decimal("0")


@dataclass(frozen=True)
class RequestAttempt:
    sequence: int
    turn_id: str
    chat_id: str
    provider_id: ProviderId = ProviderId.OPENROUTER
    currency: Currency = Currency.USD
    requested_model_id: str | None = None
    actual_model_id: str | None = None
    sent_at: datetime | None = None
    chronology_known: bool = False
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    usage_source: str = "unknown"
    cost: Decimal | None = None
    cost_source: str = "unknown"
    accounting_status: str = "unknown"
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    reserved_cost: Decimal | None = None
    reserved_tokens: int | None = None

    @property
    def model_id(self) -> str | None:
        return self.actual_model_id or self.requested_model_id


@dataclass(frozen=True)
class AnalyticsFilter:
    period: Literal["7d", "30d", "all"] = "7d"
    provider_id: str | None = None
    model_id: str | None = None
    timezone_name: str | None = None


@dataclass(frozen=True)
class ModelChoice:
    provider_id: ProviderId
    model_id: str | None


@dataclass(frozen=True)
class ModelUsage:
    provider_id: ProviderId
    model_id: str | None
    requests: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    api_usage_requests: int
    estimated_prompt_tokens: int | None
    estimated_completion_tokens: int | None
    estimated_total_tokens: int | None
    estimated_usage_requests: int
    unknown_usage_requests: int
    undated_requests: int


@dataclass(frozen=True)
class DailySpending:
    day: date
    confirmed: Decimal
    estimated: Decimal
    unknown_requests: int


@dataclass(frozen=True)
class CurrencySpending:
    currency: Currency
    days: tuple[DailySpending, ...]
    confirmed_total: Decimal
    estimated_total: Decimal
    average_per_day: Decimal
    undated_confirmed_total: Decimal
    undated_estimated_total: Decimal
    unknown_cost_requests: int
    undated_requests: int


@dataclass(frozen=True)
class AnalyticsSnapshot:
    filters: AnalyticsFilter
    models: tuple[ModelChoice, ...]
    usage_rows: tuple[ModelUsage, ...]
    spending: tuple[CurrencySpending, ...]
    start_date: date
    end_date: date
    timezone_name: str
    undated_requests: int


def _timezone(name: str | None) -> tuple[tzinfo, str]:
    name = name or os.environ.get("TZ")
    if name:
        zone = ZoneInfo(name)
        return zone, name
    # Most Linux systems expose the configured IANA zone through localtime.
    # Resolve it before falling back to the device libc timezone rules.
    localtime = Path("/etc/localtime")
    try:
        target = str(localtime.resolve())
        if "/zoneinfo/" in target:
            name = target.split("/zoneinfo/", 1)[1]
            return ZoneInfo(name), name
    except (OSError, ValueError):
        pass
    zone = datetime.now().astimezone().tzinfo or UTC
    return _DeviceTimezone(), str(zone)


class _DeviceTimezone(tzinfo):
    """Marker for per-event libc timezone conversion, including historical DST."""


def _local(value: datetime, zone: tzinfo) -> datetime:
    return (
        value.astimezone()
        if isinstance(zone, _DeviceTimezone)
        else value.astimezone(zone)
    )


def _day(attempt: RequestAttempt, zone: tzinfo) -> date | None:
    if not attempt.chronology_known or attempt.sent_at is None:
        return None
    if attempt.sent_at.tzinfo is None:
        return None
    return _local(attempt.sent_at, zone).date()


def _tokens(attempts: list[RequestAttempt], field: str, source: str) -> int | None:
    values = [
        value
        for item in attempts
        if item.usage_source == source and (value := getattr(item, field)) is not None
    ]
    return sum(values) if values else None


def build_analytics(
    attempts: Iterable[RequestAttempt],
    filters: AnalyticsFilter,
    now: datetime | None = None,
) -> AnalyticsSnapshot:
    if filters.period not in {"7d", "30d", "all"}:
        raise ValueError("analytics_period_invalid")
    zone, zone_name = _timezone(filters.timezone_name)
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("analytics_now_requires_timezone")
    end = _local(timestamp, zone).date()
    # Defensive identity deduplication: a repeated projection/result cannot
    # manufacture another dispatch. Actual retries have distinct sequences.
    unique = {item.sequence: item for item in attempts}
    records = list(unique.values())
    choices = tuple(
        ModelChoice(provider, model)
        for provider, model in sorted(
            {(item.provider_id, item.model_id) for item in records},
            key=lambda value: (value[0], value[1] or ""),
        )
    )
    matching = [
        item
        for item in records
        if (filters.provider_id is None or item.provider_id == filters.provider_id)
        and (filters.model_id is None or item.model_id == filters.model_id)
    ]
    dated = [day for item in matching if (day := _day(item, zone)) is not None]
    if filters.period == "all":
        start = min(dated, default=end)
        end = max(end, max(dated, default=end))
    else:
        start = end - timedelta(days=6 if filters.period == "7d" else 29)
    selected = [
        item
        for item in matching
        if ((day := _day(item, zone)) is None and filters.period == "all")
        or (day is not None and start <= day <= end)
    ]
    groups: dict[tuple[ProviderId, str | None], list[RequestAttempt]] = defaultdict(
        list
    )
    currencies: dict[Currency, list[RequestAttempt]] = defaultdict(list)
    for item in selected:
        groups[item.provider_id, item.model_id].append(item)
        currencies[item.currency].append(item)
    usage = []
    for (provider, model), items in groups.items():
        known = sum(
            item.usage_source == "api"
            and any(
                value is not None
                for value in (
                    item.prompt_tokens,
                    item.completion_tokens,
                    item.total_tokens,
                )
            )
            for item in items
        )
        estimated = sum(
            item.usage_source == "estimated"
            and any(
                value is not None
                for value in (
                    item.prompt_tokens,
                    item.completion_tokens,
                    item.total_tokens,
                )
            )
            for item in items
        )
        incomplete = sum(
            item.usage_source == "unknown"
            or any(
                value is None
                for value in (
                    item.prompt_tokens,
                    item.completion_tokens,
                    item.total_tokens,
                )
            )
            for item in items
        )
        usage.append(
            ModelUsage(
                provider,
                model,
                len(items),
                _tokens(items, "prompt_tokens", "api"),
                _tokens(items, "completion_tokens", "api"),
                _tokens(items, "total_tokens", "api"),
                known,
                _tokens(items, "prompt_tokens", "estimated"),
                _tokens(items, "completion_tokens", "estimated"),
                _tokens(items, "total_tokens", "estimated"),
                estimated,
                incomplete,
                sum(_day(item, zone) is None for item in items),
            )
        )
    usage.sort(
        key=lambda item: (
            -(item.total_tokens or 0),
            -(item.estimated_total_tokens or 0),
            item.provider_id,
            item.model_id or "",
        )
    )
    panels = []
    day_count = (end - start).days + 1
    for currency, items in sorted(currencies.items()):
        daily: dict[date, list[RequestAttempt]] = defaultdict(list)
        undated = []
        for item in items:
            day = _day(item, zone)
            (undated if day is None else daily[day]).append(item)
        days = []
        for offset in range(day_count):
            day = start + timedelta(days=offset)
            entries = daily[day]
            days.append(
                DailySpending(
                    day,
                    sum(
                        (
                            item.cost
                            for item in entries
                            if item.cost is not None and item.cost_source == "api"
                        ),
                        ZERO,
                    ),
                    sum(
                        (
                            item.cost
                            for item in entries
                            if item.cost is not None and item.cost_source == "estimated"
                        ),
                        ZERO,
                    ),
                    sum(
                        item.cost is None or item.cost_source == "unknown"
                        for item in entries
                    ),
                )
            )
        confirmed = sum((day.confirmed for day in days), ZERO)
        estimated_cost = sum((day.estimated for day in days), ZERO)
        panels.append(
            CurrencySpending(
                currency,
                tuple(days),
                confirmed,
                estimated_cost,
                confirmed / Decimal(day_count),
                sum(
                    (
                        item.cost
                        for item in undated
                        if item.cost is not None and item.cost_source == "api"
                    ),
                    ZERO,
                ),
                sum(
                    (
                        item.cost
                        for item in undated
                        if item.cost is not None and item.cost_source == "estimated"
                    ),
                    ZERO,
                ),
                sum(
                    item.cost is None or item.cost_source == "unknown" for item in items
                ),
                len(undated),
            )
        )
    return AnalyticsSnapshot(
        filters,
        choices,
        tuple(usage),
        tuple(panels),
        start,
        end,
        zone_name,
        sum(_day(item, zone) is None for item in selected),
    )
