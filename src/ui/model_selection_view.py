"""Выбор режима и модели для нового чата или его нового подключения."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import flet as ft

from auth.access import free_mode_allowed, paid_mode_allowed
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.models import (
    FREE_ROUTER_MODEL,
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


class ProviderConnectionStatus:
    """Only controller-supplied key metadata, with separate local click ownership."""

    def __init__(
        self,
        provider_id: ProviderId,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        *,
        on_check_key: AsyncCallback | None = None,
        key_check_busy: bool = False,
        key_notice: str | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.validity = key_validity
        self.limit = key_limit
        self._external_busy = key_check_busy
        self._notice = key_notice
        self._on_check_key = on_check_key
        self._on_change = on_change
        self._pending = False
        self._disposed = False
        self._revision = 0
        self.status = ft.Text("")
        self.limit_notice = ft.Text("", size=12, color=MUTED_COLOR)
        self.notice = ft.Text("", size=12, color=WARNING_COLOR)
        self.progress = ft.ProgressBar(visible=False)
        self.check_button = ft.TextButton(
            tr("selection.key.check"),
            icon=ft.Icons.KEY,
            style=secondary_button_style(),
            on_click=self._check,
            visible=on_check_key is not None,
        )
        self.control = ft.Container(
            bgcolor=PANEL_BACKGROUND,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=16,
            padding=16,
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    ft.Text(
                        tr(
                            "selection.connection",
                            provider=provider_spec(provider_id).name,
                        ),
                        weight=ft.FontWeight.BOLD,
                    ),
                    self.status,
                    self.limit_notice,
                    self.notice,
                    self.progress,
                    self.check_button,
                ],
            ),
        )
        self._render(notify=False)

    @property
    def busy(self) -> bool:
        return not self._disposed and (self._pending or self._external_busy)

    def set_connection_state(
        self,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        *,
        key_check_busy: bool = False,
        key_notice: str | None = None,
    ) -> None:
        if self._disposed:
            return
        self._revision += 1
        self.validity = key_validity
        self.limit = key_limit
        self._external_busy = key_check_busy
        self._notice = key_notice
        self._render()

    async def _check(self, _event: ft.Event[ft.TextButton]) -> None:
        callback = self._on_check_key
        if self._disposed or self.busy or callback is None:
            return
        revision = self._revision
        self._pending = True
        self._notice = None
        self._render()
        try:
            await callback()
        except Exception:
            # The controller supplies typed safe failures. Never echo an exception.
            if not self._disposed and revision == self._revision:
                self._notice = tr("selection.key.failed")
        finally:
            # A late local callback cannot clear a newer controller-owned busy flag.
            self._pending = False
            if not self._disposed:
                self._render()

    def _render(self, *, notify: bool = True) -> None:
        if self._disposed:
            return
        provider = provider_spec(self.provider_id).name
        if self.busy:
            value, color = (
                tr("selection.key.checking", provider=provider),
                WARNING_COLOR,
            )
        elif self.validity is KeyValidityState.VALID:
            value, color = (
                tr("selection.key.accepted", provider=provider),
                SUCCESS_COLOR,
            )
        else:
            value, color = key_access_mode_notice(
                self.validity,
                self.limit,
                provider_spec(self.provider_id).currency,
                provider_id=self.provider_id,
            )
        self.status.value, self.status.color = value, color
        limit, limit_color = (
            key_limit_mode_notice(
                self.limit,
                provider_spec(self.provider_id).currency,
                provider_id=self.provider_id,
            )
            if self.validity is KeyValidityState.VALID and not self.busy
            else ("", MUTED_COLOR)
        )
        self.limit_notice.value, self.limit_notice.color = limit, limit_color
        self.limit_notice.visible = bool(limit)
        self.notice.value = fresh_text(self._notice) if self._notice else ""
        self.notice.visible = bool(self._notice) and not self.busy
        self.progress.visible = self.busy
        self.check_button.disabled = self.busy or self._on_check_key is None
        if notify and self._on_change is not None:
            self._on_change()
        _update(self.control)

    def dispose(self) -> None:
        self._disposed = True
        self._external_busy = self._pending = False
        self._on_check_key = None
        self._on_change = None
        self._notice = None
        self.notice.value = self.status.value = self.limit_notice.value = ""
        self.progress.visible = False
        self.check_button.disabled = True
        self.control.content = ft.Container()


def _update(control: ft.Control) -> None:
    try:
        control.update()
    except (RuntimeError, AssertionError):
        pass


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
        changing_provider: bool = False,
        on_refresh: AsyncCallback | None = None,
        on_check_key: AsyncCallback | None = None,
        key_check_busy: bool = False,
        key_notice: str | None = None,
    ) -> None:
        choices = catalog.paid_models or catalog.free_models
        self.provider_id = provider_id or (
            choices[0].provider_id if choices else ProviderId.OPENROUTER
        )
        self._catalog = catalog
        self._changing_provider = changing_provider
        self._disposed = False
        self._refreshing = False
        self._on_select: ModeCallback | None = on_select
        self._on_cancel: AsyncCallback | None = on_cancel

        async def select_free(_event: ft.Event[ft.Button]) -> None:
            if not self._disposed and not self.free_button.disabled and self._on_select:
                await self._on_select(ChatMode.FREE)

        async def select_paid(_event: ft.Event[ft.Button]) -> None:
            if not self._disposed and not self.paid_button.disabled and self._on_select:
                await self._on_select(ChatMode.PAID)

        async def cancel(_event: ft.Event[ft.TextButton]) -> None:
            if not self._disposed and self._on_cancel:
                await self._on_cancel()

        self.free_button = ft.Button(
            tr("mode.choose_free"),
            icon=ft.Icons.SAVINGS,
            style=primary_button_style(),
            on_click=select_free,
        )
        self.paid_button = ft.Button(
            tr("mode.choose_paid"),
            icon=ft.Icons.PAYMENTS,
            style=primary_button_style(),
            on_click=select_paid,
        )
        self.connection_status = ProviderConnectionStatus(
            self.provider_id,
            key_validity,
            key_limit,
            on_check_key=on_check_key,
            key_check_busy=key_check_busy,
            key_notice=key_notice,
            on_change=self._sync_access,
        )
        self.check_key_button = self.connection_status.check_button
        free_card = ft.Container(
            bgcolor=PANEL_BACKGROUND,
            border_radius=16,
            padding=20,
            content=ft.Column(
                controls=[
                    ft.Text(tr("mode.free_title"), weight=ft.FontWeight.BOLD),
                    ft.Text(tr("mode.free_help"), color=MUTED_COLOR),
                    self.free_button,
                ]
            ),
        )
        controls: list[ft.Control] = [
            ft.Text(
                tr("connection.change_provider")
                if changing_provider
                else tr("chat.untitled"),
                theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
            ),
            ft.Text(
                tr(
                    "connection.choose_mode",
                    provider=provider_spec(self.provider_id).name,
                )
                if changing_provider
                else tr("mode.choose_first")
            ),
            self.connection_status.control,
            *(
                [free_card]
                if self.provider_id is ProviderId.OPENROUTER
                or bool(catalog.free_models)
                else [
                    ft.Text(
                        (
                            tr("mode.vsegpt_paid_only")
                            if catalog.paid_models
                            else tr("catalog.empty")
                        )
                        if catalog.available
                        else tr("mode.vsegpt_modes_unknown"),
                        color=MUTED_COLOR,
                    )
                ]
            ),
            ft.Container(
                bgcolor=PANEL_BACKGROUND,
                border_radius=16,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text(tr("mode.paid_title"), weight=ft.FontWeight.BOLD),
                        ft.Text(tr("workspace.mode_paid_help"), color=MUTED_COLOR),
                        self.paid_button,
                    ]
                ),
            ),
        ]
        if catalog.warning:
            controls.append(ft.Text(fresh_text(catalog.warning), color=ERROR_COLOR))
        if catalog.retry_after:
            controls.append(
                ft.Text(
                    tr("catalog.retry_wait", seconds=catalog.retry_after),
                    color=MUTED_COLOR,
                )
            )
        self.refresh_button: ft.TextButton | None = None
        if on_refresh is not None:

            async def refresh(_event: ft.Event[ft.TextButton]) -> None:
                if self._disposed or self._refreshing or self.connection_status.busy:
                    return
                self._refreshing = True
                self._sync_access()
                try:
                    await on_refresh()
                finally:
                    self._refreshing = False
                    if not self._disposed:
                        self._sync_access()

            self.refresh_button = ft.TextButton(
                tr("catalog.refresh"), icon=ft.Icons.REFRESH, on_click=refresh
            )
            controls.append(self.refresh_button)
        self.cancel_button = ft.TextButton(tr("mode.back_chats"), on_click=cancel)
        controls.append(self.cancel_button)
        self.control = build_auth_screen(controls, header=BrandHeader(), width=560)
        self._sync_access()

    def _sync_access(self) -> None:
        if self._disposed:
            return
        busy = self.connection_status.busy or self._refreshing
        self.free_button.disabled = busy or not (
            free_mode_allowed(self.connection_status.validity)
            and bool(self._catalog.free_models)
            and (not self._changing_provider or self._catalog.available)
        )
        self.paid_button.disabled = busy or not (
            paid_mode_allowed(
                self.connection_status.validity,
                self.connection_status.limit,
                self.provider_id,
            )
            and self._catalog.available
            and bool(self._catalog.paid_models)
        )
        if self.refresh_button is not None:
            self.refresh_button.disabled = busy
        if hasattr(self, "control"):
            _update(self.control)

    def set_connection_state(
        self,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        *,
        key_check_busy: bool = False,
        key_notice: str | None = None,
    ) -> None:
        self.connection_status.set_connection_state(
            key_validity,
            key_limit,
            key_check_busy=key_check_busy,
            key_notice=key_notice,
        )

    def dispose(self) -> None:
        self._disposed = True
        self._on_select = self._on_cancel = None
        self.connection_status.dispose()
        self.free_button.disabled = self.paid_button.disabled = (
            self.cancel_button.disabled
        ) = True
        self._catalog = ModelCatalog((), (), False)
        self.control.content = ft.Container()


class ModelSelectionView:
    def __init__(
        self,
        mode: ChatMode,
        models: tuple[CatalogModel, ...],
        on_select: ModelCallback,
        on_cancel: AsyncCallback,
        *,
        provider_id: ProviderId | None = None,
        catalog: ModelCatalog | None = None,
        key_validity: KeyValidityState = KeyValidityState.UNKNOWN,
        key_limit: KeyLimitInfo | None = None,
        on_check_key: AsyncCallback | None = None,
        on_refresh: AsyncCallback | None = None,
        key_check_busy: bool = False,
        key_notice: str | None = None,
        changing_provider: bool = False,
    ) -> None:
        self.provider_id = provider_id or (
            models[0].provider_id if models else ProviderId.OPENROUTER
        )
        self._models = tuple(
            model for model in models if model.provider_id is self.provider_id
        )
        self._mode = mode
        self._changing_provider = changing_provider
        self._on_select: ModelCallback | None = on_select
        self._on_cancel: AsyncCallback | None = on_cancel
        self._disposed = False
        self._refreshing = False
        self._catalog = catalog or ModelCatalog(
            models if mode is ChatMode.FREE else (),
            models if mode is ChatMode.PAID else (),
            True,
        )
        self.connection_status = ProviderConnectionStatus(
            self.provider_id,
            key_validity,
            key_limit or KeyLimitInfo.unknown(),
            on_check_key=on_check_key,
            key_check_busy=key_check_busy,
            key_notice=key_notice,
            on_change=self._sync_access,
        )
        self.check_key_button = self.connection_status.check_button
        self.refresh_button: ft.TextButton | None = None
        if on_refresh is not None:

            async def refresh(_event: ft.Event[ft.TextButton]) -> None:
                if self._disposed or self._refreshing or self.connection_status.busy:
                    return
                self._refreshing = True
                self._sync_access()
                try:
                    await on_refresh()
                finally:
                    self._refreshing = False
                    if not self._disposed:
                        self._sync_access()

            self.refresh_button = ft.TextButton(
                tr("catalog.refresh"), icon=ft.Icons.REFRESH, on_click=refresh
            )

        async def cancel(_event: ft.Event[ft.TextButton]) -> None:
            if not self._disposed and self._on_cancel:
                await self._on_cancel()

        self.cancel_button = ft.TextButton(
            tr("common.back"),
            height=48,
            style=secondary_button_style(),
            on_click=cancel,
        )
        self.search = ft.TextField(
            **input_style(),
            label=tr("catalog.search"),
            hint_text=tr("catalog.search_hint"),
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._filter,
        )
        self.results = ft.ListView(expand=True, spacing=10)
        self._render_results(self._models)
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
                                    tr("connection.change_provider")
                                    if changing_provider
                                    else tr("selection.models.vsegpt")
                                    if self.provider_id is ProviderId.VSEGPT
                                    else tr(
                                        "catalog.select_free"
                                        if mode is ChatMode.FREE
                                        else "catalog.select_paid"
                                    ),
                                    theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                                ),
                                self.search,
                                self.cancel_button,
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
        _update(self.results)

    def _router_fallback(self, model: CatalogModel) -> bool:
        return (
            not self._changing_provider
            and self.provider_id is ProviderId.OPENROUTER
            and self._mode is ChatMode.FREE
            and model == FREE_ROUTER_MODEL
        )

    def _can_select(self, model: CatalogModel) -> bool:
        return (
            not self._disposed
            and not self.connection_status.busy
            and not self._refreshing
            and (self._catalog.available or self._router_fallback(model))
            and model in self._models
            and model.provider_id is self.provider_id
            and (
                paid_mode_allowed(
                    self.connection_status.validity,
                    self.connection_status.limit,
                    self.provider_id,
                )
                if self._mode is ChatMode.PAID
                else free_mode_allowed(self.connection_status.validity)
            )
        )

    def _render_results(self, models: tuple[CatalogModel, ...]) -> None:
        if self._disposed:
            return
        leading: list[ft.Control] = [self.connection_status.control]
        if self.refresh_button is not None:
            self.refresh_button.disabled = (
                self.connection_status.busy or self._refreshing
            )
            leading.append(self.refresh_button)
        if self.provider_id is ProviderId.VSEGPT:
            leading.append(
                ft.Text(tr("selection.models.vsegpt_paid"), color=MUTED_COLOR)
            )
        if not self._catalog.available:
            leading.append(
                ft.Text(
                    fresh_text(self._catalog.warning)
                    if self._catalog.warning
                    else tr("selection.catalog.unavailable"),
                    color=ERROR_COLOR,
                )
            )
            if self._catalog.retry_after:
                leading.append(
                    ft.Text(
                        tr("catalog.retry_wait", seconds=self._catalog.retry_after),
                        color=MUTED_COLOR,
                    )
                )
            if free_mode_allowed(self.connection_status.validity):
                leading.extend(
                    self._model_card(model)
                    for model in models
                    if self._router_fallback(model)
                )
        elif not (
            paid_mode_allowed(
                self.connection_status.validity,
                self.connection_status.limit,
                self.provider_id,
            )
            if self._mode is ChatMode.PAID
            else free_mode_allowed(self.connection_status.validity)
        ):
            leading.append(
                ft.Text(
                    tr(
                        "selection.models.check_key",
                        provider=provider_spec(self.provider_id).name,
                    ),
                    color=WARNING_COLOR,
                )
            )
        elif not self._models:
            leading.append(ft.Text(tr("catalog.empty"), color=MUTED_COLOR))
        elif not models:
            leading.append(ft.Text(tr("catalog.none"), color=MUTED_COLOR))
        else:
            leading.extend(self._model_card(model) for model in models)
        self.results.controls = leading

    def _sync_access(self) -> None:
        if self._disposed or not hasattr(self, "results"):
            return
        query = self.search.value if isinstance(self.search.value, str) else ""
        self._render_results(filter_models(self._models, query))
        _update(self.results)

    def set_connection_state(
        self,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        *,
        key_check_busy: bool = False,
        key_notice: str | None = None,
    ) -> None:
        self.connection_status.set_connection_state(
            key_validity,
            key_limit,
            key_check_busy=key_check_busy,
            key_notice=key_notice,
        )

    def set_catalog(self, catalog: ModelCatalog) -> None:
        if self._disposed:
            return
        self._catalog = catalog
        models = (
            catalog.free_models if self._mode is ChatMode.FREE else catalog.paid_models
        )
        self._models = tuple(
            model for model in models if model.provider_id is self.provider_id
        )
        self._sync_access()

    def dispose(self) -> None:
        self._disposed = True
        self._models = ()
        self._on_select = self._on_cancel = None
        self.connection_status.dispose()
        self.search.value = ""
        self.results.controls = []
        self.cancel_button.disabled = True

    def _model_card(self, model: CatalogModel) -> ft.Control:
        async def select_model(_event: ft.Event[ft.Button]) -> None:
            if self._can_select(model) and self._on_select:
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
                        disabled=not self._can_select(model),
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
            tr("selection.key.not_checked", provider=provider_spec(provider_id).name),
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
