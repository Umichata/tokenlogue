"""Behavioral contracts for compact metrics and the persistent estimate line."""

from __future__ import annotations

import asyncio
import sys
import unittest
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyLimitState  # noqa: E402
from chat.accounting import RemainingBudget  # noqa: E402
from chat.estimates import DraftEstimate, EstimateState  # noqa: E402
from chat.metrics import (  # noqa: E402
    ChatMetricsSnapshot,
    LastRequestMetrics,
    LastRequestState,
)
from chat.models import ChatMode  # noqa: E402
from i18n import set_language, tr  # noqa: E402
from tests import test_chat_menu as fixtures  # noqa: E402
from ui.chat_metrics import (  # noqa: E402
    ChatMetricsStrip,
    DraftEstimateLine,
    display_usd,
)
from ui.message_composer import MessageComposer  # noqa: E402


def editor_ancestor_ids(root: ft.Control, target: ft.Control) -> tuple[int, ...]:
    """Follow the live control tree, rather than only comparing the field object."""
    if root is target:
        return (id(root),)
    for name in ("controls", "content"):
        value = getattr(root, name, None)
        for child in value if isinstance(value, list) else [value]:
            if isinstance(child, ft.Control):
                try:
                    return (id(root), *editor_ancestor_ids(child, target))
                except LookupError:
                    pass
    raise LookupError("Target is not present in the live tree")


def editor_visible_slots(
    root: ft.Control, target: ft.Control
) -> tuple[tuple[int, int], ...]:
    """Model Flet's visible-child filtering before unkeyed Flutter widgets."""
    if root is target:
        return ()
    for name in ("controls", "content"):
        value = getattr(root, name, None)
        children = [
            child
            for child in (value if isinstance(value, list) else [value])
            if isinstance(child, ft.Control) and child.visible
        ]
        for index, child in enumerate(children):
            try:
                return ((id(root), index), *editor_visible_slots(child, target))
            except LookupError:
                pass
    raise LookupError("Target is not present in the visible tree")


class ChatMetricsUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fixture = fixtures.ChatMenuTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        control_updates = patch.object(ft.Control, "update")
        control_updates.start()
        self.addCleanup(control_updates.stop)

    def paid_view(self, **kwargs):
        chat = replace(
            self.fixture.chat,
            mode=ChatMode.PAID,
            paid_without_confirmation=True,
        )
        view = self.fixture.view(
            chat,
            on_paid_confirmation_changed=kwargs.pop(
                "on_paid_confirmation_changed", AsyncMock()
            ),
            **kwargs,
        )
        self.addCleanup(view.dispose)
        return chat, view

    async def test_single_persisted_checkbox_is_above_history_and_outside_menu(self):
        chat, view = self.paid_view()
        checkbox = view.paid_confirmation_checkbox
        strip, composer, history = (
            view.metrics_strip,
            view.composer,
            view.message_history,
        )
        assert checkbox is not None and strip is not None
        assert composer is not None and history is not None
        self.assertTrue(checkbox.value)
        self.assertIn(checkbox, fixtures.walk(strip.control))
        content = view._build_selected_chat(chat)
        assert isinstance(content, ft.Column)
        self.assertLess(
            content.controls.index(strip.control),
            content.controls.index(history.control),
        )
        self.assertEqual(
            [
                node
                for node in fixtures.walk(view.control)
                if isinstance(node, ft.Checkbox)
            ],
            [checkbox],
        )
        self.assertIsInstance(checkbox.tooltip, ft.Tooltip)
        tooltip = cast(ft.Tooltip, checkbox.tooltip)
        self.assertEqual(tooltip.trigger_mode, ft.TooltipTriggerMode.LONG_PRESS)
        self.assertEqual(tooltip.message, tr("metrics.without_confirmation_help"))
        self.assertTrue(checkbox.semantics_label)
        self.assertIsNotNone(checkbox.focus_color)
        await view.open_menu()
        assert view._menu_list is not None
        self.assertNotIn(checkbox, fixtures.walk(view._menu_list))
        self.assertFalse(
            any(
                isinstance(node, ft.Checkbox) for node in fixtures.walk(view._menu_list)
            )
        )
        view.close_menu()
        self.assertIs(view.paid_confirmation_checkbox, checkbox)
        self.fixture.update(view, chat, fixtures._state(chat))
        self.assertIs(view.paid_confirmation_checkbox, checkbox)
        self.assertIs(view.composer, composer)
        self.assertIs(view.message_history, history)
        self.assertTrue(checkbox.value)

    async def test_free_chat_has_no_paid_checkbox(self):
        view = self.fixture.view(on_paid_confirmation_changed=AsyncMock())
        self.addCleanup(view.dispose)
        self.assertIsNone(view.paid_confirmation_checkbox)
        self.assertFalse(
            any(isinstance(node, ft.Checkbox) for node in fixtures.walk(view.control))
        )

    async def test_strip_resize_uses_compact_groups_with_same_controls_and_editor(self):
        _chat, view = self.paid_view()
        strip, composer = view.metrics_strip, view.composer
        checkbox = view.paid_confirmation_checkbox
        assert strip is not None and composer is not None and checkbox is not None
        view.set_metrics(self.metrics(_chat.id))
        field, history = composer.message_field, view.message_history
        values, metadata = strip.values, strip.metadata
        text_sizes = values.size, metadata.size
        field.value = "Public draft with a preserved cursor"
        field.selection = ft.TextSelection(base_offset=6, extent_offset=11)
        selection = field.selection
        for language in ("en", "ru"):
            set_language(language)
            view.refresh_menu_language()
            for width in (1280, 420, 360, 1280):
                view._handle_size_change(
                    cast(
                        ft.LayoutSizeChangeEvent,
                        SimpleNamespace(width=width, height=700),
                    )
                )
                self.assertIs(view.metrics_strip, strip)
                self.assertIs(view.paid_confirmation_checkbox, checkbox)
                self.assertIs(view.composer, composer)
                self.assertIs(view.message_history, history)
                self.assertIs(composer.message_field, field)
                self.assertIs(field.selection, selection)
                self.assertEqual(field.value, "Public draft with a preserved cursor")
                self.assertIs(strip.values, values)
                self.assertIs(strip.metadata, metadata)
                self.assertEqual((values.size, metadata.size), text_sizes)
                nodes = list(fixtures.walk(view.control))
                self.assertEqual(nodes.count(checkbox), 1)
                self.assertEqual(nodes.count(metadata), 1)
                self.assertEqual(nodes.count(values), 1)
                if width < 640:
                    self.assertIs(strip.control.content, strip.compact_column)
                    self.assertTrue(metadata.expand)
                    self.assertIn(strip.checkbox_row, strip.compact_header.controls)
                    self.assertIn(metadata, strip.compact_header.controls)
                    self.assertIn(values, strip.compact_values.controls)
                else:
                    self.assertIs(strip.control.content, strip.row)
                    self.assertIsNone(metadata.expand)

    async def test_short_height_releases_space_without_rebuilding_editor_or_history(
        self,
    ):
        _chat, view = self.paid_view()
        composer, history = view.composer, view.message_history
        checkbox, strip = view.paid_confirmation_checkbox, view.metrics_strip
        assert composer is not None and history is not None
        assert checkbox is not None and strip is not None
        field = composer.message_field
        field.value = "Public draft\nwith preserved selection 🙂"
        field.selection = ft.TextSelection(base_offset=3, extent_offset=9)
        selection = field.selection
        ancestors = editor_ancestor_ids(view.control, field)
        visible_slots = editor_visible_slots(view.control, field)
        actions, footer = view._chat_actions_row, view._privacy_footer
        buttons = tuple(view._chat_actions.controls)
        view.set_sending(True)
        for height, short in ((700, False), (320, True), (280, True), (700, False)):
            view._handle_size_change(
                cast(
                    ft.LayoutSizeChangeEvent,
                    SimpleNamespace(width=420, height=height),
                )
            )
            self.assertIs(view.composer, composer)
            self.assertIs(view.message_history, history)
            self.assertIs(view.paid_confirmation_checkbox, checkbox)
            self.assertIs(view.metrics_strip, strip)
            self.assertEqual(editor_ancestor_ids(view.control, field), ancestors)
            self.assertEqual(editor_visible_slots(view.control, field), visible_slots)
            self.assertIs(field.selection, selection)
            self.assertEqual(field.value, "Public draft\nwith preserved selection 🙂")
            self.assertIs(view._chat_actions_row, actions)
            self.assertIs(view._privacy_footer, footer)
            self.assertEqual(tuple(view._chat_actions.controls), buttons)
            self.assertTrue(actions.visible)
            self.assertTrue(footer.visible)
            self.assertEqual(actions.height, 0 if short else None)
            self.assertEqual(footer.height, 0 if short else None)
            self.assertEqual(view._chat_actions.visible, not short)
            self.assertEqual(view._privacy_warning.visible, not short)
            self.assertEqual(field.max_lines, 1 if short else 2)
            self.assertTrue(history.control.visible)
            self.assertTrue(strip.control.visible)
            self.assertTrue(composer.estimate.control.visible)
            self.assertTrue(composer.busy)
            self.assertTrue(checkbox.disabled)
            self.assertTrue(composer.send_button.disabled)
        self.assertEqual(self.fixture.calls, [])

    async def test_width_breakpoint_keeps_editor_ancestors_and_serializes_drawer(self):
        self.fixture.page.width = 1280
        updates = []
        update_page = Mock(side_effect=lambda: updates.append(self.fixture.page.drawer))
        setattr(self.fixture.page, "update", update_page)
        _chat, view = self.paid_view()
        composer = view.composer
        assert composer is not None
        field = composer.message_field
        field.value = "Public cursor position is stable"
        field.selection = ft.TextSelection(base_offset=7, extent_offset=7)
        selection = field.selection
        ancestors = editor_ancestor_ids(view.control, field)
        visible_slots = editor_visible_slots(view.control, field)
        root_row = view._layout.content
        assert isinstance(root_row, ft.Row)
        body = root_row.controls[-1]
        for width, height, lines in ((360, 700, 2), (900, 300, 1), (1280, 750, 5)):
            view._handle_size_change(
                cast(
                    ft.LayoutSizeChangeEvent,
                    SimpleNamespace(width=width, height=height),
                )
            )
            self.assertIs(view._layout.content, root_row)
            self.assertIs(root_row.controls[-1], body)
            self.assertEqual(editor_ancestor_ids(view.control, field), ancestors)
            self.assertEqual(editor_visible_slots(view.control, field), visible_slots)
            self.assertIs(field.selection, selection)
            self.assertEqual(field.value, "Public cursor position is stable")
            self.assertEqual(field.max_lines, lines)
            if width < 760:
                self.assertIsInstance(self.fixture.page.drawer, ft.NavigationDrawer)
                self.assertIs(updates[-1], self.fixture.page.drawer)
                sidebar = cast(ft.Container, view._sidebar_panel)
                self.assertTrue(sidebar.visible)
                self.assertEqual(sidebar.width, 0)
                self.assertIsNotNone(sidebar.content)
                self.assertFalse(cast(ft.Control, sidebar.content).visible)
            else:
                self.assertIsNone(self.fixture.page.drawer)
                self.assertIsNone(updates[-1])
                self.assertEqual(cast(ft.Container, view._sidebar_panel).width, 320)
            self.assertTrue(cast(ft.Control, view._sidebar_divider).visible)
        # Only crossing the breakpoint needs Page's root View drawer patch.
        self.assertEqual(update_page.call_count, 2)
        self.assertEqual(self.fixture.calls, [])

    async def test_active_checkbox_callback_does_not_require_options_menu(self):
        changes = AsyncMock()
        _chat, view = self.paid_view(on_paid_confirmation_changed=changes)
        checkbox = view.paid_confirmation_checkbox
        assert checkbox is not None and checkbox.on_change is not None
        checkbox.value = False
        await cast(Callable[[ft.Event], Awaitable[None]], checkbox.on_change)(
            ft.Event(name="change", control=checkbox)
        )
        changes.assert_awaited_once_with(_chat.id, False)
        self.assertIsNone(view._menu_dialog)
        # Without a successful persisted readback the view restores saved truth.
        self.assertTrue(checkbox.value)

    async def test_keyboard_help_is_explicit_dismisses_and_restores_its_own_focus(self):
        changes = AsyncMock()
        chat, view = self.paid_view(on_paid_confirmation_changed=changes)
        help_panel = view.paid_confirmation_help
        checkbox = view.paid_confirmation_checkbox
        assert help_panel is not None and checkbox is not None
        self.assertIsNone(help_panel.dialog)
        focus = AsyncMock()
        with patch.object(ft.IconButton, "focus", focus):
            await help_panel.open(ft.Event(name="click", control=help_panel.button))
            dialog = help_panel.dialog
            assert dialog is not None and dialog.on_dismiss is not None
            self.assertFalse(dialog.modal)
            self.assertTrue(dialog.scrollable)
            self.assertTrue(checkbox.value)
            changes.assert_not_awaited()
            self.assertTrue(cast(ft.TextButton, dialog.actions[0]).autofocus)
            set_language("en")
            view.refresh_menu_language()
            self.assertEqual(
                cast(ft.Text, dialog.content).value,
                tr("metrics.without_confirmation_help"),
            )
            await cast(Callable[[ft.Event], Awaitable[None]], dialog.on_dismiss)(
                ft.Event(name="dismiss", control=dialog)
            )
            self.assertIsNone(help_panel.dialog)
            self.assertFalse(dialog.open)
            focus.assert_awaited_once()
            await help_panel.open(ft.Event(name="click", control=help_panel.button))
            next_chat = replace(chat, id="other-chat")
            self.fixture.update(view, next_chat, fixtures._state(next_chat))
            self.assertIsNone(help_panel.dialog)
            await help_panel.open(ft.Event(name="click", control=help_panel.button))
            self.assertIsNone(help_panel.dialog)
            self.assertTrue(checkbox.value)
            changes.assert_not_awaited()

    async def test_pending_write_fence_and_late_callback_do_not_change_other_chat(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def save(_chat_id: str, _value: bool):
            entered.set()
            await release.wait()

        chat, view = self.paid_view(on_paid_confirmation_changed=save)
        old_checkbox = view.paid_confirmation_checkbox
        assert old_checkbox is not None and old_checkbox.on_change is not None
        old_checkbox.value = False
        old_callback = cast(
            Callable[[ft.Event], Awaitable[None]], old_checkbox.on_change
        )

        async def change():
            await old_callback(ft.Event(name="change", control=old_checkbox))

        changing = asyncio.create_task(change())
        await entered.wait()
        assert view.composer is not None
        self.assertTrue(view.composer.send_button.disabled)
        self.assertTrue(old_checkbox.disabled)
        view._handle_size_change(
            cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=360, height=320))
        )
        self.assertIs(view.paid_confirmation_checkbox, old_checkbox)
        self.assertFalse(old_checkbox.value)
        self.assertTrue(view.composer.send_button.disabled)
        self.assertTrue(old_checkbox.disabled)
        next_chat = replace(chat, id="other-chat", paid_without_confirmation=False)
        self.fixture.update(view, next_chat, fixtures._state(next_chat))
        next_checkbox = view.paid_confirmation_checkbox
        assert next_checkbox is not None
        self.assertFalse(next_checkbox.value)
        release.set()
        await changing
        self.assertFalse(next_checkbox.value)
        self.assertFalse(next_checkbox.disabled)
        await old_callback(ft.Event(name="change", control=old_checkbox))
        self.assertFalse(next_checkbox.value)

    async def test_metrics_and_language_refresh_preserve_editor_selection_controls(
        self,
    ):
        chat, view = self.paid_view()
        assert view.composer is not None and view.metrics_strip is not None
        composer, field, strip = (
            view.composer,
            view.composer.message_field,
            view.metrics_strip,
        )
        field.value = "public synthetic text 🙂"
        field.selection = ft.TextSelection(base_offset=3, extent_offset=8)
        selection = field.selection
        checkbox = view.paid_confirmation_checkbox
        snapshot = self.metrics(chat.id)
        labels = []
        for language in ("en", "ru"):
            set_language(language)
            view.set_metrics(snapshot)
            view.set_estimate(
                DraftEstimate(EstimateState.READY, 123, 1024, Decimal("0.0025"))
            )
            view.refresh_menu_language()
            labels.append(strip.values.value)
            self.assertIs(view.composer, composer)
            self.assertIs(composer.message_field, field)
            self.assertIs(field.selection, selection)
            self.assertEqual(field.value, "public synthetic text 🙂")
            self.assertIs(view.paid_confirmation_checkbox, checkbox)
            assert checkbox is not None and isinstance(checkbox.label, ft.Text)
            self.assertEqual(checkbox.label.value, tr("metrics.without_confirmation"))
        self.assertNotEqual(labels[0], labels[1])
        view.set_metrics(replace(snapshot, chat_id="wrong-chat"))
        self.assertIs(strip._snapshot, snapshot)
        view.dispose()
        view.set_metrics(snapshot)
        self.assertIsNone(strip._snapshot)
        self.assertEqual(field.value, "")
        self.assertEqual(composer.estimate.text.value, "")

    def metrics(self, chat_id="chat"):
        return ChatMetricsSnapshot(
            chat_id=chat_id,
            mode=ChatMode.PAID,
            remaining=RemainingBudget(120, Decimal("0.73"), False),
            last_request=LastRequestMetrics(
                LastRequestState.FINAL,
                total_tokens=45,
                prompt_tokens=90,
                completion_tokens=10,
                cost_usd=Decimal("0.0025"),
            ),
            key_limit=KeyLimitInfo.from_validated_remaining(Decimal("7.12")),
            metadata_updated_at=datetime(2026, 11, 1, tzinfo=UTC),
        )

    async def test_paid_budget_key_limit_balance_and_actual_cost_are_distinct(self):
        set_language("en")
        strip = ChatMetricsStrip()
        strip.set_metrics(replace(self.metrics(), account_balance_usd=Decimal("99")))
        self.assertIn("Chat available $0.73", strip.values.value)
        self.assertIn("Last request $0.0025", strip.values.value)
        self.assertEqual(strip.metadata.value, "Key remaining $7.12")
        self.assertNotIn("$7.12", strip.values.value)
        self.assertNotIn("$99", strip.metadata.value)
        self.assertNotIn("balance", strip.metadata.value)
        self.assertFalse(strip.metadata.selectable)
        self.assertTrue(strip.values.selectable)
        tooltip = cast(ft.Tooltip, strip.metadata.tooltip)
        self.assertEqual(tooltip.trigger_mode, ft.TooltipTriggerMode.LONG_PRESS)
        self.assertIn("Key remaining $7.12", tooltip.message)
        self.assertIn("separate amounts", tooltip.message)
        self.assertEqual(strip.account.value, "Balance unavailable")
        self.assertIn("2026-11-01", tooltip.message)
        strip.set_metrics(replace(self.metrics(), key_limit=KeyLimitInfo.unknown()))
        self.assertEqual(strip.metadata.value, "Key data unavailable")
        self.assertNotIn("$0", strip.metadata.value)

    async def test_key_limit_states_are_visible_and_distinct_in_both_languages(self):
        for language, expected in (
            (
                "en",
                (
                    "Key remaining $7.12",
                    "Key remaining < $0.0001",
                    "Key limit exhausted · $0",
                    "Key limit exhausted · $-1.25",
                    "Key limit exhausted · below $0",
                    "Key limit not set",
                    "Key data unavailable",
                ),
            ),
            (
                "ru",
                (
                    "Осталось по ключу 7,12 USD",
                    "Осталось по ключу < 0,0001 USD",
                    "Лимит ключа исчерпан · 0 USD",
                    "Лимит ключа исчерпан · -1,25 USD",
                    "Лимит ключа исчерпан · ниже 0 USD",
                    "Лимит ключа не установлен",
                    "Данные ключа недоступны",
                ),
            ),
        ):
            set_language(language)
            strip = ChatMetricsStrip()
            control, metadata, values = strip.control, strip.metadata, strip.values
            cases = [
                KeyLimitInfo.from_validated_remaining(value)
                for value in (
                    Decimal("7.12"),
                    Decimal("0.00000001"),
                    Decimal("0"),
                    Decimal("-1.25"),
                    Decimal("-0.00000001"),
                    None,
                )
            ] + [KeyLimitInfo.unknown()]
            for key_limit, label in zip(cases, expected, strict=True):
                with self.subTest(language=language, state=key_limit.state):
                    strip.set_metrics(replace(self.metrics(), key_limit=key_limit))
                    self.assertEqual(strip.metadata.value, label)
                    self.assertTrue(strip.metadata.visible)
                    self.assertIs(strip.control, control)
                    self.assertIs(strip.metadata, metadata)
                    self.assertIs(strip.values, values)
                    help_text = cast(ft.Tooltip, metadata.tooltip).message
                    self.assertIn(label, help_text)
                    if key_limit.state is KeyLimitState.NOT_SET:
                        self.assertIn(
                            "does not mean unlimited"
                            if language == "en"
                            else "не означает бесконечные",
                            help_text,
                        )
                    elif key_limit.state is KeyLimitState.UNKNOWN:
                        self.assertIn(
                            "Refresh the key status"
                            if language == "en"
                            else "Обновите статус ключа",
                            help_text,
                        )

    async def test_key_receipt_time_survives_render_and_changes_with_new_snapshot(self):
        set_language("en")
        strip = ChatMetricsStrip()
        snapshot = self.metrics()
        strip.set_metrics(snapshot)
        receipt = "2026-11-01T00:00:00+00:00"
        for width in (420, 1280, 420):
            strip.resize(width)
            strip.sync_language()
            self.assertIn(receipt, cast(ft.Tooltip, strip.metadata.tooltip).message)
            self.assertIs(strip._snapshot, snapshot)
        strip.set_metrics(
            replace(
                snapshot,
                key_limit=KeyLimitInfo.from_validated_remaining(Decimal("37.5")),
                metadata_updated_at=datetime(2026, 11, 1, 1, tzinfo=UTC),
            )
        )
        self.assertEqual(strip.metadata.value, "Key remaining $37.5")
        tooltip = cast(ft.Tooltip, strip.metadata.tooltip).message
        self.assertIn("2026-11-01T01:00:00+00:00", tooltip)
        self.assertNotIn(receipt, tooltip)

    async def test_last_request_states_do_not_invent_zero_or_keep_older_final(self):
        set_language("en")
        strip = ChatMetricsStrip()
        for state, expected in (
            (LastRequestState.NONE, "No requests"),
            (LastRequestState.PENDING, "In progress"),
            (LastRequestState.UNKNOWN, "Reconciling"),
        ):
            with self.subTest(state=state):
                snapshot = replace(
                    self.metrics(),
                    last_request=LastRequestMetrics(state),
                    remaining=RemainingBudget(None, None, True),
                )
                strip.set_metrics(snapshot)
                self.assertIn(expected, strip.values.value)
                self.assertNotIn("$0", strip.values.value)
                self.assertNotIn("$0.0025", strip.values.value)
        strip.set_metrics(replace(self.metrics(), pending=True))
        self.assertTrue(strip.pending.visible)
        self.assertIn("$0.0025", strip.values.value)
        strip.set_metrics(
            replace(
                self.metrics(),
                pending=True,
                last_request=LastRequestMetrics(LastRequestState.PENDING),
            )
        )
        self.assertFalse(strip.pending.visible)
        self.assertIn("In progress", strip.values.value)

    async def test_free_metrics_use_authoritative_total_and_no_account_or_money(self):
        set_language("en")
        strip = ChatMetricsStrip()
        strip.set_metrics(replace(self.metrics(), mode=ChatMode.FREE))
        self.assertIn("Tokens remaining 120", strip.values.value)
        self.assertIn("Last request 45 tokens", strip.values.value)
        self.assertNotIn("100", strip.values.value)
        self.assertNotIn("$", strip.values.value)
        self.assertFalse(strip.metadata.visible)
        tooltip = cast(ft.Tooltip, strip.values.tooltip)
        self.assertIn("not a global OpenRouter quota", tooltip.message)

    async def test_estimate_line_is_inside_compose_and_updates_without_replacing_field(
        self,
    ):
        set_language("en")
        observed = []
        composer: MessageComposer

        async def changed(text: str):
            # The controller calculates on this event before awaiting persistence.
            observed.append(text)
            composer.set_estimate(
                DraftEstimate(EstimateState.READY, 120, 1024, Decimal(0))
                if text.strip()
                else DraftEstimate(EstimateState.EMPTY)
            )

        composer = MessageComposer(AsyncMock(), on_change=changed)
        self.addCleanup(composer.dispose)
        field, estimate = composer.message_field, composer.estimate
        values = [
            "a",
            "",
            "replace 🙂",
            "paste\nline",
            "cut",
            "undo",
            "redo",
            "界🙂",
            " ",
        ]
        for value in values:
            field.value = value
            await composer._handle_change(ft.Event(name="change", control=field))
            self.assertIs(composer.message_field, field)
            self.assertIs(composer.estimate, estimate)
            if value.strip():
                self.assertIn("≈ 120 input tokens", estimate.text.value)
                self.assertIn("cost up to $0", estimate.text.value)
            else:
                self.assertEqual(estimate.text.value, tr("estimate.empty"))
        self.assertEqual(observed, values)
        self.assertIn(estimate.control, fixtures.walk(composer.control))
        self.assertFalse(composer.progress_row.visible)

    async def test_edit_immediately_renders_pending_or_empty_while_save_is_blocked(
        self,
    ):
        set_language("en")
        entered, release = asyncio.Event(), asyncio.Event()

        async def changed(_text: str):
            entered.set()
            await release.wait()

        composer = MessageComposer(AsyncMock(), on_change=changed)
        self.addCleanup(composer.dispose)
        field = composer.message_field
        for text, expected in (
            ("new draft", "estimate.calculating"),
            ("", "estimate.empty"),
        ):
            with self.subTest(text_is_empty=not text):
                entered.clear()
                release.clear()
                composer.set_estimate(
                    DraftEstimate(EstimateState.READY, 999, 1024, Decimal("0.25"))
                )
                field.value = text
                with patch.object(composer.estimate.control, "update") as rendered:
                    edit = asyncio.create_task(
                        composer._handle_change(ft.Event(name="change", control=field))
                    )
                    try:
                        await entered.wait()
                        self.assertFalse(edit.done())
                        rendered.assert_called_once_with()
                        self.assertEqual(composer.estimate.text.value, tr(expected))
                        self.assertNotIn("999", composer.estimate.text.value)
                        self.assertIs(composer.message_field, field)
                    finally:
                        release.set()
                        await edit

    async def test_small_positive_cost_unknown_price_and_empty_are_never_false_zero(
        self,
    ):
        for language in ("en", "ru"):
            set_language(language)
            line = DraftEstimateLine()
            tiny = Decimal("0.000000001")
            value = display_usd(tiny)
            self.assertIn("<", value)
            self.assertNotEqual(value, display_usd(Decimal(0)))
            upper = display_usd(Decimal("0.123401"), upper_bound=True)
            self.assertNotEqual(upper, display_usd(Decimal("0.123401")))
            line.set_estimate(DraftEstimate(EstimateState.READY, 20, 30, tiny))
            self.assertIn("<", line.text.value)
            line.set_estimate(DraftEstimate(EstimateState.UNAVAILABLE, 20))
            self.assertIn(tr("estimate.cost_unknown"), line.text.value)
            self.assertNotIn(display_usd(Decimal(0)), line.text.value)
            line.set_estimate(DraftEstimate(EstimateState.EMPTY))
            self.assertEqual(line.text.value, tr("estimate.empty"))
            line.set_estimate(DraftEstimate(EstimateState.OVER_LIMIT, 9000))
            self.assertIn(tr("estimate.over_limit"), line.text.value)


if __name__ == "__main__":
    unittest.main()
