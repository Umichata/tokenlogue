"""Общая система спокойных поверхностей, типографики и доступных действий."""

from typing import Any

import flet as ft

PAGE_BACKGROUND = "#101923"
PANEL_BACKGROUND = "#192633"
ELEVATED_BACKGROUND = "#223341"
INPUT_BACKGROUND = "#14212D"
PRIMARY_COLOR = "#62D6C3"
PRIMARY_FOREGROUND = "#102923"
TEXT_COLOR = "#EDF3F7"
SUCCESS_COLOR = ft.Colors.GREEN_300
WARNING_COLOR = "#F2C46D"
ERROR_COLOR = ft.Colors.RED_300
MUTED_COLOR = "#B7C5D1"
BORDER_COLOR = "#344859"
PAGE_PADDING = 16
CONTROL_SPACING = 16
SPACE_SMALL = 8
SPACE_MEDIUM = 12
SPACE_LARGE = 24
SPACE_SECTION = 32
CARD_RADIUS = 16
CONTROL_RADIUS = 10
TOUCH_SIZE = 44
AUTH_CARD_WIDTH = 420


def detail_row(label: str, value: str, *, size: int = 12) -> ft.Row:
    """Подпись и значение переносятся по ширине независимо друг от друга."""
    return ft.Row(
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.START,
        controls=[
            ft.Text(label, size=size, color=MUTED_COLOR, expand=3),
            ft.Text(
                value,
                size=size,
                selectable=True,
                expand=2,
                text_align=ft.TextAlign.RIGHT,
            ),
        ],
    )


def primary_button_style() -> ft.ButtonStyle:
    """У primary-действия различимы focus, hover, pressed и disabled."""
    return ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: PRIMARY_FOREGROUND,
            ft.ControlState.DISABLED: MUTED_COLOR,
        },
        bgcolor={
            ft.ControlState.DEFAULT: PRIMARY_COLOR,
            ft.ControlState.HOVERED: "#86E1D2",
            ft.ControlState.PRESSED: "#48BBA9",
            ft.ControlState.DISABLED: ELEVATED_BACKGROUND,
        },
        side={
            ft.ControlState.FOCUSED: ft.BorderSide(2, TEXT_COLOR),
            ft.ControlState.DEFAULT: ft.BorderSide(1, "transparent"),
        },
        shape=ft.RoundedRectangleBorder(radius=CONTROL_RADIUS),
        padding=ft.Padding.symmetric(horizontal=20, vertical=14),
        text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_600),
        elevation=0,
        animation_duration=100,
    )


def secondary_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color={
            ft.ControlState.DEFAULT: TEXT_COLOR,
            ft.ControlState.DISABLED: MUTED_COLOR,
        },
        bgcolor={
            ft.ControlState.HOVERED: ELEVATED_BACKGROUND,
            ft.ControlState.PRESSED: BORDER_COLOR,
        },
        side={
            ft.ControlState.FOCUSED: ft.BorderSide(2, PRIMARY_COLOR),
            ft.ControlState.DEFAULT: ft.BorderSide(1, "transparent"),
        },
        shape=ft.RoundedRectangleBorder(radius=CONTROL_RADIUS),
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        elevation=0,
    )


def danger_button_style() -> ft.ButtonStyle:
    style = secondary_button_style()
    style.color = {
        ft.ControlState.DEFAULT: ERROR_COLOR,
        ft.ControlState.DISABLED: MUTED_COLOR,
    }
    return style


def text_action_button_style(*, destructive: bool = False) -> ft.ButtonStyle:
    """Keep text actions clear at rest, with shared pointer and focus feedback."""
    style = secondary_button_style()
    foreground = ERROR_COLOR if destructive else PRIMARY_COLOR
    style.color = {
        ft.ControlState.DEFAULT: foreground,
        ft.ControlState.DISABLED: MUTED_COLOR,
    }
    style.icon_color = style.color
    style.bgcolor = {
        ft.ControlState.PRESSED: BORDER_COLOR,
        ft.ControlState.HOVERED: ELEVATED_BACKGROUND,
        ft.ControlState.DEFAULT: ft.Colors.TRANSPARENT,
    }
    style.overlay_color = ft.Colors.TRANSPARENT
    return style


