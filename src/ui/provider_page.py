"""Provider settings controls with injected, session-fenced service callbacks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import flet as ft

from auth.models import KeyLimitInfo, KeyLimitState
from i18n import localize_tree, number, tr
from providers.creation import NewChatPolicy
from providers.models import ProviderId, detect_key, provider_spec
from ui.language_selector import LanguageSelector
from ui.provider_filter import ProviderFilter
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    WARNING_COLOR,
    dropdown_style,
    input_style,
    primary_button_style,
    secondary_button_style,
    surface,
)


@dataclass(frozen=True)
class ProviderPresentation:
    """Public presentation state; saved or candidate keys never belong here."""

    provider_id: ProviderId
    has_saved_key: bool = False
    status: str = "not_configured"
    message: str = ""
    balance_amount: Decimal | None = None
    balance_status: str = "unavailable"
    checked_at: datetime | None = None
    key_limit: KeyLimitInfo = field(default_factory=KeyLimitInfo.unknown)


@dataclass(frozen=True)
class ProviderCheckResult:
    save_allowed: bool
    authorization_confirmed: bool = False
    message: str = ""


CheckCallback = Callable[[ProviderId, str], Awaitable[ProviderCheckResult]]
SaveCallback = Callable[[ProviderId, str, bool], Awaitable[bool]]
ProviderCallback = Callable[[ProviderId], Awaitable[None]]


class _SecretTextField(ft.TextField):
    def __repr__(self) -> str:
        return f"{type(self).__name__}(value=<redacted>)"


class _ProviderCard:
    def __init__(self, provider_id: ProviderId) -> None:
        self.provider_id = provider_id
        self.presentation = ProviderPresentation(provider_id)
        self.revision = 0
        self.busy = False
        self.result: ProviderCheckResult | None = None
        self.checked_value: str | None = None
        name = provider_spec(provider_id).name
        self.key_field = _SecretTextField(
            label=tr("providers.form_key", provider=name),
            hint_text=tr("providers.form_key_hint", provider=name),
            password=True,
            autocorrect=False,
            enable_suggestions=False,
            enable_ime_personalized_learning=False,
            enable_stylus_handwriting=False,
            smart_dashes_type=False,
            smart_quotes_type=False,
            expand=True,
            **input_style(),
        )
        self.reveal = ft.IconButton(
            icon=ft.Icons.VISIBILITY_OUTLINED,
            tooltip=tr("providers.reveal"),
        )
        self.detected = ft.Text("", color=MUTED_COLOR)
        self.status = ft.Text(tr("providers.status.not_configured"))
        self.saved = ft.Text(tr("providers.no_saved_key"), color=MUTED_COLOR)
        self.shared_key_notice = ft.Text(
            tr("connection.shared_key", provider=name), color=MUTED_COLOR, size=12
        )
        self.message = ft.Text("", color=WARNING_COLOR, selectable=True)
        self.balance = ft.Text("", selectable=True)
        self.balance_note = ft.Text("", size=12, color=MUTED_COLOR)
        self.checked = ft.Text("", size=12, color=MUTED_COLOR)
        self.key_limit = ft.Text("", size=12, color=MUTED_COLOR)
        self.daily_quota = ft.Text("", size=12, color=MUTED_COLOR, visible=False)
        self.check = ft.Button(
            tr("providers.check"), style=secondary_button_style(), disabled=True
        )
        self.save = ft.Button(
            tr("providers.save"), style=primary_button_style(), disabled=True
        )
        self.refresh = ft.TextButton(
            tr("providers.refresh_balance"), icon=ft.Icons.REFRESH, disabled=True
        )
        self.control = surface(
            ft.Column(
                tight=True,
                spacing=12,
                controls=[
                    ft.Text(provider_spec(provider_id).name, size=21),
                    self.saved,
                    self.shared_key_notice,
                    self.status,
                    ft.Row(controls=[self.key_field, self.reveal], spacing=4),
                    self.detected,
                    ft.Row(wrap=True, controls=[self.check, self.save]),
                    self.message,
                    ft.Divider(),
                    self.balance,
                    self.balance_note,
                    self.key_limit,
                    self.daily_quota,
                    self.checked,
                    self.refresh,
                ],
            ),
            padding=16,
        )


class ProviderPage:
    """One independently replaceable key per provider; no secret retrieval in UI."""

    def __init__(
        self,
        *,
        on_check: CheckCallback,
        on_save: SaveCallback,
        on_refresh: ProviderCallback,
        on_default: Callable[[NewChatPolicy], Awaitable[None]],
        default_provider: ProviderId | NewChatPolicy = NewChatPolicy.MANUAL,
    ) -> None:
        self._on_check = on_check
        self._on_save = on_save
        self._on_refresh = on_refresh
        self._on_default = on_default
        self._saved_creation_policy = NewChatPolicy(default_provider.value)
        self._cleared = False
        self.cards = {provider: _ProviderCard(provider) for provider in ProviderId}
        self.provider_filter = ProviderFilter(on_change=self.set_filter)
        self.default_selector = ft.Dropdown(
            label=tr("providers.default"),
            value=default_provider.value,
            options=self._creation_options(),
            **dropdown_style(),
            on_select=self._default_changed,
        )
        self.default_help = ft.Text("", size=12, color=MUTED_COLOR)
        self._sync_creation_help()
        self.notice = ft.Text("", color=ERROR_COLOR)
        for card in self.cards.values():
            self._wire_card(card)
            self._render_presentation(card)
        self.control = ft.ListView(
            expand=True,
            padding=16,
            spacing=16,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(tr("providers.title"), size=26, expand=True),
                        LanguageSelector(compact=True),
                    ]
                ),
                ft.Text(tr("providers.description"), color=MUTED_COLOR),
                self.provider_filter.control,
                self.default_selector,
                self.default_help,
                self.notice,
                *(card.control for card in self.cards.values()),
            ],
        )

    def _wire_card(self, card: _ProviderCard) -> None:
        def change(_event: ft.Event) -> None:
            if self._cleared:
                return
            card.revision += 1
            card.result = None
            card.checked_value = None
            card.message.value = ""
            self._render_detection(card)
            self._update()

        def reveal(_event: ft.Event) -> None:
            if self._cleared:
                return
            card.key_field.password = not card.key_field.password
            card.reveal.icon = (
                ft.Icons.VISIBILITY_OUTLINED
                if card.key_field.password
                else ft.Icons.VISIBILITY_OFF_OUTLINED
            )
            card.reveal.tooltip = tr(
                "providers.reveal" if card.key_field.password else "providers.conceal"
            )
            self._update()

        async def check(_event: ft.Event) -> None:
            await self.check_candidate(card.provider_id)

        async def save(_event: ft.Event) -> None:
            await self.save_candidate(card.provider_id)

        async def refresh(_event: ft.Event) -> None:
            if self._cleared or card.busy:
                return
            self._busy(card, True)
            try:
                await self._on_refresh(card.provider_id)
            except Exception:
                if not self._cleared:
                    card.message.value = tr("providers.operation_failed")
            finally:
                if not self._cleared:
                    self._busy(card, False)

        card.key_field.on_change = change
        card.reveal.on_click = reveal
        card.check.on_click = check
        card.save.on_click = save
        card.refresh.on_click = refresh

    def _candidate(self, card: _ProviderCard) -> str:
        return (card.key_field.value or "").strip()

    def _render_detection(self, card: _ProviderCard) -> None:
        candidate = self._candidate(card)
        detected = detect_key(candidate)
        matches = detected is card.provider_id
        card.detected.value = (
            tr(
                "providers.form_enter_key",
                provider=provider_spec(card.provider_id).name,
            )
            if candidate and not matches
            else ""
        )
        card.detected.color = MUTED_COLOR if matches or not candidate else ERROR_COLOR
        card.check.disabled = card.busy or not matches
        result = card.result
        checked = result is not None and card.checked_value == candidate
        card.save.disabled = (
            card.busy
            or not matches
            or not checked
            or result is None
            or not result.save_allowed
        )
        card.save.content = tr(
            "providers.save"
            if not checked or result is None or result.authorization_confirmed
            else "providers.save_unverified"
        )

    async def check_candidate(self, provider_id: ProviderId) -> None:
        card = self.cards[provider_id]
        candidate = self._candidate(card)
        if self._cleared or card.busy or detect_key(candidate) is not provider_id:
            return
        revision = card.revision
        self._busy(card, True)
        try:
            result = await self._on_check(provider_id, candidate)
            if self._cleared or revision != card.revision:
                return
            card.result = result
            card.checked_value = candidate
            card.message.value = result.message or tr(
                "providers.checked"
                if result.authorization_confirmed
                else "providers.unverified_help"
                if result.save_allowed
                else "providers.check_failed"
            )
        except Exception:
            if not self._cleared and revision == card.revision:
                card.result = None
                card.message.value = tr("providers.operation_failed")
        finally:
            if not self._cleared:
                self._busy(card, False)

    async def save_candidate(self, provider_id: ProviderId) -> None:
        card = self.cards[provider_id]
        candidate = self._candidate(card)
        result = card.result
        if (
            self._cleared
            or card.busy
            or detect_key(candidate) is not provider_id
            or result is None
            or not result.save_allowed
            or card.checked_value != candidate
        ):
            return
        revision = card.revision
        self._busy(card, True)
        try:
            saved = await self._on_save(
                provider_id, candidate, not result.authorization_confirmed
            )
            if self._cleared or revision != card.revision:
                return
            if saved:
                card.key_field.value = ""
                card.key_field.password = True
                card.reveal.icon = ft.Icons.VISIBILITY_OUTLINED
                card.reveal.tooltip = tr("providers.reveal")
                card.result = None
                card.checked_value = None
                card.message.value = tr("providers.saved")
            else:
                card.message.value = tr("providers.operation_failed")
        except Exception:
            if not self._cleared and revision == card.revision:
                card.message.value = tr("providers.operation_failed")
        finally:
            if not self._cleared:
                self._busy(card, False)

    def _busy(self, card: _ProviderCard, busy: bool) -> None:
        card.busy = busy
        card.key_field.disabled = card.reveal.disabled = busy
        card.refresh.disabled = busy or not card.presentation.has_saved_key
        self._render_detection(card)
        self._update()

    def set_provider(self, presentation: ProviderPresentation) -> None:
        if not self._cleared:
            card = self.cards[presentation.provider_id]
            card.presentation = presentation
            self._render_presentation(card)
            self._update()

    async def set_filter(self, provider_id: ProviderId | None) -> None:
        """Retain each candidate in its own card and conceal it before hiding."""
        if self._cleared:
            return
        self.conceal_keys()
        self.provider_filter.set_value(provider_id)
        for provider, card in self.cards.items():
            card.control.visible = provider_id is None or provider is provider_id
        self._update()

    def _render_presentation(self, card: _ProviderCard) -> None:
        state = card.presentation
        spec = provider_spec(card.provider_id)
        currency = spec.currency.value
        statuses = {
            "not_configured",
            "unverified",
            "connected",
            "invalid",
            "restricted",
            "network_error",
            "subscription_required",
            "insufficient_funds",
            "warning",
        }
        status = state.status if state.status in statuses else "unverified"
        card.status.value = tr(f"providers.status.{status}")
        card.saved.value = tr(
            "providers.saved_key" if state.has_saved_key else "providers.no_saved_key"
        )
        if state.message:
            card.message.value = state.message
        card.balance.value = (
            tr(
                "providers.balance",
                provider=spec.name,
                amount=number(state.balance_amount),
                currency=currency,
            )
            if state.balance_amount is not None
            else tr("providers.balance_unavailable", provider=spec.name)
        )
        balance_statuses = {
            "unavailable",
            "loading",
            "ready",
            "stale",
            "restricted",
            "network_error",
            "subscription_required",
            "insufficient_funds",
            "warning",
            "invalid",
            "disabled",
            "account_disabled",
        }
        balance_status = (
            state.balance_status
            if state.balance_status in balance_statuses
            else "unavailable"
        )
        balance_key = f"providers.balance_status.{balance_status}"
        if balance_status in {"restricted", "disabled"}:
            balance_key += f".{card.provider_id.value}"
        card.balance_note.value = tr(balance_key)
        card.checked.value = tr(
            "providers.checked_at",
            time=state.checked_at.astimezone().isoformat(timespec="minutes")
            if state.checked_at is not None
            else tr("providers.never_checked"),
        )
        card.key_limit.visible = spec.supports_key_limit
        if spec.supports_key_limit:
            limit = state.key_limit
            card.key_limit.value = (
                tr(
                    "providers.key_remaining",
                    amount=number(limit.remaining),
                    currency=currency,
                )
                if limit.remaining is not None
                else tr("providers.key_limit_not_set")
                if limit.state is KeyLimitState.NOT_SET
                else tr("providers.key_remaining_unknown")
            )
        else:
            card.key_limit.value = ""
        quota = state.key_limit.daily_request_quota
        card.daily_quota.visible = (
            card.provider_id is ProviderId.OPENROUTER and quota is not None
        )
        card.daily_quota.value = (
            tr(
                "providers.daily_free_quota",
                remaining=number(quota.remaining),
                limit=number(quota.limit),
            )
            if card.daily_quota.visible and quota is not None
            else ""
        )
        card.refresh.disabled = card.busy or not state.has_saved_key

    @staticmethod
    def _creation_options() -> list[ft.DropdownOption]:
        return [
            ft.DropdownOption(
                key=NewChatPolicy.MANUAL.value, text=str(tr("creation.manual"))
            ),
            *(
                ft.DropdownOption(key=p.value, text=provider_spec(p).name)
                for p in ProviderId
            ),
        ]

    def _sync_creation_help(self) -> None:
        policy = NewChatPolicy(
            self.default_selector.value or NewChatPolicy.MANUAL.value
        )
        provider = policy.provider_id
        self.default_help.value = (
            tr("creation.manual_help")
            if provider is None
            else tr("creation.provider_help", provider=provider_spec(provider).name)
        )

    def set_default(self, provider_id: ProviderId | NewChatPolicy) -> None:
        if not self._cleared:
            self._saved_creation_policy = NewChatPolicy(provider_id.value)
            self.default_selector.value = provider_id.value
            self._sync_creation_help()

    async def _default_changed(self, _event: ft.Event) -> None:
        if self._cleared or self.default_selector.value is None:
            return
        previous = self._saved_creation_policy
        try:
            policy = NewChatPolicy(self.default_selector.value)
            await self._on_default(policy)
            if not self._cleared:
                self._saved_creation_policy = policy
                self.notice.value = ""
                self._sync_creation_help()
                self._update()
        except Exception:
            if not self._cleared:
                self.default_selector.value = previous.value
                self._sync_creation_help()
                self.notice.value = tr("providers.operation_failed")
                self._update()

    def conceal_keys(self) -> None:
        for card in self.cards.values():
            card.key_field.password = True
            card.reveal.icon = ft.Icons.VISIBILITY_OUTLINED
            card.reveal.tooltip = tr("providers.reveal")

    def sync_language(self) -> None:
        if not self._cleared:
            localize_tree(self.control)
            self.provider_filter.sync_language()
            self.default_selector.options = self._creation_options()
            self._sync_creation_help()
            for card in self.cards.values():
                self._render_presentation(card)
                self._render_detection(card)

    def clear_private(self) -> None:
        self._cleared = True
        self.conceal_keys()
        self.provider_filter.control.disabled = True
        self.default_selector.disabled = True
        self.notice.value = ""
        for card in self.cards.values():
            card.revision += 1
            card.busy = False
            card.key_field.disabled = card.reveal.disabled = True
            card.key_field.value = ""
            card.checked_value = None
            card.result = None
            card.presentation = ProviderPresentation(card.provider_id)
            for control in (
                card.detected,
                card.status,
                card.saved,
                card.message,
                card.balance,
                card.balance_note,
                card.checked,
                card.key_limit,
                card.daily_quota,
            ):
                control.value = ""
            card.check.disabled = card.save.disabled = card.refresh.disabled = True

    def _update(self) -> None:
        try:
            self.control.update()
        except (RuntimeError, AssertionError):
            pass
