"""Адаптивный интерфейс списка и активного локального чата."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import flet as ft

from auth.access import free_mode_allowed, paid_mode_allowed
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.accounting import AccountingStatus, BudgetState
from chat.models import Chat, ChatMode
from chat_interaction_controller import ActiveChatState
from i18n import (
    display_chat_title,
    display_model_name,
    fresh_text,
    get_preferences,
    money,
    number,
    tr,
)
from preferences import PreferencesStore
from ui.branding import BrandHeader, BrandLoader
from ui.language_selector import LanguageSelector
from ui.message_composer import MessageComposer
from ui.message_history import MessageHistoryView
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    SUCCESS_COLOR,
    detail_row,
    primary_button_style,
)

WIDE_LAYOUT_BREAKPOINT = 760

AsyncCallback = Callable[[], Awaitable[None]]
ChatCallback = Callable[[str], Awaitable[None]]
RenameCallback = Callable[[str, str], Awaitable[None]]
MessageCallback = Callable[[str], Awaitable[None]]
TurnCallback = Callable[[str], Awaitable[None]]


class ChatWorkspaceView:
    """Сохраняет sidebar/drawer и выделяет активную историю с редактором."""

    def __init__(
        self,
        page: ft.Page,
        chats: list[Chat],
        selected_chat: Chat | None,
        interaction_state: ActiveChatState | None,
        *,
        on_new_chat: AsyncCallback,
        on_select_chat: ChatCallback,
        on_rename_chat: ChatCallback,
        on_delete_chat: ChatCallback,
        on_lock: AsyncCallback,
        on_send_message: MessageCallback,
        on_retry_turn: TurnCallback,
        on_configure_limits: ChatCallback,
        on_edit_limits: ChatCallback,
        on_release_unknown: TurnCallback,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        key_validation_in_progress: bool,
        on_retry_key: AsyncCallback,
        on_replace_key: AsyncCallback,
        on_draft_change: RenameCallback | None = None,
        preferences: PreferencesStore | None = None,
    ) -> None:
        self._page = page
        self._preferences = preferences or get_preferences()
        self._chats = chats
        self._selected_chat = selected_chat
        self._interaction_state = interaction_state
        self._on_new_chat = on_new_chat
        self._on_select_chat = on_select_chat
        self._on_rename_chat = on_rename_chat
        self._on_delete_chat = on_delete_chat
        self._on_lock = on_lock
        self._on_send_message = on_send_message
        self._on_draft_change = on_draft_change
        self._on_retry_turn = on_retry_turn
        self._on_configure_limits = on_configure_limits
        self._on_edit_limits = on_edit_limits
        self._on_release_unknown = on_release_unknown
        self._key_validity = key_validity
        self._key_limit = key_limit
        self._key_validation_in_progress = key_validation_in_progress
        self._on_retry_key = on_retry_key
        self._on_replace_key = on_replace_key
        self._new_chat_allowed = free_mode_allowed(key_validity)
        self._disposed = False
        self._sending = False
        self._chat_generation = 0
        self._menu_revision = 0
        self._menu_dialog: ft.AlertDialog | None = None
        self._menu_list: ft.ListView | None = None
        self._menu_container: ft.Container | None = None
        self._key_panel: _KeyStatusPanel | None = None
        self._key_refresh_in_progress = False
        self._available_width = page.width or 420
        self._available_height = getattr(page, "height", None) or 700
        self.menu_button = ft.IconButton(
            icon=ft.Icons.MORE_VERT,
            tooltip=tr("chat.options"),
            width=48,
            height=48,
            on_click=self._open_options,
        )
        self.sidebar_button = ft.IconButton(
            icon=ft.Icons.MENU,
            tooltip=tr("chat.open_list"),
            width=48,
            height=48,
            on_click=self._toggle_sidebar,
        )
        self.sidebar_semantics = ft.Semantics(
            label=tr("chat.open_list"), button=True, content=self.sidebar_button
        )
        self._sidebar_panel: ft.Container | None = None
        self._sidebar_divider: ft.VerticalDivider | None = None
        self.send_notice: ft.Control | None = None
        self.retry_key_button: ft.TextButton | None = None
        self.replace_key_button: ft.TextButton | None = None
        self.rename_button: ft.TextButton | None = None
        self.delete_button: ft.TextButton | None = None
        self._actions_chat_id: str | None = None
        self.limits_button: ft.Button | ft.TextButton | None = None
        self.release_unknown_button: ft.Button | None = None
        self.message_history: MessageHistoryView | None = None
        self.composer: MessageComposer | None = None
        width = page.width or 0
        self._wide = width >= WIDE_LAYOUT_BREAKPOINT
        self._layout = ft.Container(
            expand=True,
            on_size_change=self._handle_size_change,
        )
        self.control = ft.SafeArea(
            expand=True,
            maintain_bottom_view_padding=True,
            content=self._layout,
        )
        self._sync_interaction_components(force=True)
        self._render_layout()

    @property
    def editor_value(self) -> str:
        return self.composer.value if self.composer is not None else ""

    @property
    def key_replacement_busy(self) -> bool:
        return (
            self._sending
            or self._key_validation_in_progress
            or self._key_refresh_in_progress
        )

    def dispose(self) -> None:
        self._disposed = True
        self._chat_generation += 1
        self.close_menu()
        self._page.drawer = None
        if self.composer is not None:
            self.composer.dispose()

    def update_workspace(
        self,
        chats: list[Chat],
        selected_chat: Chat | None,
        interaction_state: ActiveChatState | None,
        *,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
        key_validation_in_progress: bool,
    ) -> None:
        if self._disposed:
            return
        previous_chat_id = (
            self._selected_chat.id if self._selected_chat is not None else None
        )
        current_chat_id = selected_chat.id if selected_chat is not None else None
        if previous_chat_id != current_chat_id:
            self._chat_generation += 1
            self.close_menu()
        self._chats = chats
        self._selected_chat = selected_chat
        self._interaction_state = interaction_state
        self._key_validity = key_validity
        self._key_limit = key_limit
        self._key_validation_in_progress = key_validation_in_progress
        self._new_chat_allowed = free_mode_allowed(key_validity)
        self._sync_interaction_components(force=previous_chat_id != current_chat_id)
        self._refresh_menu()
        self._render_layout()

    def set_sending(self, sending: bool) -> None:
        self._sending = sending
        if self.composer is not None:
            self.composer.set_busy(sending)
        for button in (self.rename_button, self.delete_button, self.limits_button):
            if button is not None:
                button.disabled = sending
        if self._menu_dialog is not None:
            self._build_key_status_panel()
        self._update_menu_control()

    def clear_editor_if_matches(self, expected: str) -> None:
        if self.composer is not None:
            self.composer.clear_if_matches(expected)

    def restore_editor(self, text: str) -> None:
        if self.composer is not None:
            self.composer.set_value(text)

    def show_message(self, message: str, *, error: bool = True) -> None:
        if self.composer is not None:
            self.composer.show_message(message, error=error)

    async def scroll_messages_to_end(self) -> None:
        if self.message_history is not None:
            await self.message_history.scroll_to_end()

    def _sync_interaction_components(self, *, force: bool) -> None:
        state = self._interaction_state
        if self._selected_chat is None or state is None:
            if self.composer is not None:
                self.composer.dispose()
            self.message_history = None
            self.composer = None
            return
        if force or self.message_history is None or self.composer is None:
            if self.composer is not None:
                self.composer.dispose()
            chat_id = self._selected_chat.id

            async def draft_changed(text: str) -> None:
                if self._on_draft_change is not None:
                    await self._on_draft_change(chat_id, text)

            self.message_history = MessageHistoryView(
                state.messages,
                state.turns,
                on_retry=self._on_retry_turn,
            )
            self.composer = MessageComposer(
                self._on_send_message,
                enabled=self._sending_allowed(state),
                on_change=draft_changed,
            )
        else:
            self.message_history.set_messages(state.messages, state.turns)
            self.composer.set_enabled(self._sending_allowed(state))
        self.set_sending(state.sending)

    def _sending_allowed(self, state: ActiveChatState) -> bool:
        if not state.budget.limits_configured:
            return False
        if state.budget.state in {
            BudgetState.ACCOUNTING_UNKNOWN,
            BudgetState.EXHAUSTED,
        }:
            return False
        if state.chat.mode is ChatMode.FREE:
            return free_mode_allowed(self._key_validity)
        return paid_mode_allowed(self._key_validity, self._key_limit)

    def _handle_size_change(
        self,
        event: ft.LayoutSizeChangeEvent[ft.LayoutControl],
    ) -> None:
        self._available_width = event.width
        self._available_height = getattr(event, "height", self._available_height)
        self._resize_menu()
        wide = event.width >= WIDE_LAYOUT_BREAKPOINT
        if wide == self._wide:
            return
        self._wide = wide
        self._resize_menu()
        self._render_layout()
        self._layout.update()

    @property
    def sidebar_visible(self) -> bool:
        return self._wide and self._preferences.wide_sidebar_visible

    def _apply_sidebar_visibility(self) -> None:
        if self._sidebar_panel is not None:
            self._sidebar_panel.visible = self.sidebar_visible
        if self._sidebar_divider is not None:
            self._sidebar_divider.visible = self.sidebar_visible
        self.sidebar_button.tooltip = tr(
            "chat.open_list"
            if not self._wide
            else "chat.hide_list"
            if self.sidebar_visible
            else "chat.show_list"
        )
        self.sidebar_semantics.label = self.sidebar_button.tooltip
        self._resize_menu()

    async def _toggle_sidebar(self, _event: ft.Event) -> None:
        if self._disposed:
            return
        if not self._wide:
            await self._page.show_drawer()
            return
        self._preferences.set_wide_sidebar_visible(not self.sidebar_visible)
        self._apply_sidebar_visibility()
        self._layout.update()

    def _render_layout(self) -> None:
        if self.composer is not None:
            self.composer.message_field.max_lines = 5 if self._wide else 2
        self._sync_chat_actions()
        self._sidebar_panel = self._build_chat_panel(width=320)
        self._sidebar_divider = ft.VerticalDivider(width=1)
        self._layout.content = ft.Row(
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self._sidebar_panel,
                self._sidebar_divider,
                self._build_chat_content(show_menu=True),
            ],
        )
        self._page.drawer = None if self._wide else self._build_drawer()
        self._apply_sidebar_visibility()

    def _sync_chat_actions(self) -> None:
        chat = self._selected_chat
        chat_id = chat.id if chat is not None else None
        if chat_id == self._actions_chat_id:
            return
        self._actions_chat_id = chat_id
        self.rename_button = self.delete_button = None
        if chat is None:
            return
        self.rename_button = ft.TextButton(
            tr("chat.rename"),
            icon=ft.Icons.EDIT_OUTLINED,
            height=48,
            disabled=self._sending,
            on_click=self._chat_action(self._on_rename_chat, chat.id, menu=False),
        )
        self.delete_button = ft.TextButton(
            tr("chat.delete_chat"),
            icon=ft.Icons.DELETE_OUTLINE,
            height=48,
            disabled=self._sending,
            style=ft.ButtonStyle(color=ERROR_COLOR),
            on_click=self._chat_action(self._on_delete_chat, chat.id, menu=False),
        )

    def _build_chat_panel(self, *, width: int | None = None) -> ft.Container:
        chat_list = ft.ListView(
            expand=True,
            spacing=6,
            controls=[self._build_chat_tile(chat) for chat in self._chats],
        )
        if not self._chats:
            chat_list.controls.append(
                ft.Text(
                    tr("chat.empty_list"),
                    color=MUTED_COLOR,
                    text_align=ft.TextAlign.CENTER,
                )
            )
        return ft.Container(
            width=width,
            bgcolor=PANEL_BACKGROUND,
            padding=16,
            content=ft.Column(
                expand=True,
                controls=[
                    BrandHeader(),
                    ft.Button(
                        tr("chat.untitled"),
                        icon=ft.Icons.ADD,
                        style=primary_button_style(),
                        disabled=not self._new_chat_allowed,
                        on_click=self._handle_new_chat_button,
                    ),
                    ft.Divider(),
                    chat_list,
                    ft.Divider(),
                    ft.TextButton(
                        tr("chat.lock"),
                        icon=ft.Icons.LOCK_OUTLINE,
                        on_click=self._handle_lock_text,
                    ),
                ],
            ),
        )

    def _build_drawer(self) -> ft.NavigationDrawer:
        return ft.NavigationDrawer(
            bgcolor=PANEL_BACKGROUND,
            controls=[self._build_chat_panel()],
        )

    def _build_chat_tile(self, chat: Chat) -> ft.ListTile:
        async def select_chat(_event: ft.Event[ft.ListTile]) -> None:
            self.close_menu()
            if not self._wide:
                await self._page.close_drawer()
            await self._on_select_chat(chat.id)

        mode = tr("chat.free") if chat.mode is ChatMode.FREE else tr("chat.paid")
        return ft.ListTile(
            title=ft.Text(
                display_chat_title(chat), max_lines=1, overflow=ft.TextOverflow.ELLIPSIS
            ),
            subtitle=ft.Text(
                tr(
                    "chat.subtitle",
                    mode=mode,
                    model=display_model_name(
                        chat.requested_model_id, chat.requested_model_name
                    ),
                ),
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
            leading=ft.Icons.CHAT_BUBBLE_OUTLINE,
            selected=(
                self._selected_chat is not None and self._selected_chat.id == chat.id
            ),
            selected_tile_color=ft.Colors.BLUE_GREY_700,
            on_click=select_chat,
        )

    def _build_chat_content(self, *, show_menu: bool) -> ft.Control:
        body = (
            self._build_empty_state()
            if self._selected_chat is None
            else self._build_selected_chat(self._selected_chat)
        )
        header_controls: list[ft.Control] = [self.sidebar_semantics]
        header_controls.extend(
            [
                ft.Text(
                    display_chat_title(self._selected_chat)
                    if self._selected_chat is not None
                    else "Tokenlogue",
                    tooltip=display_chat_title(self._selected_chat)
                    if self._selected_chat is not None
                    else "Tokenlogue",
                    theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    expand=True,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                ft.IconButton(
                    icon=ft.Icons.ADD,
                    tooltip=tr("chat.untitled"),
                    disabled=not self._new_chat_allowed,
                    on_click=self._handle_new_chat_icon,
                ),
                ft.IconButton(
                    icon=ft.Icons.LOCK_OUTLINE,
                    tooltip=tr("chat.lock"),
                    on_click=self._handle_lock_icon,
                ),
                self.menu_button,
            ]
        )
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    content=ft.Row(spacing=0, controls=header_controls),
                ),
                *(
                    [
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=12),
                            content=ft.Row(
                                wrap=True,
                                spacing=8,
                                run_spacing=0,
                                controls=[self.rename_button, self.delete_button],
                            ),
                        )
                    ]
                    if self.rename_button is not None and self.delete_button is not None
                    else []
                ),
                ft.Divider(height=1),
                body,
            ],
        )

    def _build_empty_state(self) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=20,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=52, color=MUTED_COLOR),
                    ft.Text(
                        tr("chat.empty"), theme_style=ft.TextThemeStyle.TITLE_LARGE
                    ),
                    ft.Text(
                        tr("chat.create_help"),
                        color=MUTED_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Button(
                        tr("chat.untitled"),
                        icon=ft.Icons.ADD,
                        style=primary_button_style(),
                        disabled=not self._new_chat_allowed,
                        on_click=self._handle_new_chat_button,
                    ),
                    *(
                        [
                            ft.Text(
                                _key_status_presentation(
                                    self._key_validity, self._key_limit
                                )[0],
                                color=ERROR_COLOR,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.TextButton(
                                tr("chat.key_options"), on_click=self._open_options
                            ),
                        ]
                        if not self._new_chat_allowed
                        else []
                    ),
                    _history_warning(),
                ],
            ),
        )

    def _build_selected_chat(self, chat: Chat) -> ft.Control:
        state = self._interaction_state
        if state is None or state.chat.id != chat.id:
            return ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[BrandLoader(), ft.Text(tr("chat.loading"))],
                ),
            )
        assert self.message_history is not None and self.composer is not None
        controls: list[ft.Control] = [self.message_history.control]
        self.send_notice = self._build_send_notice(state)
        if self.send_notice is not None:
            controls.append(self.send_notice)
        unknown = self._build_unknown_panel(state)
        if unknown is not None:
            controls.append(unknown)
        controls.extend(
            [
                self.composer.control,
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=4),
                    content=_history_warning(),
                ),
            ]
        )
        return ft.Column(expand=True, spacing=4, controls=controls)

    def _build_send_notice(self, state: ActiveChatState) -> ft.Control | None:
        message = ""
        action: ft.Control | None = None
        if not state.budget.limits_configured:
            message = tr("chat.configure_before_send")
            action = ft.TextButton(
                tr("chat.configure_limits"),
                disabled=self._sending,
                on_click=self._chat_action(self._on_configure_limits, state.chat.id),
            )
        elif state.budget.state is BudgetState.EXHAUSTED:
            message = tr("chat.exhausted")
            action = ft.TextButton(
                tr("chat.edit_limits"),
                disabled=self._sending,
                on_click=self._chat_action(self._on_edit_limits, state.chat.id),
            )
        if not self._key_allows_chat(state.chat):
            message = _key_status_presentation(self._key_validity, self._key_limit)[0]
            action = ft.TextButton(tr("chat.key_options"), on_click=self._open_options)
        if not message:
            return None
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=2),
            content=ft.Column(
                tight=True,
                spacing=0,
                controls=[
                    ft.Text(message, size=12, color=ft.Colors.AMBER_300),
                    *([action] if action is not None else []),
                ],
            ),
        )

    def _key_allows_chat(self, chat: Chat) -> bool:
        if chat.mode is ChatMode.FREE:
            return free_mode_allowed(self._key_validity)
        return paid_mode_allowed(self._key_validity, self._key_limit)

    def _chat_action(self, callback: ChatCallback, chat_id: str, *, menu: bool = False):
        generation = self._chat_generation
        revision = self._menu_revision

        async def invoke(_event: ft.Event) -> None:
            if (
                self._disposed
                or self._sending
                or generation != self._chat_generation
                or self._selected_chat is None
                or self._selected_chat.id != chat_id
            ):
                return
            if menu and (self._menu_dialog is None or revision != self._menu_revision):
                return
            self.close_menu()
            await callback(chat_id)

        return invoke

    def _menu_action(self, callback: AsyncCallback):
        revision = self._menu_revision

        async def invoke(_event: ft.Event) -> None:
            if (
                self._disposed
                or self._menu_dialog is None
                or revision != self._menu_revision
                or self.key_replacement_busy
            ):
                return
            self.close_menu()
            await callback()

        return invoke

    def _refresh_key_action(self):
        revision = self._menu_revision

        async def invoke(_event: ft.Event) -> None:
            if (
                self._disposed
                or self._menu_dialog is None
                or revision != self._menu_revision
                or self._key_validation_in_progress
                or self._key_refresh_in_progress
            ):
                return
            # Отклоняем повторные нажатия до обновления состояния контроллера.
            self._key_refresh_in_progress = True
            self._build_key_status_panel()
            self._update_menu_control()
            try:
                await self._on_retry_key()
            finally:
                self._key_refresh_in_progress = False
                if not self._disposed and self._menu_dialog is not None:
                    self._build_key_status_panel()
                    self._update_menu_control()

        return invoke

    def _build_menu_controls(self) -> list[ft.Control]:
        controls: list[ft.Control] = [
            ft.Text(tr("key.title"), weight=ft.FontWeight.BOLD),
            self._build_key_status_panel(),
            ft.Divider(),
            LanguageSelector(),
        ]
        chat, state = self._selected_chat, self._interaction_state
        self.limits_button = None
        if chat is None:
            return controls
        controls.extend(
            [
                ft.Divider(),
                ft.Text(tr("chat.chat"), weight=ft.FontWeight.BOLD),
                detail_row(
                    tr("chat.mode"),
                    tr("chat.free") if chat.mode is ChatMode.FREE else tr("chat.paid"),
                ),
                detail_row(
                    tr("meta.model"),
                    display_model_name(
                        chat.requested_model_id, chat.requested_model_name
                    ),
                ),
                detail_row(tr("meta.model_id"), chat.requested_model_id),
            ]
        )
        if chat.mode is ChatMode.PAID:
            controls.extend(
                [
                    detail_row(
                        tr("price.prompt_million"),
                        money(chat.prompt_price_per_token * Decimal(1_000_000)),
                    ),
                    detail_row(
                        tr("price.completion_million"),
                        money(chat.completion_price_per_token * Decimal(1_000_000)),
                    ),
                ]
            )
        if state is None or state.chat.id != chat.id:
            return controls
        budget = state.budget
        remaining = state.remaining
        controls.extend(
            [
                ft.Divider(),
                ft.Text(tr("budget.title"), weight=ft.FontWeight.BOLD),
                detail_row(tr("budget.used_tokens"), number(budget.total_tokens_used)),
                detail_row(
                    tr("budget.reserved_tokens"), number(budget.reserved_tokens)
                ),
                detail_row(
                    tr("budget.remaining_tokens"),
                    number(remaining.tokens) if remaining.tokens is not None else "—",
                ),
                detail_row(
                    tr("budget.token_limit"),
                    number(budget.token_limit)
                    if budget.token_limit is not None
                    else "—",
                ),
                detail_row(
                    tr("budget.next_maximum"),
                    number(budget.max_completion_tokens)
                    if budget.max_completion_tokens is not None
                    else "—",
                ),
            ]
        )
        if chat.mode is ChatMode.PAID:
            controls.extend(
                [
                    detail_row(
                        tr("budget.actual_cost"),
                        money(budget.cost_used_usd),
                    ),
                    detail_row(
                        tr("budget.reserved_cost"),
                        money(budget.cost_reserved_usd),
                    ),
                    detail_row(
                        tr("budget.remaining_money"),
                        _money_or_unknown(remaining.cost_usd),
                    ),
                    detail_row(
                        tr("budget.spending_limit"),
                        _money_or_unknown(budget.cost_limit_usd),
                    ),
                ]
            )
        self.limits_button = ft.TextButton(
            tr("chat.edit_limits")
            if budget.limits_configured
            else tr("chat.configure_limits"),
            icon=ft.Icons.TUNE,
            disabled=self._sending,
            on_click=self._chat_action(
                self._on_edit_limits
                if budget.limits_configured
                else self._on_configure_limits,
                chat.id,
                menu=True,
            ),
        )
        controls.append(self.limits_button)
        return controls

    @property
    def menu_open(self) -> bool:
        return self._menu_dialog is not None

    async def _open_options(self, _event: ft.Event) -> None:
        await self.open_menu()

    async def open_menu(self) -> None:
        if self._disposed or self._menu_dialog is not None:
            return
        self._menu_revision += 1
        self._menu_list = ft.ListView(spacing=8, padding=0, auto_scroll=False)
        self._menu_container = ft.Container(content=self._menu_list)
        dialog = ft.AlertDialog(
            modal=False,
            alignment=ft.Alignment.TOP_RIGHT,
            inset_padding=ft.Padding(12, 60, 12, 12),
            title_padding=ft.Padding(16, 4, 4, 0),
            content_padding=ft.Padding(16, 0, 16, 12),
            title=ft.Row(
                controls=[
                    ft.Text(
                        tr("chat.options"),
                        expand=True,
                        theme_style=ft.TextThemeStyle.TITLE_MEDIUM,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip=tr("chat.close_options"),
                        autofocus=True,
                        on_click=self._close_options,
                    ),
                ]
            ),
            content=self._menu_container,
            on_dismiss=self._menu_dismissed,
        )
        self._menu_dialog = dialog
        self._resize_menu(update=False)
        self._menu_list.controls = self._build_menu_controls()
        self._page.show_dialog(dialog)

    def _resize_menu(self, *, update: bool = True) -> None:
        if self._menu_container is None or self._menu_dialog is None:
            return
        main_width = self._available_width - (321 if self.sidebar_visible else 0)
        self._menu_container.width = max(100, min(360, main_width - 56))
        self._menu_container.height = max(64, min(520, self._available_height - 176))
        if update:
            self._update_menu_control()

    def _update_menu_control(self) -> None:
        if self._menu_dialog is not None:
            try:
                self._menu_dialog.update()
            except (RuntimeError, AssertionError):
                pass

    def _refresh_menu(self) -> None:
        if self._menu_dialog is None or self._menu_list is None:
            return
        self._menu_revision += 1
        self._menu_list.controls = self._build_menu_controls()
        self._update_menu_control()

    def close_menu(self) -> None:
        dialog = self._menu_dialog
        self._menu_dialog = None
        self._menu_list = None
        self._menu_container = None
        if self._key_panel is not None:
            self._key_panel.loader.dispose()
        self._key_panel = None
        self._menu_revision += 1
        self.retry_key_button = self.replace_key_button = None
        self.limits_button = None
        if dialog is not None:
            # Закрываем именно своё окно, не снимая чужой диалог с вершины стека.
            dialog.open = False
            try:
                dialog.update()
            except (RuntimeError, AssertionError):
                pass

    async def _close_options(self, _event: ft.Event) -> None:
        self.close_menu()
        await self._focus_menu_button()

    async def _menu_dismissed(self, event: ft.Event[ft.DialogControl]) -> None:
        if event.control is self._menu_dialog:
            self.close_menu()
            await self._focus_menu_button()

    async def _focus_menu_button(self) -> None:
        if not self._disposed:
            try:
                await self.menu_button.focus()
            except (RuntimeError, AssertionError):
                pass

    def _build_unknown_panel(self, state: ActiveChatState) -> ft.Control | None:
        unknown_turn = next(
            (
                turn
                for turn in state.turns
                if turn.accounting_status is AccountingStatus.UNKNOWN
            ),
            None,
        )
        if unknown_turn is None:
            self.release_unknown_button = None
            return None

        async def release(_chat_id: str) -> None:
            current = self._interaction_state
            if current is not None and any(
                t.id == unknown_turn.id
                and t.accounting_status is AccountingStatus.UNKNOWN
                for t in current.turns
            ):
                await self._on_release_unknown(unknown_turn.id)

        self.release_unknown_button = ft.Button(
            tr("reserve.release_unknown"),
            icon=ft.Icons.WARNING_AMBER,
            disabled=state.sending,
            on_click=self._chat_action(release, state.chat.id),
        )
        return ft.Container(
            margin=ft.Margin.symmetric(horizontal=12),
            padding=12,
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.AMBER_300),
            border_radius=12,
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Text(
                        tr(
                            "reserve.unknown_free",
                            tokens=number(state.budget.reserved_tokens),
                        )
                        if state.chat.mode is ChatMode.FREE
                        else tr(
                            "reserve.unknown_paid",
                            tokens=number(state.budget.reserved_tokens),
                            amount=money(state.budget.cost_reserved_usd),
                        ),
                        color=ft.Colors.AMBER_300,
                    ),
                    self.release_unknown_button,
                ],
            ),
        )

    def _build_key_status_panel(self) -> ft.Control:
        message, color, _can_retry, _can_replace = _key_status_presentation(
            self._key_validity,
            self._key_limit,
        )
        if self._key_panel is None:
            self._key_panel = _KeyStatusPanel()
        panel = self._key_panel
        panel.update_status(
            message=message,
            color=color,
            limit=self._key_limit.remaining,
            busy=self._key_validation_in_progress or self._key_refresh_in_progress,
            replacement_busy=self.key_replacement_busy,
            replacement_notice=(
                tr("key.replace_wait_check")
                if self._key_validation_in_progress or self._key_refresh_in_progress
                else tr("key.replace_wait_send")
                if self._sending
                else ""
            ),
        )
        panel.refresh_button.on_click = self._refresh_key_action()
        panel.replace_button.on_click = self._menu_action(self._on_replace_key)
        self.retry_key_button = panel.refresh_button
        self.replace_key_button = panel.replace_button
        return panel.control

    async def _handle_new_chat_button(self, _event: ft.Event[ft.Button]) -> None:
        self.close_menu()
        await self._on_new_chat()

    async def _handle_new_chat_icon(self, _event: ft.Event[ft.IconButton]) -> None:
        self.close_menu()
        await self._on_new_chat()

    async def _handle_lock_text(self, _event: ft.Event[ft.TextButton]) -> None:
        self.close_menu()
        await self._on_lock()

    async def _handle_lock_icon(self, _event: ft.Event[ft.IconButton]) -> None:
        self.close_menu()
        await self._on_lock()

    async def _open_drawer(self, _event: ft.Event[ft.IconButton]) -> None:
        await self._page.show_drawer()


class _KeyStatusPanel:
    """Сохраняет элементы статуса при обновлении открытого меню."""

    def __init__(self) -> None:
        self.message = ft.Text()
        self.limit_row = detail_row(tr("key.available_limit"), "")
        self.loader = BrandLoader(size=26, active=False)
        self.progress = ft.Row(
            controls=[
                self.loader,
                ft.Text(tr("key.checking"), color=MUTED_COLOR, expand=True),
            ],
        )
        self.refresh_button = ft.TextButton(
            tr("key.refresh"),
            icon=ft.Icons.REFRESH,
        )
        self.replace_button = ft.TextButton(
            ft.Text(tr("key.replace"), no_wrap=False),
            icon=ft.Icons.KEY,
        )
        self.replacement_notice = ft.Text(size=12, color=MUTED_COLOR, visible=False)
        self.control = ft.Container(
            padding=8,
            border_radius=12,
            content=ft.Column(
                tight=True,
                controls=[
                    self.message,
                    self.limit_row,
                    self.progress,
                    ft.Column(
                        tight=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=[
                            self.refresh_button,
                            self.replace_button,
                            self.replacement_notice,
                        ],
                    ),
                ],
            ),
        )

    def update_status(
        self,
        *,
        message: str,
        color: str,
        limit: Decimal | None,
        busy: bool,
        replacement_busy: bool,
        replacement_notice: str,
    ) -> None:
        self.message.value = fresh_text(message)
        self.message.color = color
        self.control.bgcolor = ft.Colors.with_opacity(0.12, color)
        self.limit_row.visible = limit is not None
        value = self.limit_row.controls[1]
        assert isinstance(value, ft.Text)
        value.value = _money_or_unknown(limit)
        self.progress.visible = busy
        self.loader.set_active(busy)
        self.refresh_button.disabled = busy
        self.replace_button.visible = True
        self.replace_button.disabled = replacement_busy
        self.replacement_notice.value = fresh_text(replacement_notice)
        self.replacement_notice.visible = bool(replacement_notice)


class RenameChatDialog:
    """Диалог переименования с локальной валидацией и состоянием ожидания."""

    def __init__(
        self,
        chat: Chat,
        on_confirm: RenameCallback,
        on_cancel: Callable[[], None],
    ) -> None:
        self._chat_id = chat.id
        self._on_confirm = on_confirm

        def handle_cancel(_event: ft.Event[ft.TextButton]) -> None:
            on_cancel()

        placeholder = getattr(chat, "title_origin", "legacy") == "placeholder"
        self.title_field = ft.TextField(
            value="" if placeholder else chat.title,
            hint_text=display_chat_title(chat) if placeholder else None,
            label=tr("chat.title_label"),
            max_length=120,
            autofocus=True,
            on_submit=self._handle_submit,
        )
        self.confirm_button = ft.Button(tr("chat.save"), on_click=self._handle_click)
        self.control = ft.AlertDialog(
            modal=True,
            title=ft.Text(tr("chat.rename_title")),
            content=self.title_field,
            actions=[
                ft.TextButton(tr("common.cancel"), on_click=handle_cancel),
                self.confirm_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    @property
    def chat_id(self) -> str:
        return self._chat_id

    async def _handle_click(self, _event: ft.Event[ft.Button]) -> None:
        await self._submit_title()

    async def _handle_submit(self, _event: ft.Event[ft.TextField]) -> None:
        await self._submit_title()

    async def _submit_title(self) -> None:
        if self.confirm_button.disabled:
            return
        title = self.title_field.value
        if not isinstance(title, str):
            self.show_error(tr("chat.title_text_error"))
            return
        await self._on_confirm(self._chat_id, title)

    def set_busy(self, busy: bool) -> None:
        self.title_field.disabled = busy
        self.confirm_button.disabled = busy

    def show_error(self, message: str) -> None:
        self.title_field.error = fresh_text(message)


def build_delete_chat_dialog(
    chat: Chat,
    on_confirm: ChatCallback,
    on_cancel: Callable[[], None],
) -> ft.AlertDialog:
    async def confirm(_event: ft.Event[ft.Button]) -> None:
        await on_confirm(chat.id)

    def cancel(_event: ft.Event[ft.TextButton]) -> None:
        on_cancel()

    return ft.AlertDialog(
        modal=True,
        title=ft.Text(tr("chat.delete_title")),
        content=ft.Text(tr("chat.delete_body", title=display_chat_title(chat))),
        actions=[
            ft.TextButton(tr("common.cancel"), on_click=cancel),
            ft.Button(
                tr("chat.delete"),
                icon=ft.Icons.DELETE_OUTLINE,
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.RED_600,
                on_click=confirm,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )


def _history_warning() -> ft.Control:
    return ft.Text(
        tr("chat.history_warning"),
        color=MUTED_COLOR,
        size=12,
        text_align=ft.TextAlign.CENTER,
    )


def _money_or_unknown(value: Decimal | None) -> str:
    return "—" if value is None else money(value)


def _key_status_presentation(
    key_validity: KeyValidityState,
    key_limit: KeyLimitInfo,
) -> tuple[str, str, bool, bool]:
    if key_validity is KeyValidityState.INVALID:
        return (
            tr("key.invalid_short"),
            ERROR_COLOR,
            True,
            True,
        )
    if key_validity is KeyValidityState.RESTRICTED:
        return (
            tr("key.restricted_short"),
            ft.Colors.AMBER_300,
            True,
            True,
        )
    if key_validity is KeyValidityState.UNKNOWN:
        return (
            tr("key.unknown_short"),
            ft.Colors.AMBER_300,
            True,
            True,
        )
    if key_limit.state is KeyLimitState.EXHAUSTED:
        return (
            tr("key.exhausted_short"),
            ft.Colors.AMBER_300,
            False,
            True,
        )
    if key_limit.state is KeyLimitState.UNKNOWN:
        return (
            tr("key.limit_unknown_short"),
            ft.Colors.AMBER_300,
            False,
            True,
        )
    if key_limit.state is KeyLimitState.NOT_SET:
        return (
            tr("key.unlimited_short"),
            SUCCESS_COLOR,
            False,
            True,
        )
    return (
        tr("key.valid"),
        SUCCESS_COLOR,
        False,
        True,
    )
