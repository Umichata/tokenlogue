"""Small read-only presentations of ledger metrics and local draft estimates."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext
from typing import cast

import flet as ft

from auth.models import KeyLimitState
from chat.account_balance import AccountBalanceState
from chat.estimates import DraftEstimate, EstimateState
from chat.metrics import ChatMetricsSnapshot, LastRequestState
from chat.models import ChatMode
from i18n import money, number, tr
from providers.models import Currency
from ui.styles import (
    BORDER_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    WARNING_COLOR,
    secondary_button_style,
)

_MINIMUM_DISPLAY_AMOUNT = Decimal("0.0001")


def display_usd(value: Decimal, *, upper_bound: bool = False) -> str:
    return display_money(value, Currency.USD, upper_bound=upper_bound)


def display_money(
    value: Decimal,
    currency: Currency | str,
    *,
    upper_bound: bool = False,
) -> str:
    """Round display only while preserving the sign of every nonzero amount."""
    if -_MINIMUM_DISPLAY_AMOUNT < value < Decimal(0):
        return money(value, currency)
    if Decimal(0) < value < _MINIMUM_DISPLAY_AMOUNT:
        return tr("metrics.less_than", amount=money(_MINIMUM_DISPLAY_AMOUNT, currency))
    with localcontext() as context:
        context.prec = max(context.prec, value.adjusted() + 8)
        rounded = value.quantize(
            _MINIMUM_DISPLAY_AMOUNT,
            rounding=ROUND_CEILING if upper_bound else ROUND_HALF_UP,
        )
    return money(rounded, currency)


def explanatory_tooltip(message: str) -> ft.Tooltip:
    """Flet 0.86.5 supports pointer hover and long press on this whole control."""
    return ft.Tooltip(
        message=message,
        # Flet 0.86.5 annotates this string-constant class as an instance type.
        trigger_mode=cast(ft.TooltipTriggerMode, ft.TooltipTriggerMode.LONG_PRESS),
        wait_duration=400,
        show_duration=6000,
        size_constraints=ft.BoxConstraints(max_width=340),
    )


class ChatMetricsStrip:
    """Stable wrapping controls above the active history, with no data access."""

    def __init__(
        self,
        checkbox: ft.Checkbox | None = None,
        help_button: ft.IconButton | None = None,
    ) -> None:
        self._snapshot: ChatMetricsSnapshot | None = None
        self._compact = False
        self._checkbox = checkbox
        self.values = ft.Text(
            tr("metrics.loading"), size=12, color=MUTED_COLOR, selectable=True
        )
        # Text selection consumes the touch long press needed by the tooltip.
        self.metadata = ft.Text(
            size=12, color=MUTED_COLOR, selectable=False, visible=False
        )
        self.account = ft.Text(
            tr("metrics.account_unavailable"), size=12, color=MUTED_COLOR
        )
        self.pending = ft.Text(
            tr("metrics.preparing"), size=12, color=WARNING_COLOR, visible=False
        )
        self.checkbox_row = ft.Row(
            tight=True,
            spacing=0,
            visible=checkbox is not None,
            controls=[
                *([checkbox] if checkbox is not None else []),
                *([help_button] if help_button is not None else []),
            ],
        )
        self.row = ft.Row(
            wrap=True,
            spacing=14,
            run_spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.checkbox_row,
                self.values,
                self.metadata,
                self.account,
                self.pending,
            ],
        )
        self.control = ft.Container(
            # Fill the chat column horizontally without taking its vertical flex.
            width=float("inf"),
            bgcolor=PANEL_BACKGROUND,
            border=ft.Border(bottom=ft.BorderSide(1, BORDER_COLOR)),
            padding=ft.Padding.symmetric(horizontal=12, vertical=4),
            content=self.row,
        )
        self.compact_header = ft.Row(spacing=8, visible=checkbox is not None)
        self.compact_values = ft.Row(wrap=True, spacing=12, run_spacing=2)
        self.compact_column = ft.Column(
            tight=True, spacing=2, controls=[self.compact_header, self.compact_values]
        )

    def resize(self, width: float) -> None:
        """Reparent this small strip while interactive controls keep identity."""
        compact = width < 640
        if compact == self._compact:
            return
        self._compact = compact
        self.row.controls = []
        self.compact_header.controls = []
        self.compact_values.controls = []
        if self._checkbox is not None and isinstance(self._checkbox.label, ft.Text):
            self._checkbox.label.width = 110 if compact else 185
        self.metadata.expand = True if compact else None
        if compact:
            self.compact_header.controls = [self.checkbox_row, self.metadata]
            self.compact_header.visible = (
                self._checkbox is not None or self.metadata.visible
            )
            self.compact_values.controls = [self.values, self.account, self.pending]
            self.control.content = self.compact_column
        else:
            self.row.controls = [
                self.checkbox_row,
                self.values,
                self.metadata,
                self.account,
                self.pending,
            ]
            self.control.content = self.row
        try:
            self.control.update()
        except (RuntimeError, AssertionError):
            pass

    def set_metrics(self, snapshot: ChatMetricsSnapshot) -> None:
        self._snapshot = snapshot
        self.sync_language()

    def clear(self) -> None:
        self._snapshot = None
        self.values.value = ""
        self.values.tooltip = None
        self.metadata.value = ""
        self.metadata.tooltip = None
        self.metadata.visible = False
        self.account.value = ""
        self.account.tooltip = None
        self.pending.visible = False

    def sync_language(self) -> None:
        snapshot = self._snapshot
        self.pending.value = tr("metrics.preparing")
        if snapshot is None:
            return
        account = snapshot.account_balance
        amount = (
            display_money(account.balance_amount, account.currency)
            if account.balance_amount is not None
            and account.provider_id == snapshot.provider_id
            and account.currency == snapshot.currency
            else None
        )
        if account.state is AccountBalanceState.LOADING:
            self.account.value = (
                tr("metrics.account_updating", amount=amount)
                if amount is not None
                else tr("metrics.account_loading")
            )
        elif amount is None:
            self.account.value = tr("metrics.account_unavailable")
        else:
            self.account.value = tr(
                "metrics.account_stale"
                if account.state is AccountBalanceState.STALE
                else "metrics.account_current",
                amount=amount,
            )
        account_help = tr("metrics.account_help")
        if account.fetched_at is not None:
            account_help = tr(
                "metrics.account_time",
                description=account_help,
                time=account.fetched_at.isoformat(timespec="seconds"),
            )
        self.account.tooltip = explanatory_tooltip(account_help)
        last = snapshot.last_request
        if last.state is LastRequestState.NONE:
            previous = tr("metrics.no_requests")
        elif last.state is LastRequestState.PENDING:
            previous = tr("metrics.in_progress")
        elif last.state is LastRequestState.UNKNOWN:
            previous = tr(
                "metrics.unknown"
                if not last.chronology_known
                else "metrics.reconciling"
            )
            if any(
                value is not None
                for value in (
                    last.prompt_tokens,
                    last.completion_tokens,
                    last.total_tokens,
                )
            ):
                previous = tr(
                    "workspace.last_tokens_unknown_cost",
                    input=number(last.prompt_tokens)
                    if last.prompt_tokens is not None
                    else tr("metrics.unknown"),
                    output=number(last.completion_tokens)
                    if last.completion_tokens is not None
                    else tr("metrics.unknown"),
                    total=number(last.total_tokens)
                    if last.total_tokens is not None
                    else tr("metrics.unknown"),
                    status=previous,
                )
        elif snapshot.mode is ChatMode.PAID:
            previous = (
                display_money(last.cost, last.currency)
                if last.cost is not None
                else tr(
                    "workspace.last_tokens_unknown_cost",
                    input=number(last.prompt_tokens)
                    if last.prompt_tokens is not None
                    else tr("metrics.unknown"),
                    output=number(last.completion_tokens)
                    if last.completion_tokens is not None
                    else tr("metrics.unknown"),
                    total=number(last.total_tokens)
                    if last.total_tokens is not None
                    else tr("metrics.unknown"),
                    status=tr("metrics.unknown"),
                )
                if any(
                    value is not None
                    for value in (
                        last.prompt_tokens,
                        last.completion_tokens,
                        last.total_tokens,
                    )
                )
                else tr("metrics.unknown")
            )
        else:
            previous = (
                tr("metrics.tokens", count=number(last.total_tokens))
                if last.total_tokens is not None
                else tr("metrics.unknown")
            )
        if snapshot.mode is ChatMode.PAID:
            available = (
                display_money(snapshot.remaining.cost, snapshot.currency)
                if snapshot.remaining.cost is not None
                else tr("metrics.unknown")
            )
            self.values.value = tr(
                "metrics.paid_summary", amount=available, last=previous
            )
            self.values.tooltip = explanatory_tooltip(tr("metrics.paid_help"))
            key_limit = snapshot.key_limit
            if (
                key_limit.state
                in {
                    KeyLimitState.AVAILABLE,
                    KeyLimitState.EXHAUSTED,
                }
                and key_limit.remaining is not None
            ):
                amount = (
                    tr("metrics.key_below_zero", amount=money(0, snapshot.currency))
                    if -_MINIMUM_DISPLAY_AMOUNT < key_limit.remaining < 0
                    else display_money(key_limit.remaining, snapshot.currency)
                )
                metadata = tr(
                    "metrics.key_remaining"
                    if key_limit.state is KeyLimitState.AVAILABLE
                    else "metrics.key_exhausted",
                    amount=amount,
                )
                explanation = tr("metrics.key_help")
            elif key_limit.state is KeyLimitState.NOT_SET:
                metadata = tr("metrics.key_not_set")
                explanation = tr("metrics.key_not_set_help")
            else:
                metadata = tr("metrics.key_unavailable")
                explanation = tr("metrics.key_unavailable_help")
            self.metadata.value = metadata
            self.metadata.visible = True
            help_text = tr(
                "metrics.key_details", value=metadata, description=explanation
            )
            if snapshot.metadata_updated_at is not None:
                help_text = tr(
                    "metrics.metadata_time",
                    description=help_text,
                    time=snapshot.metadata_updated_at.isoformat(timespec="seconds"),
                )
            self.metadata.tooltip = explanatory_tooltip(help_text)
            self.compact_header.visible = True
        else:
            remaining = (
                number(snapshot.remaining.tokens)
                if snapshot.remaining.tokens is not None
                else tr("metrics.unknown")
            )
            self.values.value = tr(
                "metrics.free_summary", count=remaining, last=previous
            )
            self.values.tooltip = explanatory_tooltip(tr("metrics.free_help"))
            self.metadata.visible = False
            self.metadata.value = ""
            self.metadata.tooltip = None
            self.compact_header.visible = self._checkbox is not None
        self.pending.visible = (
            snapshot.pending and last.state is not LastRequestState.PENDING
        )


class PaidConfirmationHelp:
    """Explicit keyboard/touch help, separate from toggling the paid policy."""

    def __init__(self, page: ft.Page) -> None:
        self._page = page
        self._disposed = False
        self.dialog: ft.AlertDialog | None = None
        help_style = secondary_button_style()
        help_style.padding = 8
        self.button = ft.IconButton(
            icon=ft.Icons.HELP_OUTLINE,
            icon_size=18,
            width=44,
            height=44,
            tooltip=tr("metrics.confirmation_help_title"),
            style=help_style,
            on_click=self.open,
        )

    async def open(self, _event: ft.Event) -> None:
        if self._disposed or self.dialog is not None:
            return
        dialog = ft.AlertDialog(
            modal=False,
            scrollable=True,
            bgcolor=PANEL_BACKGROUND,
            shape=ft.RoundedRectangleBorder(radius=16),
            title=ft.Text(tr("metrics.confirmation_help_title")),
            content=ft.Text(tr("metrics.without_confirmation_help")),
            actions=[
                ft.TextButton(
                    tr("metrics.close_help"),
                    height=48,
                    style=secondary_button_style(),
                    autofocus=True,
                    on_click=self.dismiss,
                )
            ],
            on_dismiss=self._native_dismissed,
        )
        self.dialog = dialog

        async def close_current(event: ft.Event) -> None:
            if self.dialog is dialog:
                await self.dismiss(event)

        close_button = dialog.actions[0]
        if isinstance(close_button, ft.TextButton):
            close_button.on_click = close_current
        self._page.show_dialog(dialog)

    def close(self) -> None:
        dialog, self.dialog = self.dialog, None
        if dialog is not None:
            dialog.open = False
            try:
                dialog.update()
            except (RuntimeError, AssertionError):
                pass

    async def dismiss(self, _event: ft.Event) -> None:
        self.close()
        if not self._disposed:
            try:
                await self.button.focus()
            except (RuntimeError, AssertionError):
                pass

    async def _native_dismissed(self, event: ft.Event) -> None:
        if event.control is self.dialog:
            await self.dismiss(event)

    def dispose(self) -> None:
        self._disposed = True
        self.close()

    def refresh_language(self) -> None:
        self.button.tooltip = tr("metrics.confirmation_help_title")
        if self.dialog is not None:
            title, content = self.dialog.title, self.dialog.content
            if isinstance(title, ft.Text):
                title.value = tr("metrics.confirmation_help_title")
            if isinstance(content, ft.Text):
                content.value = tr("metrics.without_confirmation_help")
            close_button = self.dialog.actions[0]
            if isinstance(close_button, ft.TextButton):
                close_button.content = tr("metrics.close_help")


class DraftEstimateLine:
    """A persistent small line inside compose, above the Android keyboard."""

    def __init__(self) -> None:
        self._estimate: DraftEstimate | None = None
        self.text = ft.Text(
            tr("estimate.empty"), size=12, color=MUTED_COLOR, selectable=True
        )
        self.control = ft.Container(content=self.text)
        self.text.tooltip = explanatory_tooltip(tr("estimate.help"))

    def set_estimate(self, estimate: DraftEstimate | None) -> None:
        self._estimate = estimate
        self.sync_language()

    def sync_language(self) -> None:
        estimate = self._estimate
        self.text.color = MUTED_COLOR
        self.text.tooltip = explanatory_tooltip(tr("estimate.help"))
        if estimate is None:
            self.text.value = tr("estimate.calculating")
            return
        if estimate.state is EstimateState.EMPTY:
            self.text.value = tr("estimate.empty")
            return
        values: list[str] = []
        if estimate.prompt_tokens is not None:
            values.append(tr("estimate.input", count=number(estimate.prompt_tokens)))
        if estimate.max_completion_tokens is not None:
            values.append(
                tr("estimate.reply", count=number(estimate.max_completion_tokens))
            )
        if estimate.cost_upper is not None:
            values.append(
                tr(
                    "estimate.cost",
                    amount=display_money(
                        estimate.cost_upper, estimate.currency, upper_bound=True
                    ),
                )
            )
        elif estimate.state is not EstimateState.OVER_LIMIT:
            values.append(tr("estimate.cost_unknown"))
        if estimate.state is EstimateState.OVER_LIMIT:
            values.append(tr("estimate.over_limit"))
            self.text.color = WARNING_COLOR
        if not values:
            values.append(tr("estimate.unavailable"))
        self.text.value = tr("estimate.parts", parts=" · ".join(values))
        if estimate.free_router:
            self.text.tooltip = explanatory_tooltip(tr("estimate.router_help"))

    def clear(self) -> None:
        self._estimate = None
        self.text.value = ""
        self.text.tooltip = None
