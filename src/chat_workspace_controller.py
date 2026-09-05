"""Flet-координация активного чата поверх независимого interaction-ядра."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import flet as ft

from chat.accounting import ChatLimitConfiguration, parse_chat_limit_input
from chat.drafts import (
    DRAFT_STORAGE_MESSAGE,
    ChatDraft,
    ChatDraftService,
    DraftStorageError,
)
from chat.errors import ChatErrorType
from chat.models import ChatMode
from chat.sending import MessageSendPreview, SendMessageResult
from chat_interaction_controller import (
    ActiveChatState,
    ChatInteractionController,
    InteractionOutcome,
)
from ui import (
    ChatLimitsDialog,
    ChatWorkspaceView,
    build_cost_increase_dialog,
    build_paid_request_dialog,
    build_price_reconfirmation_dialog,
    build_release_unknown_dialog,
)

RefreshCallback = Callable[[bool], Awaitable[None]]
StateCallback = Callable[[ActiveChatState | None], None]


@dataclass(frozen=True)
class _PendingSend:
    chat_id: str
    text: str = field(repr=False)
    turn_id: str | None = None
    draft: ChatDraft | None = None


class ChatWorkspaceController:
    """Управляет только взаимодействием внутри выбранного чата."""

    def __init__(
        self,
        page: ft.Page,
        interaction: ChatInteractionController,
        drafts: ChatDraftService,
        *,
        refresh_workspace: RefreshCallback,
        on_state_changed: StateCallback,
    ) -> None:
        self._page = page
        self._interaction = interaction
        self._drafts = drafts
        self._refresh_workspace = refresh_workspace
        self._on_state_changed = on_state_changed
        self._view: ChatWorkspaceView | None = None
        self._state: ActiveChatState | None = None
        self._limits_dialog: ChatLimitsDialog | None = None
        self._pending_limit_configuration: ChatLimitConfiguration | None = None
        self._limits_chat_id: str | None = None
        self._pending_send: _PendingSend | None = None
        self._pending_preview: MessageSendPreview | None = None
        self._unknown_turn_id: str | None = None
        self._generation = 0
        self._session_generation = 0
        self._active = False

    @property
    def busy(self) -> bool:
        return self._interaction.busy

    @property
    def state(self) -> ActiveChatState | None:
        return self._state

    @property
    def pending_preview(self) -> MessageSendPreview | None:
        return self._pending_preview

    def activate(self) -> None:
        self._generation += 1
        self._session_generation += 1
        self._active = True
        self._view = None
        self._set_state(None)

    def deactivate(self) -> None:
        self._generation += 1
        self._session_generation += 1
        self._active = False
        self.dismiss_dialogs()
        self._pending_send = None
        self._view = None
        self._set_state(None)

    def bind(
        self,
        view: ChatWorkspaceView,
        state: ActiveChatState | None,
    ) -> None:
        previous_id = self._state.chat.id if self._state is not None else None
        current_id = state.chat.id if state is not None else None
        if previous_id != current_id:
            self._generation += 1
        self._view = view
        self._set_state(state)
        if state is not None:
            view.restore_editor(self._drafts.current(state.chat.id).text)
            if self._drafts.failed(state.chat.id):
                view.show_message(DRAFT_STORAGE_MESSAGE)

    async def update_draft(self, chat_id: str, text: str) -> None:
        if (
            not self._active
            or self._view is None
            or self._state is None
            or self._state.chat.id != chat_id
            or not isinstance(text, str)
        ):
            return
        session = self._session_generation
        self._drafts.record_edit(chat_id, text)
        try:
            await self._drafts.flush(chat_id)
        except DraftStorageError:
            if (
                self._active
                and session == self._session_generation
                and self._state is not None
                and self._state.chat.id == chat_id
            ):
                self._show_message(DRAFT_STORAGE_MESSAGE)

    async def flush_editor(self) -> bool:
        """Capture current control state before navigation; never drop failed writes."""
        state = self._state
        view = self._view
        if not self._active or state is None or view is None:
            return True
        session = self._session_generation
        self._drafts.record_edit(state.chat.id, view.editor_value)
        try:
            await self._drafts.flush(state.chat.id)
        except DraftStorageError:
            if self._active and session == self._session_generation:
                self._show_message(DRAFT_STORAGE_MESSAGE)
            return False
        return self._active and session == self._session_generation

    def unbind(self) -> None:
        self._view = None

    def has_dialog(self) -> bool:
        return any(
            (
                self._limits_dialog is not None,
                self._pending_limit_configuration is not None,
                self._pending_preview is not None,
                self._unknown_turn_id is not None,
            )
        )

    def cancel_confirmation_for_navigation(self) -> None:
        if self._pending_preview is not None and not self._interaction.busy:
            self.cancel_pending_send()

    def begin_navigation(self, chat_id: str) -> None:
        if not _is_identifier(chat_id):
            return
        if self._state is not None and self._state.chat.id != chat_id:
            self._generation += 1

    async def request_configure_limits(self, chat_id: str) -> None:
        if not _is_identifier(chat_id):
            self._show_message("Некорректный идентификатор чата")
            return
        await self._open_limits_dialog(chat_id)

    async def request_edit_limits(self, chat_id: str) -> None:
        if not _is_identifier(chat_id):
            self._show_message("Некорректный идентификатор чата")
            return
        await self._open_limits_dialog(chat_id)

    async def _open_limits_dialog(self, chat_id: str) -> None:
        if (
            not self._active
            or self._interaction.busy
            or self._limits_dialog is not None
            or self.has_dialog()
        ):
            return
        try:
            state = await self._interaction.load_state(chat_id)
        except Exception:
            self._show_message("Не удалось загрузить лимиты чата")
            return
        if self._state is None or self._state.chat.id != chat_id:
            return
        self._set_state(state)
        self._limits_chat_id = chat_id
        self._limits_dialog = ChatLimitsDialog(
            state.chat,
            state.budget,
            self.submit_existing_chat_limits,
            self.cancel_limits_dialog,
        )
        self._page.show_dialog(self._limits_dialog.control)

    async def submit_existing_chat_limits(
        self,
        token_limit: str,
        max_completion_tokens: str,
        cost_limit_usd: str | None,
    ) -> None:
        dialog = self._limits_dialog
        state = self._state
        chat_id = self._limits_chat_id
        if (
            dialog is None
            or state is None
            or chat_id is None
            or state.chat.id != chat_id
            or self._interaction.busy
        ):
            return
        try:
            configuration = parse_chat_limit_input(
                state.chat.mode,
                token_limit,
                max_completion_tokens,
                cost_limit_usd,
            )
        except ValueError as error:
            dialog.form.show_error(str(error))
            self._page.update()
            return
        if (
            state.chat.mode is ChatMode.PAID
            and state.budget.limits_configured
            and state.budget.cost_limit_usd is not None
            and configuration.cost_limit_usd > state.budget.cost_limit_usd
        ):
            self._pending_limit_configuration = configuration
            dialog.form.set_busy(True)
            self._page.show_dialog(
                build_cost_increase_dialog(
                    state.budget.cost_limit_usd,
                    configuration.cost_limit_usd,
                    self.confirm_cost_increase,
                    self.cancel_cost_increase,
                )
            )
            return
        await self._save_existing_limits(
            configuration,
            cost_increase_confirmed=(
                state.chat.mode is ChatMode.PAID and not state.budget.limits_configured
            ),
        )

    async def confirm_cost_increase(self) -> None:
        configuration = self._pending_limit_configuration
        if configuration is None:
            return
        self._pending_limit_configuration = None
        self._page.pop_dialog()
        await self._save_existing_limits(
            configuration,
            cost_increase_confirmed=True,
        )

    def cancel_cost_increase(self) -> None:
        if self._pending_limit_configuration is None:
            return
        self._pending_limit_configuration = None
        self._page.pop_dialog()
        if self._limits_dialog is not None:
            self._limits_dialog.form.set_busy(False)
            self._page.update()

    async def _save_existing_limits(
        self,
        configuration: ChatLimitConfiguration,
        *,
        cost_increase_confirmed: bool,
    ) -> None:
        dialog = self._limits_dialog
        chat_id = self._limits_chat_id
        if dialog is None or chat_id is None:
            return
        dialog.form.set_busy(True)
        dialog.form.show_error("")
        self._page.update()
        try:
            state = await self._interaction.save_limits(
                chat_id,
                configuration,
                cost_increase_confirmed=cost_increase_confirmed,
            )
        except Exception as error:
            if self._limits_dialog is dialog:
                dialog.form.set_busy(False)
                dialog.form.show_error(_safe_local_error(error))
                self._page.update()
            return
        self._set_state(state)
        if self._limits_dialog is dialog:
            self._limits_dialog = None
            self._limits_chat_id = None
            self._page.pop_dialog()
        await self._refresh_workspace(False)

    def cancel_limits_dialog(self) -> None:
        if self._limits_dialog is None:
            return
        self._limits_dialog = None
        self._limits_chat_id = None
        self._pending_limit_configuration = None
        self._page.pop_dialog()

    async def submit_message(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            self._show_message("Введите непустое текстовое сообщение")
            return
        state = self._state
        view = self._view
        if (
            not self._active
            or state is None
            or view is None
            or self._pending_send is not None
            or self._interaction.busy
        ):
            return
        snapshot = self._drafts.record_edit(state.chat.id, text)
        pending = _PendingSend(state.chat.id, text, draft=snapshot)
        self._pending_send = pending
        view.set_sending(True)
        view.show_message("")
        self._page.update()
        try:
            await self._drafts.flush(state.chat.id)
        except DraftStorageError:
            if self._pending_send is pending:
                self._finish_pending_with_message(DRAFT_STORAGE_MESSAGE)
            return
        if not self._active or self._pending_send is not pending:
            return
        if state.chat.mode is ChatMode.PAID:
            preview = await self._interaction.preview_message(state.chat.id, text)
            if self._pending_send is not pending:
                return
            if not preview.allowed:
                await self._handle_preview_failure(preview)
                return
            self._pending_preview = preview
            self._page.show_dialog(
                build_paid_request_dialog(
                    preview,
                    self.confirm_paid_request,
                    self.cancel_pending_send,
                )
            )
            return
        await self._execute_send(pending, paid_confirmed=False)

    async def request_retry_turn(self, turn_id: str) -> None:
        if not _is_identifier(turn_id):
            self._show_message("Некорректный идентификатор попытки")
            return
        state = self._state
        view = self._view
        if (
            state is None
            or view is None
            or self._pending_send is not None
            or self._interaction.busy
        ):
            return
        pending = _PendingSend(state.chat.id, "", turn_id=turn_id)
        self._pending_send = pending
        view.set_sending(True)
        view.show_message("")
        self._page.update()
        preview = await self._interaction.preview_retry(turn_id)
        if self._pending_send is not pending:
            return
        if not preview.allowed:
            await self._handle_preview_failure(preview)
            return
        if state.chat.mode is ChatMode.PAID:
            self._pending_preview = preview
            self._page.show_dialog(
                build_paid_request_dialog(
                    preview,
                    self.confirm_paid_request,
                    self.cancel_pending_send,
                )
            )
            return
        await self._execute_retry(pending, paid_confirmed=False)

    async def confirm_paid_request(self) -> None:
        pending = self._pending_send
        preview = self._pending_preview
        if pending is None or preview is None or not preview.allowed:
            return
        self._pending_preview = None
        self._page.pop_dialog()
        if pending.turn_id is None:
            await self._execute_send(pending, paid_confirmed=True)
        else:
            await self._execute_retry(pending, paid_confirmed=True)

    def cancel_pending_send(self) -> None:
        if self._pending_send is None:
            return
        self._pending_send = None
        self._pending_preview = None
        self._page.pop_dialog()
        if self._view is not None:
            self._view.set_sending(False)
            self._page.update()

    async def _handle_preview_failure(self, preview: MessageSendPreview) -> None:
        self._pending_preview = preview
        if (
            preview.error_type is ChatErrorType.PRICE_RECONFIRMATION_REQUIRED
            and preview.price_change is not None
        ):
            self._page.show_dialog(
                build_price_reconfirmation_dialog(
                    preview.price_change,
                    self.confirm_price_change,
                    self.cancel_pending_send,
                )
            )
            return
        self._pending_send = None
        self._pending_preview = None
        await self._refresh_workspace(False)
        if self._view is not None:
            self._view.set_sending(False)
            self._view.show_message(_preview_message(preview))
            self._page.update()

    async def confirm_price_change(self) -> None:
        pending = self._pending_send
        if pending is None:
            return
        self._page.pop_dialog()
        self._pending_preview = None
        try:
            await self._interaction.reconfirm_price(pending.chat_id, confirmed=True)
            preview = (
                await self._interaction.preview_message(pending.chat_id, pending.text)
                if pending.turn_id is None
                else await self._interaction.preview_retry(pending.turn_id)
            )
        except Exception as error:
            self._finish_pending_with_message(_safe_local_error(error))
            return
        if self._pending_send is not pending:
            return
        if not preview.allowed:
            await self._handle_preview_failure(preview)
            return
        self._pending_preview = preview
        self._page.show_dialog(
            build_paid_request_dialog(
                preview,
                self.confirm_paid_request,
                self.cancel_pending_send,
            )
        )

    async def _execute_send(
        self,
        pending: _PendingSend,
        *,
        paid_confirmed: bool,
    ) -> None:
        generation = self._generation
        session = self._session_generation

        async def on_reserved(_turn_id: str) -> None:
            if not self._active or session != self._session_generation:
                return
            assert pending.draft is not None
            was_current = self._drafts.current(pending.chat_id) == pending.draft
            self._drafts.acknowledge_reserved(pending.draft)
            view = self._view
            if (
                view is None
                or self._pending_send is not pending
                or generation != self._generation
                or self._state is None
                or self._state.chat.id != pending.chat_id
            ):
                return
            if was_current:
                view.clear_editor_if_matches(pending.text)
            await self._refresh_workspace(True)

        outcome = await self._interaction.send_message(
            pending.chat_id,
            pending.text,
            paid_confirmed=paid_confirmed,
            on_reserved=on_reserved,
            draft_revision=pending.draft.revision
            if pending.draft is not None
            else None,
        )
        if session != self._session_generation:
            return
        await self._finish_send(pending, outcome, generation)

    async def _execute_retry(
        self,
        pending: _PendingSend,
        *,
        paid_confirmed: bool,
    ) -> None:
        assert pending.turn_id is not None
        generation = self._generation
        session = self._session_generation

        async def on_reserved(_turn_id: str) -> None:
            if (
                self._pending_send is pending
                and generation == self._generation
                and self._state is not None
                and self._state.chat.id == pending.chat_id
            ):
                await self._refresh_workspace(True)

        outcome = await self._interaction.retry_turn(
            pending.chat_id,
            pending.turn_id,
            paid_confirmed=paid_confirmed,
            on_reserved=on_reserved,
        )
        if session != self._session_generation:
            return
        await self._finish_send(pending, outcome, generation)

    async def _finish_send(
        self,
        pending: _PendingSend,
        outcome: InteractionOutcome,
        generation: int,
    ) -> None:
        if not self._active:
            return
        if generation != self._generation:
            if self._pending_send is pending:
                self._pending_send = None
                self._pending_preview = None
            if not self._interaction.busy:
                await self._refresh_workspace(False)
            return
        if not outcome.applied:
            if self._pending_send is pending:
                self._pending_send = None
                self._pending_preview = None
            await self._refresh_workspace(False)
            return
        if (
            outcome.result.error_type is ChatErrorType.PRICE_RECONFIRMATION_REQUIRED
            and outcome.result.price_change is not None
        ):
            self._set_state(outcome.state)
            self._pending_send = pending
            self._pending_preview = _price_preview_from_result(
                pending,
                outcome.result,
            )
            self._page.show_dialog(
                build_price_reconfirmation_dialog(
                    outcome.result.price_change,
                    self.confirm_price_change,
                    self.cancel_pending_send,
                )
            )
            return
        if self._pending_send is pending:
            self._pending_send = None
            self._pending_preview = None
        self._set_state(outcome.state)
        await self._refresh_workspace(outcome.result.turn_id is not None)
        if self._view is not None and not outcome.result.successful:
            self._view.show_message(_result_message(outcome.result))
            self._page.update()
        elif self._view is not None and outcome.result.truncated:
            self._view.show_message(
                "Ответ сохранён, но завершён по ограничению длины.",
                error=False,
            )
            self._page.update()

    async def request_release_unknown(self, turn_id: str) -> None:
        if not _is_identifier(turn_id):
            self._show_message("Некорректный идентификатор попытки")
            return
        state = self._state
        if (
            state is None
            or self._interaction.busy
            or self._unknown_turn_id is not None
            or self.has_dialog()
        ):
            return
        turn = next((item for item in state.turns if item.id == turn_id), None)
        if turn is None:
            return
        self._unknown_turn_id = turn_id
        self._page.show_dialog(
            build_release_unknown_dialog(
                turn,
                self.confirm_release_unknown,
                self.cancel_release_unknown,
            )
        )

    async def confirm_release_unknown(self) -> None:
        turn_id = self._unknown_turn_id
        state = self._state
        if turn_id is None or state is None:
            return
        self._unknown_turn_id = None
        self._page.pop_dialog()
        try:
            updated = await self._interaction.release_unknown(
                state.chat.id,
                turn_id,
                confirmed=True,
            )
        except Exception as error:
            self._show_message(_safe_local_error(error))
            return
        self._set_state(updated)
        await self._refresh_workspace(False)

    def cancel_release_unknown(self) -> None:
        if self._unknown_turn_id is None:
            return
        self._unknown_turn_id = None
        self._page.pop_dialog()

    def dismiss_dialogs(self) -> None:
        dialog_count = sum(
            (
                self._limits_dialog is not None,
                self._pending_limit_configuration is not None,
                self._pending_preview is not None,
                self._unknown_turn_id is not None,
            )
        )
        for _ in range(dialog_count):
            self._page.pop_dialog()
        self._limits_dialog = None
        self._limits_chat_id = None
        self._pending_limit_configuration = None
        self._pending_preview = None
        self._unknown_turn_id = None

    def _finish_pending_with_message(self, message: str) -> None:
        self._pending_send = None
        self._pending_preview = None
        if self._view is not None:
            self._view.set_sending(False)
            self._view.show_message(message)
            self._page.update()

    def _show_message(self, message: str) -> None:
        if self._view is not None:
            self._view.show_message(message)
            self._page.update()

    def _set_state(self, state: ActiveChatState | None) -> None:
        self._state = state
        self._on_state_changed(state)


def _preview_message(preview: MessageSendPreview) -> str:
    message = preview.safe_message or "Запрос не может быть подготовлен."
    if preview.error_type in {
        ChatErrorType.CONTEXT_LENGTH_EXCEEDED,
        ChatErrorType.TOKEN_LIMIT_EXCEEDED,
    }:
        return message + " Создайте новый чат или увеличьте допустимый лимит."
    return message


def _price_preview_from_result(
    pending: _PendingSend,
    result: SendMessageResult,
) -> MessageSendPreview:
    return MessageSendPreview(
        chat_id=pending.chat_id,
        turn_id=pending.turn_id,
        model_id=None,
        model_name=None,
        estimated_prompt_tokens=None,
        max_completion_tokens=None,
        reserved_tokens=None,
        reserved_cost_usd=None,
        remaining_tokens_after_reservation=None,
        remaining_cost_after_reservation=None,
        error_type=result.error_type,
        safe_message=result.safe_message,
        price_change=result.price_change,
        key_validity_update=result.key_validity_update,
        key_limit_update=result.key_limit_update,
    )


def _result_message(result: SendMessageResult) -> str:
    message = result.safe_message or "Запрос завершился ошибкой."
    if result.retry_after is not None:
        message += f" Повторите не раньше чем через {result.retry_after} с."
    if result.error_type in {
        ChatErrorType.CONTEXT_LENGTH_EXCEEDED,
        ChatErrorType.TOKEN_LIMIT_EXCEEDED,
    }:
        message += " Создайте новый чат или увеличьте допустимый лимит."
    return message


def _safe_local_error(error: Exception) -> str:
    if isinstance(error, (ValueError, KeyError, RuntimeError)):
        message = str(error).strip("' ")
        if message:
            return message[:240]
    return "Локальную операцию не удалось завершить."


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
