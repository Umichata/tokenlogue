"""Общие адаптивные стили приложения."""

import flet as ft

PAGE_BACKGROUND = ft.Colors.BLUE_GREY_900
PANEL_BACKGROUND = ft.Colors.BLUE_GREY_800
PRIMARY_COLOR = ft.Colors.BLUE_400
SUCCESS_COLOR = ft.Colors.GREEN_300
ERROR_COLOR = ft.Colors.RED_300
MUTED_COLOR = ft.Colors.BLUE_GREY_200
PAGE_PADDING = 20
CONTROL_SPACING = 16


def primary_button_style() -> ft.ButtonStyle:
    """Явно различает активное и отключённое состояния кнопки."""
    return ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: ft.Colors.WHITE,
            ft.ControlState.HOVERED: ft.Colors.WHITE,
            ft.ControlState.PRESSED: ft.Colors.WHITE,
            ft.ControlState.DISABLED: MUTED_COLOR,
        },
        bgcolor={
            ft.ControlState.DEFAULT: PRIMARY_COLOR,
            ft.ControlState.HOVERED: ft.Colors.BLUE_300,
            ft.ControlState.PRESSED: ft.Colors.BLUE_600,
            ft.ControlState.DISABLED: ft.Colors.BLUE_GREY_700,
        },
    )


def configure_page(page: ft.Page) -> None:
    """Настраивает страницу без фиксированного размера окна."""
    page.title = "Tokenlogue"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = PAGE_BACKGROUND
    page.padding = 0


def build_screen(controls: list[ft.Control]) -> ft.SafeArea:
    """Создаёт экран, прокручиваемый при появлении мобильной клавиатуры."""
    return ft.SafeArea(
        expand=True,
        maintain_bottom_view_padding=True,
        content=ft.ListView(
            expand=True,
            spacing=CONTROL_SPACING,
            padding=PAGE_PADDING,
            controls=controls,
        ),
    )
