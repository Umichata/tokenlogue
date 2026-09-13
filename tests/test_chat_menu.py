"""Поведение компактной шапки и панели параметров поверх переписки."""

from __future__ import annotations

import inspect
import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState  # noqa: E402
from chat.accounting import BudgetState, RemainingBudget  # noqa: E402
from chat.models import Chat, ChatMode  # noqa: E402
from chat_interaction_controller import ActiveChatState  # noqa: E402
from tests.test_chat_view import FakePage, _chat, _state  # noqa: E402
from ui.chat_view import ChatWorkspaceView  # noqa: E402


def walk(control: ft.Control):
    yield control
    for field in ("controls", "actions", "content", "title", "leading", "trailing"):
        value = getattr(control, field, None)
        children = value if isinstance(value, list) else [value]
        for child in children:
            if isinstance(child, ft.Control):
                yield from walk(child)


def texts(control: ft.Control) -> list[str]:
    result = []
    for child in walk(control):
        if isinstance(child, ft.Text) and child.value:
            result.append(child.value)
        if isinstance(child, (ft.Button, ft.TextButton)) and isinstance(
            child.content, str
        ):
            result.append(child.content)
    return result


class ChatMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.page = FakePage(420)
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.chat = _chat()

    def view(
        self, chat: Chat | None = None, state: ActiveChatState | None = None, **kwargs
    ) -> ChatWorkspaceView:
        chat = chat or self.chat

        def callback(name):
            async def invoke(*args: str) -> None:
                self.calls.append((name, args))

            return invoke

        options = {
            "key_validity": KeyValidityState.VALID,
            "key_limit": KeyLimitInfo.from_validated_remaining(None),
            "key_validation_in_progress": False,
            **kwargs,
        }
        return ChatWorkspaceView(
            cast(ft.Page, self.page),
            [chat],
            chat,
            state or _state(chat),
            on_new_chat=callback("new"),
            on_select_chat=callback("select"),
            on_rename_chat=callback("rename"),
            on_delete_chat=callback("delete"),
            on_lock=callback("lock"),
            on_send_message=callback("send"),
            on_retry_turn=callback("retry"),
            on_configure_limits=callback("configure"),
            on_edit_limits=callback("limits"),
            on_release_unknown=callback("release"),
            on_retry_key=callback("key"),
            on_replace_key=callback("replace"),
            on_draft_change=callback("draft"),
            **options,
        )

    async def click(self, control) -> None:
        result = control.on_click(ft.Event(name="click", control=control))
        if inspect.isawaitable(result):
            await result

    def update(
        self, view: ChatWorkspaceView, chat: Chat, state: ActiveChatState, **kwargs
    ) -> None:
        view.update_workspace(
            [chat],
            chat,
            state,
            key_validity=kwargs.get("key_validity", KeyValidityState.VALID),
            key_limit=kwargs.get(
                "key_limit", KeyLimitInfo.from_validated_remaining(None)
            ),
            key_validation_in_progress=kwargs.get("key_validation_in_progress", False),
        )

    async def test_both_layouts_keep_button_order_and_one_line_full_title_tooltip(
        self,
    ) -> None:
        title = "Длинное название: пользовательский текст; " * 3
        for width in (1280, 420):
            with self.subTest(width=width):
                self.page.width = width
                view = self.view(replace(self.chat, title=title))
                header = next(
                    c
                    for c in walk(view.control)
                    if isinstance(c, ft.Row) and view.menu_button in c.controls
                )
                icons = [
                    c.icon for c in header.controls if isinstance(c, ft.IconButton)
                ]
                self.assertEqual(
                    icons[-3:],
                    [ft.Icons.ADD, ft.Icons.LOCK_OUTLINE, ft.Icons.MORE_VERT],
                )
                self.assertIs(header.controls[-1], view.menu_button)
                text = next(c for c in header.controls if isinstance(c, ft.Text))
                self.assertEqual(text.value, title)
                self.assertEqual(text.tooltip, title)
                self.assertEqual(text.max_lines, 1)
                self.assertEqual(text.overflow, ft.TextOverflow.ELLIPSIS)
                self.assertEqual(view.menu_button.tooltip, "Параметры чата")
                self.assertEqual(view.menu_button.width, 48)
                self.assertFalse(view.menu_open)
                self.assertIsNone(view.send_notice)
                normal = texts(view.control)
                for label in (
                    "Ключ OpenRouter",
                    "Использовано токенов",
                    "ID модели",
                    "Переименовать",
                    "Удалить чат",
                ):
                    self.assertNotIn(label, normal)
                assert view.message_history is not None
                self.assertTrue(view.message_history.control.expand)

    async def test_open_close_resize_preserve_editor_history_and_do_not_call_services(
        self,
    ) -> None:
        view = self.view()
        assert view.composer is not None and view.message_history is not None
        composer, history = view.composer, view.message_history
        exact = "  Текст: строка;\n🙂 ещё\n "
        composer.set_value(exact)
        before = view._layout.content
        await self.click(view.menu_button)
        self.assertTrue(view.menu_open)
        self.assertIs(view._layout.content, before)
        dialog = self.page.dialogs[-1]
        assert isinstance(dialog, ft.AlertDialog)
        self.assertFalse(dialog.modal)
        self.assertEqual(dialog.alignment, ft.Alignment.TOP_RIGHT)
        with patch.object(ft.Control, "update"):
            view._handle_size_change(
                cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=1280, height=750))
            )
            view._handle_size_change(
                cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=420, height=700))
            )
        self.assertIs(view.composer, composer)
        self.assertIs(view.message_history, history)
        self.assertEqual(view.editor_value, exact)
        assert view._menu_container is not None
        assert (
            view._menu_container.width is not None
            and view._menu_container.height is not None
        )
        self.assertLessEqual(view._menu_container.width, 420 - 56)
        self.assertLessEqual(view._menu_container.height, 700 - 176)
        with patch.object(ft.IconButton, "focus", new_callable=AsyncMock) as focus:
            await view._menu_dismissed(ft.Event(name="dismiss", control=dialog))
            focus.assert_awaited_once()
        self.assertFalse(view.menu_open)
        self.assertEqual(view.editor_value, exact)
        self.assertEqual(self.calls, [])

    async def test_controls_never_have_two_live_parents(self) -> None:
        view = self.view()
        await view.open_menu()
        controls = [*walk(view.control), *walk(self.page.dialogs[-1])]
        self.assertEqual(len(controls), len({id(c) for c in controls}))

    async def test_action_closes_menu_and_old_action_cannot_target_new_chat(
        self,
    ) -> None:
        view = self.view()
        await view.open_menu()
        old_delete = view.delete_button
        assert old_delete is not None
        other = replace(self.chat, id="other", title="Другой чат")
        self.update(view, other, _state(other))
        self.assertFalse(view.menu_open)
        await self.click(old_delete)
        self.assertEqual(self.calls, [])
        await view.open_menu()
        assert view.rename_button is not None
        await self.click(view.rename_button)
        self.assertEqual(self.calls, [("rename", ("other",))])
        self.assertFalse(view.menu_open)

    async def test_sending_keeps_mutations_disabled_even_for_queued_click(self) -> None:
        view = self.view()
        await view.open_menu()
        rename = view.rename_button
        assert rename is not None
        view.set_sending(True)
        for button in (view.rename_button, view.delete_button, view.limits_button):
            assert button is not None
            self.assertTrue(button.disabled)
        await self.click(rename)
        self.assertEqual(self.calls, [])
        self.assertTrue(view.menu_open)

    async def test_paid_values_refresh_and_unknown_money_is_not_zero(self) -> None:
        chat = replace(self.chat, mode=ChatMode.PAID)
        state = _state(chat)
        budget = replace(
            state.budget,
            reserved_tokens=123,
            total_tokens_used=861,
            cost_used_usd=Decimal("0.12"),
            cost_reserved_usd=Decimal("0.03"),
            cost_limit_usd=Decimal("2"),
        )
        state = replace(
            state, budget=budget, remaining=RemainingBudget(100, None, False)
        )
        view = self.view(chat, state)
        await view.open_menu()
        dialog = self.page.dialogs[-1]
        rows = {
            cast(ft.Text, c.controls[0]).value: cast(ft.Text, c.controls[1]).value
            for c in walk(dialog)
            if isinstance(c, ft.Row)
            and len(c.controls) == 2
            and all(isinstance(item, ft.Text) for item in c.controls)
        }
        self.assertEqual(rows["Остаток денежного бюджета"], "—")
        self.assertEqual(rows["Фактическая стоимость"], "$0.12")
        self.assertEqual(rows["Зарезервированная стоимость"], "$0.03")
        self.assertEqual(rows["Зарезервировано токенов"], "123")
        self.assertIn("Лимит расходов", rows)
        updated = replace(
            state,
            budget=replace(budget, total_tokens_used=900, reserved_tokens=0),
            remaining=RemainingBudget(900, Decimal("0"), False),
        )
        self.update(view, chat, updated)
        self.assertTrue(view.menu_open)
        self.assertIn("900", texts(dialog))
        self.assertNotIn("123", texts(dialog))
        assert view._menu_list is not None
        self.assertIs(view._menu_list.controls[-1], view.delete_button)
        self.assertIsInstance(view._menu_list.controls[-2], ft.Divider)

    async def test_empty_chat_menu_has_only_key_state_and_no_chat_actions(self) -> None:
        view = self.view()
        view.update_workspace(
            [],
            None,
            None,
            key_validity=KeyValidityState.INVALID,
            key_limit=KeyLimitInfo.unknown(),
            key_validation_in_progress=False,
        )
        await view.open_menu()
        self.assertIsNone(view.rename_button)
        self.assertIsNone(view.delete_button)
        self.assertIsNone(view.limits_button)
        self.assertIsNotNone(view.replace_key_button)
        self.assertEqual(self.calls, [])

    async def test_blocking_reasons_remain_visible_and_key_check_is_explicit(
        self,
    ) -> None:
        for budget_state in (BudgetState.UNCONFIGURED, BudgetState.EXHAUSTED):
            state = _state(self.chat)
            state = replace(
                state,
                budget=replace(
                    state.budget,
                    state=budget_state,
                    limits_configured=budget_state is not BudgetState.UNCONFIGURED,
                ),
            )
            view = self.view(state=state)
            self.assertIsNotNone(view.send_notice)
            self.assertFalse(view.menu_open)
        invalid = self.view(
            key_validity=KeyValidityState.INVALID,
            key_limit=KeyLimitInfo(KeyLimitState.UNKNOWN),
        )
        self.assertIsNotNone(invalid.send_notice)
        await invalid.open_menu()
        self.assertEqual(self.calls, [])
        assert invalid.retry_key_button is not None
        await self.click(invalid.retry_key_button)
        self.assertEqual(self.calls, [("key", ())])

    async def test_menu_shows_key_validation_progress_without_another_check(
        self,
    ) -> None:
        view = self.view(
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
            key_validation_in_progress=True,
        )
        await view.open_menu()
        assert view.retry_key_button is not None
        self.assertTrue(view.retry_key_button.disabled)
        self.assertIn("Проверка ключа OpenRouter…", texts(self.page.dialogs[-1]))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
