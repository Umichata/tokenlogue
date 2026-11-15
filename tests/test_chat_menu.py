"""Поведение компактной шапки и панели параметров поверх переписки."""

from __future__ import annotations

import asyncio
import inspect
import sys
import unittest
from collections.abc import Awaitable, Callable
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
from chat.metrics import ChatMetricsSnapshot  # noqa: E402
from chat.models import Chat, ChatMode  # noqa: E402
from chat_interaction_controller import ActiveChatState  # noqa: E402
from i18n import (  # noqa: E402
    configure_localization,
    localize_tree,
    set_language,
    tr,
)
from preferences import PreferencesStore  # noqa: E402
from providers.models import Currency, ProviderId  # noqa: E402
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
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
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
            "key_display": "••••",
            "on_retry_key": callback("key"),
            "on_replace_key": callback("replace"),
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
            key_display=kwargs.get("key_display", "••••"),
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
                self.assertEqual(view.menu_button.tooltip, tr("chat.options"))
                self.assertEqual(view.menu_button.width, 48)
                self.assertFalse(view.menu_open)
                self.assertIsNone(view.send_notice)
                normal = texts(view.control)
                for label in (
                    "Ключ OpenRouter",
                    "Использовано токенов",
                    "ID модели",
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
        self.assertEqual(rows[tr("budget.remaining_money")], "—")
        self.assertEqual(rows[tr("budget.actual_cost")], "0,12 USD")
        self.assertEqual(rows[tr("budget.reserved_cost")], "0,03 USD")
        self.assertEqual(rows[tr("budget.reserved_tokens")], "123")
        self.assertIn(tr("budget.spending_limit"), rows)
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
        self.assertIs(view._menu_list.controls[-1], view.limits_button)
        self.assertNotIn(view.rename_button, list(walk(dialog)))
        self.assertNotIn(view.delete_button, list(walk(dialog)))

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

    async def test_empty_home_keeps_provider_context_through_key_menu_refresh(self):
        view = self.view(provider_id=ProviderId.VSEGPT)
        for language in ("en", "ru"):
            set_language(language)
            view.update_workspace(
                [],
                None,
                None,
                key_validity=KeyValidityState.VALID,
                key_limit=KeyLimitInfo.unknown(),
                key_validation_in_progress=False,
                provider_id=ProviderId.VSEGPT,
                key_display="••••",
            )
            await view.open_menu()
            assert view._key_panel is not None
            self.assertIn("VSEGPT", str(view._key_panel.message.value))
            self.assertNotIn("OpenRouter", str(view._key_panel.message.value))
            self.assertFalse(view._key_panel.limit_row.visible)
            self.assertNotIn(
                tr("key.limit_unknown_short"), texts(self.page.dialogs[-1])
            )
            # A new empty-Home provider context updates the same retained panel.
            panel = view._key_panel
            view.update_workspace(
                [],
                None,
                None,
                key_validity=KeyValidityState.VALID,
                key_limit=KeyLimitInfo.from_validated_remaining(Decimal("7.89")),
                key_validation_in_progress=False,
                provider_id=ProviderId.OPENROUTER,
                key_display="••••",
            )
            self.assertIs(view._key_panel, panel)
            self.assertTrue(panel.limit_row.visible)
            self.assertIn(
                "USD" if language == "ru" else "$",
                str(cast(ft.Text, panel.limit_row.controls[1]).value),
            )
            view.close_menu()
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
        self.assertIn(tr("key.checking"), texts(self.page.dialogs[-1]))
        self.assertEqual(self.calls, [])

    async def test_key_refresh_stays_open_with_same_controls_during_success_or_error(
        self,
    ) -> None:
        for result in (KeyValidityState.VALID, KeyValidityState.UNKNOWN):
            with self.subTest(result=result):
                view = self.view(key_validity=KeyValidityState.UNKNOWN)
                view.restore_editor("  Сохранить\n🙂 черновик  ")
                await view.open_menu()
                dialog, menu_list = view._menu_dialog, view._menu_list
                assert menu_list is not None and view.retry_key_button is not None
                started, release = asyncio.Event(), asyncio.Event()
                calls = 0

                async def refresh() -> None:
                    nonlocal calls
                    calls += 1
                    self.update(
                        view,
                        self.chat,
                        _state(self.chat),
                        key_validity=KeyValidityState.UNKNOWN,
                        key_validation_in_progress=True,
                    )
                    started.set()
                    await release.wait()
                    self.update(view, self.chat, _state(self.chat), key_validity=result)

                view._on_retry_key = refresh
                # Создаём обработчик с текущей тестовой реализацией сервиса.
                self.update(
                    view,
                    self.chat,
                    _state(self.chat),
                    key_validity=KeyValidityState.UNKNOWN,
                )
                button = view.retry_key_button
                assert button is not None
                panel = menu_list.controls[1]
                pending = asyncio.create_task(self.click(button))
                try:
                    await asyncio.wait_for(started.wait(), timeout=1)
                    self.assertTrue(view.menu_open)
                    self.assertIs(view._menu_dialog, dialog)
                    self.assertIs(view._menu_list, menu_list)
                    self.assertIs(menu_list.controls[1], panel)
                    self.assertIs(view.retry_key_button, button)
                    self.assertTrue(button.disabled)
                    await self.click(button)
                    self.assertEqual(calls, 1)
                finally:
                    release.set()
                    await pending
                self.assertTrue(view.menu_open)
                self.assertIs(view._menu_dialog, dialog)
                self.assertIs(view._menu_list, menu_list)
                self.assertIs(view.retry_key_button, button)
                self.assertFalse(button.disabled)
                self.assertEqual(view.editor_value, "  Сохранить\n🙂 черновик  ")
                self.assertEqual(len(self.page.dialogs), 1)
                view.dispose()
                self.page.dialogs.clear()

    async def test_valid_key_has_explicit_enabled_refresh_action(self) -> None:
        for limit in (
            KeyLimitInfo.unknown(),
            KeyLimitInfo.from_validated_remaining(None),
            KeyLimitInfo.from_validated_remaining(Decimal("0")),
            KeyLimitInfo.from_validated_remaining(Decimal("5")),
        ):
            with self.subTest(limit=limit):
                view = self.view(key_limit=limit)
                await view.open_menu()
                self.assertIsNotNone(view.retry_key_button)
                assert view.retry_key_button is not None
                self.assertEqual(view.retry_key_button.content, tr("key.refresh"))
                self.assertFalse(view.retry_key_button.disabled)
                await self.click(view.retry_key_button)
                self.assertTrue(view.menu_open)
                view.dispose()

    async def test_replacement_is_visible_for_all_states_limits_modes_and_layouts(
        self,
    ) -> None:
        for language in ("ru", "en"):
            set_language(language)
            for width in (420, 1280):
                self.page.width = width
                for validity in KeyValidityState:
                    for limit in (
                        KeyLimitInfo.unknown(),
                        KeyLimitInfo.from_validated_remaining(None),
                        KeyLimitInfo.from_validated_remaining(Decimal("0")),
                        KeyLimitInfo.from_validated_remaining(Decimal("5")),
                    ):
                        for mode in (ChatMode.FREE, ChatMode.PAID, None):
                            with self.subTest(
                                language=language,
                                width=width,
                                validity=validity,
                                limit=limit.state,
                                mode=mode,
                            ):
                                chat = replace(self.chat, mode=mode or ChatMode.FREE)
                                view = self.view(
                                    chat,
                                    _state(chat),
                                    key_validity=validity,
                                    key_limit=limit,
                                )
                                if mode is None:
                                    view.update_workspace(
                                        [],
                                        None,
                                        None,
                                        key_validity=validity,
                                        key_limit=limit,
                                        key_validation_in_progress=False,
                                    )
                                await view.open_menu()
                                button = view.replace_key_button
                                assert button is not None
                                self.assertTrue(button.visible)
                                self.assertFalse(button.disabled)
                                self.assertIn(
                                    tr(
                                        "connection.configure_key",
                                        provider="OpenRouter",
                                    ),
                                    texts(self.page.dialogs[-1]),
                                )
                                self.assertIsInstance(button.content, ft.Text)
                                assert isinstance(button.content, ft.Text)
                                self.assertFalse(button.content.no_wrap)
                                view.dispose()
                                self.page.dialogs.clear()

    async def test_replacement_stays_visible_and_rejects_queued_click_while_sending(
        self,
    ) -> None:
        view = self.view()
        view.restore_editor("  Сохранить\n🙂 черновик  ")
        await view.open_menu()
        button = view.replace_key_button
        assert button is not None
        view.set_sending(True)
        self.assertIs(view.replace_key_button, button)
        self.assertTrue(button.visible)
        self.assertTrue(button.disabled)
        self.assertIn(tr("key.replace_wait_send"), texts(self.page.dialogs[-1]))
        await self.click(button)
        self.assertTrue(view.menu_open)
        self.assertEqual(self.calls, [])
        self.assertEqual(view.editor_value, "  Сохранить\n🙂 черновик  ")
        view.set_sending(False)
        self.assertIs(view.replace_key_button, button)
        self.assertFalse(button.disabled)
        assert view._key_panel is not None
        self.assertFalse(view._key_panel.replacement_notice.visible)
        await self.click(button)
        self.assertFalse(view.menu_open)
        self.assertEqual(self.calls, [("replace", ())])
        await self.click(button)
        self.assertEqual(self.calls, [("replace", ())])

    async def test_replacement_callback_is_fresh_after_status_and_language_change(
        self,
    ) -> None:
        view = self.view()
        await view.open_menu()
        button = view.replace_key_button
        assert button is not None
        old_callback = button.on_click
        assert old_callback is not None
        original_dialog, original_list = view._menu_dialog, view._menu_list
        original_parent = next(
            control
            for control in walk(self.page.dialogs[-1])
            if isinstance(control, ft.Column) and button in control.controls
        )
        self.update(
            view,
            self.chat,
            _state(self.chat),
            key_validity=KeyValidityState.RESTRICTED,
        )
        set_language("en")
        localize_tree(self.page.dialogs[-1])
        self.assertIs(view.replace_key_button, button)
        self.assertIs(view._menu_dialog, original_dialog)
        self.assertIs(view._menu_list, original_list)
        self.assertIn(button, original_parent.controls)
        self.assertIn(
            tr("connection.configure_key", provider="OpenRouter"),
            texts(self.page.dialogs[-1]),
        )
        await cast(Callable[[ft.Event], Awaitable[None]], old_callback)(
            ft.Event(name="click", control=button)
        )
        self.assertEqual(self.calls, [])
        self.assertTrue(view.menu_open)
        await self.click(button)
        self.assertEqual(self.calls, [("replace", ())])
        self.assertFalse(view.menu_open)

    async def test_pending_key_refresh_rejects_queued_click_before_state_refresh(
        self,
    ) -> None:
        view = self.view(key_validity=KeyValidityState.UNKNOWN)
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def refresh() -> None:
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()

        view._on_retry_key = refresh
        await view.open_menu()
        button = view.retry_key_button
        assert button is not None
        pending = asyncio.create_task(self.click(button))
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            self.assertTrue(view.menu_open)
            self.assertTrue(button.disabled)
            await self.click(button)
            self.assertEqual(calls, 1)
        finally:
            release.set()
            await pending
        self.assertFalse(button.disabled)

    async def test_dismiss_or_chat_change_or_lock_does_not_reopen_after_refresh(
        self,
    ) -> None:
        for navigation in ("dismiss", "chat_change", "lock"):
            with self.subTest(navigation=navigation):
                view = self.view(key_validity=KeyValidityState.UNKNOWN)
                view.restore_editor("Синтетический черновик")
                started, release = asyncio.Event(), asyncio.Event()
                calls = 0

                async def refresh() -> None:
                    nonlocal calls
                    calls += 1
                    self.update(
                        view,
                        self.chat,
                        _state(self.chat),
                        key_validity=KeyValidityState.UNKNOWN,
                        key_validation_in_progress=True,
                    )
                    started.set()
                    await release.wait()
                    self.update(view, self.chat, _state(self.chat))

                view._on_retry_key = refresh
                await view.open_menu()
                button, dialog = view.retry_key_button, view._menu_dialog
                assert button is not None and dialog is not None
                pending = asyncio.create_task(self.click(button))
                try:
                    await asyncio.wait_for(started.wait(), timeout=1)
                    self.assertTrue(view.menu_open)
                    if navigation == "dismiss":
                        with patch.object(
                            ft.IconButton, "focus", new_callable=AsyncMock
                        ):
                            await view._menu_dismissed(
                                ft.Event(name="dismiss", control=dialog)
                            )
                    elif navigation == "chat_change":
                        other = replace(self.chat, id="other")
                        self.update(view, other, _state(other))
                    else:
                        view.dispose()
                    self.assertFalse(view.menu_open)
                finally:
                    release.set()
                    await pending
                await self.click(button)
                self.assertEqual(calls, 1)
                self.assertFalse(view.menu_open)
                self.assertEqual(len(self.page.dialogs), 1)
                if navigation == "dismiss":
                    self.assertEqual(view.editor_value, "Синтетический черновик")
                if navigation == "lock":
                    self.assertIsNone(self.page.drawer)
                view.dispose()
                self.page.dialogs.clear()

    async def test_chat_connection_uses_selected_provider_and_only_a_safe_label(self):
        async def change(chat_id: str):
            self.calls.append(("provider", (chat_id,)))

        view = self.view(
            provider_id=ProviderId.VSEGPT,
            key_display="•••• 7A2F",
            on_change_provider=change,
        )
        view.restore_editor("Keep this draft")
        await view.open_menu()
        dialog = self.page.dialogs[-1]
        self.assertIn("OpenRouter", texts(dialog))
        self.assertIn(
            tr("connection.masked_key", provider="OpenRouter", mask="•••• 7A2F"),
            texts(dialog),
        )
        self.assertIn(
            tr("connection.configure_key", provider="OpenRouter"), texts(dialog)
        )
        switch = view.change_provider_button
        assert switch is not None
        old_callback = switch.on_click
        assert old_callback is not None
        # A new provider for the same ID invalidates every old menu callback.
        other = replace(self.chat, provider_id=ProviderId.VSEGPT, currency=Currency.RUB)
        self.update(view, other, _state(other), key_display="•••• 9B3C")
        self.assertFalse(view.menu_open)
        result = cast(Callable[[ft.Event], Awaitable[None]], old_callback)(
            ft.Event(name="click", control=switch)
        )
        if inspect.isawaitable(result):
            await result
        self.assertFalse(self.calls)
        await view.open_menu()
        dialog = self.page.dialogs[-1]
        self.assertIn(
            tr("connection.masked_key", provider="VSEGPT", mask="•••• 9B3C"),
            texts(dialog),
        )
        assert view._key_panel is not None
        self.assertFalse(view._key_panel.limit_row.visible)
        self.assertEqual(view.editor_value, "Keep this draft")
        assert view.change_provider_button is not None
        await self.click(view.change_provider_button)
        self.assertEqual(self.calls, [("provider", (self.chat.id,))])

    async def test_missing_key_and_malformed_display_do_not_expose_a_credential(self):
        for display in (None, "sk-or-v1-ABCDEFGH7A2F"):
            view = self.view(key_display=display)
            await view.open_menu()
            dialog = self.page.dialogs[-1]
            joined = " ".join(texts(dialog))
            self.assertNotIn("sk-or-v1-ABCDEFGH7A2F", joined)
            if display is None:
                self.assertIn(tr("connection.no_key"), texts(dialog))
            view.dispose()
            self.assertIsNone(view._key_display)
            self.assertNotIn("7A2F", " ".join(texts(dialog)))

    async def test_mask_refresh_is_provider_local_and_dispose_clears_old_controls(self):
        view = self.view(key_display="•••• 7A2F")
        await view.open_menu()
        dialog = self.page.dialogs[-1]
        self.update(view, self.chat, _state(self.chat), key_display="•••• 4D8E")
        self.assertNotIn("7A2F", " ".join(texts(dialog)))
        self.assertIn("4D8E", " ".join(texts(dialog)))
        view.dispose()
        self.assertNotIn("4D8E", " ".join(texts(dialog)))

    async def test_metrics_from_same_chat_old_connection_cannot_reappear(self):
        view = self.view()
        state = _state(self.chat)
        current = ChatMetricsSnapshot(
            self.chat.id, self.chat.mode, state.remaining, state.last_request
        )
        assert view.metrics_strip is not None
        with patch.object(view.metrics_strip, "set_metrics") as apply:
            view.set_metrics(
                replace(current, provider_id=ProviderId.VSEGPT, currency=Currency.RUB)
            )
            view.set_metrics(replace(current, currency=Currency.RUB))
            view.set_metrics(replace(current, connection_revision=1))
            apply.assert_not_called()
            view.set_metrics(current)
            apply.assert_called_once_with(current)

    async def test_new_connection_rebinds_paid_toggle_and_chat_actions_without_losing_draft(
        self,
    ):
        async def paid_setting(chat_id, enabled):
            self.calls.append(("paid", (chat_id, enabled)))

        chat = replace(self.chat, mode=ChatMode.PAID, paid_without_confirmation=True)
        view = self.view(chat, _state(chat), on_paid_confirmation_changed=paid_setting)
        view.restore_editor("Exact draft survives")
        old_checkbox = view.paid_confirmation_checkbox
        old_rename = view.rename_button
        assert old_checkbox is not None and old_checkbox.on_change is not None
        old_change = old_checkbox.on_change
        target = replace(
            chat,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            paid_without_confirmation=False,
        )
        self.update(view, target, _state(target), key_display="•••• 9B3C")
        checkbox = view.paid_confirmation_checkbox
        assert checkbox is not None and checkbox.on_change is not None
        self.assertIsNot(checkbox, old_checkbox)
        self.assertFalse(checkbox.value)
        await cast(Callable[[ft.Event], Awaitable[None]], old_change)(
            ft.Event(name="change", control=old_checkbox)
        )
        assert old_rename is not None
        await self.click(old_rename)
        self.assertFalse(self.calls)
        checkbox.value = True
        await cast(Callable[[ft.Event], Awaitable[None]], checkbox.on_change)(
            ft.Event(name="change", control=checkbox)
        )
        self.assertEqual(self.calls, [("paid", (chat.id, True))])
        self.assertEqual(view.editor_value, "Exact draft survives")
        assert view.rename_button is not None
        await self.click(view.rename_button)
        self.assertEqual(self.calls[-1], ("rename", (chat.id,)))

    async def test_old_connection_refresh_cannot_clear_new_connection_busy_state(self):
        starts = [asyncio.Event(), asyncio.Event()]
        releases = [asyncio.Event(), asyncio.Event()]
        calls = 0

        async def refresh():
            nonlocal calls
            index = calls
            calls += 1
            starts[index].set()
            await releases[index].wait()

        view = self.view(on_retry_key=refresh)
        await view.open_menu()
        old_button = view.retry_key_button
        assert old_button is not None
        old = asyncio.create_task(self.click(old_button))
        await starts[0].wait()
        target = replace(
            self.chat, provider_id=ProviderId.VSEGPT, currency=Currency.RUB
        )
        self.update(view, target, _state(target), key_display="•••• 9B3C")
        await view.open_menu()
        new_button = view.retry_key_button
        assert new_button is not None
        self.assertFalse(new_button.disabled)
        new = asyncio.create_task(self.click(new_button))
        await starts[1].wait()
        releases[0].set()
        await old
        self.assertTrue(new_button.disabled)
        self.assertTrue(view._key_refresh_in_progress)
        releases[1].set()
        await new
        self.assertFalse(view._key_refresh_in_progress)


if __name__ == "__main__":
    unittest.main()
