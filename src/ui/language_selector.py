"""Компактный переключатель языка без повторного входа или запросов."""

from __future__ import annotations

import flet as ft

from i18n import get_language, localize_tree, set_language, tr
from ui.styles import (
    BORDER_COLOR,
    CONTROL_RADIUS,
    MUTED_COLOR,
    PRIMARY_COLOR,
    TEXT_COLOR,
)


class LanguageSelector(ft.Dropdown):
    def __init__(self, *, compact: bool = False) -> None:
        super().__init__(
            label=tr("language.label"),
            value=get_language(),
            options=[
                ft.DropdownOption(key="ru", text="RU" if compact else "Русский"),
                ft.DropdownOption(key="en", text="EN" if compact else "English"),
            ],
            on_select=self._select,
            width=104 if compact else 220,
            tooltip=tr("language.label"),
            text_size=13 if compact else 14,
            border_radius=CONTROL_RADIUS,
            border_color=BORDER_COLOR,
            focused_border_color=PRIMARY_COLOR,
            focused_border_width=2,
            color=TEXT_COLOR,
            label_style=ft.TextStyle(size=11, color=MUTED_COLOR),
            content_padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            dense=compact,
            menu_width=160,
            menu_height=176,
            elevation=2,
        )

    def sync_language(self) -> None:
        self.value = get_language()

    def _select(self, _event: ft.Event) -> None:
        if self.value not in {"ru", "en"}:
            return
        set_language(self.value)
        try:
            localize_tree(self.page)
            self.page.update()
        except (RuntimeError, AssertionError):
            pass
