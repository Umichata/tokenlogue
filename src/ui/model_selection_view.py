"""Экраны выбора режима и модели нового чата."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from auth.access import free_mode_allowed, paid_mode_allowed
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.models import (
    CatalogModel,
    ChatMode,
    ModelCatalog,
    format_price_per_million,
    maximum_pricing,
)
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    SUCCESS_COLOR,
    build_screen,
    primary_button_style,
)

ModeCallback = Callable[[ChatMode], Awaitable[None]]
ModelCallback = Callable[[CatalogModel], Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


class CatalogLoadingView:
    def __init__(self, on_cancel: AsyncCallback) -> None:
        async def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
            await on_cancel()

        self.control = build_screen(
            [
                ft.Text(
                    "Загрузка каталога моделей",
                    theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM,
                ),
                ft.ProgressRing(),
                ft.Text(
                    "Выполняется только чтение списка моделей OpenRouter.",
                    color=MUTED_COLOR,
                ),
                ft.TextButton("Отмена", on_click=handle_cancel),
            ]
        )


class ModeSelectionView:
    def __init__(
        self,
        catalog: ModelCatalog,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        on_select: ModeCallback,
        on_cancel: AsyncCallback,
    ) -> None:
        async def select_free(_event: ft.Event[ft.Button]) -> None:
            await on_select(ChatMode.FREE)

        async def select_paid(_event: ft.Event[ft.Button]) -> None:
            await on_select(ChatMode.PAID)

        async def cancel(_event: ft.Event[ft.TextButton]) -> None:
            await on_cancel()

        paid_enabled = (
            paid_mode_allowed(key_validity, key_limit)
            and catalog.available
            and bool(catalog.paid_models)
        )
        limit_notice, limit_notice_color = key_access_mode_notice(
            key_validity,
            key_limit,
        )
        self.free_button = ft.Button(
            "Выбрать бесплатный режим",
            icon=ft.Icons.SAVINGS,
            style=primary_button_style(),
            disabled=not free_mode_allowed(key_validity),
            on_click=select_free,
        )
        self.paid_button = ft.Button(
            "Выбрать платный режим",
            icon=ft.Icons.PAYMENTS,
            style=primary_button_style(),
            disabled=not paid_enabled,
            on_click=select_paid,
        )
        controls: list[ft.Control] = [
            ft.Text("Новый чат", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
            ft.Text("Сначала выберите режим использования модели."),
            ft.Container(
                bgcolor=PANEL_BACKGROUND,
                border_radius=16,
                padding=20,
                content=ft.Column(
                    controls=[
                        ft.Text("Бесплатный режим", weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Бесплатный режим не расходует средства, но имеет "
                            "ограничения по количеству запросов и доступности моделей. "
                            "Используется openrouter/free или модель со всеми "
                            "применимыми нулевыми компонентами цены.",
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
                        ft.Text("Платный режим", weight=ft.FontWeight.BOLD),
                        ft.Text(
                            "Перед созданием будет показано отдельное предупреждение "
                            "о возможных расходах. Баланс аккаунта будет проверен "
                            "OpenRouter при платном запросе.",
                            color=MUTED_COLOR,
                        ),
                        ft.Text(limit_notice, color=limit_notice_color),
                        self.paid_button,
                    ]
                ),
            ),
        ]
        if catalog.warning:
            controls.append(ft.Text(catalog.warning, color=ERROR_COLOR))
        controls.append(ft.TextButton("Назад к чатам", on_click=cancel))
        self.control = build_screen(controls)


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
            label="Поиск модели",
            hint_text="Название или ID",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._filter,
        )
        self.results = ft.ListView(expand=True, spacing=10)
        self._render_results(models)
        mode_name = "бесплатного" if mode is ChatMode.FREE else "платного"
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
                                ft.Text(
                                    f"Выбор модели для {mode_name} чата",
                                    theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                                ),
                                self.search,
                                ft.TextButton("Назад", on_click=cancel),
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
            self.results.controls = [
                ft.Text("Подходящие модели не найдены.", color=MUTED_COLOR)
            ]
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
            ft.Text(model.id, color=MUTED_COLOR, selectable=True),
            ft.Text(
                "Вход: "
                f"${format_price_per_million(displayed_pricing.prompt)} / 1 млн; "
                "выход: "
                f"${format_price_per_million(displayed_pricing.completion)} / 1 млн",
                size=12,
            ),
        ]
        if self._mode is ChatMode.PAID:
            details.extend(_additional_price_controls(model))
        if model.recommended:
            details.insert(0, ft.Text("Рекомендуется", color=SUCCESS_COLOR))
        return ft.Container(
            bgcolor=PANEL_BACKGROUND,
            border_radius=12,
            padding=14,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Text(model.name, weight=ft.FontWeight.BOLD),
                    *details,
                    ft.Button(
                        "Выбрать",
                        style=primary_button_style(),
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
    )


def key_limit_mode_notice(key_limit: KeyLimitInfo) -> tuple[str, str]:
    """Описывает лимит ключа, не называя его балансом аккаунта."""
    if key_limit.state is KeyLimitState.EXHAUSTED:
        return (
            "Расходный лимит этого ключа исчерпан. Бесплатный режим остаётся доступным",
            ERROR_COLOR,
        )
    if key_limit.state is KeyLimitState.NOT_SET:
        return (
            "Для ключа не установлен отдельный расходный лимит. "
            "Это не подтверждает наличие средств на аккаунте.",
            MUTED_COLOR,
        )
    if key_limit.state is KeyLimitState.AVAILABLE:
        return (
            f"Доступный лимит ключа: {key_limit.remaining} USD. "
            "Это не баланс аккаунта.",
            SUCCESS_COLOR,
        )
    return (
        "Доступный лимит ключа не удалось проверить. Платный режим временно "
        "недоступен. Бесплатный режим остаётся доступным.",
        ERROR_COLOR,
    )


def key_access_mode_notice(
    key_validity: KeyValidityState,
    key_limit: KeyLimitInfo,
) -> tuple[str, str]:
    """Показывает валидность отдельно от расходного лимита."""
    if key_validity is KeyValidityState.INVALID:
        return (
            "Сохранённый ключ OpenRouter недействителен или отозван. "
            "Замените ключ, чтобы продолжить работу с моделями.",
            ERROR_COLOR,
        )
    if key_validity is KeyValidityState.RESTRICTED:
        return (
            "OpenRouter отклонил проверку разрешений ключа. Бесплатный запрос "
            "также может завершиться ошибкой. Платный режим недоступен.",
            ft.Colors.AMBER_300,
        )
    if key_validity is KeyValidityState.UNKNOWN:
        return (
            "Проверка ключа ещё не завершена. Бесплатный режим доступен, "
            "платный режим временно закрыт.",
            ft.Colors.AMBER_300,
        )
    return key_limit_mode_notice(key_limit)


def _additional_price_controls(model: CatalogModel) -> list[ft.Control]:
    pricing = maximum_pricing(model)
    details: list[str] = []
    if pricing.request > 0:
        details.append(f"за запрос: ${pricing.request}")
    if pricing.internal_reasoning > 0:
        details.append(
            "внутреннее рассуждение: "
            f"${format_price_per_million(pricing.internal_reasoning)} / 1 млн"
        )
    if pricing.input_cache_read > 0:
        details.append(
            "чтение кэша: "
            f"${format_price_per_million(pricing.input_cache_read)} / 1 млн"
        )
    if pricing.input_cache_write > 0:
        details.append(
            "запись кэша: "
            f"${format_price_per_million(pricing.input_cache_write)} / 1 млн"
        )
    if model.pricing_overrides:
        details.append("указаны ценовые overrides; показаны верхние значения")
    if not details:
        return []
    return [
        ft.Text(
            "Дополнительная цена: " + "; ".join(details),
            size=12,
            color=MUTED_COLOR,
        )
    ]
