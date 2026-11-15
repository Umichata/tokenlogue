"""Secret-free controls for an explicitly confirmed chat connection change."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from decimal import Decimal

import flet as ft

from chat.accounting import ChatBudget, calculate_remaining_budget
from chat.models import CatalogModel, Chat, ChatMode
from i18n import display_model_name, fresh_text, money, number, tr
from providers.models import Currency, ProviderId, provider_spec
from ui.styles import (
    MUTED_COLOR,
    PANEL_BACKGROUND,
    WARNING_COLOR,
    detail_row,
    primary_button_style,
    secondary_button_style,
)

ProviderCallback = Callable[[ProviderId], Awaitable[None]]
CancelCallback = Callable[[], None | Awaitable[None]]
AsyncCallback = Callable[[], Awaitable[None]]


async def _cancel(callback: CancelCallback) -> None:
    result = callback()
    if inspect.isawaitable(result):
        await result


class ProviderSwitchDialog:
    def __init__(
        self,
        current: ProviderId,
        on_select: ProviderCallback,
        on_cancel: CancelCallback,
        *,
        message: str = "",
    ) -> None:
        self._closed = False
        self._busy = False
        self.message = ft.Text(
            fresh_text(message), color=WARNING_COLOR, visible=bool(message)
        )
        self.provider_buttons: dict[ProviderId, ft.Button] = {}

        def select(provider: ProviderId):
            async def invoke(_event: ft.Event) -> None:
                if self._closed or self._busy:
                    return
                self.set_busy(True)
                self._closed = True
                await on_select(provider)

            return invoke

        async def cancel(_event: ft.Event) -> None:
            if not self._closed:
                self.dispose()
                await _cancel(on_cancel)

        for provider in ProviderId:
            self.provider_buttons[provider] = ft.Button(
                content=ft.Row(
                    controls=[
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE_OUTLINE
                            if provider is current
                            else ft.Icons.CIRCLE_OUTLINED
                        ),
                        ft.Text(provider_spec(provider).name, expand=True),
                        *(
                            [ft.Text(tr("connection.current"), size=12)]
                            if provider is current
                            else []
                        ),
                    ],
                ),
                style=secondary_button_style(),
                height=52,
                on_click=select(provider),
            )
        self.cancel_button = ft.TextButton(
            tr("common.cancel"),
            style=secondary_button_style(),
            height=48,
            on_click=cancel,
        )
        self.control = ft.AlertDialog(
            modal=True,
            scrollable=True,
            bgcolor=PANEL_BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Text(tr("connection.change_provider")),
            content=ft.Column(
                tight=True,
                spacing=12,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Text(tr("connection.choose_provider")),
                    *self.provider_buttons.values(),
                    self.message,
                ],
            ),
            actions=[self.cancel_button],
            on_dismiss=cancel,
        )

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        for button in self.provider_buttons.values():
            button.disabled = busy

    def show_message(self, message: str) -> None:
        self.message.value = fresh_text(message)
        self.message.visible = bool(message)

    def dispose(self) -> None:
        self._closed = True
        self.message.value = ""
        for button in self.provider_buttons.values():
            button.disabled = True


def build_missing_provider_key_dialog(
    provider: ProviderId,
    on_configure: ProviderCallback,
    on_cancel: CancelCallback,
) -> ft.AlertDialog:
    settled = False

    async def configure(_event: ft.Event) -> None:
        nonlocal settled
        if settled:
            return
        settled = True
        await on_configure(provider)

    async def cancel(_event: ft.Event) -> None:
        nonlocal settled
        if settled:
            return
        settled = True
        await _cancel(on_cancel)

    name = provider_spec(provider).name
    return ft.AlertDialog(
        modal=True,
        scrollable=True,
        bgcolor=PANEL_BACKGROUND,
        shape=ft.RoundedRectangleBorder(radius=16),
        title=ft.Text(tr("connection.configure_key", provider=name)),
        content=ft.Text(tr("connection.missing_key", provider=name)),
        actions=[
            ft.TextButton(tr("common.cancel"), height=48, on_click=cancel),
            ft.Button(
                tr("connection.configure_key", provider=name),
                height=48,
                style=primary_button_style(),
                on_click=configure,
            ),
        ],
        on_dismiss=cancel,
    )


def build_connection_confirmation(
    chat: Chat,
    model: CatalogModel,
    mode: ChatMode,
    currency: Currency,
    cost_limit: Decimal | None,
    on_confirm: AsyncCallback,
    on_cancel: CancelCallback,
    *,
    token_limit: int | None = None,
    budget: ChatBudget | None = None,
    context_warning: str | None = None,
) -> ft.AlertDialog:
    if currency is not model.currency:
        raise ValueError("connection_currency_mismatch")
    name = provider_spec(model.provider_id).name
    controls: list[ft.Control] = [
        detail_row(tr("connection.provider"), name),
        detail_row(tr("meta.model"), display_model_name(model.id, model.name)),
        detail_row(
            tr("chat.mode"),
            tr("chat.free") if mode is ChatMode.FREE else tr("chat.paid"),
        ),
        detail_row(tr("connection.currency"), currency.value),
    ]
    if token_limit is not None:
        controls.append(detail_row(tr("budget.token_limit"), number(token_limit)))
    if mode is ChatMode.PAID:
        controls.append(
            detail_row(
                tr("connection.cost_limit"),
                money(cost_limit, currency)
                if cost_limit is not None
                else tr("connection.not_configured"),
            )
        )
        if (
            budget is not None
            and budget.chat_id == chat.id
            and budget.provider_id is model.provider_id
            and budget.currency is currency
            and budget.cost_limit == cost_limit
        ):
            remaining = calculate_remaining_budget(budget).cost
            controls.extend(
                [
                    detail_row(
                        tr("connection.cost_used"), money(budget.cost_used, currency)
                    ),
                    detail_row(
                        tr("connection.cost_remaining"),
                        money(remaining, currency) if remaining is not None else "—",
                    ),
                ]
            )
    controls.extend(
        [
            ft.Text(
                tr("connection.context_warning", provider=name)
                if context_warning is None
                else fresh_text(context_warning),
                color=WARNING_COLOR,
            ),
            ft.Text(tr("connection.no_send"), color=MUTED_COLOR),
        ]
    )

    settled = False

    async def confirm(_event: ft.Event) -> None:
        nonlocal settled
        if settled:
            return
        settled = True
        await on_confirm()

    async def cancel(_event: ft.Event) -> None:
        nonlocal settled
        if settled:
            return
        settled = True
        await _cancel(on_cancel)

    return ft.AlertDialog(
        modal=True,
        scrollable=True,
        bgcolor=PANEL_BACKGROUND,
        shape=ft.RoundedRectangleBorder(radius=16),
        title=ft.Text(tr("connection.confirm_title")),
        content=ft.Column(tight=True, spacing=12, controls=controls),
        actions=[
            ft.TextButton(
                tr("common.cancel"),
                height=48,
                style=secondary_button_style(),
                autofocus=True,
                on_click=cancel,
            ),
            ft.Button(
                tr("connection.change_provider"),
                height=48,
                style=primary_button_style(),
                on_click=confirm,
            ),
        ],
        on_dismiss=cancel,
    )
