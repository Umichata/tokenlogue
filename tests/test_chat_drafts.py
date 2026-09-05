"""Editor draft scenarios with temporary SQLite and fake completion clients."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import threading
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.drafts import DRAFT_STORAGE_MESSAGE, DraftStorageError  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, ChatMode  # noqa: E402
from chat_controller import ChatSessionController  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from tests import test_chat_ui_integration as ui_fixture  # noqa: E402
from tests.test_chat_ui_integration import (  # noqa: E402
    BlockingCompletionClient,
    _known_error,
    _success,
)
from tests.test_drafts import EXACT_TEXT  # noqa: E402


class ChatDraftUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.fixture = ui_fixture.ChatUiIntegrationTests()
        await self.fixture.asyncSetUp()
        self.addCleanup(self.fixture.temp_dir.cleanup)
        self.updates = patch.object(ft.Control, "update", return_value=None)
        self.updates.start()
        self.addCleanup(self.updates.stop)
        self.a = await self.fixture._create_chat(ChatMode.FREE)
        self.b = await self.fixture._create_chat(ChatMode.FREE)
        self.controller, self.client = self.fixture._controller([_success("answer")])
        self.addCleanup(self.controller.dispose)
        await self.fixture._activate(self.controller)
        await self.controller.select_chat(self.a)

    async def _type(
        self, text: str, controller: ChatSessionController | None = None
    ) -> None:
        controller = controller or self.controller
        view = controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = text
        await view.composer._handle_change(
            ft.Event(name="change", control=view.composer.message_field)
        )

    def _text(self, controller: ChatSessionController | None = None) -> str:
        view = (controller or self.controller)._workspace_view
        assert view is not None
        return view.editor_value

    async def test_independent_drafts_are_restored_exactly_and_empty_chat_starts_empty(
        self,
    ) -> None:
        await self._type(EXACT_TEXT)
        await self.controller.select_chat(self.b)
        self.assertEqual(self._text(), "")
        await self._type(" B\nsecond ")
        await self.controller.select_chat(self.a)
        self.assertEqual(self._text(), EXACT_TEXT)
        await self.controller.select_chat(self.b)
        self.assertEqual(self._text(), " B\nsecond ")
        self.assertEqual(self.fixture.chat_repository.list_messages(self.a), [])
        self.assertEqual(self.client.calls, 0)

    async def test_navigation_flushes_latest_control_value_before_pending_event(
        self,
    ) -> None:
        view = self.controller._workspace_view
        assert view is not None and view.composer is not None
        view.composer.message_field.value = EXACT_TEXT
        await self.controller.select_chat(self.b)
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.a).text, EXACT_TEXT
        )
        await self.controller.select_chat(self.a)
        self.assertEqual(self._text(), EXACT_TEXT)

    async def test_new_chat_cancel_and_creation_preserve_original_draft(self) -> None:
        await self._type(EXACT_TEXT)
        original_view = self.controller._workspace_view
        await self.controller.request_new_chat()
        self.assertIsNone(self.controller._workspace_view)
        await self.controller.cancel_new_chat()
        self.assertIsNot(self.controller._workspace_view, original_view)
        self.assertEqual(self._text(), EXACT_TEXT)
        await self.controller.request_new_chat()
        await self.controller.select_chat_mode(ChatMode.FREE)
        await self.controller.select_chat_model(FREE_ROUTER_MODEL)
        await self.controller.submit_new_chat_limits("8192", "256", None)
        self.assertNotEqual(self.controller.selected_chat_id, self.a)
        self.assertEqual(self._text(), "")
        await self.controller.select_chat(self.a)
        self.assertEqual(self._text(), EXACT_TEXT)

    async def test_rename_resize_and_state_refresh_preserve_input(self) -> None:
        await self._type(EXACT_TEXT)
        view = self.controller._workspace_view
        assert view is not None
        view._handle_size_change(
            cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=1000))
        )
        view._handle_size_change(
            cast(ft.LayoutSizeChangeEvent, SimpleNamespace(width=400))
        )
        await self.controller.request_rename_chat(self.a)
        await self.controller.confirm_rename_chat(self.a, "Renamed")
        await self.controller.request_edit_limits(self.a)
        await self.controller.submit_existing_chat_limits("16384", "256", None)
        await self.controller._refresh_after_key_validation(
            self.controller._session_generation
        )
        self.assertEqual(self._text(), EXACT_TEXT)
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.a).text, EXACT_TEXT
        )

    async def test_restart_loads_draft_from_sqlite_with_fresh_service(self) -> None:
        await self._type(EXACT_TEXT)
        self.assertTrue(await self.controller.flush_drafts())
        self.controller.dispose()
        AuthDatabase(self.fixture.temp_dir.name)
        restarted, client = self.fixture._controller([])
        self.addCleanup(restarted.dispose)
        await self.fixture._activate(restarted)
        await restarted.select_chat(self.a)
        self.assertEqual(self._text(restarted), EXACT_TEXT)
        self.assertEqual(client.calls, 0)

    async def test_delete_removes_only_its_draft(self) -> None:
        await self._type(EXACT_TEXT)
        await self.controller.select_chat(self.b)
        await self._type("keep B")
        await self.controller.select_chat(self.a)
        await self.controller.request_delete_chat(self.a)
        await self.controller.confirm_delete_chat(self.a)
        self.assertEqual(self.controller.selected_chat_id, self.b)
        self.assertEqual(self._text(), "keep B")
        with self.assertRaises(DraftStorageError):
            self.fixture.draft_repository.get_draft(self.a)

    async def test_preflight_error_preserves_saved_draft(self) -> None:
        chat = await self.fixture.chat_service.create_chat(
            ChatMode.FREE,
            FREE_ROUTER_MODEL,
            catalog=self.fixture.catalog,
            key_validity=KeyValidityState.VALID,
            key_limit=KeyLimitInfo.from_validated_remaining(None),
        )
        await self.controller.select_chat(chat.id)
        await self._type(EXACT_TEXT)
        await self.controller.submit_message(EXACT_TEXT)
        self.assertEqual(self._text(), EXACT_TEXT)
        self.assertEqual(
            self.fixture.draft_repository.get_draft(chat.id).text, EXACT_TEXT
        )
        self.assertEqual(self.fixture.chat_repository.list_messages(chat.id), [])
        self.assertEqual(self.client.calls, 0)

    async def test_paid_confirmation_cancel_preserves_draft_without_http(self) -> None:
        paid = await self.fixture._create_chat(ChatMode.PAID)
        await self.controller.select_chat(paid)
        await self._type(EXACT_TEXT)
        await self.controller.submit_message(EXACT_TEXT)
        self.assertIsNotNone(self.controller._workspace_controller.pending_preview)
        self.controller.cancel_pending_send()
        self.assertEqual(self._text(), EXACT_TEXT)
        self.assertEqual(self.fixture.draft_repository.get_draft(paid).text, EXACT_TEXT)
        self.assertEqual(self.client.calls, 0)

    async def test_reservation_and_late_answer_do_not_clear_new_text_in_either_chat(
        self,
    ) -> None:
        blocked = BlockingCompletionClient(_success("answer"))
        controller, _ = self.fixture._controller([], completion_client=blocked)
        self.addCleanup(controller.dispose)
        await self.fixture._activate(controller)
        await controller.select_chat(self.a)
        await self._type("sent", controller)
        send = asyncio.create_task(controller.submit_message("sent"))
        await asyncio.wait_for(blocked.started.wait(), 1)
        self.assertEqual(self._text(controller), "")
        self.assertEqual(self.fixture.draft_repository.get_draft(self.a).text, "")
        await self._type("next A", controller)
        await controller.select_chat(self.b)
        await self._type("next B", controller)
        blocked.release.set()
        await send
        self.assertEqual(self._text(controller), "next B")
        await controller.select_chat(self.a)
        self.assertEqual(self._text(controller), "next A")

    async def test_switch_during_slow_reservation_preserves_newer_identical_text_revision(
        self,
    ) -> None:
        await self._type("same text")
        started, release = threading.Event(), threading.Event()
        reserve = self.fixture.message_repository.reserve_turn

        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(3):
                raise TimeoutError("fixture timed out")
            return reserve(*args, **kwargs)

        with patch.object(
            self.fixture.message_repository, "reserve_turn", side_effect=delayed
        ):
            send = asyncio.create_task(self.controller.submit_message("same text"))
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            try:
                await self.controller.select_chat(self.b)
                await self._type("draft B")
                await self.controller.select_chat(self.a)
                await self._type("intermediate")
                await self._type("same text")
            finally:
                release.set()
            await send
        self.assertEqual(self._text(), "same text")
        self.assertEqual(self.fixture.draft_repository.get_draft(self.a).revision, 3)
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.b).text, "draft B"
        )
        self.assertEqual(self.client.calls, 1)

    async def test_retry_of_existing_turn_does_not_touch_new_draft(self) -> None:
        controller, _ = self.fixture._controller(
            [
                _known_error(ChatErrorType.INVALID_REQUEST),
                _success("retried answer"),
            ]
        )
        self.addCleanup(controller.dispose)
        await self.fixture._activate(controller)
        await controller.select_chat(self.a)
        await self._type("first", controller)
        await controller.submit_message("first")
        turn = self.fixture.message_repository.list_turns(self.a)[0]
        await self._type(EXACT_TEXT, controller)
        await controller.request_retry_turn(turn.id)
        self.assertEqual(self._text(controller), EXACT_TEXT)
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.a).text, EXACT_TEXT
        )
        self.assertEqual(len(self.fixture.chat_repository.list_messages(self.a)), 2)

    async def test_write_failure_keeps_editor_blocks_navigation_and_reports_safely(
        self,
    ) -> None:
        with patch.object(
            self.fixture.draft_repository,
            "save_draft",
            side_effect=sqlite3.OperationalError(EXACT_TEXT),
        ):
            await self._type(EXACT_TEXT)
            await self.controller.select_chat(self.b)
            await self.controller.request_new_chat()
            self.assertEqual(self.controller.selected_chat_id, self.a)
            self.assertEqual(self._text(), EXACT_TEXT)
            view = self.controller._workspace_view
            assert view is not None and view.composer is not None
            self.assertEqual(view.composer.status.value, DRAFT_STORAGE_MESSAGE)
        await self.controller.select_chat(self.b)
        await self.controller.select_chat(self.a)
        self.assertEqual(self._text(), EXACT_TEXT)

    async def test_lock_and_old_view_event_do_not_replace_new_session_draft(
        self,
    ) -> None:
        await self._type(EXACT_TEXT)
        old_view = self.controller._workspace_view
        assert old_view is not None and old_view.composer is not None
        await self.controller.lock_application()
        await self.fixture._activate(self.controller)
        await self.controller.select_chat(self.a)
        await self._type("new session")
        old_view.composer.message_field.value = "late old view"
        await old_view.composer._handle_change(
            ft.Event(name="change", control=old_view.composer.message_field)
        )
        self.assertEqual(self._text(), "new session")
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.a).text, "new session"
        )
        with closing(sqlite3.connect(self.fixture.chat_repository.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)

    async def test_other_chat_draft_never_enters_request_context(self) -> None:
        await self.controller.select_chat(self.b)
        await self._type("unsent B private fixture")
        await self.controller.select_chat(self.a)
        await self._type("current message")
        complete = self.client.complete
        with patch.object(self.client, "complete", wraps=complete) as completion:
            await self.controller.submit_message("current message")
        completion.assert_awaited_once()
        context = completion.call_args.args[2]
        self.assertEqual([message.content for message in context], ["current message"])
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.b).text,
            "unsent B private fixture",
        )

    async def test_late_answer_after_reauthentication_keeps_new_session_draft(
        self,
    ) -> None:
        blocked = BlockingCompletionClient(_success("old session answer"))
        controller, _ = self.fixture._controller([], completion_client=blocked)
        self.addCleanup(controller.dispose)
        await self.fixture._activate(controller)
        await controller.select_chat(self.a)
        await self._type("sent", controller)
        send = asyncio.create_task(controller.submit_message("sent"))
        await asyncio.wait_for(blocked.started.wait(), 1)
        await controller.lock_application()
        await self.fixture._activate(controller)
        await controller.select_chat(self.a)
        await self._type("new session draft", controller)
        view = controller._workspace_view
        with patch.object(self.fixture.page, "update") as update:
            blocked.release.set()
            await send
            update.assert_not_called()
        self.assertIs(controller._workspace_view, view)
        self.assertEqual(self._text(controller), "new session draft")
        self.assertEqual(
            self.fixture.draft_repository.get_draft(self.a).text, "new session draft"
        )


if __name__ == "__main__":
    unittest.main()
