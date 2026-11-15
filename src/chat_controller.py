"""Координация экранов локальных чатов в рамках разблокированной сессии."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

import flet as ft

from api.models import ModelCatalogService
from api.openrouter import KeyValidationResult, KeyValidationStatus
from auth.access import free_mode_allowed, paid_mode_allowed
from auth.contracts import KeyValidator
from auth.key_validation import interpret_key_validation
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState
from chat.account_balance import (
    AccountBalanceService,
    AccountBalanceSnapshot,
    AccountBalanceState,
    CreditsReader,
)
from chat.accounting import (
    AccountingStatus,
    ChatBudget,
    ChatBudgetService,
    ChatLimitConfiguration,
    TurnStatus,
    parse_chat_limit_input,
)
from chat.drafts import DRAFT_STORAGE_MESSAGE, ChatDraftService, DraftStorageError
from chat.metrics import LastRequestState
from chat.models import FREE_ROUTER_MODEL, CatalogModel, Chat, ChatMode, ModelCatalog
from chat.sending import MessageSendingService
from chat.service import ChatPolicyError, ChatService
from chat_interaction_controller import (
    ActiveChatState,
    ChatInteractionController,
    ChatSessionContext,
    InteractionOperationLock,
)
from chat_workspace_controller import ChatWorkspaceController
from i18n import tr
from platform_security.local_protection import ProtectionSnapshot
from providers.credentials import masked_key_display
from providers.models import ProviderId, detect_key
from service_errors import localized_error_text
from storage.data_access import DataAccess
from ui import (
    CatalogLoadingView,
    ChatWorkspaceView,
    ModelSelectionView,
    ModeSelectionView,
    NewChatLimitsView,
    RenameChatDialog,
    build_delete_chat_dialog,
)
from ui.chat_connection_view import (
    ProviderSwitchDialog,
    build_connection_confirmation,
    build_missing_provider_key_dialog,
)

AsyncCallback = Callable[[], Awaitable[None]]
StorageErrorCallback = Callable[[str], None]


class _ChatScreen(str, Enum):
    WORKSPACE = "workspace"
    CATALOG_LOADING = "catalog_loading"
    MODE_SELECTION = "mode_selection"
    MODEL_SELECTION = "model_selection"
    LIMITS_SELECTION = "limits_selection"
    SECURITY = "security"


@dataclass(frozen=True)
class _ChatActionContext:
    session: int
    request: int
    view: ChatWorkspaceView
    chat_id: str
    connection_revision: int


@dataclass(frozen=True)
class _ConnectionChange:
    session: int
    request: int
    chat: Chat
    target: ProviderId | None = None
    credential_revision: object = None
    budget: ChatBudget | None = None


@dataclass(frozen=True, eq=False)
class WorkspaceDeletionOrigin:
    """Одноразовая привязка глобального действия к живому workspace."""

    generation: int
    workspace: ChatWorkspaceView


class ProviderProfiles(Protocol):
    @property
    def default_provider(self) -> ProviderId: ...
    @property
    def active(self) -> bool: ...
    def key_for(self, provider: ProviderId) -> str | None: ...
    def key_validity_for(self, provider: ProviderId) -> KeyValidityState: ...
    def key_limit_for(self, provider: ProviderId) -> KeyLimitInfo: ...
    def balance_for(self, provider: ProviderId) -> AccountBalanceSnapshot: ...
    def credential_revision(self, provider: ProviderId) -> object: ...
    def key_display(self, provider: ProviderId) -> str | None: ...
    def apply_validation(
        self, provider: ProviderId, key: str, result: KeyValidationResult
    ) -> None: ...
    async def refresh(
        self,
        provider: ProviderId,
        *,
        after_response: bool = False,
        validate_key: bool = False,
    ) -> None: ...


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
        credits_reader: CreditsReader | None = None,
        on_lock: AsyncCallback,
        on_replace_key: AsyncCallback,
        on_storage_error: StorageErrorCallback,
        on_security: AsyncCallback | None = None,
        on_test_screen_lock: AsyncCallback | None = None,
        on_test_sleep: AsyncCallback | None = None,
        on_delete_profile: Callable[[WorkspaceDeletionOrigin], Awaitable[None]]
        | None = None,
        data_access: DataAccess | None = None,
        provider_profiles: ProviderProfiles | None = None,
        on_provider_settings: AsyncCallback | None = None,
        on_provider_settings_for: Callable[[ProviderId], Awaitable[None]] | None = None,
        present_content: Callable[[ft.Control], None] | None = None,
    ) -> None:
        self._page = page
        self._data_access = data_access
        self._provider_profiles = provider_profiles
        self._on_provider_settings = on_provider_settings
        self._on_provider_settings_for = on_provider_settings_for
        self._present_content = present_content
        self._navigation_hidden = False
        self._provider_tasks: set[asyncio.Task[None]] = set()
        self._provider_revisions: dict[ProviderId, object] = {}
        self._selected_provider = ProviderId.OPENROUTER
        self._creation_provider = ProviderId.OPENROUTER
        self._key_validator = key_validator
        self._chat_service = chat_service
        self._catalog_service = catalog_service
        self._drafts = drafts
        self._budget_service = budget_service
        self._sending_service = sending_service
        self._on_lock = on_lock
        self._on_replace_key = on_replace_key
        self._on_security = on_security
        self._on_test_screen_lock = on_test_screen_lock
        self._on_test_sleep = on_test_sleep
        self._protection_status: ProtectionSnapshot | None = None
        self._on_delete_profile = on_delete_profile
        self._profile_deletion_origin: WorkspaceDeletionOrigin | None = None
        self._security_generation: int | None = None
        self._on_storage_error = on_storage_error
        self._workspace_view: ChatWorkspaceView | None = None
        self._deferred_workspace = False
        self._session_watch_status: tuple[bool, bool] | None = None
        self._workspace_state: ActiveChatState | None = None
        self._rename_dialog: RenameChatDialog | None = None
        self._new_limits_view: NewChatLimitsView | None = None
        self._catalog_task: asyncio.Task[object] | None = None
        self._estimate_metadata_task: asyncio.Task[None] | None = None
        self._estimate_metadata_expiry: asyncio.TimerHandle | None = None
        self._estimate_metadata_request = 0
        self._estimate_metadata_after = 0.0
        self._estimate_refresh_key = False
        self._observed_attempt: (
            tuple[str, int | None, str | None, datetime | None, LastRequestState] | None
        ) = None
        self._completed_attempt: (
            tuple[str, int | None, str | None, datetime | None] | None
        ) = None
        self._key_validation_task: asyncio.Task[None] | None = None
        self._balance_task: asyncio.Task[None] | None = None
        self._balance_expiry: asyncio.TimerHandle | None = None
        self._balance_service = (
            AccountBalanceService(credits_reader, self._publish_account_balance)
            if credits_reader is not None
            else None
        )
        self._operation_lock = InteractionOperationLock()
        self._deletion_tasks: set[asyncio.Task[object]] = set()
        self._pending_model: CatalogModel | None = None
        self._delete_chat_id: str | None = None
        self._delete_dialog: ft.AlertDialog | None = None
        self._chat_dialog_context: _ChatActionContext | None = None
        self._connection_change: _ConnectionChange | None = None
        self._connection_dialog: ft.AlertDialog | None = None
        self._provider_switch_dialog: ProviderSwitchDialog | None = None
        self._connection_request = 0
        self._connection_waiting_for_key = False
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
        self._key_metadata_updated_at: datetime | None = None
        self._key_validation_in_progress = False
        self._key_replacement_generation: int | None = None
        self._draft_save_failed = False
        self._screen = _ChatScreen.WORKSPACE
        self._interaction = ChatInteractionController(
            chat_service,
            budget_service,
            sending_service,
            session_provider=self._session_context,
            on_key_state_changed=self._apply_interaction_key_state,
            on_request_finished=(
                self._model_request_finished
                if self._balance_service is not None
                else None
            ),
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
    def session_generation(self) -> int:
        return self._session_generation

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
        *,
        present_workspace: bool = True,
    ) -> None:
        """Принимает ключ только после успешной PIN-аутентификации."""
        if self._disposed:
            return
        self.deactivate()
        self._session_api_key = api_key
        self._selected_provider = detect_key(api_key) or ProviderId.OPENROUTER
        self._creation_provider = (
            self._provider_profiles.default_provider
            if self._provider_profiles is not None
            else self._selected_provider
        )
        self._key_validity = key_validity
        self._key_limit = key_limit
        if self._balance_service is not None:
            self._balance_service.begin_session()
        self._interaction.activate()
        self._workspace_controller.activate()
        self._deferred_workspace = not present_workspace
        self._key_validation_in_progress = key_validity is KeyValidityState.UNKNOWN
        if present_workspace:
            await self.present_workspace()
        self._start_balance_refresh()

    async def present_workspace(self) -> None:
        """Shows chats only after the separate protected first-run step is handled."""
        if self._disposed or not self.session_active:
            return
        self._deferred_workspace = False
        self._navigation_hidden = False
        generation = self._session_generation
        await self._show_workspace(expected_generation=generation)
        if self._present_content is not None and self._workspace_view is not None:
            self._replace_page(self._workspace_view.control)
        if (
            not self._disposed
            and generation == self._session_generation
            and self._key_validity is KeyValidityState.UNKNOWN
        ):
            self._start_key_validation()

    async def prepare_navigation(self) -> bool:
        """Keep the bound workspace and in-flight attempt while leaving Home."""
        if self._disposed or not self.session_active:
            return False
        if not await self.flush_drafts():
            return False
        if self._connection_change is not None and not self._connection_waiting_for_key:
            self._discard_connection_change()
            self._catalog = None
            self._pending_mode = None
            self._pending_model = None
            self._new_limits_view = None
            self._screen = _ChatScreen.WORKSPACE
        self._dismiss_chat_dialog()
        self._workspace_controller.cancel_confirmation_for_navigation()
        self._workspace_controller.cancel_cost_increase()
        self._workspace_controller.cancel_limits_dialog()
        self._workspace_controller.cancel_release_unknown()
        if self._workspace_view is not None:
            self._workspace_view.close_menu()
            await self._workspace_view.close_drawer()
        self._page.drawer = None
        self._navigation_hidden = True
        return True

    async def resume_home(self) -> None:
        """Reveal the retained Home without restarting a send or its workspace."""
        if self._disposed or not self.session_active:
            return
        self._navigation_hidden = False
        waiting = self._connection_change if self._connection_waiting_for_key else None
        if waiting is not None:
            self._connection_waiting_for_key = False
            if self._connection_matches(waiting, credential=False):
                self._screen = _ChatScreen.WORKSPACE
                await self._show_workspace(expected_generation=self._session_generation)
                if self._connection_matches(waiting, credential=False):
                    configured = (
                        waiting.target is not None
                        and self._key_for_provider(waiting.target) is not None
                    )
                    self._show_connection_provider_choice(
                        waiting,
                        tr("connection.resume")
                        if configured
                        else tr("connection.choose_provider"),
                    )
                return
            self._discard_connection_change()
        if self._workspace_view is not None and self._screen is _ChatScreen.WORKSPACE:
            self._workspace_view.restore_navigation()
            if self._provider_profiles is not None:
                self._sync_provider_metadata(self._selected_provider)
            self._push_estimate_metadata()
            self._replace_page(self._workspace_view.control)
            return
        await self.cancel_new_chat()

    async def handle_application_back(self) -> bool:
        """Consume local navigation surfaces before the platform leaves Home."""
        if self._disposed or not self.session_active:
            return False
        if self._connection_dialog is not None:
            await self.cancel_connection_change()
            return True
        view = self._workspace_view
        if view is not None and getattr(view, "_menu_dialog", None) is not None:
            view.close_menu()
            return True
        if view is not None and view.drawer_open:
            await view.close_drawer()
            return True
        if self._delete_dialog is not None or self._rename_dialog is not None:
            self._dismiss_chat_dialog()
            return True
        if self._workspace_controller.has_dialog():
            self._workspace_controller.cancel_confirmation_for_navigation()
            self._workspace_controller.cancel_cost_increase()
            self._workspace_controller.cancel_limits_dialog()
            self._workspace_controller.cancel_release_unknown()
            return True
        if self._screen is _ChatScreen.LIMITS_SELECTION:
            await self.back_to_model_selection()
            return True
        if self._screen is _ChatScreen.MODEL_SELECTION:
            await self.back_to_mode_selection()
            return True
        if self._screen in {_ChatScreen.MODE_SELECTION, _ChatScreen.CATALOG_LOADING}:
            await self.cancel_new_chat()
            return True
        if not await self.flush_drafts():
            return True
        return False

    async def refresh_provider_state(self) -> None:
        if self._provider_profiles is None or not self.session_active or self._disposed:
            return
        change = self._connection_change
        if (
            change is not None
            and not self._connection_waiting_for_key
            and change.target is not None
            and change.credential_revision != self._provider_revision(change.target)
        ):
            await self.cancel_connection_change()
            self._show_chat_action_error(tr("connection.stale"))
            return
        provider = self._current_provider()
        revision = self._provider_revision(provider)
        if self._provider_revisions.get(provider) != revision:
            self._provider_revisions[provider] = revision
            self._catalog_service.clear_cache()
            self._cancel_estimate_metadata()
        self._sync_provider_metadata(provider)
        self._push_estimate_metadata()
        if self._screen is _ChatScreen.WORKSPACE:
            await self._show_workspace(expected_generation=self._session_generation)

    async def _open_provider_settings(self) -> None:
        if self._on_provider_settings is not None:
            if await self.prepare_navigation():
                await self._on_provider_settings()

    @property
    def current_provider(self) -> ProviderId:
        """Service of the current chat or the active new-chat context."""
        return self._current_provider()

    def _current_provider(self) -> ProviderId:
        if self._screen in {
            _ChatScreen.CATALOG_LOADING,
            _ChatScreen.MODE_SELECTION,
            _ChatScreen.MODEL_SELECTION,
            _ChatScreen.LIMITS_SELECTION,
        }:
            return self._creation_provider
        return self._selected_provider

    def _key_for_provider(self, provider: ProviderId) -> str | None:
        if self._provider_profiles is not None:
            return self._provider_profiles.key_for(provider)
        return self._session_api_key

    def _key_display_for(self, provider: ProviderId) -> str | None:
        profiles = self._provider_profiles
        reader = getattr(profiles, "key_display", None)
        if reader is not None:
            return reader(provider)
        return masked_key_display(provider, self._key_for_provider(provider))

    def _provider_revision(self, provider: ProviderId) -> object:
        if self._provider_profiles is not None:
            return self._provider_profiles.credential_revision(provider)
        return self._session_generation

    def _peek_catalog(self, provider: ProviderId | None = None) -> ModelCatalog | None:
        if self._provider_profiles is None:
            return self._catalog_service.peek_catalog()
        key = self._key_for_provider(provider or self._selected_provider)
        return self._catalog_service.peek_catalog(key) if key is not None else None

    def _sync_provider_metadata(
        self, provider: ProviderId, *, publish_balance: bool = True
    ) -> None:
        profiles = self._provider_profiles
        if profiles is None:
            return
        self._key_validity = profiles.key_validity_for(provider)
        self._key_limit = profiles.key_limit_for(provider)
        if profiles.key_for(provider) is None:
            self._key_validity = KeyValidityState.INVALID
        self._key_validation_in_progress = False
        if publish_balance:
            self._workspace_controller.set_account_balance(
                profiles.balance_for(provider)
            )

    def _start_provider_refresh(
        self,
        provider: ProviderId,
        *,
        after_response: bool = False,
        validate_key: bool = False,
    ) -> None:
        profiles = self._provider_profiles
        if profiles is None or not profiles.active or not self.session_active:
            return
        generation = self._session_generation

        async def refresh() -> None:
            try:
                await profiles.refresh(
                    provider, after_response=after_response, validate_key=validate_key
                )
                if generation == self._session_generation and self.session_active:
                    await self.refresh_provider_state()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        task = asyncio.create_task(refresh())
        self._provider_tasks.add(task)
        task.add_done_callback(self._provider_tasks.discard)

    def deactivate(self) -> None:
        """Удаляет ключ и каталог из памяти, не изменяя SQLite."""
        self._session_generation += 1
        self._discard_connection_change()
        self._workspace_request_id += 1
        self._session_api_key = None
        self._navigation_hidden = False
        self._cancel_balance_refresh()
        self._deferred_workspace = False
        self._cancel_estimate_metadata()
        self._key_metadata_updated_at = None
        self._estimate_metadata_after = 0.0
        self._estimate_refresh_key = False
        self._observed_attempt = None
        self._completed_attempt = None
        self._workspace_controller.deactivate()
        self._interaction.deactivate()
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._workspace_state = None
        self._new_limits_view = None
        self._key_validity = KeyValidityState.UNKNOWN
        self._key_limit = KeyLimitInfo.unknown()
        self._key_validation_in_progress = False
        self._key_replacement_generation = None
        self._security_generation = None
        self._profile_deletion_origin = None
        self._screen = _ChatScreen.WORKSPACE
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

    def set_session_watch_status(
        self, *, system_events: bool, screen_events: bool
    ) -> None:
        self._session_watch_status = (system_events, screen_events)
        if self._workspace_view is not None and not self._disposed:
            self._workspace_view.set_session_watch_status(self._session_watch_status)

    def set_protection_status(self, snapshot: ProtectionSnapshot) -> None:
        self._protection_status = snapshot
        if self._workspace_view is not None and not self._disposed:
            self._workspace_view.set_protection_status(snapshot)

    @property
    def protection_anchor(self) -> ft.IconButton | None:
        """The current visible shield, for restoring focus after a PIN handoff."""
        return (
            self._workspace_view.protection_button
            if self._workspace_view is not None
            else None
        )

    async def prepare_screen_lock_test(self) -> bool:
        view = self._workspace_view
        generation = self._session_generation
        selected = self._selected_chat_id
        if (
            self._disposed
            or not self.session_active
            or (view is None and not self._deferred_workspace)
            or (
                self._deferred_workspace
                and (self._data_access is None or not self._data_access.unlocked)
            )
            or self._screen is not _ChatScreen.WORKSPACE
            or (view is not None and view.security_busy)
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or self._dialog_request_pending
            or self._chat_dialog_context is not None
            or self._operation_lock.locked()
            or self._profile_deletion_origin is not None
            or self._security_generation is not None
            or self._key_replacement_generation is not None
        ):
            return False
        if not await self._workspace_controller.flush_editor():
            return False
        return (
            not self._disposed
            and self.session_active
            and self._workspace_view is view
            and self._session_generation == generation
            and self._screen is _ChatScreen.WORKSPACE
            and self._selected_chat_id == selected
            and not self._workspace_controller.busy
            and not self._workspace_controller.has_dialog()
            and not self._dialog_request_pending
            and self._chat_dialog_context is None
            and not self._operation_lock.locked()
            and self._profile_deletion_origin is None
            and self._security_generation is None
            and self._key_replacement_generation is None
        )

    async def request_screen_lock_test(self) -> None:
        if (
            not self._disposed
            and self.session_active
            and self._screen is _ChatScreen.WORKSPACE
            and self._workspace_view is not None
            and self._on_test_screen_lock is not None
        ):
            await self._on_test_screen_lock()

    async def request_sleep_test(self) -> None:
        if (
            not self._disposed
            and self.session_active
            and self._screen is _ChatScreen.WORKSPACE
            and self._workspace_view is not None
            and self._on_test_sleep is not None
        ):
            await self._on_test_sleep()

    def report_screen_lock_test_busy(self) -> None:
        if self._workspace_view is not None and not self._disposed:
            self._workspace_view.show_message(tr("service.operation_pending"))
            self._page.update()

    def begin_profile_deletion(self) -> None:
        """Отзывает UI и отменяет только собственные фоновые операции."""
        tasks = (
            self._key_validation_task,
            self._catalog_task,
            self._estimate_metadata_task,
            self._operation_lock.owner,
            self._interaction.operation_task,
        )
        self.deactivate()
        self._disposed = True
        self._selected_chat_id = None
        current = asyncio.current_task()
        for task in tasks:
            if task is not None and task is not current and not task.done():
                self._deletion_tasks.add(task)
                task.cancel()

    async def wait_profile_deletion(self) -> None:
        if self._deletion_tasks:
            await asyncio.gather(*self._deletion_tasks, return_exceptions=True)
            self._deletion_tasks.clear()
        async with self._operation_lock:
            pass
        await self._interaction.wait_idle()
        await self._drafts.discard_for_deletion()

    def _connection_matches(
        self, change: _ConnectionChange, *, credential: bool = True
    ) -> bool:
        state = self._workspace_state
        return (
            self._connection_change is change
            and not self._disposed
            and self.session_active
            and change.session == self._session_generation
            and change.request == self._connection_request
            and self._selected_chat_id == change.chat.id
            and state is not None
            and state.chat.id == change.chat.id
            and state.chat.connection_revision == change.chat.connection_revision
            and state.chat.provider_id is change.chat.provider_id
            and (
                not credential
                or change.target is None
                or (
                    self._key_for_provider(change.target) is not None
                    and change.credential_revision
                    == self._provider_revision(change.target)
                )
            )
        )

    def _close_connection_dialog(self) -> None:
        dialog, self._connection_dialog = self._connection_dialog, None
        selector, self._provider_switch_dialog = self._provider_switch_dialog, None
        if selector is not None:
            selector.dispose()
        if dialog is not None:
            dialog.open = False
            try:
                dialog.update()
            except (RuntimeError, AssertionError):
                pass

    def _discard_connection_change(self) -> None:
        self._connection_request += 1
        self._connection_change = None
        self._connection_waiting_for_key = False
        self._close_connection_dialog()

    async def cancel_connection_change(self) -> None:
        if self._connection_change is None:
            return
        generation = self._session_generation
        self._discard_connection_change()
        self._invalidate_catalog_request()
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        self._screen = _ChatScreen.WORKSPACE
        if self.session_active and not self._disposed:
            await self._show_workspace(expected_generation=generation)

    def _connection_block_reason(self, state: ActiveChatState) -> str:
        if self._workspace_controller.busy or state.sending:
            return tr("connection.wait_send")
        if (
            state.budget.reserved_tokens
            or state.budget.cost_reserved
            or any(
                turn.status is TurnStatus.PENDING
                or turn.accounting_status
                in {AccountingStatus.RESERVED, AccountingStatus.UNKNOWN}
                for turn in state.turns
            )
        ):
            return tr("service.previous_unknown")
        return ""

    async def request_change_provider(self, chat_id: str) -> None:
        if self._workspace_controller.busy or self._operation_lock.locked():
            self._show_chat_action_error(tr("connection.wait_send"))
            return
        loaded = await self._load_chat_action(chat_id)
        if loaded is None:
            return
        chat, origin = loaded
        state = self._workspace_state
        if state is None or state.chat.id != chat.id:
            return
        reason = self._connection_block_reason(state)
        if reason:
            self._show_chat_action_error(reason)
            return
        if not await self._workspace_controller.flush_editor():
            return
        if not self._chat_action_matches(origin):
            return
        self._discard_connection_change()
        self._workspace_request_id += 1
        self._cancel_estimate_metadata()
        self._workspace_controller.invalidate_connection_context()
        self._interaction.invalidate_connection_context(chat.id)
        change = _ConnectionChange(
            self._session_generation, self._connection_request, chat
        )
        self._connection_change = change
        self._show_connection_provider_choice(change)

    def _show_connection_provider_choice(
        self, change: _ConnectionChange, message: str = ""
    ) -> None:
        if not self._connection_matches(change, credential=False):
            return
        self._close_connection_dialog()

        async def choose(provider: ProviderId) -> None:
            if self._connection_dialog is selector.control:
                await self.select_connection_provider(provider)

        async def cancel() -> None:
            if self._connection_change is change:
                await self.cancel_connection_change()

        selector = ProviderSwitchDialog(
            change.chat.provider_id, choose, cancel, message=message
        )
        self._provider_switch_dialog = selector
        self._connection_dialog = selector.control
        self._page.show_dialog(selector.control)
        self._page.update()

    async def select_connection_provider(self, provider: ProviderId) -> None:
        change = self._connection_change
        if (
            not isinstance(provider, ProviderId)
            or change is None
            or not self._connection_matches(change, credential=False)
        ):
            return
        if provider is change.chat.provider_id:
            await self.cancel_connection_change()
            return
        if self._workspace_controller.busy or self._operation_lock.locked():
            self._show_chat_action_error(tr("connection.wait_send"))
            return
        change = replace(
            change,
            target=provider,
            credential_revision=self._provider_revision(provider),
            budget=None,
        )
        self._connection_change = change
        if self._key_for_provider(provider) is None:
            self._close_connection_dialog()

            async def configure(target: ProviderId) -> None:
                if (
                    self._connection_dialog is dialog
                    and self._connection_matches(change, credential=False)
                    and target is change.target
                ):
                    self._connection_waiting_for_key = True
                    self._close_connection_dialog()
                    if self._on_provider_settings_for is not None:
                        await self._on_provider_settings_for(target)
                    elif self._on_provider_settings is not None:
                        await self._on_provider_settings()

            async def cancel() -> None:
                if self._connection_dialog is dialog:
                    await self.cancel_connection_change()

            dialog = build_missing_provider_key_dialog(provider, configure, cancel)
            self._connection_dialog = dialog
            self._page.show_dialog(dialog)
            self._page.update()
            return
        self._close_connection_dialog()
        self._creation_provider = provider
        self._sync_provider_metadata(provider, publish_balance=False)
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        self._catalog_service.clear_cache()
        self._show_catalog_loading()
        key = self._key_for_provider(provider)
        assert key is not None
        task = asyncio.current_task()
        self._catalog_task = task
        try:
            catalog = await self._catalog_service.get_catalog(key)
            if not self._connection_matches(change):
                return
            budget = await self._budget_service.get_chat_budget(
                change.chat.id, provider_id=provider
            )
        except asyncio.CancelledError:
            return
        except Exception:
            if self._connection_matches(change):
                await self.cancel_connection_change()
                self._show_chat_action_error(tr("connection.catalog_unavailable"))
            return
        finally:
            if self._catalog_task is task:
                self._catalog_task = None
        if not self._connection_matches(change):
            return
        if not catalog.available:
            await self.cancel_connection_change()
            self._show_chat_action_error(tr("connection.catalog_unavailable"))
            return
        self._connection_change = replace(change, budget=budget)
        self._catalog = catalog
        self._show_mode_selection()

    async def _review_connection_change(
        self, configuration: ChatLimitConfiguration
    ) -> None:
        change = self._connection_change
        model, mode = self._pending_model, self._pending_mode
        if (
            change is None
            or change.target is None
            or change.budget is None
            or model is None
            or mode is None
            or not self._connection_matches(change)
        ):
            return
        if configuration.token_limit != change.budget.token_limit:
            if self._new_limits_view is not None:
                self._new_limits_view.form.show_error(tr("connection.shared_tokens"))
                self._page.update()
            return
        self._close_connection_dialog()

        async def confirm() -> None:
            if self._connection_dialog is dialog:
                await self._confirm_connection_change(change, configuration)

        async def cancel() -> None:
            if self._connection_dialog is dialog:
                await self.cancel_connection_change()

        shown_budget = replace(
            change.budget,
            limits_configured=True,
            cost_limit=configuration.cost_limit,
            cost_limit_usd=configuration.cost_limit
            if configuration.currency.value == "USD"
            else None,
        )
        dialog = build_connection_confirmation(
            change.chat,
            model,
            mode,
            configuration.currency,
            configuration.cost_limit,
            confirm,
            cancel,
            token_limit=configuration.token_limit,
            budget=shown_budget,
        )
        self._connection_dialog = dialog
        self._page.show_dialog(dialog)
        self._page.update()

    async def _confirm_connection_change(
        self, change: _ConnectionChange, configuration: ChatLimitConfiguration
    ) -> None:
        model, mode, view = (
            self._pending_model,
            self._pending_mode,
            self._new_limits_view,
        )
        if (
            model is None
            or mode is None
            or view is None
            or change.target is None
            or self._operation_lock.locked()
            or self._workspace_controller.busy
            or not self._connection_matches(change)
        ):
            return
        view.form.set_busy(True)
        self._page.update()
        async with self._operation_lock:
            try:
                key = self._key_for_provider(change.target)
                if key is None:
                    return
                self._catalog_service.clear_cache()
                catalog = await self._catalog_service.get_catalog(key)
                if not self._connection_matches(change):
                    return
                # Reconfirm the exact selected model, including prices and
                # constraints. Never substitute a same-ID model or new price.
                if model not in (*catalog.free_models, *catalog.paid_models):
                    raise ChatPolicyError(tr("service.model_missing"))
                profiles = self._provider_profiles
                chat = await self._sending_service.switch_chat_connection(
                    change.chat.id,
                    expected_revision=change.chat.connection_revision,
                    model=model,
                    mode=mode,
                    catalog=catalog,
                    key_validity=profiles.key_validity_for(change.target)
                    if profiles is not None
                    else self._key_validity,
                    key_limit=profiles.key_limit_for(change.target)
                    if profiles is not None
                    else self._key_limit,
                    configuration=configuration,
                    dispatch_guard=lambda: self._connection_matches(change),
                )
            except (ChatPolicyError, ValueError, RuntimeError) as error:
                if self._connection_matches(change):
                    self._close_connection_dialog()
                    view.form.set_busy(False)
                    view.form.show_error(localized_error_text(error))
                    self._page.update()
                return
            except Exception:
                if self._connection_matches(change):
                    self._close_connection_dialog()
                    view.form.set_busy(False)
                    view.form.show_error(tr("connection.change_failed"))
                    self._page.update()
                return
        if not self._connection_matches(change):
            return
        self._discard_connection_change()
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        self._cancel_estimate_metadata()
        self._workspace_controller.invalidate_connection_context()
        self._interaction.invalidate_connection_context(chat.id)
        self._selected_provider = chat.provider_id
        self._screen = _ChatScreen.WORKSPACE
        await self._show_workspace(expected_generation=change.session)
        self._start_provider_refresh(chat.provider_id)

    async def request_new_chat(self) -> None:
        self._discard_connection_change()
        if self._provider_profiles is not None:
            self._creation_provider = self._provider_profiles.default_provider
            if self._provider_profiles.key_for(self._creation_provider) is None:
                await self._open_provider_settings()
                return
            self._sync_provider_metadata(self._creation_provider, publish_balance=False)
        if (
            self._disposed
            or self._screen is _ChatScreen.SECURITY
            or self._session_api_key is None
            or self._catalog_task is not None
            or (self._key_validity is KeyValidityState.INVALID)
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
        ):
            return
        generation = self._session_generation
        if not await self._workspace_controller.flush_editor():
            return
        if generation != self._session_generation or self._session_api_key is None:
            return
        task = asyncio.current_task()
        if task is None:
            return
        self._catalog_task = task
        self._catalog_request_id += 1
        request_id = self._catalog_request_id
        generation = self._session_generation
        api_key = self._key_for_provider(self._creation_provider)
        if api_key is None:
            self._catalog_task = None
            return
        credential_revision = self._provider_revision(self._creation_provider)
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
            or credential_revision != self._provider_revision(self._creation_provider)
            or api_key != self._key_for_provider(self._creation_provider)
        ):
            return
        self._catalog = catalog
        self._pending_mode = None
        self._show_mode_selection()

    async def cancel_new_chat(self) -> None:
        if self._connection_change is not None:
            await self.cancel_connection_change()
            return
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
        if self._screen is not _ChatScreen.MODE_SELECTION:
            return
        change = self._connection_change
        if change is not None and not self._connection_matches(change):
            return
        catalog = self._catalog
        if self._disposed or catalog is None or self._session_api_key is None:
            return
        if mode is ChatMode.FREE and not free_mode_allowed(self._key_validity):
            return
        if mode is ChatMode.PAID and (
            not paid_mode_allowed(
                self._key_validity, self._key_limit, self._creation_provider
            )
            or not catalog.available
            or not catalog.paid_models
        ):
            return
        self._pending_mode = mode
        self._pending_model = None
        models = catalog.free_models if mode is ChatMode.FREE else catalog.paid_models

        async def choose(model: CatalogModel) -> None:
            if (
                self._catalog is catalog
                and self._pending_mode is mode
                and self._connection_change is change
            ):
                await self.select_chat_model(model)

        async def cancel() -> None:
            if self._catalog is catalog and self._connection_change is change:
                await self.back_to_mode_selection()

        view = ModelSelectionView(
            mode,
            models,
            on_select=choose,
            on_cancel=cancel,
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
            or self._screen is not _ChatScreen.MODEL_SELECTION
        ):
            return
        if model.provider_id is not self._creation_provider:
            return
        change = self._connection_change
        if change is not None and not self._connection_matches(change):
            return
        catalog, mode = self._catalog, self._pending_mode
        candidates = (
            catalog.free_models if mode is ChatMode.FREE else catalog.paid_models
        )
        if model not in candidates:
            return
        self._pending_model = model

        async def submit(total: str, completion: str, cost: str | None) -> None:
            if (
                self._new_limits_view is view
                and self._pending_model is model
                and self._connection_change is change
            ):
                await self.submit_new_chat_limits(total, completion, cost)

        async def cancel() -> None:
            if self._new_limits_view is view and self._connection_change is change:
                await self.back_to_model_selection()

        view = NewChatLimitsView(
            mode,
            model,
            submit,
            cancel,
            initial_budget=change.budget if change is not None else None,
            preserve_tokens=change is not None,
            submit_label=tr("connection.review") if change is not None else None,
        )
        self._new_limits_view = view
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
        change = self._connection_change

        async def choose(model: CatalogModel) -> None:
            if self._catalog is catalog and self._connection_change is change:
                await self.select_chat_model(model)

        async def cancel() -> None:
            if self._catalog is catalog and self._connection_change is change:
                await self.back_to_mode_selection()

        view = ModelSelectionView(
            mode,
            models,
            on_select=choose,
            on_cancel=cancel,
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
                currency=model.currency,
            )
        except ValueError as error:
            view.form.show_error(localized_error_text(error))
            self._page.update()
            return
        if self._connection_change is not None:
            await self._review_connection_change(configuration)
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
                    cost_limit=configuration.cost_limit,
                    paid_confirmed=mode is ChatMode.PAID,
                )
            except (ChatPolicyError, ValueError) as error:
                if (
                    self._new_limits_view is view
                    and generation == self._session_generation
                ):
                    view.form.set_busy(False)
                    view.form.show_error(localized_error_text(error))
                    self._page.update()
                return
            except Exception:
                if (
                    self._new_limits_view is view
                    and generation == self._session_generation
                ):
                    view.form.set_busy(False)
                    view.form.show_error(tr("service.chat_create_failed"))
                    self._page.update()
                return
        if self._disposed or generation != self._session_generation:
            return
        self._selected_chat_id = chat.id
        self._selected_provider = chat.provider_id
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        await self._show_workspace(expected_generation=generation, scroll_to_end=True)

    async def select_chat(self, chat_id: str) -> None:
        if (
            self._disposed
            or self._screen is _ChatScreen.SECURITY
            or self._session_api_key is None
            or not _is_identifier(chat_id)
        ):
            return
        generation = self._session_generation
        if not await self._workspace_controller.flush_editor():
            return
        if generation != self._session_generation or self._session_api_key is None:
            return
        self._discard_connection_change()
        self._invalidate_catalog_request()
        self._catalog = None
        self._pending_mode = None
        self._pending_model = None
        self._new_limits_view = None
        self._dismiss_chat_dialog()
        self._workspace_controller.cancel_confirmation_for_navigation()
        self._cancel_estimate_metadata()
        self._workspace_controller.begin_navigation(chat_id)
        self._selected_chat_id = chat_id
        await self._show_workspace(expected_generation=generation)

    def _chat_action_matches(self, context: _ChatActionContext | None) -> bool:
        return (
            context is not None
            and not self._disposed
            and self.session_active
            and context.session == self._session_generation
            and context.request == self._dialog_request_id
            and context.view is self._workspace_view
            and context.chat_id == self._selected_chat_id
            and self._workspace_state is not None
            and self._workspace_state.chat.connection_revision
            == context.connection_revision
            and self._screen is _ChatScreen.WORKSPACE
        )

    async def _load_chat_action(
        self, chat_id: str
    ) -> tuple[Chat, _ChatActionContext] | None:
        if (
            self._disposed
            or not self.session_active
            or self._workspace_view is None
            or self._selected_chat_id != chat_id
            or self._delete_chat_id is not None
            or self._rename_dialog is not None
            or self._dialog_request_pending
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or not _is_identifier(chat_id)
        ):
            return None
        self._dialog_request_pending = True
        self._dialog_request_id += 1
        context = _ChatActionContext(
            self._session_generation,
            self._dialog_request_id,
            self._workspace_view,
            chat_id,
            self._workspace_state.chat.connection_revision
            if self._workspace_state is not None
            else 0,
        )
        try:
            chat = await self._chat_service.get_chat(chat_id)
        except Exception:
            if self._chat_action_matches(context):
                self._show_chat_action_error(tr("service.chat_open_failed"))
            return None
        finally:
            if context.request == self._dialog_request_id:
                self._dialog_request_pending = False
        if (
            chat is None
            or not self._chat_action_matches(context)
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
        ):
            return None
        return chat, context

    async def request_delete_chat(self, chat_id: str) -> None:
        loaded = await self._load_chat_action(chat_id)
        if loaded is None:
            return
        chat, context = loaded

        async def confirm(target: str) -> None:
            if self._delete_dialog is dialog and self._chat_action_matches(context):
                await self.confirm_delete_chat(target)

        def cancel() -> None:
            if self._delete_dialog is dialog and self._chat_action_matches(context):
                self.cancel_delete_chat()

        dialog = build_delete_chat_dialog(chat, on_confirm=confirm, on_cancel=cancel)
        self._delete_chat_id = chat_id
        self._delete_dialog = dialog
        self._chat_dialog_context = context
        self._page.show_dialog(dialog)

    async def confirm_delete_chat(self, chat_id: str) -> None:
        context, dialog = self._chat_dialog_context, self._delete_dialog
        if (
            not self._chat_action_matches(context)
            or dialog is None
            or self._delete_chat_id != chat_id
            or self._operation_lock.locked()
            or self._workspace_controller.busy
        ):
            return
        assert context is not None
        async with self._operation_lock:
            if not await self._workspace_controller.flush_editor():
                return
            if (
                not self._chat_action_matches(context)
                or self._delete_dialog is not dialog
            ):
                return
            for button in dialog.actions:
                button.disabled = True
            self._page.update()
            try:
                deleted = await self._chat_service.delete_chat(chat_id)
            except Exception:
                if self._chat_action_matches(context) and self._delete_dialog is dialog:
                    self._dismiss_chat_dialog()
                    self._show_chat_action_error(tr("service.chat_delete_failed"))
                return
            if (
                not self._chat_action_matches(context)
                or self._delete_dialog is not dialog
            ):
                return
            self._dismiss_chat_dialog()
            if not deleted:
                self._show_chat_action_error(tr("service.delete_already_missing"))
                return
            self._drafts.forget(chat_id)
            self._clear_workspace()
            self._selected_chat_id = None
            await self._show_workspace(expected_generation=context.session)

    def cancel_delete_chat(self) -> None:
        if self._delete_dialog is not None:
            self._dismiss_chat_dialog()

    async def request_rename_chat(self, chat_id: str) -> None:
        loaded = await self._load_chat_action(chat_id)
        if loaded is None:
            return
        chat, context = loaded

        async def confirm(target: str, title: str) -> None:
            if self._rename_dialog is dialog and self._chat_action_matches(context):
                await self.confirm_rename_chat(target, title)

        def cancel() -> None:
            if self._rename_dialog is dialog and self._chat_action_matches(context):
                self.cancel_rename_chat()

        dialog = RenameChatDialog(chat, on_confirm=confirm, on_cancel=cancel)
        self._rename_dialog = dialog
        self._chat_dialog_context = context
        self._page.show_dialog(dialog.control)

    async def confirm_rename_chat(self, chat_id: str, title: str) -> None:
        dialog, context = self._rename_dialog, self._chat_dialog_context
        if (
            dialog is None
            or not self._chat_action_matches(context)
            or self._operation_lock.locked()
            or self._workspace_controller.busy
            or dialog.chat_id != chat_id
            or not isinstance(title, str)
        ):
            return
        assert context is not None
        dialog.set_busy(True)
        dialog.show_error("")
        self._page.update()
        async with self._operation_lock:
            if not await self._workspace_controller.flush_editor():
                if self._rename_dialog is dialog and self._chat_action_matches(context):
                    dialog.set_busy(False)
                    dialog.show_error(DRAFT_STORAGE_MESSAGE)
                    self._page.update()
                return
            if (
                not self._chat_action_matches(context)
                or self._rename_dialog is not dialog
            ):
                return
            error_message = ""
            try:
                renamed = await self._chat_service.rename_chat(chat_id, title)
                if not renamed:
                    error_message = tr("service.chat_already_missing")
            except ValueError as error:
                error_message = localized_error_text(error)
            except Exception:
                error_message = tr("service.title_save_failed")
            if (
                not self._chat_action_matches(context)
                or self._rename_dialog is not dialog
            ):
                return
            if error_message:
                dialog.set_busy(False)
                dialog.show_error(error_message)
                self._page.update()
                return
            self._dismiss_chat_dialog()
            await self._show_workspace(expected_generation=context.session)

    def cancel_rename_chat(self) -> None:
        if self._rename_dialog is not None:
            self._dismiss_chat_dialog()

    def _show_chat_action_error(self, message: str) -> None:
        if self._workspace_view is not None:
            self._workspace_view.show_message(message)
            self._page.update()

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
        if (
            self._provider_profiles is not None
            and self._key_for_provider(self._selected_provider) is None
        ):
            await self._open_provider_settings()
            return
        await self._workspace_controller.submit_message(text)

    async def request_retry_turn(self, turn_id: str) -> None:
        if (
            self._provider_profiles is not None
            and self._key_for_provider(self._selected_provider) is None
        ):
            await self._open_provider_settings()
            return
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
        if self._provider_profiles is not None:
            await self._provider_profiles.refresh(
                self._current_provider(), validate_key=True
            )
            await self.refresh_provider_state()
            return
        if (
            self._disposed
            or self._screen is _ChatScreen.SECURITY
            or self._session_api_key is None
            or self._key_validation_task is not None
        ):
            return
        generation = self._session_generation
        self._start_balance_refresh()
        if not self._start_key_validation():
            return
        await self._refresh_after_key_validation(generation)

    def _start_balance_refresh(self, *, after_response: bool = False) -> None:
        if self._provider_profiles is not None:
            self._start_provider_refresh(
                self._current_provider(), after_response=after_response
            )
            return
        if (
            self._disposed
            or self._session_api_key is None
            or self._balance_service is None
        ):
            return
        if self._balance_task is not None:
            self._balance_task.cancel()
        generation = self._session_generation
        key = self._session_api_key
        service = self._balance_service

        async def refresh() -> None:
            try:
                await service.refresh(key, after_response=after_response)
            finally:
                if (
                    generation == self._session_generation
                    and self._balance_task is asyncio.current_task()
                ):
                    self._balance_task = None

        self._balance_task = asyncio.create_task(refresh())

    def _model_request_finished(self) -> None:
        """Account refresh belongs to the session even after chat navigation."""
        self._start_balance_refresh(after_response=True)

    def _publish_account_balance(self, snapshot: AccountBalanceSnapshot) -> None:
        if self._disposed or self._session_api_key is None:
            return
        if self._balance_expiry is not None:
            self._balance_expiry.cancel()
            self._balance_expiry = None
        self._workspace_controller.set_account_balance(snapshot)
        if snapshot.state is AccountBalanceState.CURRENT:
            generation = self._session_generation

            def expire() -> None:
                if (
                    generation == self._session_generation
                    and not self._disposed
                    and self._balance_service is not None
                    and self.session_active
                ):
                    self._balance_service.expire_if_needed()

            self._balance_expiry = asyncio.get_running_loop().call_later(300, expire)

    def _cancel_balance_refresh(self) -> None:
        for task in self._provider_tasks:
            task.cancel()
        self._provider_tasks.clear()
        if self._balance_task is not None:
            self._balance_task.cancel()
            self._balance_task = None
        if self._balance_expiry is not None:
            self._balance_expiry.cancel()
            self._balance_expiry = None
        if self._balance_service is not None:
            self._balance_service.invalidate()

    async def request_key_replacement(self) -> None:
        """Передаёт замену API-ключа из свободной разблокированной сессии."""
        if self._provider_profiles is not None:
            await self._open_provider_settings()
            return
        view = self._workspace_view
        if (
            self._disposed
            or self._screen is _ChatScreen.SECURITY
            or self._session_api_key is None
            or view is None
            or view.key_replacement_busy
            or self._key_validation_in_progress
            or self._key_validation_task is not None
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or self._dialog_request_pending
            or self._chat_dialog_context is not None
            or self._operation_lock.locked()
            or self._key_replacement_generation is not None
            or self._security_generation is not None
        ):
            return
        generation = self._session_generation
        self._key_replacement_generation = generation
        self._cancel_estimate_metadata()
        self._catalog_service.clear_cache()
        self._key_metadata_updated_at = None
        self._workspace_controller.set_estimate_metadata(None, self._key_limit, None)
        try:
            await self._on_replace_key()
        finally:
            if self._key_replacement_generation == generation:
                self._key_replacement_generation = None

    async def set_paid_without_confirmation(self, chat_id: str, enabled: bool) -> None:
        if (
            self._disposed
            or not self.session_active
            or self._screen is not _ChatScreen.WORKSPACE
            or self._workspace_view is None
            or self._selected_chat_id != chat_id
            or self._security_generation is not None
            or self._profile_deletion_origin is not None
            or self._key_replacement_generation is not None
            or self._chat_dialog_context is not None
            or self._dialog_request_pending
        ):
            return
        await self._workspace_controller.set_paid_without_confirmation(chat_id, enabled)

    async def request_security_settings(self) -> None:
        """Передаёт выдачу кода только из свободной защищённой сессии."""
        view = self._workspace_view
        if (
            self._disposed
            or self._screen is not _ChatScreen.WORKSPACE
            or self._session_api_key is None
            or self._on_security is None
            or view is None
            or view.security_busy
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or self._dialog_request_pending
            or self._chat_dialog_context is not None
            or self._operation_lock.locked()
            or self._key_replacement_generation is not None
            or self._security_generation is not None
        ):
            return
        generation = self._session_generation
        self._security_generation = generation
        try:
            await self._on_security()
        finally:
            if self._security_generation == generation:
                self._security_generation = None

    async def suspend_for_security(self) -> bool:
        """Сохраняет редактор и отзывает callbacks чата, оставляя вход действующим."""
        view = self._workspace_view
        if (
            self._disposed
            or not self.session_active
            or self._screen is not _ChatScreen.WORKSPACE
            or view is None
            or view.security_busy
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or self._dialog_request_pending
            or self._chat_dialog_context is not None
            or self._operation_lock.locked()
            or self._key_replacement_generation is not None
        ):
            return False
        generation = self._session_generation
        self._screen = _ChatScreen.SECURITY
        self._workspace_request_id += 1
        self._dialog_request_id += 1
        self._workspace_controller.capture_editor()
        if not await self.flush_drafts():
            if generation == self._session_generation and self.session_active:
                self._screen = _ChatScreen.WORKSPACE
            return False
        if (
            self._disposed
            or generation != self._session_generation
            or not self.session_active
        ):
            return False
        self._workspace_controller.deactivate()
        self._cancel_estimate_metadata()
        self._clear_workspace()
        return True

    async def request_profile_deletion(
        self, workspace: ChatWorkspaceView, generation: int
    ) -> None:
        """Принимает действие только от конкретного текущего представления."""
        if (
            self._on_delete_profile is None
            or self._disposed
            or self._screen is not _ChatScreen.WORKSPACE
            or workspace is not self._workspace_view
            or generation != self._session_generation
            or self._profile_deletion_origin is not None
            or self._security_generation is not None
            or not self.session_active
            or workspace.security_busy
            or self._workspace_controller.busy
            or self._workspace_controller.has_dialog()
            or self._dialog_request_pending
            or self._chat_dialog_context is not None
            or self._operation_lock.locked()
            or self._key_replacement_generation is not None
        ):
            return
        origin = WorkspaceDeletionOrigin(generation, workspace)
        self._profile_deletion_origin = origin
        try:
            await self._on_delete_profile(origin)
        finally:
            if self._screen is not _ChatScreen.SECURITY:
                if self._profile_deletion_origin is origin:
                    self._profile_deletion_origin = None

    async def suspend_for_profile_deletion(
        self, origin: WorkspaceDeletionOrigin
    ) -> bool:
        if (
            self._profile_deletion_origin is not origin
            or origin.workspace is not self._workspace_view
            or origin.generation != self._session_generation
        ):
            return False
        return await self.suspend_for_security()

    def profile_deletion_origin_current(self, origin: WorkspaceDeletionOrigin) -> bool:
        return (
            not self._disposed
            and self.session_active
            and self._profile_deletion_origin is origin
            and origin.generation == self._session_generation
            and self._screen is _ChatScreen.SECURITY
        )

    async def resume_profile_deletion(self, origin: WorkspaceDeletionOrigin) -> None:
        if self.profile_deletion_origin_current(origin):
            self._profile_deletion_origin = None
            await self.resume_after_security()

    def show_profile_deletion_error(self, message: str) -> None:
        if not self._disposed and self._workspace_view is not None:
            if self._workspace_view.composer is not None:
                self._workspace_view.show_message(message)
            else:
                self._page.show_dialog(ft.SnackBar(content=ft.Text(message)))
            self._page.update()

    def handle_language_change(self) -> None:
        if not self._disposed and self._workspace_view is not None:
            self._workspace_view.refresh_menu_language()

    async def resume_after_security(self) -> None:
        """Возвращает выбранный чат после закрытия настроек, пока сессия открыта."""
        if (
            self._disposed
            or not self.session_active
            or self._screen is not _ChatScreen.SECURITY
        ):
            return
        self._screen = _ChatScreen.WORKSPACE
        self._workspace_controller.activate()
        await self._show_workspace(expected_generation=self._session_generation)

    @property
    def draft_save_failed(self) -> bool:
        return self._draft_save_failed

    def begin_lock(self) -> None:
        """Отзывает доступ до первого await и удерживает последнюю правку в памяти."""
        if self._disposed:
            return
        self._workspace_controller.capture_editor()
        self._drafts.prepare_lock()
        if self._data_access is not None:
            self._data_access.lock()
        self.deactivate()

    async def lock_application(self) -> None:
        if self._disposed or self._session_api_key is None:
            return
        self.begin_lock()
        await self._on_lock()
        generation = self._session_generation
        saved = await self.flush_drafts()
        if (
            not saved
            and not self._disposed
            and generation == self._session_generation
            and not self.session_active
        ):
            await self._on_lock()

    async def flush_drafts(self) -> bool:
        if not await self._workspace_controller.flush_editor():
            self._draft_save_failed = True
            return False
        try:
            await self._drafts.flush_all()
        except DraftStorageError:
            self._draft_save_failed = True
            if self._workspace_view is not None:
                self._workspace_view.show_message(DRAFT_STORAGE_MESSAGE)
                self._page.update()
            return False
        self._draft_save_failed = False
        return True

    def _start_key_validation(self, *, metadata_only: bool = False) -> bool:
        if self._provider_profiles is not None:
            self._start_provider_refresh(self._current_provider(), validate_key=True)
            return False
        if (
            self._disposed
            or self._session_api_key is None
            or self._key_validation_task is not None
        ):
            return False
        self._key_validation_in_progress = not metadata_only
        generation = self._session_generation
        api_key = self._session_api_key
        self._key_validation_task = asyncio.create_task(
            self._run_key_validation(api_key, generation, metadata_only=metadata_only)
        )
        return True

    async def _run_key_validation(
        self, api_key: str, generation: int, *, metadata_only: bool = False
    ) -> None:
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
            if metadata_only and key_validity in {
                KeyValidityState.UNKNOWN,
                KeyValidityState.RESTRICTED,
            }:
                # A background metadata failure is not an inference-key
                # rejection. Retain the last known snapshot and its old time.
                self._push_estimate_metadata()
                return
            self._key_validity = key_validity
            self._key_limit = key_limit
            self._key_metadata_updated_at = (
                datetime.now(UTC) if key_validity is KeyValidityState.VALID else None
            )
            if key_validity is KeyValidityState.INVALID:
                self._catalog = None
                self._pending_mode = None
                self._catalog_service.clear_cache()
                self._cancel_estimate_metadata()
                self._invalidate_catalog_request()
            if metadata_only and key_validity is KeyValidityState.VALID:
                # Update only the compact metrics and estimate. Reloading
                # SQLite/history here could overtake the send's own UI refresh.
                self._push_estimate_metadata()
                return
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
        if self._screen is _ChatScreen.SECURITY:
            return

        can_use_free = free_mode_allowed(self._key_validity)
        can_use_paid = paid_mode_allowed(
            self._key_validity, self._key_limit, self._current_provider()
        )
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
            or self._deferred_workspace
            or self._screen is _ChatScreen.SECURITY
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
                self._report_storage_error(tr("service.chats_load_failed"))
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
        self._selected_provider = (
            selected.provider_id
            if selected is not None
            else (
                self._provider_profiles.default_provider
                if self._provider_profiles is not None
                else self._selected_provider
            )
        )
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
                    self._report_storage_error(tr("service.history_load_failed"))
                return
            if not self._workspace_request_matches(expected_generation, request_id):
                return
            selected = interaction_state.chat
            chats = [selected if chat.id == selected.id else chat for chat in chats]
            self._selected_provider = selected.provider_id
            try:
                await self._drafts.load(selected.id)
            except DraftStorageError:
                if self._workspace_request_matches(expected_generation, request_id):
                    if self._workspace_view is not None:
                        self._workspace_view.show_message(DRAFT_STORAGE_MESSAGE)
                        self._page.update()
                    else:
                        self._report_storage_error(tr("service.draft_load_failed"))
                return
        if not self._workspace_request_matches(expected_generation, request_id):
            return
        if self._provider_profiles is not None:
            self._sync_provider_metadata(self._selected_provider)
        self._workspace_state = interaction_state
        if self._workspace_view is not None and self._screen is _ChatScreen.WORKSPACE:
            self._workspace_view.update_workspace(
                chats,
                selected,
                interaction_state,
                key_validity=self._key_validity,
                key_limit=self._key_limit,
                key_validation_in_progress=self._key_validation_in_progress,
                provider_id=self._selected_provider,
                key_display=self._key_display_for(self._selected_provider),
            )
            self._workspace_controller.bind(self._workspace_view, interaction_state)
            self._push_estimate_metadata()
            self._page.update()
        else:
            self._clear_workspace()
            generation = self._session_generation

            async def delete_profile() -> None:
                await self.request_profile_deletion(workspace, generation)

            async def paid_confirmation_changed(chat_id: str, enabled: bool) -> None:
                if (
                    self._workspace_view is workspace
                    and generation == self._session_generation
                ):
                    await self.set_paid_without_confirmation(chat_id, enabled)

            async def test_screen_lock() -> None:
                if (
                    self._workspace_view is workspace
                    and generation == self._session_generation
                    and self._on_test_screen_lock is not None
                ):
                    await self.request_screen_lock_test()

            async def test_sleep() -> None:
                if (
                    self._workspace_view is workspace
                    and generation == self._session_generation
                    and self._on_test_sleep is not None
                ):
                    await self.request_sleep_test()

            workspace = ChatWorkspaceView(
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
                provider_id=self._selected_provider,
                key_display=self._key_display_for(self._selected_provider),
                on_retry_key=self.request_key_revalidation,
                on_replace_key=self.request_key_replacement,
                on_change_provider=self.request_change_provider,
                on_paid_confirmation_changed=paid_confirmation_changed,
                protection_status=self._protection_status,
                on_test_screen_lock=(
                    test_screen_lock if self._on_test_screen_lock is not None else None
                ),
                on_test_sleep=(test_sleep if self._on_test_sleep is not None else None),
                on_delete_profile=(
                    delete_profile if self._on_delete_profile is not None else None
                ),
                on_security=(
                    self.request_security_settings
                    if self._on_security is not None
                    else None
                ),
                session_watch_status=self._session_watch_status,
            )
            self._workspace_view = workspace
            self._workspace_controller.bind(self._workspace_view, interaction_state)
            self._push_estimate_metadata()
            self._replace_page(self._workspace_view.control)
        self._screen = _ChatScreen.WORKSPACE
        self._start_estimate_metadata_refresh()
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
            and not self._deferred_workspace
            and self._screen is not _ChatScreen.SECURITY
            and self.session_active
            and generation == self._session_generation
            and request_id == self._workspace_request_id
        )

    def _set_workspace_state(self, state: ActiveChatState | None) -> None:
        self._workspace_state = state
        if state is None:
            self._observed_attempt = None
            self._completed_attempt = None
            return
        last = state.last_request
        marker = (
            state.chat.id,
            last.attempt_sequence,
            last.turn_id,
            last.sent_at,
            last.state,
        )
        previous = self._observed_attempt
        self._observed_attempt = marker
        completed = last.state in {LastRequestState.FINAL, LastRequestState.UNKNOWN}
        completed_marker = (
            state.chat.id,
            last.attempt_sequence,
            last.turn_id,
            last.sent_at,
        )
        if previous is None or previous[0] != state.chat.id:
            self._completed_attempt = completed_marker if completed else None
            return
        if (
            completed
            and completed_marker != self._completed_attempt
            and last.chronology_known
            and last.sent_at is not None
        ):
            self._completed_attempt = completed_marker
            # Fresh inference may have adopted a new price. Discard the old
            # model before publishing any estimate, then refresh at most once
            # per short interval. A pending reservation never enters here.
            self._cancel_estimate_metadata()
            self._catalog_service.clear_cache()
            self._estimate_refresh_key = True
            self._push_estimate_metadata()
            self._start_estimate_metadata_refresh()

    def _session_context(self) -> ChatSessionContext | None:
        if self._disposed or self._session_api_key is None:
            return None
        provider = self._selected_provider
        key = self._key_for_provider(provider)
        if key is None:
            return None
        profiles = self._provider_profiles
        revision = self._provider_revision(provider)
        return ChatSessionContext(
            key,
            profiles.key_validity_for(provider)
            if profiles is not None
            else self._key_validity,
            profiles.key_limit_for(provider)
            if profiles is not None
            else self._key_limit,
            provider_id=provider,
            connection_revision=self._workspace_state.chat.connection_revision
            if self._workspace_state is not None
            else 0,
            credential_revision=revision,
            request_finished=(
                lambda: self._start_provider_refresh(provider, after_response=True)
            )
            if self._provider_profiles is not None
            else None,
            apply_key_state=(
                lambda validity, limit: self._apply_provider_key_state(
                    provider, key, revision, validity, limit
                )
            )
            if profiles is not None
            else None,
        )

    def _apply_provider_key_state(
        self,
        provider: ProviderId,
        key: str,
        revision: object,
        validity: KeyValidityState,
        limit: KeyLimitInfo,
    ) -> None:
        if self._provider_profiles is None or revision != self._provider_revision(
            provider
        ):
            return
        status = {
            KeyValidityState.INVALID: KeyValidationStatus.INVALID,
            KeyValidityState.RESTRICTED: KeyValidationStatus.RESTRICTED,
            KeyValidityState.UNVERIFIED: KeyValidationStatus.UNVERIFIED,
        }.get(validity)
        if validity is KeyValidityState.VALID:
            if (
                provider is ProviderId.OPENROUTER
                and limit.state is KeyLimitState.UNKNOWN
            ):
                return
            status = (
                KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT
                if limit.state in {KeyLimitState.NOT_SET, KeyLimitState.UNKNOWN}
                else (
                    KeyValidationStatus.ACCEPTED
                    if limit.state is KeyLimitState.AVAILABLE
                    else KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED
                )
            )
        if status is not None:
            self._provider_profiles.apply_validation(
                provider,
                key,
                KeyValidationResult(status, limit.remaining, provider_id=provider),
            )

    def _apply_interaction_key_state(
        self,
        validity: KeyValidityState,
        limit: KeyLimitInfo,
    ) -> None:
        if self._disposed or self._session_api_key is None:
            return
        if self._provider_profiles is not None:
            # The provider manager owns validity per credential revision. Its
            # callback will publish the selected provider's current snapshot.
            self._sync_provider_metadata(self._selected_provider)
            self._push_estimate_metadata()
            return
        if validity is not self._key_validity or limit != self._key_limit:
            # Interaction results can echo cached free-mode metadata, and a
            # long generation finishes after its paid preflight key check.
            # Neither is an exact metadata receipt time for this controller.
            self._key_metadata_updated_at = None
        self._key_validity = validity
        self._key_limit = limit
        if validity is KeyValidityState.INVALID:
            self._catalog = None
            self._pending_mode = None
            self._pending_model = None
            self._catalog_service.clear_cache()
            self._cancel_estimate_metadata()
            self._invalidate_catalog_request()
        self._push_estimate_metadata()
        self._start_estimate_metadata_refresh()

    def _push_estimate_metadata(self) -> None:
        """Publish only cached metadata without reading a key or editor text."""
        state = self._workspace_state
        model: CatalogModel | None = None
        if self.session_active and self._key_validity is not KeyValidityState.INVALID:
            if state is not None:
                if (
                    state.chat.provider_id is ProviderId.OPENROUTER
                    and state.chat.requested_model_id == FREE_ROUTER_MODEL.id
                ):
                    model = FREE_ROUTER_MODEL
                else:
                    catalog = self._peek_catalog(state.chat.provider_id)
                    if catalog is not None:
                        model = next(
                            (
                                item
                                for item in (*catalog.free_models, *catalog.paid_models)
                                if item.id == state.chat.requested_model_id
                                and item.provider_id is state.chat.provider_id
                            ),
                            None,
                        )
        self._workspace_controller.set_estimate_metadata(
            model, self._key_limit, self._key_metadata_updated_at
        )
        self._schedule_estimate_metadata_expiry()

    def _schedule_estimate_metadata_expiry(self) -> None:
        handle = self._estimate_metadata_expiry
        self._estimate_metadata_expiry = None
        if handle is not None:
            handle.cancel()
        state = self._workspace_state
        if (
            not self.session_active
            or self._disposed
            or state is None
            or self._workspace_view is None
            or state.chat.requested_model_id == FREE_ROUTER_MODEL.id
        ):
            return
        remaining = self._catalog_service.cache_remaining_seconds()
        if remaining is None or remaining <= 0:
            return
        self._estimate_metadata_expiry = asyncio.get_running_loop().call_later(
            remaining,
            self._expire_estimate_metadata,
            self._session_generation,
            self._estimate_metadata_request,
        )

    def _expire_estimate_metadata(self, generation: int, request: int) -> None:
        self._estimate_metadata_expiry = None
        if (
            self._disposed
            or not self.session_active
            or self._screen is not _ChatScreen.WORKSPACE
            or generation != self._session_generation
            or request != self._estimate_metadata_request
        ):
            return
        self._push_estimate_metadata()

    def _start_estimate_metadata_refresh(self) -> bool:
        """Start at most one catalog refresh, independently of typing and UI."""
        if (
            self._disposed
            or not self.session_active
            or self._workspace_view is None
            or self._workspace_state is None
            or self._screen is not _ChatScreen.WORKSPACE
            or self._key_replacement_generation is not None
            or self._key_validity is KeyValidityState.INVALID
            or (
                self._workspace_state.chat.requested_model_id == FREE_ROUTER_MODEL.id
                and not self._estimate_refresh_key
            )
            or self._estimate_metadata_task is not None
            or (self._peek_catalog() is not None and not self._estimate_refresh_key)
        ):
            return False
        generation = self._session_generation
        request = self._estimate_metadata_request
        api_key = self._key_for_provider(self._selected_provider)
        if api_key is None:
            return False
        self._estimate_metadata_task = asyncio.create_task(
            self._run_estimate_metadata_refresh(api_key, generation, request)
        )
        return True

    async def _run_estimate_metadata_refresh(
        self, api_key: str, generation: int, request: int
    ) -> None:
        current = asyncio.current_task()
        try:
            delay = max(0.0, self._estimate_metadata_after - time.monotonic())
            if delay:
                await asyncio.sleep(delay)
            if not self._estimate_metadata_matches(generation, request, current):
                return
            self._estimate_metadata_after = time.monotonic() + 30.0
            try:
                state = self._workspace_state
                if (
                    state is not None
                    and state.chat.requested_model_id != FREE_ROUTER_MODEL.id
                ):
                    await self._catalog_service.get_catalog(api_key)
            except asyncio.CancelledError:
                return
            except Exception:
                return
            if not self._estimate_metadata_matches(generation, request, current):
                return
            self._push_estimate_metadata()
            if self._estimate_refresh_key:
                self._estimate_refresh_key = False
                self._start_key_validation(metadata_only=True)
        except asyncio.CancelledError:
            return
        finally:
            if self._estimate_metadata_task is current:
                self._estimate_metadata_task = None

    def _estimate_metadata_matches(
        self, generation: int, request: int, task: asyncio.Task[object] | None
    ) -> bool:
        return (
            not self._disposed
            and self.session_active
            and self._screen is _ChatScreen.WORKSPACE
            and generation == self._session_generation
            and request == self._estimate_metadata_request
            and self._estimate_metadata_task is task
            and self._key_replacement_generation is None
        )

    def _cancel_estimate_metadata(self) -> None:
        self._estimate_metadata_request += 1
        handle = self._estimate_metadata_expiry
        self._estimate_metadata_expiry = None
        if handle is not None:
            handle.cancel()
        task = self._estimate_metadata_task
        self._estimate_metadata_task = None
        if task is None or task.done():
            return
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        if task is not current:
            task.cancel()

    def _show_catalog_loading(self) -> None:
        self._workspace_request_id += 1
        self._clear_workspace()
        self._screen = _ChatScreen.CATALOG_LOADING
        self._replace_page(CatalogLoadingView(self.cancel_new_chat).control)

    def _show_mode_selection(self) -> None:
        catalog = self._catalog
        if catalog is None:
            return
        self._workspace_request_id += 1
        change = self._connection_change

        async def choose(mode: ChatMode) -> None:
            if self._catalog is catalog and self._connection_change is change:
                await self.select_chat_mode(mode)

        async def cancel() -> None:
            if self._catalog is catalog and self._connection_change is change:
                await self.cancel_new_chat()

        self._clear_workspace()
        view = ModeSelectionView(
            catalog,
            key_validity=self._key_validity,
            key_limit=self._key_limit,
            on_select=choose,
            on_cancel=cancel,
            provider_id=self._creation_provider,
        )
        self._screen = _ChatScreen.MODE_SELECTION
        self._replace_page(view.control)

    def _replace_page(self, control: ft.Control) -> None:
        if self._disposed:
            return
        if self._navigation_hidden:
            return
        if self._present_content is not None:
            self._present_content(control)
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
        self._dialog_request_id += 1
        self._dialog_request_pending = False
        dialogs = (
            self._delete_dialog,
            self._rename_dialog.control if self._rename_dialog is not None else None,
        )
        self._delete_chat_id = None
        self._delete_dialog = None
        self._rename_dialog = None
        self._chat_dialog_context = None
        for dialog in dialogs:
            if dialog is not None:
                # Снимаем только принадлежащий действию диалог, сохраняя чужой стек.
                dialog.open = False
                try:
                    dialog.update()
                except (RuntimeError, AssertionError):
                    pass


def _is_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
