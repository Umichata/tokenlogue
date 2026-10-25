"""Компактный переключатель языка без повторного входа или запросов."""

from __future__ import annotations

import flet as ft

from i18n import get_language, localize_tree, set_language, tr


class LanguageSelector(ft.Dropdown):
    def __init__(self) -> None:
        super().__init__(
            label=tr("language.label"),
            value=get_language(),
            options=[
                ft.DropdownOption(key="ru", text="Русский"),
                ft.DropdownOption(key="en", text="English"),
            ],
            on_select=self._select,
            width=220,
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
