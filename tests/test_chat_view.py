"""Проверки адаптивного представления чатов и поиска моделей."""

from __future__ import annotations

import inspect
import sys
import unittest
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import (  # noqa: E402
    BudgetState,
    ChatBudget,
    calculate_remaining_budget,
)
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    ModelCatalog,
)
from chat_interaction_controller import ActiveChatState  # noqa: E402
from i18n import tr  # noqa: E402
from providers.models import Currency, ProviderId  # noqa: E402
from ui.chat_view import ChatWorkspaceView, _key_status_presentation  # noqa: E402
from ui.model_selection_view import (  # noqa: E402
    ModelSelectionView,
    ModeSelectionView,
    filter_models,
    key_access_mode_notice,
    key_limit_mode_notice,
)
from ui.styles import SUCCESS_COLOR, WARNING_COLOR  # noqa: E402


class FakePage:
    def __init__(self, width: int) -> None:
        self.width = width
        self.height = 700
        self.dialogs: list[ft.DialogControl] = []
        self.drawer: ft.NavigationDrawer | None = None

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        dialog.open = True
        self.dialogs.append(dialog)

    async def show_drawer(self) -> None:
        return None

    async def close_drawer(self) -> None:
        return None


class ChatViewTests(unittest.IsolatedAsyncioTestCase):
    def test_narrow_layout_uses_drawer_and_wide_layout_does_not(self) -> None:
        async def callback(*_args: str) -> None:
            return None

        chat = _chat()
        narrow_page = FakePage(400)
        narrow = ChatWorkspaceView(
            cast(ft.Page, narrow_page),
            [chat],
            chat,
            _state(chat),
            on_new_chat=callback,
            on_select_chat=callback,
            on_rename_chat=callback,
            on_delete_chat=callback,
            on_lock=callback,
            on_send_message=callback,
            on_retry_turn=callback,
            on_configure_limits=callback,
            on_edit_limits=callback,
            on_release_unknown=callback,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            key_validation_in_progress=False,
            on_retry_key=callback,
            on_replace_key=callback,
        )
        self.assertIsInstance(narrow_page.drawer, ft.NavigationDrawer)

        wide_page = FakePage(1000)
        wide = ChatWorkspaceView(
            cast(ft.Page, wide_page),
            [chat],
            chat,
            _state(chat),
            on_new_chat=callback,
            on_select_chat=callback,
            on_rename_chat=callback,
            on_delete_chat=callback,
            on_lock=callback,
            on_send_message=callback,
            on_retry_turn=callback,
            on_configure_limits=callback,
            on_edit_limits=callback,
            on_release_unknown=callback,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            key_validation_in_progress=False,
            on_retry_key=callback,
            on_replace_key=callback,
        )
        self.assertIsNone(wide_page.drawer)

        narrow.dispose()
        wide.dispose()

    def test_model_search_matches_name_and_id(self) -> None:
        async def select_model(_model: CatalogModel) -> None:
            return None

        async def cancel() -> None:
            return None

        first = CatalogModel(
            id="vendor/alpha",
            name="Alpha model",
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
        )
        second = CatalogModel(
            id="vendor/beta",
            name="Beta model",
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
        )
        view = ModelSelectionView(
            ChatMode.FREE,
            (first, second),
            on_select=select_model,
            on_cancel=cancel,
        )

        from tests.test_chat_menu import walk

        selections = [
            control
            for control in walk(view.results)
            if isinstance(control, ft.Button)
            and control.content == tr("catalog.select")
        ]
        self.assertEqual(len(selections), 2)
        self.assertEqual(filter_models((first, second), " ALPHA "), (first,))
        self.assertEqual(filter_models((first, second), "vendor/beta"), (second,))

    def test_key_limit_notices_do_not_confuse_limit_with_balance(self) -> None:
        zero_notice, _ = key_limit_mode_notice(
            KeyLimitInfo.from_validated_remaining(Decimal("0"))
        )
        null_notice, _ = key_limit_mode_notice(
            KeyLimitInfo.from_validated_remaining(None)
        )
        positive_notice, _ = key_limit_mode_notice(
            KeyLimitInfo.from_validated_remaining(Decimal("5"))
        )

        self.assertEqual(
            zero_notice,
            tr("key.exhausted_notice"),
        )
        self.assertEqual(tr("key.unlimited_notice"), null_notice)
        self.assertNotIn("положитель", null_notice.casefold())
        self.assertEqual(tr("key.available_notice", amount="5"), positive_notice)

    def test_paid_button_is_closed_for_zero_but_not_null_or_positive(self) -> None:
        async def select_mode(_mode: ChatMode) -> None:
            return None

        async def cancel() -> None:
            return None

        paid_model = CatalogModel(
            id="vendor/paid",
            name="Paid model",
            prompt_price_per_token=Decimal("0.000001"),
            completion_price_per_token=Decimal("0.000002"),
        )
        catalog = ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(paid_model,),
            available=True,
        )

        zero_view = ModeSelectionView(
            catalog,
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(Decimal("0")),
            select_mode,
            cancel,
        )
        null_view = ModeSelectionView(
            catalog,
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
            select_mode,
            cancel,
        )
        positive_view = ModeSelectionView(
            catalog,
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(Decimal("5")),
            select_mode,
            cancel,
        )

        self.assertFalse(zero_view.free_button.disabled)
        self.assertTrue(zero_view.paid_button.disabled)
        self.assertFalse(null_view.paid_button.disabled)
        self.assertFalse(positive_view.paid_button.disabled)

    async def test_vsegpt_modes_hide_dead_free_card_and_keep_refresh_distinct(self):
        from i18n import configure_localization, get_preferences, set_language
        from preferences import PreferencesStore

        previous_preferences = get_preferences()
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, previous_preferences)

        def mounted(root):
            yield root
            content = getattr(root, "content", None)
            if isinstance(content, ft.Control):
                yield from mounted(content)
            for child in getattr(root, "controls", ()):
                yield from mounted(child)

        callback = AsyncMock()
        for available in (True, False):
            for language in ("en", "ru"):
                set_language(language)
                refresh = AsyncMock()
                view = ModeSelectionView(
                    ModelCatalog((), (), available=available),
                    KeyValidityState.UNVERIFIED,
                    KeyLimitInfo.unknown(),
                    callback,
                    callback,
                    provider_id=ProviderId.VSEGPT,
                    on_refresh=refresh,
                )
                controls = list(mounted(view.control))
                self.assertNotIn(view.free_button, controls)
                self.assertIn(view.paid_button, controls)
                self.assertIn(view.refresh_button, controls)
                assert view.refresh_button is not None
                handler = cast(
                    Callable[[ft.Event[ft.TextButton]], Awaitable[None]],
                    view.refresh_button.on_click,
                )
                await handler(ft.Event(name="click", control=view.refresh_button))
                refresh.assert_awaited_once()
                callback.assert_not_awaited()
        set_language("ru")

    def test_unavailable_router_is_only_new_chat_fallback_not_connection_switch(self):
        callback = AsyncMock()
        catalog = ModelCatalog((FREE_ROUTER_MODEL,), (), available=False)
        new_chat = ModeSelectionView(
            catalog, KeyValidityState.VALID, KeyLimitInfo.unknown(), callback, callback
        )
        changing = ModeSelectionView(
            catalog,
            KeyValidityState.VALID,
            KeyLimitInfo.unknown(),
            callback,
            callback,
            changing_provider=True,
        )
        self.assertFalse(new_chat.free_button.disabled)
        self.assertTrue(changing.free_button.disabled)
        self.assertTrue(new_chat.paid_button.disabled)
        self.assertTrue(changing.paid_button.disabled)

    def test_vsegpt_missing_key_limit_is_normal_and_does_not_disable_paid_models(self):
        async def callback(*_args):
            return None

        model = CatalogModel(
            id="vendor/paid",
            name="A VSEGPT model",
            prompt_price_per_token=Decimal("0.01"),
            completion_price_per_token=Decimal("0.02"),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
        )
        unknown = KeyLimitInfo.unknown()
        view = ModeSelectionView(
            ModelCatalog((), (model,), available=True),
            KeyValidityState.VALID,
            unknown,
            callback,
            callback,
        )
        self.assertFalse(view.paid_button.disabled)
        notice, _color = key_access_mode_notice(
            KeyValidityState.VALID,
            unknown,
            Currency.RUB,
            provider_id=ProviderId.VSEGPT,
        )
        self.assertEqual(notice, "")
        text, color, retry, _replace = _key_status_presentation(
            KeyValidityState.VALID, unknown, ProviderId.VSEGPT
        )
        self.assertEqual(color, SUCCESS_COLOR)
        self.assertIn("VSEGPT", text)
        self.assertNotIn("OpenRouter", text)
        self.assertFalse(retry)
        for validity in (KeyValidityState.UNVERIFIED, KeyValidityState.INVALID):
            with self.subTest(validity=validity):
                notice, notice_color = key_access_mode_notice(
                    validity, unknown, Currency.RUB, provider_id=ProviderId.VSEGPT
                )
                self.assertTrue(notice)
                self.assertNotEqual(notice_color, SUCCESS_COLOR)

    def test_vsegpt_unverified_key_is_never_presented_as_accepted(self):
        for key_limit in (
            KeyLimitInfo.unknown(),
            KeyLimitInfo.from_validated_remaining(None),
        ):
            text, color, retry, _replace = _key_status_presentation(
                KeyValidityState.UNVERIFIED, key_limit, ProviderId.VSEGPT
            )
            self.assertIn("VSEGPT", text)
            self.assertNotEqual(color, SUCCESS_COLOR)
            self.assertTrue(retry)
            notice, color = key_access_mode_notice(
                KeyValidityState.UNVERIFIED,
                key_limit,
                Currency.RUB,
                provider_id=ProviderId.VSEGPT,
            )
            self.assertTrue(notice)
            self.assertEqual(color, WARNING_COLOR)

    def test_empty_vsegpt_catalog_does_not_fall_back_to_openrouter_cap_warning(self):
        from tests.test_chat_menu import texts

        async def callback(*_args):
            return None

        view = ModeSelectionView(
            ModelCatalog((), (), available=False),
            KeyValidityState.VALID,
            KeyLimitInfo.unknown(),
            callback,
            callback,
            provider_id=ProviderId.VSEGPT,
        )
        self.assertTrue(view.paid_button.disabled)
        self.assertTrue(view.free_button.disabled)
        rendered = texts(view.control)
        self.assertNotIn(tr("key.unknown_limit_notice"), rendered)
        self.assertNotIn(tr("key.unlimited_notice"), rendered)
        self.assertFalse(any("OpenRouter" in text for text in rendered))

    async def test_key_validity_controls_current_connection_but_not_creation_entry(
        self,
    ) -> None:
        async def callback(*_args: str) -> None:
            return None

        chat = _chat()
        invalid = ChatWorkspaceView(
            cast(ft.Page, FakePage(400)),
            [chat],
            chat,
            _state(chat),
            on_new_chat=callback,
            on_select_chat=callback,
            on_rename_chat=callback,
            on_delete_chat=callback,
            on_lock=callback,
            on_send_message=callback,
            on_retry_turn=callback,
            on_configure_limits=callback,
            on_edit_limits=callback,
            on_release_unknown=callback,
            key_validity=KeyValidityState.INVALID,
            key_limit=KeyLimitInfo.unknown(),
            key_validation_in_progress=False,
            on_retry_key=callback,
            on_replace_key=callback,
        )
        restricted = ChatWorkspaceView(
            cast(ft.Page, FakePage(400)),
            [chat],
            chat,
            _state(chat),
            on_new_chat=callback,
            on_select_chat=callback,
            on_rename_chat=callback,
            on_delete_chat=callback,
            on_lock=callback,
            on_send_message=callback,
            on_retry_turn=callback,
            on_configure_limits=callback,
            on_edit_limits=callback,
            on_release_unknown=callback,
            key_validity=KeyValidityState.RESTRICTED,
            key_limit=KeyLimitInfo.unknown(),
            key_validation_in_progress=False,
            on_retry_key=callback,
            on_replace_key=callback,
        )

        await invalid.open_menu()
        await restricted.open_menu()
        self.assertIsNotNone(invalid.retry_key_button)
        self.assertIsNotNone(invalid.replace_key_button)
        self.assertTrue(invalid._new_chat_allowed)
        self.assertIsNotNone(restricted.retry_key_button)
        self.assertIsNotNone(restricted.replace_key_button)
        self.assertTrue(restricted._new_chat_allowed)

        invalid_message, *_ = _key_status_presentation(
            KeyValidityState.INVALID,
            KeyLimitInfo.unknown(),
        )
        restricted_message, *_ = _key_status_presentation(
            KeyValidityState.RESTRICTED,
            KeyLimitInfo.unknown(),
        )
        self.assertEqual(invalid_message, tr("key.invalid_short"))
        self.assertEqual(restricted_message, tr("key.restricted_short"))

        # All rendered creation entries are usable despite the current key,
        # while an in-flight send or an old disposed callback remains blocked.
        create = AsyncMock()
        invalid._on_new_chat = create
        buttons = list(invalid._new_chat_controls.values())
        self.assertGreaterEqual(len(buttons), 2)
        for button in buttons:
            self.assertFalse(button.disabled)
            handler = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
            await handler(ft.Event(name="click", control=button))
        self.assertEqual(create.await_count, len(buttons))
        invalid.set_sending(True)
        for button in buttons:
            self.assertTrue(button.disabled)
            handler = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
            await handler(ft.Event(name="click", control=button))
        self.assertEqual(create.await_count, len(buttons))
        invalid.set_sending(False)
        self.assertTrue(all(not button.disabled for button in buttons))
        invalid.dispose()
        restricted.dispose()
        for button in buttons:
            handler = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
            await handler(ft.Event(name="click", control=button))
        self.assertEqual(create.await_count, len(buttons))

    async def test_rename_and_delete_buttons_await_callbacks_with_chat_id(
        self,
    ) -> None:
        renamed: list[str] = []
        deleted: list[str] = []

        async def no_op(*_args: str) -> None:
            return None

        async def rename(chat_id: str) -> None:
            renamed.append(chat_id)

        async def delete(chat_id: str) -> None:
            deleted.append(chat_id)

        chat = _chat()
        view = ChatWorkspaceView(
            cast(ft.Page, FakePage(400)),
            [chat],
            chat,
            _state(chat),
            on_new_chat=no_op,
            on_select_chat=no_op,
            on_rename_chat=rename,
            on_delete_chat=delete,
            on_lock=no_op,
            on_send_message=no_op,
            on_retry_turn=no_op,
            on_configure_limits=no_op,
            on_edit_limits=no_op,
            on_release_unknown=no_op,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
            key_validation_in_progress=False,
            on_retry_key=no_op,
            on_replace_key=no_op,
        )
        await view.open_menu()
        assert view.rename_button is not None
        assert view.delete_button is not None
        rename_handler = cast(
            Callable[[ft.Event[ft.TextButton]], Awaitable[None]],
            view.rename_button.on_click,
        )
        delete_handler = cast(
            Callable[[ft.Event[ft.TextButton]], Awaitable[None]],
            view.delete_button.on_click,
        )

        self.assertTrue(inspect.iscoroutinefunction(rename_handler))
        self.assertTrue(inspect.iscoroutinefunction(delete_handler))
        old_delete_button = view.delete_button
        assert old_delete_button is not None
        await rename_handler(ft.Event(name="click", control=view.rename_button))
        await delete_handler(ft.Event(name="click", control=old_delete_button))
        self.assertFalse(view.menu_open)
        self.assertIs(view.delete_button, old_delete_button)
        self.assertEqual(deleted, [chat.id])
        await view.open_menu()
        assert view.delete_button is not None
        delete_handler = cast(
            Callable[[ft.Event[ft.TextButton]], Awaitable[None]],
            view.delete_button.on_click,
        )
        await delete_handler(ft.Event(name="click", control=view.delete_button))

        self.assertEqual(renamed, [chat.id])
        self.assertEqual(deleted, [chat.id, chat.id])
        self.assertFalse(view.menu_open)
        view.dispose()
        await rename_handler(ft.Event(name="click", control=view.rename_button))
        await delete_handler(ft.Event(name="click", control=old_delete_button))
        self.assertEqual(renamed, [chat.id])
        self.assertEqual(deleted, [chat.id, chat.id])


