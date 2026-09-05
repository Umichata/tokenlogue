"""Координация экранов локальных чатов в рамках разблокированной сессии."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum

import flet as ft

from api.models import ModelCatalogService
from auth.access import free_mode_allowed, paid_mode_allowed
from auth.contracts import KeyValidator
from auth.key_validation import interpret_key_validation
from auth.models import KeyLimitInfo, KeyValidityState
from chat.accounting import ChatBudgetService, parse_chat_limit_input
from chat.drafts import DRAFT_STORAGE_MESSAGE, ChatDraftService, DraftStorageError
from chat.models import CatalogModel, ChatMode, ModelCatalog
from chat.sending import MessageSendingService
from chat.service import ChatPolicyError, ChatService
from chat_interaction_controller import (
    ActiveChatState,
    ChatInteractionController,
    ChatSessionContext,
)
from chat_workspace_controller import ChatWorkspaceController
from ui import (
    CatalogLoadingView,
    ChatWorkspaceView,
    ModelSelectionView,
    ModeSelectionView,
    NewChatLimitsView,
    RenameChatDialog,
    build_delete_chat_dialog,
)

AsyncCallback = Callable[[], Awaitable[None]]
StorageErrorCallback = Callable[[str], None]


class _ChatScreen(str, Enum):
    WORKSPACE = "workspace"
    CATALOG_LOADING = "catalog_loading"
    MODE_SELECTION = "mode_selection"
    MODEL_SELECTION = "model_selection"
    LIMITS_SELECTION = "limits_selection"


class ChatSessionController:
    """Хранит только краткоживущее состояние разблокированной чат-сессии."""

    def __init__(
        self,
        page: ft.Page,
        key_validator: KeyValidator,
        chat_service: ChatService,
        catalog_service: ModelCatalogService,
        budget_service: ChatBudgetService,
        sending_service: MessageSendingService,
        drafts: ChatDraftService,
        *,
        on_lock: AsyncCallback,
        on_replace_key: AsyncCallback,
        on_storage_error: StorageErrorCallback,
    ) -> None:
        self._page = page
        self._key_validator = key_validator
        self._chat_service = chat_service
        self._catalog_service = catalog_service
        self._drafts = drafts
        self._on_lock = on_lock
        self._on_replace_key = on_replace_key
        self._on_storage_error = on_storage_error
        self._workspace_view: ChatWorkspaceView | None = None
        self._workspace_state: ActiveChatState | None = None
        self._rename_dialog: RenameChatDialog | None = None
        self._new_limits_view: NewChatLimitsView | None = None
        self._catalog_task: asyncio.Task[object] | None = None
        self._key_validation_task: asyncio.Task[None] | None = None
        self._operation_lock = asyncio.Lock()
        self._pending_model: CatalogModel | None = None
        self._delete_chat_id: str | None = None
        self._dialog_request_pending = False
        self._dialog_request_id = 0
        self._disposed = False
        self._session_api_key: str | None = None
        self._session_generation = 0
        self._workspace_request_id = 0
        self._catalog_request_id = 0
        self._catalog: ModelCatalog | None = None
        self._pending_mode: ChatMode | None = None
        self._selected_chat_id: str | None = None
        self._key_validity = KeyValidityState.UNKNOWN
        self._key_limit = KeyLimitInfo.unknown()
        self._key_validation_in_progress = False
        self._screen = _ChatScreen.WORKSPACE
        self._interaction = ChatInteractionController(
            chat_service,
            budget_service,
            sending_service,
            session_provider=self._session_context,
            on_key_state_changed=self._apply_interaction_key_state,
        )
        self._workspace_controller = ChatWorkspaceController(
            page,
            self._interaction,
            drafts,
            refresh_workspace=self._refresh_workspace_from_interaction,
            on_state_changed=self._set_workspace_state,
        )

    @property
    def session_active(self) -> bool:
        return self._session_api_key is not None

    @property
    def workspace_visible(self) -> bool:
        return self._workspace_view is not None

    @property
    def selected_chat_id(self) -> str | None:
        return self._selected_chat_id

    @property
    def key_validity(self) -> KeyValidityState:
        return self._key_validity

    @property
    def key_limit(self) -> KeyLimitInfo:
        return self._key_limit

    @property
    def key_validation_in_progress(self) -> bool:
        return self._key_validation_in_progress

    async def activate(
        self,
        api_key: str,
        key_validity: KeyValidityState,
        key_limit: KeyLimitInfo,
    ) -> None:
        """Принимает ключ только после успешной PIN-аутентификации."""
        if self._disposed:
            return
        self.deactivate()
        self._session_api_key = api_key
        self._key_validity = key_validity
        self._key_limit = key_limit
        self._interaction.activate()
        self._workspace_controller.activate()
        self._key_validation_in_progress = key_validity is KeyValidityState.UNKNOWN
        generation = self._session_generation
        await self._show_workspace(expected_generation=generation)
        if (
            not self._disposed
            and generation == self._session_generation
            and key_validity is KeyValidityState.UNKNOWN
        ):
            self._start_key_validation()

    def deactivate(self) -> None:
        """Удаляет ключ и каталог из памяти, не изменяя SQLite."""
        self._session_generation += 1
        self._workspace_request_id += 1
        self._session_api_key = None
        self._workspace_controller.deactivate()
        self._interaction.deactivate()
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._selected_chat_id = None
        self._workspace_state = None
        self._new_limits_view = None
        self._key_validity = KeyValidityState.UNKNOWN
        self._key_limit = KeyLimitInfo.unknown()
        self._key_validation_in_progress = False
        self._cancel_key_validation()
        self._dialog_request_pending = False
        self._dialog_request_id += 1
        self._catalog_service.clear_cache()
        self._invalidate_catalog_request()
        self._dismiss_chat_dialog()
        self._clear_workspace()

    def dispose(self) -> None:
        if self._disposed:
            return
        self.deactivate()
        self._disposed = True

    async def request_new_chat(self) -> None:
        if (
            self._disposed
            or self._session_api_key is None
            or self._catalog_task is not None
            or not free_mode_allowed(self._key_validity)
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
        ):
            return
        if not await self._workspace_controller.flush_editor():
            return
        task = asyncio.current_task()
        if task is None:
            return
        self._catalog_task = task
        self._catalog_request_id += 1
        request_id = self._catalog_request_id
        generation = self._session_generation
        api_key = self._session_api_key
        self._show_catalog_loading()
        try:
            catalog = await self._catalog_service.get_catalog(api_key)
        except asyncio.CancelledError:
            return
        finally:
            if self._catalog_task is task:
                self._catalog_task = None

        if (
            self._disposed
            or request_id != self._catalog_request_id
            or generation != self._session_generation
            or self._session_api_key is None
        ):
            return
        self._catalog = catalog
        self._pending_mode = None
        self._show_mode_selection()

    async def cancel_new_chat(self) -> None:
        generation = self._session_generation
        self._invalidate_catalog_request()
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        await self._show_workspace(expected_generation=generation)

    async def select_chat_mode(self, mode: ChatMode) -> None:
        if not isinstance(mode, ChatMode):
            return
        catalog = self._catalog
        if self._disposed or catalog is None or self._session_api_key is None:
            return
        if mode is ChatMode.FREE and not free_mode_allowed(self._key_validity):
            return
        if mode is ChatMode.PAID and (
            not paid_mode_allowed(self._key_validity, self._key_limit)
            or not catalog.available
            or not catalog.paid_models
        ):
            return
        self._pending_mode = mode
        self._pending_model = None
        models = catalog.free_models if mode is ChatMode.FREE else catalog.paid_models
        view = ModelSelectionView(
            mode,
            models,
            on_select=self.select_chat_model,
            on_cancel=self.back_to_mode_selection,
        )
        self._screen = _ChatScreen.MODEL_SELECTION
        self._replace_page(view.control)

    async def back_to_mode_selection(self) -> None:
        if self._catalog is None or self._session_api_key is None:
            return
        self._pending_mode = None
        self._pending_model = None
        self._show_mode_selection()

    async def select_chat_model(self, model: CatalogModel) -> None:
        if not isinstance(model, CatalogModel):
            return
        if (
            self._disposed
            or self._catalog is None
            or self._pending_mode is None
            or self._session_api_key is None
        ):
            return
        self._pending_model = model
        self._new_limits_view = NewChatLimitsView(
            self._pending_mode,
            model,
            self.submit_new_chat_limits,
            self.back_to_model_selection,
        )
        self._screen = _ChatScreen.LIMITS_SELECTION
        self._replace_page(self._new_limits_view.control)

    async def back_to_model_selection(self) -> None:
        mode = self._pending_mode
        catalog = self._catalog
        if mode is None or catalog is None or self._session_api_key is None:
            return
        self._pending_model = None
        self._new_limits_view = None
        models = catalog.free_models if mode is ChatMode.FREE else catalog.paid_models
        view = ModelSelectionView(
            mode,
            models,
            on_select=self.select_chat_model,
            on_cancel=self.back_to_mode_selection,
        )
        self._screen = _ChatScreen.MODEL_SELECTION
        self._replace_page(view.control)

    async def submit_new_chat_limits(
        self,
        token_limit: str,
        max_completion_tokens: str,
        cost_limit_usd: str | None,
    ) -> None:
        view = self._new_limits_view
        mode = self._pending_mode
        model = self._pending_model
        catalog = self._catalog
        if (
            view is None
            or mode is None
            or model is None
            or catalog is None
            or self._session_api_key is None
            or self._operation_lock.locked()
        ):
            return
        try:
            configuration = parse_chat_limit_input(
                mode,
                token_limit,
                max_completion_tokens,
                cost_limit_usd,
            )
        except ValueError as error:
            view.form.show_error(str(error))
            self._page.update()
            return
        view.form.set_busy(True)
        view.form.show_error("")
        self._page.update()
        generation = self._session_generation
        async with self._operation_lock:
            try:
                chat = await self._chat_service.create_chat_with_limits(
                    mode,
                    model,
                    catalog=catalog,
                    key_validity=self._key_validity,
                    key_limit=self._key_limit,
                    token_limit=configuration.token_limit,
                    max_completion_tokens=configuration.max_completion_tokens,
                    cost_limit_usd=configuration.cost_limit_usd,
                    paid_confirmed=mode is ChatMode.PAID,
                )
            except (ChatPolicyError, ValueError) as error:
                if (
                    self._new_limits_view is view
                    and generation == self._session_generation
                ):
                    view.form.set_busy(False)
                    view.form.show_error(str(error))
                    self._page.update()
                return
            except Exception:
                if (
                    self._new_limits_view is view
                    and generation == self._session_generation
                ):
                    view.form.set_busy(False)
                    view.form.show_error("Не удалось создать локальный чат")
                    self._page.update()
                return
        if self._disposed or generation != self._session_generation:
            return
        self._selected_chat_id = chat.id
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        await self._show_workspace(expected_generation=generation, scroll_to_end=True)

    async def select_chat(self, chat_id: str) -> None:
        if (
            self._disposed
            or self._session_api_key is None
            or not _is_identifier(chat_id)
        ):
            return
        if not await self._workspace_controller.flush_editor():
            return
        self._workspace_controller.cancel_confirmation_for_navigation()
        self._workspace_controller.begin_navigation(chat_id)
        self._selected_chat_id = chat_id
        await self._show_workspace(expected_generation=self._session_generation)

    async def request_delete_chat(self, chat_id: str) -> None:
        if (
            self._disposed
            or self._session_api_key is None
            or self._delete_chat_id is not None
            or self._rename_dialog is not None
            or self._dialog_request_pending
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or not _is_identifier(chat_id)
        ):
            return
        generation = self._session_generation
        self._dialog_request_pending = True
        self._dialog_request_id += 1
        request_id = self._dialog_request_id
        try:
            chat = await self._chat_service.get_chat(chat_id)
        except Exception:
            if generation == self._session_generation and not self._disposed:
                self._report_storage_error("Не удалось открыть локальный чат.")
            return
        finally:
            if request_id == self._dialog_request_id:
                self._dialog_request_pending = False
        if chat is None or self._disposed or generation != self._session_generation:
            return
        self._delete_chat_id = chat_id
        self._page.show_dialog(
            build_delete_chat_dialog(
                chat,
                on_confirm=self.confirm_delete_chat,
                on_cancel=self.cancel_delete_chat,
            )
        )

    async def confirm_delete_chat(self, chat_id: str) -> None:
        if (
            not _is_identifier(chat_id)
            or self._delete_chat_id != chat_id
            or self._operation_lock.locked()
        ):
            return
        self._delete_chat_id = None
        self._page.pop_dialog()
        generation = self._session_generation
        async with self._operation_lock:
            try:
                await self._chat_service.delete_chat(chat_id)
            except Exception:
                if generation == self._session_generation and not self._disposed:
                    self._report_storage_error("Не удалось удалить локальный чат.")
                return
            if generation != self._session_generation or self._disposed:
                return
            self._drafts.forget(chat_id)
            if self._selected_chat_id == chat_id:
                self._clear_workspace()
                self._selected_chat_id = None
            await self._show_workspace(expected_generation=generation)

    def cancel_delete_chat(self) -> None:
        if self._delete_chat_id is None:
            return
        self._delete_chat_id = None
        self._page.pop_dialog()

    async def request_rename_chat(self, chat_id: str) -> None:
        if (
            self._disposed
            or self._session_api_key is None
            or self._rename_dialog is not None
            or self._delete_chat_id is not None
            or self._dialog_request_pending
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or not _is_identifier(chat_id)
        ):
            return
        generation = self._session_generation
        self._dialog_request_pending = True
        self._dialog_request_id += 1
        request_id = self._dialog_request_id
        try:
            chat = await self._chat_service.get_chat(chat_id)
        except Exception:
            if generation == self._session_generation and not self._disposed:
                self._report_storage_error("Не удалось открыть локальный чат.")
            return
        finally:
            if request_id == self._dialog_request_id:
                self._dialog_request_pending = False
        if chat is None or self._disposed or generation != self._session_generation:
            return
        self._rename_dialog = RenameChatDialog(
            chat,
            on_confirm=self.confirm_rename_chat,
            on_cancel=self.cancel_rename_chat,
        )
        self._page.show_dialog(self._rename_dialog.control)

    async def confirm_rename_chat(self, chat_id: str, title: str) -> None:
        dialog = self._rename_dialog
        if (
            dialog is None
            or self._operation_lock.locked()
            or not _is_identifier(chat_id)
            or not isinstance(title, str)
        ):
            return
        dialog.set_busy(True)
        dialog.show_error("")
        self._page.update()
        generation = self._session_generation
        async with self._operation_lock:
            try:
                renamed = await self._chat_service.rename_chat(chat_id, title)
            except ValueError as error:
                if (
                    self._disposed
                    or generation != self._session_generation
                    or self._rename_dialog is not dialog
                ):
                    return
                dialog.set_busy(False)
                dialog.show_error(str(error))
                self._page.update()
                return
            except Exception:
                if (
                    self._disposed
                    or generation != self._session_generation
                    or self._rename_dialog is not dialog
                ):
                    return
                dialog.set_busy(False)
                dialog.show_error("Не удалось сохранить название чата")
                self._page.update()
                return
            if not renamed:
                if (
                    self._disposed
                    or generation != self._session_generation
                    or self._rename_dialog is not dialog
                ):
                    return
                dialog.set_busy(False)
                dialog.show_error("Чат уже отсутствует")
                self._page.update()
                return
            if self._rename_dialog is dialog:
                self._rename_dialog = None
                self._page.pop_dialog()
            if generation == self._session_generation and not self._disposed:
                await self._show_workspace(expected_generation=generation)

    def cancel_rename_chat(self) -> None:
        if self._rename_dialog is None:
            return
        self._rename_dialog = None
        self._page.pop_dialog()

    async def request_configure_limits(self, chat_id: str) -> None:
        await self._workspace_controller.request_configure_limits(chat_id)

    async def request_edit_limits(self, chat_id: str) -> None:
        await self._workspace_controller.request_edit_limits(chat_id)

    async def submit_existing_chat_limits(
        self,
        token_limit: str,
        max_completion_tokens: str,
        cost_limit_usd: str | None,
    ) -> None:
        await self._workspace_controller.submit_existing_chat_limits(
            token_limit,
            max_completion_tokens,
            cost_limit_usd,
        )

    async def confirm_cost_increase(self) -> None:
        await self._workspace_controller.confirm_cost_increase()

    def cancel_cost_increase(self) -> None:
        self._workspace_controller.cancel_cost_increase()

    async def submit_message(self, text: str) -> None:
        await self._workspace_controller.submit_message(text)

    async def request_retry_turn(self, turn_id: str) -> None:
        await self._workspace_controller.request_retry_turn(turn_id)

    async def confirm_paid_request(self) -> None:
        await self._workspace_controller.confirm_paid_request()

    def cancel_pending_send(self) -> None:
        self._workspace_controller.cancel_pending_send()

    async def confirm_price_change(self) -> None:
        await self._workspace_controller.confirm_price_change()

    async def request_release_unknown(self, turn_id: str) -> None:
        await self._workspace_controller.request_release_unknown(turn_id)

    async def confirm_release_unknown(self) -> None:
        await self._workspace_controller.confirm_release_unknown()

    def cancel_release_unknown(self) -> None:
        self._workspace_controller.cancel_release_unknown()

    async def request_key_revalidation(self) -> None:
        """Запускает одну повторную проверку и сразу возвращает управление UI."""
        if (
            self._disposed
            or self._session_api_key is None
            or self._key_validity is KeyValidityState.VALID
            or self._key_validation_task is not None
        ):
            return
        generation = self._session_generation
        if not self._start_key_validation():
            return
        await self._refresh_after_key_validation(generation)

    async def request_key_replacement(self) -> None:
        """Передаёт замену ключа в явный подтверждаемый reset-сценарий."""
        if (
            self._disposed
            or self._session_api_key is None
            or self._key_validity is not KeyValidityState.INVALID
        ):
            return
        await self._on_replace_key()

    async def lock_application(self) -> None:
        if self._disposed or self._session_api_key is None:
            return
        generation = self._session_generation
        await self.flush_drafts()
        if generation != self._session_generation or self._disposed:
            return
        self.deactivate()
        await self._on_lock()

    async def flush_drafts(self) -> bool:
        if not await self._workspace_controller.flush_editor():
            return False
        try:
            await self._drafts.flush_all()
        except DraftStorageError:
            if self._workspace_view is not None:
                self._workspace_view.show_message(DRAFT_STORAGE_MESSAGE)
                self._page.update()
            return False
        return True

    def _start_key_validation(self) -> bool:
        if (
            self._disposed
            or self._session_api_key is None
            or self._key_validation_task is not None
        ):
            return False
        self._key_validation_in_progress = True
        generation = self._session_generation
        api_key = self._session_api_key
        self._key_validation_task = asyncio.create_task(
            self._run_key_validation(api_key, generation)
        )
        return True

    async def _run_key_validation(self, api_key: str, generation: int) -> None:
        current_task = asyncio.current_task()
        try:
            try:
                validation = await self._key_validator.validate_key(api_key)
            except asyncio.CancelledError:
                return
            except Exception:
                key_validity = KeyValidityState.UNKNOWN
                key_limit = KeyLimitInfo.unknown()
            else:
                try:
                    key_validity, key_limit = interpret_key_validation(validation)
                except Exception:
                    key_validity = KeyValidityState.UNKNOWN
                    key_limit = KeyLimitInfo.unknown()

            if (
                self._disposed
                or generation != self._session_generation
                or self._session_api_key is None
                or self._key_validation_task is not current_task
            ):
                return
            self._key_validation_task = None
            self._key_validation_in_progress = False
            self._key_validity = key_validity
            self._key_limit = key_limit
            if key_validity is KeyValidityState.INVALID:
                self._catalog = None
                self._pending_mode = None
                self._catalog_service.clear_cache()
                self._invalidate_catalog_request()
            try:
                await self._refresh_after_key_validation(generation)
            except asyncio.CancelledError:
                return
            except Exception:
                return
        finally:
            if self._key_validation_task is current_task:
                self._key_validation_task = None
                self._key_validation_in_progress = False

    async def _refresh_after_key_validation(self, generation: int) -> None:
        if (
            self._disposed
            or self._session_api_key is None
            or generation != self._session_generation
        ):
            return

        can_use_free = free_mode_allowed(self._key_validity)
        can_use_paid = paid_mode_allowed(self._key_validity, self._key_limit)
        if not can_use_paid and self._workspace_controller.pending_preview is not None:
            self._workspace_controller.cancel_pending_send()

        if not can_use_free:
            self._invalidate_catalog_request()
            self._catalog = None
            self._pending_mode = None
            await self._show_workspace(expected_generation=generation)
            return
        if self._screen is _ChatScreen.CATALOG_LOADING:
            return
        if self._screen is _ChatScreen.MODE_SELECTION:
            self._show_mode_selection()
            return
        if self._screen is _ChatScreen.MODEL_SELECTION:
            if self._pending_mode is ChatMode.PAID and not can_use_paid:
                self._pending_mode = None
                self._show_mode_selection()
            return
        if self._screen is _ChatScreen.LIMITS_SELECTION:
            if self._pending_mode is ChatMode.PAID and not can_use_paid:
                self._pending_mode = None
                self._pending_model = None
                self._new_limits_view = None
                self._show_mode_selection()
            return
        await self._show_workspace(expected_generation=generation)

    async def _show_workspace(
        self,
        *,
        expected_generation: int,
        scroll_to_end: bool = False,
    ) -> None:
        if (
            self._disposed
            or self._session_api_key is None
            or expected_generation != self._session_generation
        ):
            return
        self._workspace_request_id += 1
        request_id = self._workspace_request_id
        if not await self._workspace_controller.flush_editor():
            return
        if not self._workspace_request_matches(expected_generation, request_id):
            return
        try:
            chats = await self._chat_service.list_chats()
        except Exception:
            if expected_generation == self._session_generation and not self._disposed:
                self._report_storage_error("Не удалось загрузить локальные чаты.")
            return
        if (
            self._disposed
            or self._session_api_key is None
            or expected_generation != self._session_generation
            or request_id != self._workspace_request_id
        ):
            return

        selected = next(
            (chat for chat in chats if chat.id == self._selected_chat_id),
            None,
        )
        if selected is None and chats:
            selected = chats[0]
        self._selected_chat_id = selected.id if selected is not None else None
        interaction_state: ActiveChatState | None = None
        if selected is not None:
            try:
                interaction_state = (
                    await self._interaction.select_chat(selected.id)
                    if self._interaction.active_chat_id != selected.id
                    else await self._interaction.load_state(selected.id)
                )
            except Exception:
                if (
                    expected_generation == self._session_generation
                    and not self._disposed
                ):
                    self._report_storage_error("Не удалось загрузить историю чата.")
                return
            if not self._workspace_request_matches(expected_generation, request_id):
                return
            try:
                await self._drafts.load(selected.id)
            except DraftStorageError:
                if self._workspace_request_matches(expected_generation, request_id):
                    if self._workspace_view is not None:
                        self._workspace_view.show_message(DRAFT_STORAGE_MESSAGE)
                        self._page.update()
                    else:
                        self._report_storage_error(
                            "Не удалось загрузить локальный черновик."
                        )
                return
        if not self._workspace_request_matches(expected_generation, request_id):
            return
        self._workspace_state = interaction_state
        if self._workspace_view is not None and self._screen is _ChatScreen.WORKSPACE:
            self._workspace_view.update_workspace(
                chats,
                selected,
                interaction_state,
                key_validity=self._key_validity,
                key_limit=self._key_limit,
                key_validation_in_progress=self._key_validation_in_progress,
            )
            self._workspace_controller.bind(self._workspace_view, interaction_state)
            self._page.update()
        else:
            self._clear_workspace()
            self._workspace_view = ChatWorkspaceView(
                self._page,
                chats,
                selected,
                interaction_state,
                on_new_chat=self.request_new_chat,
                on_select_chat=self.select_chat,
                on_rename_chat=self.request_rename_chat,
                on_delete_chat=self.request_delete_chat,
                on_lock=self.lock_application,
                on_send_message=self.submit_message,
                on_draft_change=self._workspace_controller.update_draft,
                on_retry_turn=self.request_retry_turn,
                on_configure_limits=self.request_configure_limits,
                on_edit_limits=self.request_edit_limits,
                on_release_unknown=self.request_release_unknown,
                key_validity=self._key_validity,
                key_limit=self._key_limit,
                key_validation_in_progress=self._key_validation_in_progress,
                on_retry_key=self.request_key_revalidation,
                on_replace_key=self.request_key_replacement,
            )
            self._workspace_controller.bind(self._workspace_view, interaction_state)
            self._replace_page(self._workspace_view.control)
        self._screen = _ChatScreen.WORKSPACE
        if scroll_to_end and self._workspace_view is not None:
            await self._workspace_view.scroll_messages_to_end()

    async def _refresh_workspace_from_interaction(
        self,
        scroll_to_end: bool,
    ) -> None:
        if self._screen is not _ChatScreen.WORKSPACE or not self.session_active:
            return
        await self._show_workspace(
            expected_generation=self._session_generation,
            scroll_to_end=scroll_to_end,
        )

    def _workspace_request_matches(self, generation: int, request_id: int) -> bool:
        return (
            not self._disposed
            and self.session_active
            and generation == self._session_generation
            and request_id == self._workspace_request_id
        )

    def _set_workspace_state(self, state: ActiveChatState | None) -> None:
        self._workspace_state = state

    def _session_context(self) -> ChatSessionContext | None:
        if self._disposed or self._session_api_key is None:
            return None
        return ChatSessionContext(
            self._session_api_key,
            self._key_validity,
            self._key_limit,
        )

    def _apply_interaction_key_state(
        self,
        validity: KeyValidityState,
        limit: KeyLimitInfo,
    ) -> None:
        if self._disposed or self._session_api_key is None:
            return
        self._key_validity = validity
        self._key_limit = limit
        if validity is KeyValidityState.INVALID:
            self._catalog = None
            self._pending_mode = None
            self._pending_model = None
            self._catalog_service.clear_cache()
            self._invalidate_catalog_request()

    def _show_catalog_loading(self) -> None:
        self._clear_workspace()
        self._screen = _ChatScreen.CATALOG_LOADING
        self._replace_page(CatalogLoadingView(self.cancel_new_chat).control)

    def _show_mode_selection(self) -> None:
        catalog = self._catalog
        if catalog is None:
            return
        self._clear_workspace()
        view = ModeSelectionView(
            catalog,
            key_validity=self._key_validity,
            key_limit=self._key_limit,
            on_select=self.select_chat_mode,
            on_cancel=self.cancel_new_chat,
        )
        self._screen = _ChatScreen.MODE_SELECTION
        self._replace_page(view.control)

    def _replace_page(self, control: ft.Control) -> None:
        if self._disposed:
            return
        self._page.controls.clear()
        self._page.add(control)

    def _report_storage_error(self, message: str) -> None:
        self.deactivate()
        self._on_storage_error(message)

    def _clear_workspace(self) -> None:
        if self._workspace_view is not None:
            self._workspace_view.dispose()
        self._workspace_view = None
        self._workspace_controller.unbind()

    def _cancel_key_validation(self) -> None:
        task = self._key_validation_task
        self._key_validation_task = None
        self._key_validation_in_progress = False
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _invalidate_catalog_request(self) -> None:
        self._catalog_request_id += 1
        task = self._catalog_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
        self._catalog_task = None

    def _dismiss_chat_dialog(self) -> None:
        dialog_count = sum(
            (
                self._delete_chat_id is not None,
                self._rename_dialog is not None,
            )
        )
        for _ in range(dialog_count):
            self._page.pop_dialog()
        self._delete_chat_id = None
        self._rename_dialog = None


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
