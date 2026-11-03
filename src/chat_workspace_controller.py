"""Flet-координация активного чата поверх независимого interaction-ядра."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

import flet as ft

from auth.models import KeyLimitInfo
from chat.accounting import (
    ChatLimitConfiguration,
    ModelPriceChange,
    TurnStatus,
    parse_chat_limit_input,
)
from chat.context import PreparedHistory, prepare_history
from chat.drafts import (
    DRAFT_STORAGE_MESSAGE,
    ChatDraft,
    ChatDraftService,
    DraftStorageError,
)
from chat.errors import ChatErrorType
from chat.estimates import DraftEstimate, PreparedEstimateSnapshot
from chat.live_estimate import EstimateRevision, LiveEstimateWorker
from chat.metrics import build_chat_metrics
from chat.models import FREE_ROUTER_MODEL, CatalogModel, ChatMode, Message
from chat.paid_consent import PaidConsent
from chat.sending import MessageSendPreview, SendMessageResult
from chat_interaction_controller import (
    ActiveChatState,
    ChatInteractionController,
    InteractionOutcome,
)
from i18n import tr
from service_errors import localized_error_text
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
    paid_consent: PaidConsent | None = None


@dataclass(frozen=True)
class _WorkspaceOperation:
    session: int
    generation: int
    chat_id: str


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
        self._paid_setting_writes: dict[tuple[int, str], int] = {}
        self._estimate_model: CatalogModel | None = None
        self._estimate_key_limit = KeyLimitInfo.unknown()
        self._metadata_updated_at: datetime | None = None
        self._estimate_history_messages: tuple[Message, ...] | None = None
        self._estimate_history: PreparedHistory | None = None
        self._estimate_snapshot: PreparedEstimateSnapshot | None = None
        self._estimate_context_revision = 0
        self._estimate_view_revision = 0
        self._estimate_worker = LiveEstimateWorker(
            self._estimate_is_current, self._publish_estimate
        )

    @property
    def busy(self) -> bool:
        return self._interaction.busy or any(
            session == self._session_generation and count > 0
            for (session, _chat), count in self._paid_setting_writes.items()
        )

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
            self._clear_estimate_context()
        if self._view is not view:
            self._estimate_view_revision += 1
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
        draft = self._drafts.record_edit(chat_id, text)
        # Schedule from the accepted revision before the first SQLite await.
        self._request_estimate(draft)
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

    def capture_editor(self) -> None:
        """Сохраняет последнюю правку в памяти до отзыва доступа к workspace."""
        if self._active and self._state is not None and self._view is not None:
            self._drafts.record_edit(self._state.chat.id, self._view.editor_value)

    async def flush_editor(self) -> bool:
        """Сохраняет редактор перед переходом, не отбрасывая неудачные записи."""
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
        self._clear_estimate_context()
        self._view = None

    def set_estimate_metadata(
        self,
        model: CatalogModel | None,
        key_limit: KeyLimitInfo,
        metadata_updated_at: datetime | None,
    ) -> None:
        """Accept only the current session's already authorized metadata cache."""
        if not self._active or self._state is None or self._view is None:
            return
        self._estimate_model = model
        self._estimate_key_limit = key_limit
        self._metadata_updated_at = metadata_updated_at
        self._refresh_local_estimate()

    async def wait_estimate_idle(self) -> None:
        """Drain the bounded pure worker without opening storage or transport."""
        await self._estimate_worker.wait_idle()

    def _clear_estimate_context(self) -> None:
        self._estimate_context_revision += 1
        self._estimate_worker.invalidate()
        self._estimate_snapshot = None
        self._estimate_history = None
        self._estimate_history_messages = None
        self._estimate_model = None
        self._estimate_key_limit = KeyLimitInfo.unknown()
        self._metadata_updated_at = None

    def _refresh_local_estimate(self) -> None:
        state, view = self._state, self._view
        if not self._active or state is None or view is None:
            self._clear_estimate_context()
            return
        view.set_metrics(
            build_chat_metrics(
                state.chat,
                state.budget,
                state.last_request,
                pending=state.sending
                or any(turn.status is TurnStatus.PENDING for turn in state.turns),
                key_limit=self._estimate_key_limit,
                metadata_updated_at=self._metadata_updated_at,
            )
        )
        if (
            self._estimate_history is None
            or state.messages != self._estimate_history_messages
        ):
            self._estimate_history = prepare_history(state.messages)
            self._estimate_history_messages = state.messages
        model = self._estimate_model
        if state.chat.requested_model_id == FREE_ROUTER_MODEL.id:
            model = FREE_ROUTER_MODEL
        elif model is not None and model.id != state.chat.requested_model_id:
            model = None
        self._estimate_context_revision += 1
        self._estimate_snapshot = PreparedEstimateSnapshot(
            state.chat,
            state.budget,
            model,
            self._estimate_history,
            self._estimate_key_limit,
        )
        self._request_estimate(self._drafts.current(state.chat.id))

    def _request_estimate(self, draft: ChatDraft) -> None:
        if (
            not self._active
            or self._state is None
            or self._view is None
            or self._estimate_snapshot is None
            or draft.chat_id != self._state.chat.id
        ):
            return
        revision = EstimateRevision(
            self._session_generation,
            self._generation,
            self._estimate_view_revision,
            self._estimate_context_revision,
            draft.chat_id,
            draft.revision,
        )
        self._estimate_worker.submit(revision, self._estimate_snapshot, draft.text)

    def _estimate_is_current(self, revision: EstimateRevision) -> bool:
        matches = (
            self._active
            and self._view is not None
            and self._state is not None
            and revision.session == self._session_generation
            and revision.workspace == self._generation
            and revision.view == self._estimate_view_revision
            and revision.context == self._estimate_context_revision
            and revision.chat_id == self._state.chat.id
        )
        if not matches:
            return False
        try:
            return revision.draft == self._drafts.current(revision.chat_id).revision
        except Exception:
            # Access may already have been revoked before the UI closes.
            return False

    def _publish_estimate(
        self, revision: EstimateRevision, estimate: DraftEstimate
    ) -> None:
        if self._estimate_is_current(revision) and self._view is not None:
            self._view.set_estimate(estimate)

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
            self._estimate_worker.invalidate()

    async def set_paid_without_confirmation(self, chat_id: str, enabled: bool) -> None:
        if not _is_identifier(chat_id) or type(enabled) is not bool:
            return
        key = (self._session_generation, chat_id)
        self._paid_setting_writes[key] = self._paid_setting_writes.get(key, 0) + 1
        try:
            await self._save_paid_without_confirmation(chat_id, enabled)
        finally:
            count = self._paid_setting_writes[key] - 1
            if count:
                self._paid_setting_writes[key] = count
            else:
                self._paid_setting_writes.pop(key)

    async def _save_paid_without_confirmation(
        self, chat_id: str, enabled: bool
    ) -> None:
        state = self._state
        if (
            not self._active
            or state is None
            or self._view is None
            or state.chat.id != chat_id
            or state.chat.mode is not ChatMode.PAID
            or type(enabled) is not bool
        ):
            return
        self.capture_editor()
        self.cancel_pending_send()
        self._generation += 1
        operation = self._capture_operation(chat_id)
        if operation is None:
            return
        failed = False
        try:
            updated = await self._interaction.save_paid_without_confirmation(
                chat_id, enabled
            )
        except Exception:
            failed = True
            try:
                updated = await self._interaction.load_state(chat_id)
            except Exception:
                if self._operation_matches(operation):
                    self._show_message(tr("service.paid_setting_save_failed"))
                return
        if not self._operation_matches(operation):
            return
        self._set_state(updated)
        await self._refresh_workspace(False)
        if failed and self._operation_matches(operation):
            self._show_message(tr("service.paid_setting_save_failed"))

    async def request_configure_limits(self, chat_id: str) -> None:
        if not _is_identifier(chat_id):
            self._show_message(tr("service.chat_id_invalid"))
            return
        await self._open_limits_dialog(chat_id)

    async def request_edit_limits(self, chat_id: str) -> None:
        if not _is_identifier(chat_id):
            self._show_message(tr("service.chat_id_invalid"))
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
        operation = self._capture_operation(chat_id)
        view = self._view
        if operation is None:
            return

        def can_open() -> bool:
            return (
                self._operation_matches(operation)
                and self._view is view
                and not self._interaction.busy
                and not self.has_dialog()
            )

        try:
            state = await self._interaction.load_state(chat_id)
        except Exception:
            if can_open():
                self._show_message(tr("service.limits_load_failed"))
            return
        if not can_open():
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
            dialog.form.show_error(localized_error_text(error))
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
        operation = self._capture_operation(chat_id)
        if operation is None:
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
            if self._operation_matches(operation) and self._limits_dialog is dialog:
                dialog.form.set_busy(False)
                dialog.form.show_error(_safe_local_error(error))
                self._page.update()
            return
        if not self._operation_matches(operation) or self._limits_dialog is not dialog:
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
            self._show_message(tr("service.message_empty"))
            return
        state = self._state
        view = self._view
        if (
            not self._active
            or state is None
            or view is None
            or self._pending_send is not None
            or self._interaction.busy
            or self._paid_setting_writes.get(
                (self._session_generation, state.chat.id), 0
            )
        ):
            return
        operation = self._capture_operation(state.chat.id)
        if operation is None:
            return
        snapshot = self._drafts.record_edit(state.chat.id, text)
        pending = _PendingSend(
            state.chat.id,
            text,
            draft=snapshot,
            paid_consent=self._interaction.paid_consent(state.chat),
        )
        self._pending_send = pending
        view.set_sending(True)
        view.show_message("")
        self._page.update()
        try:
            await self._drafts.flush(state.chat.id)
        except DraftStorageError:
            if await self._pending_operation_is_current(pending, operation):
                self._finish_pending_with_message(DRAFT_STORAGE_MESSAGE)
            return
        if not await self._pending_operation_is_current(pending, operation):
            return
        if state.chat.mode is ChatMode.PAID and pending.paid_consent is None:
            try:
                preview = await self._interaction.preview_message(state.chat.id, text)
            except Exception as error:
                if await self._pending_operation_is_current(pending, operation):
                    self._finish_pending_with_message(_safe_local_error(error))
                return
            if not await self._pending_operation_is_current(pending, operation):
                return
            if not preview.allowed:
                await self._handle_preview_failure(preview, operation)
                return
            self._pending_preview = preview
            self._show_paid_dialog(preview, pending, operation)
            return
        await self._execute_send(pending, paid_confirmed=False)

    async def request_retry_turn(self, turn_id: str) -> None:
        if not _is_identifier(turn_id):
            self._show_message(tr("service.turn_id_invalid"))
            return
        state = self._state
        view = self._view
        if (
            state is None
            or view is None
            or self._pending_send is not None
            or self._interaction.busy
            or self._paid_setting_writes.get(
                (self._session_generation, state.chat.id), 0
            )
        ):
            return
        operation = self._capture_operation(state.chat.id)
        if operation is None:
            return
        pending = _PendingSend(
            state.chat.id,
            "",
            turn_id=turn_id,
            paid_consent=self._interaction.paid_consent(state.chat),
        )
        self._pending_send = pending
        view.set_sending(True)
        view.show_message("")
        self._page.update()
        try:
            preview = await self._interaction.preview_retry(
                turn_id, pending.paid_consent
            )
        except Exception as error:
            if await self._pending_operation_is_current(pending, operation):
                self._finish_pending_with_message(_safe_local_error(error))
            return
        if not await self._pending_operation_is_current(pending, operation):
            return
        if not preview.allowed:
            await self._handle_preview_failure(preview, operation)
            return
        if state.chat.mode is ChatMode.PAID and pending.paid_consent is None:
            self._pending_preview = preview
            self._show_paid_dialog(preview, pending, operation)
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

    def _dialog_callbacks(
        self, pending: _PendingSend, operation: _WorkspaceOperation, *, price: bool
    ):
        preview = self._pending_preview

        def current() -> bool:
            return (
                self._pending_send is pending
                and self._pending_preview is preview
                and self._operation_matches(operation)
            )

        async def confirm() -> None:
            if current():
                if price:
                    await self.confirm_price_change()
                else:
                    await self.confirm_paid_request()

        def cancel() -> None:
            if current():
                self.cancel_pending_send()

        return confirm, cancel

    def _show_paid_dialog(
        self,
        preview: MessageSendPreview,
        pending: _PendingSend,
        operation: _WorkspaceOperation,
    ) -> None:
        confirm, cancel = self._dialog_callbacks(pending, operation, price=False)
        self._page.show_dialog(build_paid_request_dialog(preview, confirm, cancel))

    def _show_price_dialog(
        self,
        change: ModelPriceChange,
        pending: _PendingSend,
        operation: _WorkspaceOperation,
    ) -> None:
        confirm, cancel = self._dialog_callbacks(pending, operation, price=True)
        self._page.show_dialog(
            build_price_reconfirmation_dialog(change, confirm, cancel)
        )

    def cancel_pending_send(self) -> None:
        if self._pending_send is None:
            return
        self._pending_send = None
        self._pending_preview = None
        self._page.pop_dialog()
        if self._view is not None:
            self._view.set_sending(False)
            self._page.update()

    async def _handle_preview_failure(
        self,
        preview: MessageSendPreview,
        operation: _WorkspaceOperation,
    ) -> None:
        self._pending_preview = preview
        if (
            preview.error_type is ChatErrorType.PRICE_RECONFIRMATION_REQUIRED
            and preview.price_change is not None
        ):
            pending = self._pending_send
            if pending is not None:
                self._show_price_dialog(preview.price_change, pending, operation)
            return
        self._pending_send = None
        self._pending_preview = None
        await self._refresh_workspace(False)
        if self._operation_matches(operation) and self._view is not None:
            self._view.set_sending(False)
            self._view.show_message(_preview_message(preview))
            self._page.update()

    async def confirm_price_change(self) -> None:
        pending = self._pending_send
        if pending is None:
            return
        operation = self._capture_operation(pending.chat_id)
        if operation is None:
            return
        self._page.pop_dialog()
        self._pending_preview = None
        try:
            await self._interaction.reconfirm_price(pending.chat_id, confirmed=True)
            if not await self._pending_operation_is_current(pending, operation):
                return
            preview = (
                await self._interaction.preview_message(pending.chat_id, pending.text)
                if pending.turn_id is None
                else await self._interaction.preview_retry(pending.turn_id)
            )
        except Exception as error:
            if await self._pending_operation_is_current(pending, operation):
                self._finish_pending_with_message(_safe_local_error(error))
            return
        if not await self._pending_operation_is_current(pending, operation):
            return
        if not preview.allowed:
            await self._handle_preview_failure(preview, operation)
            return
        self._pending_preview = preview
        self._show_paid_dialog(preview, pending, operation)

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
            paid_consent=pending.paid_consent,
            on_reserved=on_reserved,
            draft_revision=pending.draft.revision
            if pending.draft is not None
            else None,
        )
        if session != self._session_generation:
            return
        await self._finish_send(pending, outcome, generation, session)

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
            paid_consent=pending.paid_consent,
            on_reserved=on_reserved,
        )
        if session != self._session_generation:
            return
        await self._finish_send(pending, outcome, generation, session)

    async def _finish_send(
        self,
        pending: _PendingSend,
        outcome: InteractionOutcome,
        generation: int,
        session: int,
    ) -> None:
        if not self._active or session != self._session_generation:
            return
        operation = _WorkspaceOperation(session, generation, pending.chat_id)
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
            self._show_price_dialog(outcome.result.price_change, pending, operation)
            return
        if self._pending_send is pending:
            self._pending_send = None
            self._pending_preview = None
        self._set_state(outcome.state)
        await self._refresh_workspace(outcome.result.turn_id is not None)
        # Штатное обновление может заменить view в пределах той же операции.
        if not self._operation_matches(operation):
            return
        if self._view is not None and not outcome.result.successful:
            self._view.show_message(_result_message(outcome.result))
            self._page.update()
        elif self._view is not None and outcome.result.truncated:
            self._view.show_message(
                tr("service.response_truncated"),
                error=False,
            )
            self._page.update()

    async def request_release_unknown(self, turn_id: str) -> None:
        if not _is_identifier(turn_id):
            self._show_message(tr("service.turn_id_invalid"))
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
        operation = self._capture_operation(state.chat.id)
        if operation is None:
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
            if self._operation_matches(operation):
                self._show_message(_safe_local_error(error))
            return
        if not self._operation_matches(operation):
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

    def _capture_operation(self, chat_id: str) -> _WorkspaceOperation | None:
        operation = _WorkspaceOperation(
            self._session_generation, self._generation, chat_id
        )
        return operation if self._operation_matches(operation) else None

    def _operation_matches(self, operation: _WorkspaceOperation) -> bool:
        return (
            self._active
            and self._session_generation == operation.session
            and self._generation == operation.generation
            and self._state is not None
            and self._state.chat.id == operation.chat_id
            and self._view is not None
        )

    async def _pending_operation_is_current(
        self,
        pending: _PendingSend,
        operation: _WorkspaceOperation,
    ) -> bool:
        if (
            self._pending_send is not pending
            or not self._active
            or self._session_generation != operation.session
        ):
            return False
        if self._operation_matches(operation):
            return True
        # Навигация отзывает UI-результат, но ожидание завершает его владелец.
        # Чужие диалоги и pending новой сессии здесь не затрагиваются.
        self._pending_send = None
        self._pending_preview = None
        await self._refresh_workspace(False)
        return False

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
        self._refresh_local_estimate()


def _limit_message(error: ChatErrorType | None, fallback: str) -> str:
    if error is ChatErrorType.CONTEXT_LENGTH_EXCEEDED:
        return tr("service.context_estimate")
    if error is ChatErrorType.TOKEN_LIMIT_EXCEEDED:
        return tr("service.token_budget_short")
    if error is ChatErrorType.COST_LIMIT_EXCEEDED:
        return tr("service.money_budget_short")
    return fallback


def _preview_message(preview: MessageSendPreview) -> str:
    return _limit_message(
        preview.error_type,
        preview.safe_message or tr("service.preview_failed"),
    )


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
    message = _limit_message(
        result.error_type,
        result.safe_message or tr("service.request_failed"),
    )
    if result.retry_after is not None:
        message = tr("service.retry_after", message=message, seconds=result.retry_after)
    return message


def _safe_local_error(error: Exception) -> str:
    return localized_error_text(error)


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
