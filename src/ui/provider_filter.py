"""One provider view filter shared by settings and analytics pages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from i18n import tr
from providers.models import ProviderId, provider_spec
from ui.styles import dropdown_style


class ProviderFilter:
    """Select a page's view without changing any chat or saved credential."""

    def __init__(
        self,
        *,
        on_change: Callable[[ProviderId | None], Awaitable[None]],
        value: ProviderId | None = None,
    ) -> None:
        self._on_change = on_change
        self.control = ft.Dropdown(
            label=tr("analytics.provider"),
            value=value.value if value is not None else "all",
            options=self._options(),
            on_select=self._changed,
            col={"xs": 12, "md": 4},
            **dropdown_style(),
        )

    @staticmethod
    def _options() -> list[ft.DropdownOption]:
        return [
            ft.DropdownOption(key="all", text=str(tr("common.provider_all"))),
            *(
                ft.DropdownOption(key=p.value, text=provider_spec(p).name)
                for p in ProviderId
            ),
        ]

    @property
    def value(self) -> ProviderId | None:
        selected = self.control.value
        return ProviderId(selected) if selected and selected != "all" else None

    def set_value(self, value: ProviderId | None) -> None:
        self.control.value = value.value if value is not None else "all"

    async def _changed(self, _event: ft.Event) -> None:
        await self._on_change(self.value)

    def sync_language(self) -> None:
        self.control.label = tr("analytics.provider")
        # Mounted DropdownOption objects are immutable in this Flet version.
        # Rebuild labels without touching the selected key or firing callbacks.
        self.control.options = self._options()
