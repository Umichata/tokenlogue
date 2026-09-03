"""Настройка локальных бюджетов и подтверждения расходов чата."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import flet as ft

from chat.accounting import (
    DEFAULT_CHAT_TOKEN_LIMIT,
    DEFAULT_MAX_COMPLETION_TOKENS,
    SUGGESTED_PAID_COST_LIMIT_USD,
    ChatBudget,
    ModelPriceChange,
    TurnRecord,
    format_decimal_usd,
)
from chat.models import (
    CatalogModel,
    Chat,
    ChatMode,
    PriceComponents,
    format_price_per_million,
)
from chat.sending import MessageSendPreview
from ui.styles import ERROR_COLOR, MUTED_COLOR, primary_button_style

LimitSubmitCallback = Callable[[str, str, str | None], Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


class ChatLimitsForm:
    def __init__(
        self,
        mode: ChatMode,
        on_submit: LimitSubmitCallback,
        *,
        initial_budget: ChatBudget | None = None,
        submit_label: str = "Сохранить лимиты",
    ) -> None:
        self._mode = mode
        self._on_submit = on_submit
        initial_token_limit = (
            initial_budget.token_limit if initial_budget is not None else None
        )
        initial_completion_limit = (
            initial_budget.max_completion_tokens if initial_budget is not None else None
        )
        self.token_limit = ft.TextField(
            label="Общий лимит токенов чата",
            value=str(initial_token_limit or DEFAULT_CHAT_TOKEN_LIMIT),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.max_completion_tokens = ft.TextField(
            label="Максимум токенов одного ответа",
            value=str(initial_completion_limit or DEFAULT_MAX_COMPLETION_TOKENS),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.cost_limit: ft.TextField | None = None
        fields: list[ft.Control] = [
            self.token_limit,
            ft.Text(
                "Общий лимит учитывает prompt- и completion-токены всех запросов "
                "этого чата.",
                size=12,
                color=MUTED_COLOR,
            ),
            self.max_completion_tokens,
            ft.Text(
                "Максимум ответа применяется отдельно к одному ответу. До завершения "
                "запроса токены учитываются как защитный резерв.",
                size=12,
                color=MUTED_COLOR,
            ),
        ]
        if mode is ChatMode.PAID:
            suggested = (
                initial_budget.cost_limit_usd
                if initial_budget is not None
                and initial_budget.cost_limit_usd is not None
                else SUGGESTED_PAID_COST_LIMIT_USD
            )
            self.cost_limit = ft.TextField(
                label="Денежный лимит чата, USD",
                value=format_decimal_usd(suggested),
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            fields.extend(
                [
                    self.cost_limit,
                    ft.Text(
                        "Предложенное значение нужно подтвердить самостоятельно. "
                        "Это локальный предохранитель, а не гарантия баланса "
                        "OpenRouter. Денежный резерв учитывается до результата запроса.",
                        size=12,
                        color=MUTED_COLOR,
                    ),
                ]
            )
        self.error = ft.Text("", color=ERROR_COLOR, visible=False)
        self.submit_button = ft.Button(
            submit_label,
            style=primary_button_style(),
            on_click=self._handle_click,
        )
        self.progress = ft.ProgressRing(
            width=18,
            height=18,
            stroke_width=2,
            visible=False,
        )
        self.control = ft.Column(
            tight=True,
            spacing=12,
            controls=[
                *fields,
                self.error,
                ft.Row(controls=[self.progress, self.submit_button]),
            ],
        )

    async def _handle_click(self, _event: ft.Event[ft.Button]) -> None:
        await self._submit_values()

    async def _submit_values(self) -> None:
        if self.submit_button.disabled:
            return
        token_limit = self.token_limit.value
        max_completion_tokens = self.max_completion_tokens.value
        cost_limit = self.cost_limit.value if self.cost_limit is not None else None
        if not isinstance(token_limit, str) or not isinstance(
            max_completion_tokens,
            str,
        ):
            self.show_error("Лимиты должны быть введены текстом")
            return
        if cost_limit is not None and not isinstance(cost_limit, str):
            self.show_error("Денежный лимит должен быть введён текстом")
            return
        await self._on_submit(
            token_limit,
            max_completion_tokens,
            cost_limit,
        )

    def set_busy(self, busy: bool) -> None:
        self.token_limit.disabled = busy
        self.max_completion_tokens.disabled = busy
        if self.cost_limit is not None:
            self.cost_limit.disabled = busy
        self.submit_button.disabled = busy
        self.progress.visible = busy

    def show_error(self, message: str) -> None:
        self.error.value = message
        self.error.visible = bool(message)


class NewChatLimitsView:
    def __init__(
        self,
        mode: ChatMode,
        model: CatalogModel,
        on_submit: LimitSubmitCallback,
        on_cancel: AsyncCallback,
    ) -> None:
        async def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
            await on_cancel()

        submit_label = (
            "Создать бесплатный чат" if mode is ChatMode.FREE else "Создать платный чат"
        )
        self.form = ChatLimitsForm(mode, on_submit, submit_label=submit_label)
        controls: list[ft.Control] = [
            ft.Text("Настройка лимитов", theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM),
            ft.Text(model.name, weight=ft.FontWeight.BOLD),
            ft.Text(model.id, selectable=True, color=MUTED_COLOR),
        ]
        if mode is ChatMode.PAID:
            controls.append(
                ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.AMBER_300),
                    border_radius=12,
                    padding=12,
                    content=ft.Text(
                        "Запросы к этой модели могут расходовать баланс OpenRouter.",
                        color=ft.Colors.AMBER_300,
                    ),
                )
            )
        controls.extend(
            [self.form.control, ft.TextButton("Назад", on_click=handle_cancel)]
        )
        self.control = ft.SafeArea(
            expand=True,
            maintain_bottom_view_padding=True,
            content=ft.ListView(expand=True, spacing=16, padding=20, controls=controls),
        )


class ChatLimitsDialog:
    def __init__(
        self,
        chat: Chat,
        budget: ChatBudget,
        on_submit: LimitSubmitCallback,
        on_cancel: Callable[[], None],
    ) -> None:
        def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
            on_cancel()

        self.form = ChatLimitsForm(
            chat.mode,
            on_submit,
            initial_budget=budget,
        )
        self.control = ft.AlertDialog(
            modal=True,
            scrollable=True,
            title=ft.Text("Настроить лимиты чата"),
            content=self.form.control,
            actions=[ft.TextButton("Отмена", on_click=handle_cancel)],
            actions_alignment=ft.MainAxisAlignment.END,
        )


def build_paid_request_dialog(
    preview: MessageSendPreview,
    on_confirm: AsyncCallback,
    on_cancel: Callable[[], None],
) -> ft.AlertDialog:
    async def handle_confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm()

    def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Подтвердить платный запрос?"),
        content=ft.Column(
            tight=True,
            controls=[
                ft.Text(
                    preview.model_name or "Платная модель", weight=ft.FontWeight.BOLD
                ),
                ft.Text(preview.model_id or "", selectable=True, color=MUTED_COLOR),
                ft.Text(
                    f"Оценка prompt-токенов: {preview.estimated_prompt_tokens or 0}"
                ),
                ft.Text(
                    f"Максимум completion-токенов: {preview.max_completion_tokens or 0}"
                ),
                ft.Text(
                    "Максимальный денежный резерв: $"
                    f"{format_decimal_usd(preview.reserved_cost_usd or Decimal('0'))}"
                ),
                ft.Text(
                    "Остаток локального бюджета после резерва: $"
                    f"{format_decimal_usd(preview.remaining_cost_after_reservation or Decimal('0'))}"
                ),
                ft.Text(
                    "Это защитная верхняя оценка, а не точная будущая стоимость.",
                    size=12,
                    color=MUTED_COLOR,
                ),
            ],
        ),
        actions=[
            ft.TextButton("Отмена", on_click=handle_cancel),
            ft.Button(
                "Отправить платный запрос",
                icon=ft.Icons.PAYMENTS,
                style=primary_button_style(),
                on_click=handle_confirm,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_price_reconfirmation_dialog(
    change: ModelPriceChange,
    on_confirm: AsyncCallback,
    on_cancel: Callable[[], None],
) -> ft.AlertDialog:
    async def handle_confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm()

    def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Цена модели изменилась"),
        content=ft.Column(
            tight=True,
            controls=[
                ft.Text("Ранее подтверждённые верхние цены:"),
                ft.Text(_format_price_components(change.confirmed), selectable=True),
                ft.Text("Текущие верхние цены:"),
                ft.Text(_format_price_components(change.current), selectable=True),
                ft.Text(
                    "Запрос не будет отправлен, пока новые цены не подтверждены.",
                    color=ft.Colors.AMBER_300,
                ),
            ],
        ),
        actions=[
            ft.TextButton("Отмена", on_click=handle_cancel),
            ft.Button(
                "Подтвердить новые цены",
                style=primary_button_style(),
                on_click=handle_confirm,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_cost_increase_dialog(
    old_value: Decimal,
    new_value: Decimal,
    on_confirm: AsyncCallback,
    on_cancel: Callable[[], None],
) -> ft.AlertDialog:
    async def handle_confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm()

    def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Увеличить денежный лимит?"),
        content=ft.Text(
            f"Текущий лимит: ${format_decimal_usd(old_value)}. "
            f"Новый лимит: ${format_decimal_usd(new_value)}."
        ),
        actions=[
            ft.TextButton("Отмена", on_click=handle_cancel),
            ft.Button("Подтвердить увеличение", on_click=handle_confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def build_release_unknown_dialog(
    turn: TurnRecord,
    on_confirm: AsyncCallback,
    on_cancel: Callable[[], None],
) -> ft.AlertDialog:
    async def handle_confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm()

    def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text("Освободить неизвестный резерв?"),
        content=ft.Text(
            "Запрос мог быть обработан и тарифицирован OpenRouter. Освобождаются "
            f"только локальные резервы: {turn.reserved_tokens} токенов и "
            f"${format_decimal_usd(turn.reserved_cost_usd)}."
        ),
        actions=[
            ft.TextButton("Отмена", on_click=handle_cancel),
            ft.Button("Освободить резерв", on_click=handle_confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _format_price_components(pricing: PriceComponents) -> str:
    return (
        f"prompt: ${format_price_per_million(pricing.prompt)} / 1 млн; "
        f"completion: ${format_price_per_million(pricing.completion)} / 1 млн; "
        f"request: ${format_decimal_usd(pricing.request)}; "
        "internal reasoning: "
        f"${format_price_per_million(pricing.internal_reasoning)} / 1 млн; "
        f"cache read: ${format_price_per_million(pricing.input_cache_read)} / 1 млн; "
        f"cache write: ${format_price_per_million(pricing.input_cache_write)} / 1 млн"
    )
