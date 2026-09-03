"""Адаптивный интерфейс списка и активного локального чата."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

import flet as ft

from auth.access import free_mode_allowed, paid_mode_allowed
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.accounting import AccountingStatus, BudgetState, format_decimal_usd
from chat.models import Chat, ChatMode, format_price_per_million
from chat_interaction_controller import ActiveChatState
from ui.message_composer import MessageComposer
from ui.message_history import MessageHistoryView
from ui.styles import (
    ERROR_COLOR,
    MUTED_COLOR,
    PANEL_BACKGROUND,
    SUCCESS_COLOR,
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
    ) -> None:
        self._page = page
        self._chats = chats
        self._selected_chat = selected_chat
        self._interaction_state = interaction_state
        self._on_new_chat = on_new_chat
        self._on_select_chat = on_select_chat
        self._on_rename_chat = on_rename_chat
        self._on_delete_chat = on_delete_chat
        self._on_lock = on_lock
        self._on_send_message = on_send_message
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
        self.retry_key_button: ft.TextButton | None = None
        self.replace_key_button: ft.TextButton | None = None
        self.rename_button: ft.TextButton | None = None
        self.delete_button: ft.TextButton | None = None
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

    def dispose(self) -> None:
        self._page.drawer = None

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
        previous_chat_id = (
            self._selected_chat.id if self._selected_chat is not None else None
        )
        self._chats = chats
        self._selected_chat = selected_chat
        self._interaction_state = interaction_state
        self._key_validity = key_validity
        self._key_limit = key_limit
        self._key_validation_in_progress = key_validation_in_progress
        self._new_chat_allowed = free_mode_allowed(key_validity)
        current_chat_id = selected_chat.id if selected_chat is not None else None
        self._sync_interaction_components(force=previous_chat_id != current_chat_id)
        self._render_layout()

    def set_sending(self, sending: bool) -> None:
        if self.composer is not None:
            self.composer.set_busy(sending)
        for button in (self.rename_button, self.delete_button, self.limits_button):
            if button is not None:
                button.disabled = sending

    def clear_editor_if_matches(self, expected: str) -> None:
        if self.composer is not None:
            self.composer.clear_if_matches(expected)

    def show_message(self, message: str, *, error: bool = True) -> None:
        if self.composer is not None:
            self.composer.show_message(message, error=error)

    async def scroll_messages_to_end(self) -> None:
        if self.message_history is not None:
            await self.message_history.scroll_to_end()

    def _sync_interaction_components(self, *, force: bool) -> None:
        state = self._interaction_state
        if self._selected_chat is None or state is None:
            self.message_history = None
            self.composer = None
            return
        if force or self.message_history is None or self.composer is None:
            self.message_history = MessageHistoryView(
                state.messages,
                state.turns,
                on_retry=self._on_retry_turn,
            )
            self.composer = MessageComposer(
                self._on_send_message,
                enabled=self._sending_allowed(state),
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
        wide = event.width >= WIDE_LAYOUT_BREAKPOINT
        if wide == self._wide:
            return
        self._wide = wide
        self._render_layout()
        self._layout.update()

    def _render_layout(self) -> None:
        if self._wide:
            self._page.drawer = None
            self._layout.content = ft.Row(
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    self._build_chat_panel(width=320),
                    ft.VerticalDivider(width=1),
                    self._build_chat_content(show_menu=False),
                ],
            )
            return
        self._page.drawer = self._build_drawer()
        self._layout.content = self._build_chat_content(show_menu=True)

    def _build_chat_panel(self, *, width: int | None = None) -> ft.Container:
        chat_list = ft.ListView(
            expand=True,
            spacing=6,
            controls=[self._build_chat_tile(chat) for chat in self._chats],
        )
        if not self._chats:
            chat_list.controls.append(
                ft.Text(
                    "Чатов пока нет.",
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
                    ft.Text("Tokenlogue", theme_style=ft.TextThemeStyle.HEADLINE_SMALL),
                    ft.Button(
                        "Новый чат",
                        icon=ft.Icons.ADD,
                        style=primary_button_style(),
                        disabled=not self._new_chat_allowed,
                        on_click=self._handle_new_chat_button,
                    ),
                    ft.Divider(),
                    chat_list,
                    ft.Divider(),
                    ft.TextButton(
                        "Заблокировать приложение",
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
            if not self._wide:
                await self._page.close_drawer()
            await self._on_select_chat(chat.id)

        mode = "Бесплатный" if chat.mode is ChatMode.FREE else "Платный"
        return ft.ListTile(
            title=ft.Text(chat.title, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            subtitle=ft.Text(
                f"{mode} · {chat.requested_model_name}",
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
        header_controls: list[ft.Control] = []
        if show_menu:
            header_controls.append(
                ft.IconButton(
                    icon=ft.Icons.MENU,
                    tooltip="Открыть список чатов",
                    on_click=self._open_drawer,
                )
            )
        header_controls.extend(
            [
                ft.Text(
                    "Tokenlogue",
                    theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.ADD,
                    tooltip="Новый чат",
                    disabled=not self._new_chat_allowed,
                    on_click=self._handle_new_chat_icon,
                ),
                ft.IconButton(
                    icon=ft.Icons.LOCK_OUTLINE,
                    tooltip="Заблокировать приложение",
                    on_click=self._handle_lock_icon,
                ),
            ]
        )
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    content=ft.Row(controls=header_controls),
                ),
                ft.Divider(height=1),
                self._build_key_status_panel(),
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
                        "Чатов пока нет", theme_style=ft.TextThemeStyle.TITLE_LARGE
                    ),
                    ft.Text(
                        "Создайте чат и выберите для него режим, модель и лимиты.",
                        color=MUTED_COLOR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Button(
                        "Новый чат",
                        icon=ft.Icons.ADD,
                        style=primary_button_style(),
                        disabled=not self._new_chat_allowed,
                        on_click=self._handle_new_chat_button,
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
                content=ft.ProgressRing(),
            )

        async def rename_chat(_event: ft.Event[ft.TextButton]) -> None:
            await self._on_rename_chat(chat.id)

        async def delete_chat(_event: ft.Event[ft.TextButton]) -> None:
            await self._on_delete_chat(chat.id)

        mode_is_free = chat.mode is ChatMode.FREE
        mode_label = "Бесплатный режим" if mode_is_free else "Платный режим"
        mode_color = SUCCESS_COLOR if mode_is_free else ft.Colors.AMBER_300
        details: list[ft.Control] = [
            ft.Row(
                wrap=True,
                controls=[
                    ft.Text(chat.title, theme_style=ft.TextThemeStyle.HEADLINE_SMALL),
                    ft.Container(
                        bgcolor=ft.Colors.with_opacity(0.18, mode_color),
                        border_radius=12,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                        content=ft.Text(mode_label, color=mode_color, size=12),
                    ),
                ],
            ),
            ft.Text(chat.requested_model_name, weight=ft.FontWeight.BOLD),
            ft.Text(chat.requested_model_id, color=MUTED_COLOR, selectable=True),
        ]
        if chat.mode is ChatMode.PAID:
            details.append(
                ft.Text(
                    "Вход: "
                    f"${format_price_per_million(chat.prompt_price_per_token)} "
                    "за 1 млн токенов · выход: "
                    f"${format_price_per_million(chat.completion_price_per_token)} "
                    "за 1 млн токенов",
                    size=12,
                )
            )
        self.rename_button = ft.TextButton(
            "Переименовать",
            icon=ft.Icons.EDIT_OUTLINED,
            disabled=state.sending,
            on_click=rename_chat,
        )
        self.delete_button = ft.TextButton(
            "Удалить чат",
            icon=ft.Icons.DELETE_OUTLINE,
            style=ft.ButtonStyle(color=ERROR_COLOR),
            disabled=state.sending,
            on_click=delete_chat,
        )
        details.append(
            ft.Row(wrap=True, controls=[self.rename_button, self.delete_button])
        )
        assert self.message_history is not None
        controls: list[ft.Control] = [
            ft.Container(
                padding=ft.Padding(16, 12, 16, 4),
                content=ft.Column(controls=details),
            ),
            self._build_budget_panel(state),
        ]
        unknown_panel = self._build_unknown_panel(state)
        if unknown_panel is not None:
            controls.append(unknown_panel)
        controls.append(self.message_history.control)
        if state.budget.limits_configured:
            assert self.composer is not None
            controls.append(self.composer.control)
        controls.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                content=_history_warning(),
            )
        )
        return ft.Column(expand=True, spacing=8, controls=controls)

    def _build_budget_panel(self, state: ActiveChatState) -> ft.Control:
        budget = state.budget
        if not budget.limits_configured:

            async def configure(_event: ft.Event[ft.Button]) -> None:
                await self._on_configure_limits(state.chat.id)

            self.limits_button = ft.Button(
                "Настроить лимиты",
                icon=ft.Icons.TUNE,
                disabled=state.sending,
                on_click=configure,
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
                            "Чат доступен для чтения. Перед отправкой настройте лимиты.",
                            color=ft.Colors.AMBER_300,
                        ),
                        self.limits_button,
                    ],
                ),
            )

        async def edit(_event: ft.Event[ft.TextButton]) -> None:
            await self._on_edit_limits(state.chat.id)

        self.limits_button = ft.TextButton(
            "Изменить лимиты",
            icon=ft.Icons.TUNE,
            disabled=state.sending,
            on_click=edit,
        )
        remaining_tokens = state.remaining.tokens
        lines = [
            f"Использовано токенов: {budget.total_tokens_used}",
            f"Зарезервировано токенов: {budget.reserved_tokens}",
            "Осталось токенов: "
            f"{remaining_tokens if remaining_tokens is not None else '—'}",
            f"Максимум следующего ответа: {budget.max_completion_tokens or '—'}",
        ]
        if state.chat.mode is ChatMode.PAID:
            remaining_cost = state.remaining.cost_usd or Decimal("0")
            lines.extend(
                [
                    f"Фактическая стоимость: ${format_decimal_usd(budget.cost_used_usd)}",
                    "Зарезервированная стоимость: $"
                    f"{format_decimal_usd(budget.cost_reserved_usd)}",
                    f"Остаток денежного бюджета: ${format_decimal_usd(remaining_cost)}",
                ]
            )
        return ft.Container(
            margin=ft.Margin.symmetric(horizontal=12),
            padding=12,
            bgcolor=PANEL_BACKGROUND,
            border_radius=12,
            content=ft.Column(
                tight=True,
                controls=[ft.Text(" · ".join(lines), size=12), self.limits_button],
            ),
        )

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

        async def release(_event: ft.Event[ft.Button]) -> None:
            await self._on_release_unknown(unknown_turn.id)

        self.release_unknown_button = ft.Button(
            "Освободить неизвестный резерв",
            icon=ft.Icons.WARNING_AMBER,
            disabled=state.sending,
            on_click=release,
        )
        cost_text = (
            ""
            if state.chat.mode is ChatMode.FREE
            else " и $" + format_decimal_usd(state.budget.cost_reserved_usd)
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
                        "Результат предыдущего запроса неизвестен. Сохранён защитный "
                        f"резерв {state.budget.reserved_tokens} токенов{cost_text}; это "
                        "не фактический расход.",
                        color=ft.Colors.AMBER_300,
                    ),
                    self.release_unknown_button,
                ],
            ),
        )

    def _build_key_status_panel(self) -> ft.Control:
        message, color, can_retry, can_replace = _key_status_presentation(
            self._key_validity,
            self._key_limit,
        )
        actions: list[ft.Control] = []
        if can_retry:
            self.retry_key_button = ft.TextButton(
                "Повторить проверку ключа",
                icon=ft.Icons.REFRESH,
                disabled=self._key_validation_in_progress,
                on_click=self._handle_retry_key,
            )
            actions.append(self.retry_key_button)
        else:
            self.retry_key_button = None
        if can_replace:
            self.replace_key_button = ft.TextButton(
                "Заменить ключ",
                icon=ft.Icons.KEY,
                on_click=self._handle_replace_key,
            )
            actions.append(self.replace_key_button)
        else:
            self.replace_key_button = None
        content: list[ft.Control] = [ft.Text(message, color=color)]
        if self._key_validation_in_progress:
            content.append(
                ft.Row(
                    controls=[
                        ft.ProgressRing(width=18, height=18, stroke_width=2),
                        ft.Text("Проверка ключа OpenRouter…", color=MUTED_COLOR),
                    ]
                )
            )
        if actions:
            content.append(ft.Row(wrap=True, controls=actions))
        return ft.Container(
            margin=ft.Margin.symmetric(horizontal=12, vertical=8),
            padding=12,
            bgcolor=ft.Colors.with_opacity(0.12, color),
            border_radius=12,
            content=ft.Column(tight=True, controls=content),
        )

    async def _handle_new_chat_button(self, _event: ft.Event[ft.Button]) -> None:
        await self._on_new_chat()

    async def _handle_new_chat_icon(self, _event: ft.Event[ft.IconButton]) -> None:
        await self._on_new_chat()

    async def _handle_lock_text(self, _event: ft.Event[ft.TextButton]) -> None:
        await self._on_lock()

    async def _handle_lock_icon(self, _event: ft.Event[ft.IconButton]) -> None:
        await self._on_lock()

    async def _handle_retry_key(self, _event: ft.Event[ft.TextButton]) -> None:
        await self._on_retry_key()

    async def _handle_replace_key(self, _event: ft.Event[ft.TextButton]) -> None:
        await self._on_replace_key()

    async def _open_drawer(self, _event: ft.Event[ft.IconButton]) -> None:
        await self._page.show_drawer()


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

        self.title_field = ft.TextField(
            value=chat.title,
            label="Название чата",
            max_length=120,
            autofocus=True,
            on_submit=self._handle_submit,
        )
        self.confirm_button = ft.Button("Сохранить", on_click=self._handle_click)
        self.control = ft.AlertDialog(
            modal=True,
            title=ft.Text("Переименовать чат"),
            content=self.title_field,
            actions=[
                ft.TextButton("Отмена", on_click=handle_cancel),
                self.confirm_button,
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    async def _handle_click(self, _event: ft.Event[ft.Button]) -> None:
        await self._submit_title()

    async def _handle_submit(self, _event: ft.Event[ft.TextField]) -> None:
        await self._submit_title()

    async def _submit_title(self) -> None:
        if self.confirm_button.disabled:
            return
        title = self.title_field.value
        if not isinstance(title, str):
            self.show_error("Название чата должно быть текстом")
            return
        await self._on_confirm(self._chat_id, title)

    def set_busy(self, busy: bool) -> None:
        self.title_field.disabled = busy
        self.confirm_button.disabled = busy

    def show_error(self, message: str) -> None:
        self.title_field.error = message


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
        title=ft.Text("Удалить чат?"),
        content=ft.Text(
            f"Чат «{chat.title}» и его локальная история будут удалены безвозвратно."
        ),
        actions=[
            ft.TextButton("Отмена", on_click=cancel),
            ft.Button(
                "Удалить",
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
        "История сохраняется локально на устройстве. "
        "Не отправляйте конфиденциальные данные.",
        color=MUTED_COLOR,
        size=12,
        text_align=ft.TextAlign.CENTER,
    )


def _key_status_presentation(
    key_validity: KeyValidityState,
    key_limit: KeyLimitInfo,
) -> tuple[str, str, bool, bool]:
    if key_validity is KeyValidityState.INVALID:
        return (
            "Сохранённый ключ OpenRouter недействителен или отозван. "
            "Замените ключ, чтобы продолжить работу с моделями",
            ERROR_COLOR,
            True,
            True,
        )
    if key_validity is KeyValidityState.RESTRICTED:
        return (
            "OpenRouter отклонил проверку разрешений ключа. "
            "Бесплатный запрос также может завершиться ошибкой",
            ft.Colors.AMBER_300,
            True,
            False,
        )
    if key_validity is KeyValidityState.UNKNOWN:
        return (
            "Состояние ключа OpenRouter пока неизвестно. Локальная история и "
            "бесплатный режим доступны; платный режим временно закрыт.",
            ft.Colors.AMBER_300,
            True,
            False,
        )
    if key_limit.state is KeyLimitState.EXHAUSTED:
        return (
            "Расходный лимит этого ключа исчерпан. "
            "Бесплатный режим остаётся доступным.",
            ft.Colors.AMBER_300,
            False,
            False,
        )
    if key_limit.state is KeyLimitState.NOT_SET:
        return (
            "Ключ OpenRouter действителен. Отдельный расходный лимит не установлен.",
            SUCCESS_COLOR,
            False,
            False,
        )
    return (
        "Ключ OpenRouter действителен.",
        SUCCESS_COLOR,
        False,
        False,
    )
