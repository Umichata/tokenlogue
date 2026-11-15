"""Four application pages around the retained, controller-owned chat workspace."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum

import flet as ft

from i18n import localize_tree, tr
from ui.styles import PANEL_BACKGROUND, PRIMARY_COLOR


class WorkspacePage(StrEnum):
    HOME = "home"
    PROVIDERS = "providers"
    TOKENS = "tokens"
    SPENDING = "spending"


NavigateCallback = Callable[[WorkspacePage], Awaitable[bool | None]]


class WorkspaceShell:
    """Own navigation controls, while the session owner owns access and effects."""

    def __init__(
        self,
        page: ft.Page,
        home: ft.Control,
        providers: ft.Control,
        tokens: ft.Control,
        spending: ft.Control,
        *,
        on_navigate: NavigateCallback,
    ) -> None:
        self._page = page
        self._on_navigate = on_navigate
        self._views = dict(zip(WorkspacePage, (home, providers, tokens, spending)))
        self._selected = WorkspacePage.HOME
        self._cleared = False
        self._changing = False
        self._android = getattr(page, "platform", None) is ft.PagePlatform.ANDROID
        icons = (
            ft.Icons.HOME_OUTLINED,
            ft.Icons.KEY_OUTLINED,
            ft.Icons.BAR_CHART,
            ft.Icons.PAYMENTS_OUTLINED,
        )
        self.rail = ft.NavigationRail(
            selected_index=0,
            min_width=88,
            bgcolor=PANEL_BACKGROUND,
            indicator_color=PRIMARY_COLOR,
            label_type=ft.NavigationRailLabelType.ALL,
            destinations=[
                ft.NavigationRailDestination(icon=icon, label=tr(f"nav.{item}"))
                for item, icon in zip(WorkspacePage, icons)
            ],
            on_change=self._rail_changed,
        )
        self.navigation = ft.NavigationBar(
            selected_index=0,
            bgcolor=PANEL_BACKGROUND,
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
            destinations=[
                ft.NavigationBarDestination(icon=icon, label=tr(f"nav.{item}"))
                for item, icon in zip(WorkspacePage, icons)
            ],
            on_change=self._bar_changed,
        )
        self._content = ft.Container(expand=True, content=home)
        self._rail_slot = ft.Container(content=self.rail)
        self._bottom_slot = ft.Container(content=self.navigation)
        self.control = ft.SafeArea(
            expand=True,
            maintain_bottom_view_padding=True,
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.Row(
                        expand=True,
                        spacing=0,
                        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=[self._rail_slot, self._content],
                    ),
                    self._bottom_slot,
                ],
            ),
        )
        self.resize(page.width or 420)

    @property
    def selected_page(self) -> WorkspacePage:
        return self._selected

    def set_home(self, control: ft.Control) -> None:
        """Background chat refreshes cannot navigate away from another page."""
        if self._cleared:
            return
        self._views[WorkspacePage.HOME] = control
        if self._selected is WorkspacePage.HOME:
            self._set_content(control)

    def _set_content(self, control: ft.Control) -> None:
        if self._content.content is not control:
            # Flet observables compare dataclass values; structurally equal
            # controls can still belong to different pages and callbacks.
            self._content.content = None
            self._content.content = control

    async def select(self, page_id: WorkspacePage | str) -> bool:
        target = WorkspacePage(page_id)
        if self._cleared or self._changing:
            return False
        if target is self._selected:
            return True
        self._changing = True
        try:
            # The owner flushes drafts and dismisses unsubmitted confirmations.
            allowed = await self._on_navigate(target)
            if self._cleared or allowed is False:
                self._sync_selection()
                if not self._cleared:
                    self._page.update()
                return False
            self._selected = target
            self._set_content(self._views[target])
            self._sync_selection()
            self._page.update()
            return True
        finally:
            self._changing = False

    def _sync_selection(self) -> None:
        index = list(WorkspacePage).index(self._selected)
        self.rail.selected_index = self.navigation.selected_index = index

    async def _rail_changed(self, _event: ft.Event) -> None:
        await self.select(list(WorkspacePage)[self.rail.selected_index or 0])

    async def _bar_changed(self, _event: ft.Event) -> None:
        await self.select(list(WorkspacePage)[self.navigation.selected_index])

    def resize(self, width: float) -> None:
        wide = width >= 1000 and not self._android
        self._rail_slot.width = 88 if wide else 0
        self.rail.visible = wide
        self._bottom_slot.height = 0 if wide else None
        self.navigation.visible = not wide

    def sync_language(self) -> None:
        localize_tree(self.control)

    def clear_private(self) -> None:
        """Revoke retained references before the owner's next asynchronous wait."""
        self._cleared = True
        self._views.clear()
        self._content.content = None
        self._selected = WorkspacePage.HOME
        self._sync_selection()
