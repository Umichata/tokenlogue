"""A local formatter never loads URLs and copies the original message/code."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.models import Message, MessageRole, MessageStatus  # noqa: E402
from i18n import configure_localization, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402
from ui.message_history import MessageHistoryView, _message_content  # noqa: E402


def message(content: str) -> Message:
    return Message(
        id="formatting-message",
        chat_id="formatting-chat",
        turn_id="formatting-turn",
        role=MessageRole.ASSISTANT,
        content=content,
        status=MessageStatus.SENT,
        requested_model_id="synthetic/model",
        actual_model_id="synthetic/model",
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


class MessageFormattingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())

    def nodes(self, content):
        return [node for control in _message_content(content) for node in walk(control)]

    async def click(self, button):
        await button.on_click(ft.Event(name="click", control=button))

    async def test_code_copy_preserves_exact_fenced_contents_and_whole_copy_keeps_source(
        self,
    ):
        code = "    print('synthetic')\r\n\tvalue = 1\r\n\r\n"
        original = "# A heading\r\n\r\n```python\r\n" + code + "```\r\n**Done**"
        view = MessageHistoryView((message(original),), (), on_retry=AsyncMock())
        nodes = list(walk(view.control))
        code_text = next(c for c in nodes if isinstance(c, ft.Text) and c.value == code)
        self.assertTrue(code_text.selectable)
        self.assertEqual(code_text.font_family, "monospace")
        code_copy = next(
            c
            for c in nodes
            if isinstance(c, ft.IconButton)
            and c.tooltip == tr("protection_panel.copy_code")
        )
        all_copy = next(
            c
            for c in nodes
            if isinstance(c, ft.IconButton)
            and c.tooltip == tr("protection_panel.copy_message")
        )
        with patch.object(ft.Clipboard, "set", new_callable=AsyncMock) as clipboard:
            clipboard.assert_not_awaited()
            await self.click(code_copy)
            clipboard.assert_awaited_once_with(code)
            await self.click(all_copy)
            self.assertEqual(clipboard.await_args_list[-1].args, (original,))

    async def test_remote_images_links_html_and_uris_remain_inert_selectable_text(self):
        original = (
            "![tracker](https://invalid.example/image.png)\n"
            "[open](file:///not-opened) <img src='https://invalid.example/x'>\n"
            "https://invalid.example/path javascript:alert(1)"
        )
        nodes = self.nodes(original)
        self.assertFalse(any(isinstance(c, (ft.Image, ft.Markdown)) for c in nodes))
        self.assertTrue(all(getattr(c, "url", None) is None for c in nodes))
        self.assertTrue(all(getattr(c, "on_tap_link", None) is None for c in nodes))
        text = next(c for c in nodes if isinstance(c, ft.Text))
        self.assertTrue(text.selectable)
        assert text.spans is not None
        self.assertEqual("".join(span.text or "" for span in text.spans), original)

    async def test_heading_list_quote_bold_and_inline_code_are_native_text_controls(
        self,
    ):
        nodes = self.nodes("## Summary\n- **First** and `value`\n2. Second\n> A quote")
        controls = [c for c in nodes if isinstance(c, ft.Text)]
        displayed = [
            "".join(span.text or "" for span in c.spans or []) for c in controls
        ]
        self.assertEqual(
            displayed, ["Summary", "• First and value", "2. Second", "A quote"]
        )
        self.assertTrue(all(c.selectable for c in controls))
        spans = controls[1].spans
        assert spans is not None
        bold = next(span for span in spans if span.text == "First")
        code = next(span for span in spans if span.text == "value")
        assert bold.style is not None and code.style is not None
        self.assertEqual(bold.style.weight, ft.FontWeight.W_600)
        self.assertEqual(code.style.font_family, "monospace")

    async def test_unclosed_or_embedded_fences_keep_code_and_do_not_parse_its_contents(
        self,
    ):
        content = "~~~text\n**not bold inside code**\n![still text](https://invalid.example/x)\n"
        nodes = self.nodes(content)
        code = next(
            c for c in nodes if isinstance(c, ft.Text) and c.font_family == "monospace"
        )
        self.assertEqual(code.value, content.split("\n", 1)[1])
        self.assertTrue(code.selectable)
        self.assertIsNone(code.spans)
        nested = self.nodes("````text\n``` literal shorter fence\n````\n")
        self.assertTrue(
            any(
                isinstance(c, ft.Text) and c.value == "``` literal shorter fence\n"
                for c in nested
            )
        )