def _chat() -> Chat:
    timestamp = datetime(2026, 3, 1, tzinfo=UTC)
    return Chat(
        id="chat",
        title="Новый чат",
        mode=ChatMode.FREE,
        requested_model_id="openrouter/free",
        requested_model_name="Автоматический выбор бесплатной модели",
        prompt_price_per_token=Decimal("0"),
        completion_price_per_token=Decimal("0"),
        created_at=timestamp,
        updated_at=timestamp,
    )


def _state(chat: Chat, *, configured: bool = True) -> ActiveChatState:
    budget = ChatBudget(
        chat_id=chat.id,
        limits_configured=configured,
        token_limit=1000 if configured else None,
        max_completion_tokens=64 if configured else None,
        prompt_tokens_used=0,
        completion_tokens_used=0,
        total_tokens_used=0,
        reserved_tokens=0,
        cost_limit_usd=Decimal("0") if chat.mode is ChatMode.FREE else Decimal("1"),
        cost_used_usd=Decimal("0"),
        cost_reserved_usd=Decimal("0"),
        state=BudgetState.READY if configured else BudgetState.UNCONFIGURED,
        updated_at=chat.updated_at,
    )
    return ActiveChatState(
        chat=chat,
        messages=(),
        turns=(),
        budget=budget,
        remaining=calculate_remaining_budget(budget),
    )


if __name__ == "__main__":
    unittest.main()
