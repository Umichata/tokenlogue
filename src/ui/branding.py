"""Компактное оформление Tokenlogue и индикаторы с управляемым временем жизни."""

from __future__ import annotations

import asyncio
import weakref
from concurrent.futures import Future
from dataclasses import dataclass

import flet as ft

from i18n import tr

_HEADER_SIZE = 32
_HEADER_ASSET = "branding/tokenlogue-logo-transparent.png"
_LOADING_ASSET = "branding/tokenlogue-loading.webp"
_STATIC_ASSET = "branding/tokenlogue-loading-static.png"
_ACCESSIBILITY_TIMEOUT_SECONDS = 2


class BrandHeader(ft.Row):
    """Прозрачный логотип фиксированного размера рядом с названием приложения."""

    def __init__(self) -> None:
        super().__init__(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Image(
                    src=_HEADER_ASSET,
                    width=_HEADER_SIZE,
                    height=_HEADER_SIZE,
                    fit=ft.BoxFit.CONTAIN,
                    exclude_from_semantics=True,
                ),
                ft.Text(
                    "Tokenlogue",
                    theme_style=ft.TextThemeStyle.TITLE_LARGE,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                ),
            ],
        )


@dataclass
class _PageMotion:
    page: weakref.ReferenceType[ft.Page]
    active: bool = True
    service: ft.SemanticsService | None = None
    reduce_motion: bool | None = None


_pages: dict[int, _PageMotion] = {}
_loaders: weakref.WeakValueDictionary[int, BrandLoader] = weakref.WeakValueDictionary()


def _page_motion(page: ft.Page) -> _PageMotion:
    identity = id(page)
    state = _pages.get(identity)
    if state is None:
        state = _PageMotion(weakref.ref(page, lambda _ref: _pages.pop(identity, None)))
        _pages[identity] = state
    return state


def set_page_animations_active(page: ft.Page, active: bool) -> None:
    """Останавливает индикаторы из общего обработчика жизненного цикла страницы."""
    state = _page_motion(page)
    changed = state.active != active
    state.active = active
    for loader in list(_loaders.values()):
        if loader._mounted_page is not None and loader._mounted_page() is page:
            if changed:
                loader._motion_checked = False
            previous = loader._logo.src
            loader._sync_animation()
            loader._publish_source_change(previous)


class BrandLoader(ft.Container):
    """Квадратный индикатор с готовым циклом WebP длительностью около 2,4 секунды."""

    def __init__(self, *, size: int = 56, active: bool = True) -> None:
        if not 24 <= size <= 64:
            raise ValueError("Размер индикатора должен быть от 24 до 64")
        self._mounted = False
        self._disposed = False
        self._mounted_page: weakref.ReferenceType[ft.Page] | None = None
        self._task: Future[None] | None = None
        self._generation = 0
        self._motion_checked = False
        self._animations_enabled = False
        self._motion_status = "unchecked"
        self._logo = ft.Image(
            src=_STATIC_ASSET,
            width=size,
            height=size,
            fit=ft.BoxFit.CONTAIN,
            gapless_playback=False,
            exclude_from_semantics=True,
        )
        super().__init__(
            width=size,
            height=size,
            visible=active,
            alignment=ft.Alignment.CENTER,
            content=ft.Semantics(
                label=tr("common.waiting"), image=True, content=self._logo
            ),
        )

    def did_mount(self) -> None:
        self._mounted = True
        self._mounted_page = weakref.ref(self.page)
        self._motion_checked = False
        _loaders[id(self)] = self
        self._sync_animation()

    def before_update(self) -> None:
        self._sync_animation()

    def will_unmount(self) -> None:
        self._mounted = False
        self._stop_animation()
        _loaders.pop(id(self), None)
        self._mounted_page = None

    def dispose(self) -> None:
        self._disposed = True
        previous = self._logo.src
        self._stop_animation()
        self._publish_source_change(previous)
        self.will_unmount()

    def set_active(self, active: bool) -> None:
        if self._disposed:
            return
        if active != self.visible:
            self._motion_checked = False
        previous = self._logo.src
        self.visible = active
        self._sync_animation()
        self._publish_source_change(previous)

    def _can_animate(self) -> bool:
        if not self._mounted or self._disposed or not self.visible:
            return False
        page = self._mounted_page() if self._mounted_page is not None else None
        if page is None or not _page_motion(page).active or not page.app_visible:
            return False
        ancestor = self.parent
        while ancestor is not None:
            if not getattr(ancestor, "visible", True):
                return False
            if isinstance(ancestor, ft.DialogControl) and not ancestor.open:
                return False
            ancestor = ancestor.parent
        return True

    def _sync_animation(self) -> None:
        if not self._can_animate():
            self._stop_animation()
            return
        if self._task is not None or self._motion_checked:
            return
        self._generation += 1
        self._task = self.page.run_task(self._animate, self._generation)

    def _stop_animation(self) -> None:
        self._generation += 1
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
        self._motion_checked = False
        self._animations_enabled = False
        # Замена источника освобождает слушатель анимированного изображения Flutter.
        self._logo.src = _STATIC_ASSET

    def _publish_source_change(self, previous: str | bytes) -> None:
        if not self._mounted or previous == self._logo.src:
            return
        try:
            self.update()
        except (RuntimeError, AssertionError):
            # Удалённый клиент или уже закрытое представление не надо оживлять.
            self._stop_animation()

    async def _animate(self, generation: int) -> None:
        """Проверяет доступность движения, сами кадры воспроизводит Flutter."""
        try:
            state = _page_motion(self.page)
            if state.service is None:
                state.service = ft.SemanticsService()
            try:
                features = await asyncio.wait_for(
                    state.service.get_accessibility_features(),
                    timeout=_ACCESSIBILITY_TIMEOUT_SECONDS,
                )
                reduced = features.disable_animations or features.reduce_motion
                status = "reduced" if reduced else "enabled"
            except Exception:
                # Ошибка чтения не доказывает уменьшение движения. Сохраняем лишь
                # ранее подтверждённый запрет, не приписывая пользователю настройку.
                reduced = state.reduce_motion is True
                status = "unavailable"
            if generation != self._generation or not self._can_animate():
                return
            if status != "unavailable":
                state.reduce_motion = reduced
            self._motion_checked = True
            self._animations_enabled = not reduced
            self._motion_status = status
            previous = self._logo.src
            self._logo.src = _STATIC_ASSET if reduced else _LOADING_ASSET
            self._publish_source_change(previous)
        finally:
            if generation == self._generation:
                self._task = None