def input_style() -> dict[str, Any]:
    """Без фиксированной высоты, чтобы подпись и счётчик не обрезались."""
    return dict(
        text_size=16,
        color=TEXT_COLOR,
        filled=True,
        fill_color=INPUT_BACKGROUND,
        border_color=BORDER_COLOR,
        border_radius=CONTROL_RADIUS,
        focused_border_color=PRIMARY_COLOR,
        focused_border_width=2,
        cursor_color=PRIMARY_COLOR,
        content_padding=ft.Padding.symmetric(horizontal=16, vertical=18),
        label_style=ft.TextStyle(color=MUTED_COLOR, size=14),
        counter_style=ft.TextStyle(color=MUTED_COLOR, size=12),
    )


def surface(
    content: ft.Control, *, padding: int = SPACE_LARGE, width: int | None = None
) -> ft.Container:
    return ft.Container(
        content=content,
        width=width,
        bgcolor=PANEL_BACKGROUND,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=CARD_RADIUS,
        padding=padding,
    )


def configure_page(page: ft.Page) -> None:
    """Локальная Material 3 тема без сетевых шрифтов и принудительного масштаба."""
    page.title = "Tokenlogue"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = PAGE_BACKGROUND
    page.padding = 0
    page.theme = ft.Theme(
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=PRIMARY_COLOR,
            on_primary=PRIMARY_FOREGROUND,
            secondary=PRIMARY_COLOR,
            surface=PANEL_BACKGROUND,
            on_surface=TEXT_COLOR,
            on_surface_variant=MUTED_COLOR,
            outline=BORDER_COLOR,
            error=ERROR_COLOR,
        ),
        scaffold_bgcolor=PAGE_BACKGROUND,
        text_theme=ft.TextTheme(
            headline_medium=ft.TextStyle(
                size=26, weight=ft.FontWeight.W_600, color=TEXT_COLOR, height=1.2
            ),
            title_large=ft.TextStyle(
                size=20, weight=ft.FontWeight.W_600, color=TEXT_COLOR
            ),
            title_medium=ft.TextStyle(
                size=16, weight=ft.FontWeight.W_600, color=TEXT_COLOR
            ),
            body_large=ft.TextStyle(size=16, color=TEXT_COLOR, height=1.45),
            body_medium=ft.TextStyle(size=14, color=TEXT_COLOR, height=1.45),
            body_small=ft.TextStyle(size=12, color=MUTED_COLOR, height=1.4),
        ),
        divider_color=BORDER_COLOR,
        hover_color=ELEVATED_BACKGROUND,
        focus_color=BORDER_COLOR,
        disabled_color=MUTED_COLOR,
    )
    page.dark_theme = page.theme


def build_screen(controls: list[ft.Control]) -> ft.SafeArea:
    """Экран с прокруткой при малой высоте и мобильной клавиатуре."""
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


def build_auth_screen(
    controls: list[ft.Control], *, header: ft.Control, width: int = AUTH_CARD_WIDTH
) -> ft.SafeArea:
    """Общая шапка и ограниченная карточка без вертикального центрирования."""
    return ft.SafeArea(
        expand=True,
        maintain_bottom_view_padding=True,
        content=ft.Column(
            spacing=0,
            controls=[
                header,
                ft.ListView(
                    expand=True,
                    spacing=0,
                    padding=ft.Padding.only(top=24, bottom=32, left=16, right=16),
                    controls=[
                        ft.Container(
                            alignment=ft.Alignment.TOP_CENTER,
                            content=surface(
                                ft.Column(
                                    controls=controls,
                                    spacing=16,
                                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                ),
                                width=width,
                            ),
                        )
                    ],
                ),
            ],
        ),
    )
