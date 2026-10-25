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
)
from chat.sending import MessageSendPreview
from i18n import display_model_name, fresh_text, money, number, tr
from ui.branding import BrandHeader, BrandLoader
from ui.styles import ERROR_COLOR, MUTED_COLOR, detail_row, primary_button_style

LimitSubmitCallback = Callable[[str, str, str | None], Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


class ChatLimitsForm:
    def __init__(
        self,
        mode: ChatMode,
        on_submit: LimitSubmitCallback,
        *,
        initial_budget: ChatBudget | None = None,
        submit_label: str | None = None,
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
            label=tr("limits.total"),
            value=str(initial_token_limit or DEFAULT_CHAT_TOKEN_LIMIT),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.max_completion_tokens = ft.TextField(
            label=tr("limits.completion"),
            value=str(initial_completion_limit or DEFAULT_MAX_COMPLETION_TOKENS),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.cost_limit: ft.TextField | None = None
        fields: list[ft.Control] = [
            self.token_limit,
            ft.Text(
                tr("limits.total_help"),
                size=12,
                color=MUTED_COLOR,
            ),
            self.max_completion_tokens,
            ft.Text(
                tr("limits.completion_help"),
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
                label=tr("limits.money"),
                value=format_decimal_usd(suggested),
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            fields.extend(
                [
                    self.cost_limit,
                    ft.Text(
                        tr("limits.money_help"),
                        size=12,
                        color=MUTED_COLOR,
                    ),
                ]
            )
        self.error = ft.Text("", color=ERROR_COLOR, visible=False)
        self.submit_button = ft.Button(
            submit_label if submit_label is not None else tr("limits.save"),
            style=primary_button_style(),
            on_click=self._handle_click,
        )
        self.progress = BrandLoader(size=26, active=False)
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
            self.show_error(tr("limits.text_error"))
            return
        if cost_limit is not None and not isinstance(cost_limit, str):
            self.show_error(tr("limits.money_text_error"))
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
        self.progress.set_active(busy)

    def show_error(self, message: str) -> None:
        self.error.value = fresh_text(message)
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
            tr("limits.create_free")
            if mode is ChatMode.FREE
            else tr("limits.create_paid")
        )
        self.form = ChatLimitsForm(mode, on_submit, submit_label=submit_label)
        controls: list[ft.Control] = [
            BrandHeader(),
            ft.Text(
                tr("limits.configure"), theme_style=ft.TextThemeStyle.HEADLINE_MEDIUM
            ),
            ft.Text(
                display_model_name(model.id, model.name), weight=ft.FontWeight.BOLD
            ),
            ft.Text(model.id, selectable=True, color=MUTED_COLOR),
        ]
        if mode is ChatMode.PAID:
            controls.append(
                ft.Container(
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.AMBER_300),
                    border_radius=12,
                    padding=12,
                    content=ft.Text(
                        tr("limits.paid_warning"),
                        color=ft.Colors.AMBER_300,
                    ),
                )
            )
        controls.extend(
            [
                self.form.control,
                ft.TextButton(tr("common.back"), on_click=handle_cancel),
            ]
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
            title=ft.Text(tr("limits.dialog")),
            content=self.form.control,
            actions=[ft.TextButton(tr("common.cancel"), on_click=handle_cancel)],
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
        title=ft.Text(tr("paid.confirm_title")),
        scrollable=True,
        content=ft.Column(
            tight=True,
            controls=[
                ft.Text(
                    preview.model_name or tr("paid.model"), weight=ft.FontWeight.BOLD
                ),
                ft.Text(preview.model_id or "", selectable=True, color=MUTED_COLOR),
                detail_row(
                    tr("paid.prompt_estimate"),
                    _number_or_unknown(preview.estimated_prompt_tokens),
                ),
                detail_row(
                    tr("paid.completion_maximum"),
                    _number_or_unknown(preview.max_completion_tokens),
                ),
                detail_row(
                    tr("paid.reserve_maximum"),
                    _money_or_unknown(preview.reserved_cost_usd),
                ),
                detail_row(
                    tr("paid.remaining"),
                    _money_or_unknown(preview.remaining_cost_after_reservation),
                ),
                ft.Text(
                    tr("paid.estimate_help"),
                    size=12,
                    color=MUTED_COLOR,
                ),
            ],
        ),
        actions=[
            ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
            ft.Button(
                tr("paid.send"),
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
        title=ft.Text(tr("paid.price_changed")),
        scrollable=True,
        content=ft.Column(
            tight=True,
            controls=[
                ft.Text(tr("paid.old_prices")),
                *_price_component_rows(change.confirmed),
                ft.Text(tr("paid.current_prices")),
                *_price_component_rows(change.current),
                ft.Text(
                    tr("paid.confirm_required"),
                    color=ft.Colors.AMBER_300,
                ),
            ],
        ),
        actions=[
            ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
            ft.Button(
                tr("paid.confirm_prices"),
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
        title=ft.Text(tr("paid.increase_title")),
        scrollable=True,
        content=ft.Column(
            tight=True,
            controls=[
                detail_row(tr("paid.old_limit"), money(old_value)),
                detail_row(tr("paid.new_limit"), money(new_value)),
            ],
        ),
        actions=[
            ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
            ft.Button(tr("paid.confirm_increase"), on_click=handle_confirm),
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
        title=ft.Text(tr("reserve.release_title")),
        content=ft.Text(
            tr(
                "reserve.release_body",
                tokens=number(turn.reserved_tokens),
                amount=money(turn.reserved_cost_usd),
            )
        ),
        actions=[
            ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
            ft.Button(tr("reserve.release"), on_click=handle_confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _price_component_rows(pricing: PriceComponents) -> list[ft.Control]:
    return [
        detail_row(tr("price.prompt_million"), money_million(pricing.prompt)),
        detail_row(tr("price.completion_million"), money_million(pricing.completion)),
        detail_row(tr("price.request"), money(pricing.request)),
        detail_row(
            tr("price.reasoning_million"),
            money_million(pricing.internal_reasoning),
        ),
        detail_row(
            tr("price.cache_read_million"),
            money_million(pricing.input_cache_read),
        ),
        detail_row(
            tr("price.cache_write_million"),
            money_million(pricing.input_cache_write),
        ),
    ]


def _number_or_unknown(value: int | None) -> str:
    return "—" if value is None else number(value)


def _money_or_unknown(value: Decimal | None) -> str:
    return "—" if value is None else money(value)


def money_million(value: Decimal) -> str:
    return money(value * Decimal(1_000_000))
