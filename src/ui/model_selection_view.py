"""Экраны выбора режима и модели нового чата."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import flet as ft

from auth.access import free_mode_allowed, paid_mode_allowed
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.models import (
    CatalogModel,
    ChatMode,
    ModelCatalog,
    maximum_pricing,
)
from i18n import display_model_name, fresh_text, money, number, tr
from providers.models import Currency, PriceUnit, ProviderId, provider_spec
from ui.branding import BrandHeader, BrandLoader
from ui.styles import (
    BORDER_COLOR,
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    SUCCESS_COLOR,
    WARNING_COLOR,
    build_auth_screen,
    detail_row,
    input_style,
    primary_button_style,
    secondary_button_style,
)

ModeCallback = Callable[[ChatMode], Awaitable[None]]
ModelCallback = Callable[[CatalogModel], Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


class CatalogLoadingView:
    def __init__(self, on_cancel: AsyncCallback) -> None:
        async def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
            await on_cancel()

        self.progress = BrandLoader()
        self.control = build_auth_screen(
            [
                ft.Text(
                    tr("catalog.loading"),
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                ),
                ft.Row(controls=[self.progress]),
                ft.Text(
                    tr("catalog.read_only"),
                    color=MUTED_COLOR,
                ),
                ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
            ],
            header=BrandHeader(),
            width=560,
        )


class ModeSelectionView:
    def __init__(
        self,
        catalog: ModelCatalog,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        on_select: ModeCallback,
        on_cancel: AsyncCallback,
        *,
        provider_id: ProviderId | None = None,
    ) -> None:
        async def select_free(_event: ft.Event[ft.Button]) -> None:
            await on_select(ChatMode.FREE)

        async def select_paid(_event: ft.Event[ft.Button]) -> None:
            await on_select(ChatMode.PAID)

        async def cancel(_event: ft.Event[ft.TextButton]) -> None:
            await on_cancel()

        choices = catalog.paid_models or catalog.free_models
        provider_id = provider_id or (
            choices[0].provider_id if choices else ProviderId.OPENROUTER
        )
        paid_enabled = (
            paid_mode_allowed(key_validity, key_limit, provider_id)
            and catalog.available
            and bool(catalog.paid_models)
        )
        currency = provider_spec(provider_id).currency
        limit_notice, limit_notice_color = key_access_mode_notice(
            key_validity,
            key_limit,
            currency,
            provider_id=provider_id,
        )
        self.free_button = ft.Button(
            tr("mode.choose_free"),
            icon=ft.Icons.SAVINGS,
            style=primary_button_style(),
            disabled=not (
                free_mode_allowed(key_validity) and bool(catalog.free_models)
            ),
            on_click=select_free,
        )
        self.paid_button = ft.Button(
            tr("mode.choose_paid"),
            icon=ft.Icons.PAYMENTS,
            style=primary_button_style(),
            disabled=not paid_enabled,
            on_click=select_paid,
        )
        controls: list[ft.Control] = [
            ft.Text(tr("chat.untitled"), theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
            ft.Text(tr("mode.choose_first")),
            ft.Container(
                bgcolor=PANEL_BACKGROUND,
                border_radius=16,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text(tr("mode.free_title"), weight=ft.FontWeight.BOLD),
                        ft.Text(
                            tr("mode.free_help"),
                            color=MUTED_COLOR,
                        ),
                        self.free_button,
                    ]
                ),
            ),
            ft.Container(
                bgcolor=PANEL_BACKGROUND,
                border_radius=16,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text(tr("mode.paid_title"), weight=ft.FontWeight.BOLD),
                        ft.Text(
                            tr("workspace.mode_paid_help"),
                            color=MUTED_COLOR,
                        ),
                        ft.Text(limit_notice, color=limit_notice_color),
                        self.paid_button,
                    ]
                ),
            ),
        ]
        if catalog.warning:
            controls.append(ft.Text(fresh_text(catalog.warning), color=ERROR_COLOR))
        controls.append(ft.TextButton(tr("mode.back_chats"), on_click=cancel))
        self.control = build_auth_screen(controls, header=BrandHeader(), width=560)


class ModelSelectionView:
    def __init__(
        self,
        mode: ChatMode,
        models: tuple[CatalogModel, ...],
        on_select: ModelCallback,
        on_cancel: AsyncCallback,
    ) -> None:
        self._models = models
        self._mode = mode
        self._on_select = on_select

        async def cancel(_event: ft.Event[ft.TextButton]) -> None:
            await on_cancel()

        self.search = ft.TextField(
            **input_style(),
            label=tr("catalog.search"),
            hint_text=tr("catalog.search_hint"),
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._filter,
        )
        self.results = ft.ListView(expand=True, spacing=10)
        self._render_results(models)
        self.control = ft.SafeArea(
            expand=True,
            maintain_bottom_view_padding=True,
            content=ft.Column(
                expand=True,
                spacing=12,
                controls=[
                    ft.Container(
                        padding=20,
                        content=ft.Column(
                            controls=[
                                BrandHeader(),
                                ft.Text(
                                    tr(
                                        "catalog.select_free"
                                        if mode is ChatMode.FREE
                                        else "catalog.select_paid"
                                    ),
                                    theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                                ),
                                self.search,
                                ft.TextButton(
                                    tr("common.back"),
                                    height=48,
                                    style=secondary_button_style(),
                                    on_click=cancel,
                                ),
                            ]
                        ),
                    ),
                    ft.Container(
                        expand=True,
                        padding=ft.Padding(20, 0, 20, 20),
                        content=self.results,
                    ),
                ],
            ),
        )

    def _filter(self, _event: ft.Event[ft.TextField]) -> None:
        query = self.search.value
        filtered = filter_models(self._models, query if isinstance(query, str) else "")
        self._render_results(filtered)
        self.results.update()

    def _render_results(self, models: tuple[CatalogModel, ...]) -> None:
        if not models:
            self.results.controls = [ft.Text(tr("catalog.none"), color=MUTED_COLOR)]
            return
        self.results.controls = [self._model_card(model) for model in models]

    def _model_card(self, model: CatalogModel) -> ft.Control:
        async def select_model(_event: ft.Event[ft.Button]) -> None:
            await self._on_select(model)

        displayed_pricing = (
            maximum_pricing(model)
            if self._mode is ChatMode.PAID
            else model.base_pricing
        )
        details: list[ft.Control] = [
            ft.Text(provider_spec(model.provider_id).name, color=MUTED_COLOR),
            ft.Text(model.id, color=MUTED_COLOR, selectable=True),
        ]
        if model.pricing_is_complete and model.pricing_unit is PriceUnit.TOKEN:
            details.extend(
                [
                    detail_row(
                        tr("price.prompt_million"),
                        money_million(displayed_pricing.prompt, model.currency),
                    ),
                    detail_row(
                        tr("price.completion_million"),
                        money_million(displayed_pricing.completion, model.currency),
                    ),
                ]
            )
            if self._mode is ChatMode.PAID:
                details.extend(_additional_price_controls(model))
        else:
            details.append(
                ft.Text(tr("workspace.pricing_unknown"), color=WARNING_COLOR)
            )
        if model.recommended:
            details.insert(0, ft.Text(tr("catalog.recommended"), color=SUCCESS_COLOR))
        return ft.Container(
            bgcolor=PANEL_BACKGROUND,
            border_radius=16,
            border=ft.Border.all(1, BORDER_COLOR),
            padding=16,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(
                        display_model_name(model.id, model.name),
                        weight=ft.FontWeight.BOLD,
                    ),
                    *details,
                    ft.Button(
                        tr("catalog.select"),
                        style=primary_button_style(),
                        height=48,
                        on_click=select_model,
                    ),
                ],
            ),
        )


def filter_models(
    models: tuple[CatalogModel, ...],
    query: str,
) -> tuple[CatalogModel, ...]:
    """Фильтрует снимок каталога по имени или ID без изменения порядка."""
    normalized_query = query.strip().casefold()
    return tuple(
        model
        for model in models
        if not normalized_query
        or normalized_query in model.name.casefold()
        or normalized_query in model.id.casefold()
        or normalized_query in display_model_name(model.id, model.name).casefold()
    )


def key_limit_mode_notice(
    key_limit: KeyLimitInfo,
    currency: Currency = Currency.USD,
    *,
    provider_id: ProviderId = ProviderId.OPENROUTER,
) -> tuple[str, str]:
    """Описывает лимит ключа, не называя его балансом аккаунта."""
    if not provider_spec(provider_id).supports_key_limit:
        return "", MUTED_COLOR
    if key_limit.state is KeyLimitState.EXHAUSTED:
        return (
            tr("key.exhausted_notice"),
            ERROR_COLOR,
        )
    if key_limit.state is KeyLimitState.NOT_SET:
        return (
            tr("key.unlimited_notice"),
            MUTED_COLOR,
        )
    if key_limit.state is KeyLimitState.AVAILABLE:
        return (
            tr(
                "key.available_notice"
                if currency is Currency.USD
                else "workspace.key_available_notice",
                amount=(
                    number(key_limit.remaining)
                    if currency is Currency.USD
                    else money(key_limit.remaining, currency)
                )
                if key_limit.remaining is not None
                else "—",
            ),
            SUCCESS_COLOR,
        )
    return (
        tr("key.unknown_limit_notice"),
        ERROR_COLOR,
    )


def key_access_mode_notice(
    key_validity: KeyValidityState,
    key_limit: KeyLimitInfo,
    currency: Currency = Currency.USD,
    *,
    provider_id: ProviderId = ProviderId.OPENROUTER,
) -> tuple[str, str]:
    """Показывает валидность отдельно от расходного лимита."""
    if key_validity is KeyValidityState.INVALID:
        return (
            tr("key.invalid_notice"),
            ERROR_COLOR,
        )
    if key_validity is KeyValidityState.RESTRICTED:
        return (
            tr("key.restricted_notice"),
            WARNING_COLOR,
        )
    if key_validity is KeyValidityState.UNKNOWN:
        return (
            tr("key.checking_notice"),
            WARNING_COLOR,
        )
    if key_validity is KeyValidityState.UNVERIFIED:
        return (
            tr("metrics.key_unverified", provider=provider_spec(provider_id).name),
            WARNING_COLOR,
        )
    return key_limit_mode_notice(key_limit, currency, provider_id=provider_id)


def _additional_price_controls(model: CatalogModel) -> list[ft.Control]:
    pricing = maximum_pricing(model)
    details: list[ft.Control] = []
    if pricing.request > 0:
        details.append(
            detail_row(tr("price.request"), money(pricing.request, model.currency))
        )
    if pricing.internal_reasoning > 0:
        details.append(
            detail_row(
                tr("price.reasoning_million"),
                money_million(pricing.internal_reasoning, model.currency),
            )
        )
    if pricing.input_cache_read > 0:
        details.append(
            detail_row(
                tr("price.cache_read_million"),
                money_million(pricing.input_cache_read, model.currency),
            )
        )
    if pricing.input_cache_write > 0:
        details.append(
            detail_row(
                tr("price.cache_write_million"),
                money_million(pricing.input_cache_write, model.currency),
            )
        )
    if model.pricing_overrides:
        details.append(
            ft.Text(
                tr("price.overrides_help"),
                size=12,
                color=MUTED_COLOR,
            )
        )
    if not details:
        return []
    return [ft.Text(tr("price.additional"), size=12, color=MUTED_COLOR), *details]


def money_million(value: Decimal, currency: Currency = Currency.USD) -> str:
    return money(value * Decimal(1_000_000), currency)
