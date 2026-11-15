"""One compact provider view filter shared by settings and analytics pages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from i18n import localize_tree, tr
from providers.models import ProviderId, provider_spec
from ui.styles import (
    BORDER_COLOR,
    ELEVATED_BACKGROUND,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    PRIMARY_COLOR,
    PRIMARY_FOREGROUND,
    TEXT_COLOR,
    secondary_button_style,
)


class ProviderFilter:
    """Select a page's view without changing any chat or saved credential."""

    def __init__(
        self,
        *,
        on_change: Callable[[ProviderId | None], Awaitable[None]],
        value: ProviderId | None = None,
    ) -> None:
        self._on_change = on_change
        style = secondary_button_style()
        style.color = {
            ft.ControlState.DISABLED: MUTED_COLOR,
            ft.ControlState.SELECTED: PRIMARY_FOREGROUND,
            ft.ControlState.DEFAULT: TEXT_COLOR,
        }
        style.bgcolor = {
            ft.ControlState.SELECTED: PRIMARY_COLOR,
            ft.ControlState.PRESSED: BORDER_COLOR,
            ft.ControlState.HOVERED: ELEVATED_BACKGROUND,
            ft.ControlState.DEFAULT: PANEL_BACKGROUND,
        }
        style.side = {
            ft.ControlState.FOCUSED: ft.BorderSide(2, TEXT_COLOR),
            ft.ControlState.DEFAULT: ft.BorderSide(1, BORDER_COLOR),
        }
        style.padding = ft.Padding.symmetric(horizontal=10, vertical=12)
        self.control = ft.SegmentedButton(
            segments=[
                ft.Segment(value="all", label=ft.Text(tr("common.provider_all"))),
                *(
                    ft.Segment(value=p.value, label=ft.Text(provider_spec(p).name))
                    for p in ProviderId
                ),
            ],
            selected=[value.value if value is not None else "all"],
            show_selected_icon=False,
            style=style,
            tooltip=tr("analytics.provider"),
            on_change=self._changed,
        )

    @property
    def value(self) -> ProviderId | None:
        selected = self.control.selected
        return ProviderId(selected[0]) if selected and selected[0] != "all" else None

    def set_value(self, value: ProviderId | None) -> None:
        self.control.selected = [value.value if value is not None else "all"]

    async def _changed(self, _event: ft.Event) -> None:
        await self._on_change(self.value)

    def sync_language(self) -> None:
        localize_tree(self.control)
