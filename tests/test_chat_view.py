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
from ui.chat_view import ChatWorkspaceView, _key_status_presentation  # noqa: E402
from ui.model_selection_view import (  # noqa: E402
    ModelSelectionView,
    ModeSelectionView,
    filter_models,
    key_limit_mode_notice,
)


class FakePage:
    def __init__(self, width: int) -> None:
        self.width = width
        self.drawer: ft.NavigationDrawer | None = None

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

        self.assertEqual(len(view.results.controls), 2)
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
            "Расходный лимит этого ключа исчерпан. Бесплатный режим остаётся доступным",
        )
        self.assertIn("не установлен отдельный расходный лимит", null_notice)
        self.assertNotIn("положитель", null_notice.casefold())
        self.assertIn("Доступный лимит ключа: 5 USD", positive_notice)
        self.assertIn("не баланс аккаунта", positive_notice)

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

    def test_key_validity_controls_retry_replace_and_new_chat(self) -> None:
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

        self.assertIsNotNone(invalid.retry_key_button)
        self.assertIsNotNone(invalid.replace_key_button)
        self.assertFalse(invalid._new_chat_allowed)
        self.assertIsNotNone(restricted.retry_key_button)
        self.assertIsNone(restricted.replace_key_button)
        self.assertTrue(restricted._new_chat_allowed)

        invalid_message, *_ = _key_status_presentation(
            KeyValidityState.INVALID,
            KeyLimitInfo.unknown(),
        )
        restricted_message, *_ = _key_status_presentation(
            KeyValidityState.RESTRICTED,
            KeyLimitInfo.unknown(),
        )
        self.assertEqual(
            invalid_message,
            "Сохранённый ключ OpenRouter недействителен или отозван. "
            "Замените ключ, чтобы продолжить работу с моделями",
        )
        self.assertEqual(
            restricted_message,
            "OpenRouter отклонил проверку разрешений ключа. "
            "Бесплатный запрос также может завершиться ошибкой",
        )

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
        await rename_handler(ft.Event(name="click", control=view.rename_button))
        await delete_handler(ft.Event(name="click", control=view.delete_button))

        self.assertEqual(renamed, [chat.id])
        self.assertEqual(deleted, [chat.id])


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
