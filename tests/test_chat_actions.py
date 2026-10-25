"""Действия выбранного чата с настоящей временной SQLite и управляемыми гонками."""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import PinRecord  # noqa: E402
from chat.drafts import DraftStorageError  # noqa: E402
from chat.models import ChatMode  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from tests import test_chat_ui_integration as fixtures  # noqa: E402
from tests.test_chat_menu import walk  # noqa: E402


class ChatActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.fixture = fixtures.ChatUiIntegrationTests()
        await self.fixture.asyncSetUp()
        self.addCleanup(self.fixture.temp_dir.cleanup)
        self.first = await self.fixture._create_chat(ChatMode.FREE)
        self.second = await self.fixture._create_chat(ChatMode.FREE)
        self.controller, self.client = self.fixture._controller(
            [fixtures._success("answer")]
        )
        await self.fixture._activate(self.controller)
        await self.controller.select_chat(self.first)

    async def asyncTearDown(self) -> None:
        await self.controller.flush_drafts()
        self.controller.dispose()

    async def test_actions_visible_without_menu_and_stable_across_menu_refresh(
        self,
    ) -> None:
        view = self.controller._workspace_view
        assert view is not None
        self.assertIsNotNone(view.rename_button)
        self.assertIsNotNone(view.delete_button)
        buttons = (view.rename_button, view.delete_button)
        callbacks = tuple(button.on_click for button in buttons if button is not None)
        self.assertTrue(all(button in list(walk(view.control)) for button in buttons))
        await view.open_menu()
        assert view._menu_dialog is not None
        self.assertTrue(
            all(button not in list(walk(view._menu_dialog)) for button in buttons)
        )
        await self.controller.request_key_revalidation()
        view.close_menu()
        self.assertEqual((view.rename_button, view.delete_button), buttons)
        self.assertEqual(
            tuple(button.on_click for button in buttons if button is not None),
            callbacks,
        )

    async def test_late_open_does_not_show_other_chat_dialog(self) -> None:
        for action in ("rename", "delete"):
            with self.subTest(action=action):
                await self.controller.select_chat(self.first)
                entered, release = asyncio.Event(), asyncio.Event()
                original = self.fixture.chat_service.get_chat

                async def delayed(chat_id):
                    result = await original(chat_id)
                    entered.set()
                    await release.wait()
                    return result

                with patch.object(self.fixture.chat_service, "get_chat", delayed):
                    task = asyncio.create_task(
                        getattr(self.controller, f"request_{action}_chat")(self.first)
                    )
                    await asyncio.wait_for(entered.wait(), 3)
                    # Восстанавливаем чтение для настоящей навигации, сохраняя held await.
                    with patch.object(self.fixture.chat_service, "get_chat", original):
                        await self.controller.select_chat(self.second)
                    release.set()
                    await asyncio.wait_for(task, 3)
                dialogs = self.fixture.page.dialogs
                self.controller._dismiss_chat_dialog()
                self.assertEqual(dialogs, [])

    async def test_cancel_closes_own_dialog_only(self) -> None:
        for action in ("rename", "delete"):
            with self.subTest(action=action):
                await getattr(self.controller, f"request_{action}_chat")(self.first)
                own = self.fixture.page.dialogs[-1]
                foreign = ft.AlertDialog(title=ft.Text("Другое окно"))
                self.fixture.page.show_dialog(foreign)
                getattr(self.controller, f"cancel_{action}_chat")()
                self.assertFalse(own.open)
                self.assertTrue(foreign.open)
                foreign.open = False

    async def _click(self, button) -> None:
        result = button.on_click(ft.Event(name="click", control=button))
        if inspect.isawaitable(result):
            await result

    def _data(self, chat_id: str) -> tuple:
        f = self.fixture
        return (
            f.chat_repository.list_messages(chat_id),
            f.message_repository.list_turns(chat_id),
            f.message_repository.get_chat_budget(chat_id),
            f.draft_repository.get_draft(chat_id),
        )

    async def test_rename_persists_title_and_latest_draft_without_changing_chat_data(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        await c.submit_message("existing history")
        self.assertEqual(self.client.calls, 1)
        view = c._workspace_view
        assert view is not None and view.composer is not None
        view.composer.set_value("  latest editor Ω\n ")
        await c.request_rename_chat(self.first)
        dialog = c._rename_dialog
        assert dialog is not None
        before_chat = f.chat_repository.get_chat(self.first)
        assert before_chat is not None
        self.assertEqual(dialog.title_field.value, before_chat.title)
        await c.flush_drafts()
        before_data = self._data(self.first)
        await c.confirm_rename_chat(self.first, "  My   local title ")
        current = SqliteChatRepository(f.chat_repository.path).get_chat(self.first)
        assert current is not None
        self.assertEqual(current.title, "My local title")
        self.assertEqual(current.id, before_chat.id)
        self.assertEqual(current.requested_model_id, before_chat.requested_model_id)
        self.assertEqual(current.mode, before_chat.mode)
        self.assertEqual(self._data(self.first), before_data)
        assert (
            c._workspace_view is not None
            and c._workspace_view._selected_chat is not None
        )
        self.assertEqual(c._workspace_view._selected_chat.title, "My local title")
        self.assertEqual(
            next(
                chat.title for chat in c._workspace_view._chats if chat.id == self.first
            ),
            "My local title",
        )
        await c.select_chat(self.second)
        await c.select_chat(self.first)
        self.assertEqual(c._workspace_view.editor_value, "  latest editor Ω\n ")
        await c.lock_application()
        await f._activate(c)
        await c.select_chat(self.first)
        assert c._workspace_view._selected_chat is not None
        self.assertEqual(c._workspace_view._selected_chat.title, "My local title")

    async def test_manual_default_title_survives_first_successful_send(self) -> None:
        await self.controller.request_rename_chat(self.first)
        await self.controller.confirm_rename_chat(self.first, "Новый чат")
        await self.controller.submit_message("must not become the title")
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(len(self.fixture.message_repository.list_turns(self.first)), 1)
        chat = self.fixture.chat_repository.get_chat(self.first)
        assert chat is not None
        self.assertEqual(chat.title, "Новый чат")

    async def test_rename_cancel_blank_and_storage_error_preserve_all_data(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        view = c._workspace_view
        assert view is not None and view.composer is not None
        view.composer.set_value("draft unchanged")
        await c.flush_drafts()
        before = (f.chat_repository.get_chat(self.first), self._data(self.first))
        await c.request_rename_chat(self.first)
        c.cancel_rename_chat()
        self.assertEqual(
            (f.chat_repository.get_chat(self.first), self._data(self.first)), before
        )
        for title in ("", " \t\n "):
            await c.request_rename_chat(self.first)
            await c.confirm_rename_chat(self.first, title)
            assert c._rename_dialog is not None
            self.assertIn("пустым", str(c._rename_dialog.title_field.error))
            self.assertFalse(c._rename_dialog.confirm_button.disabled)
            self.assertEqual(
                (f.chat_repository.get_chat(self.first), self._data(self.first)), before
            )
            c.cancel_rename_chat()
        await c.request_rename_chat(self.first)
        with patch.object(
            f.chat_repository,
            "rename_chat",
            side_effect=sqlite3.OperationalError("fixture failure"),
        ):
            await c.confirm_rename_chat(self.first, "not persisted")
        assert c._rename_dialog is not None
        self.assertIn("Не удалось сохранить", str(c._rename_dialog.title_field.error))
        self.assertEqual(
            (f.chat_repository.get_chat(self.first), self._data(self.first)), before
        )

    async def test_delete_cancels_then_removes_only_confirmed_chat_and_last_empty_state(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        auth = AuthDatabase(f.temp_dir.name)
        record = PinRecord(
            1, "pbkdf2_sha256", 600000, b"synthetic salt", b"synthetic verifier"
        )
        auth.save_auth_state("synthetic registration", record)
        auth_before = auth.get_auth_state()
        await c.submit_message("first history")
        await c.select_chat(self.second)
        self.client.results.append(fixtures._success("second answer"))
        await c.submit_message("second history")
        assert c._workspace_view is not None and c._workspace_view.composer is not None
        c._workspace_view.composer.set_value("neighbor draft")
        await c.select_chat(self.first)
        c._workspace_view.composer.set_value("deleted draft")
        await c.flush_drafts()
        neighbor = (f.chat_repository.get_chat(self.second), self._data(self.second))
        before = self._data(self.first)
        await c.request_delete_chat(self.first)
        dialog = f.page.dialogs[-1]
        assert isinstance(dialog, ft.AlertDialog) and isinstance(
            dialog.content, ft.Text
        )
        self.assertIn("черновик", dialog.content.value)
        chat = f.chat_repository.get_chat(self.first)
        assert chat is not None
        self.assertIn(chat.title, dialog.content.value)
        c.cancel_delete_chat()
        self.assertEqual(self._data(self.first), before)
        await c.request_delete_chat(self.first)
        await c.confirm_delete_chat(self.first)
        self.assertIsNone(f.chat_repository.get_chat(self.first))
        self.assertEqual(f.chat_repository.list_messages(self.first), [])
        self.assertEqual(f.message_repository.list_turns(self.first), [])
        with self.assertRaises(DraftStorageError):
            f.draft_repository.get_draft(self.first)
        self.assertEqual(
            (f.chat_repository.get_chat(self.second), self._data(self.second)), neighbor
        )
        self.assertEqual(auth.get_auth_state(), auth_before)
        self.assertEqual(c._session_api_key, fixtures.TEST_CREDENTIAL)
        self.assertEqual(c.selected_chat_id, self.second)
        await c.request_delete_chat(self.second)
        await c.confirm_delete_chat(self.second)
        self.assertIsNone(c.selected_chat_id)
        assert c._workspace_view is not None
        self.assertIsNone(c._workspace_view.rename_button)
        self.assertIsNone(c._workspace_view.delete_button)
        self.assertIsNone(c._workspace_view.composer)
        self.assertEqual(auth.get_auth_state(), auth_before)
        self.assertEqual(c._session_api_key, fixtures.TEST_CREDENTIAL)

    async def test_delete_failure_keeps_chat_and_latest_draft(self) -> None:
        c, f = self.controller, self.fixture
        for result in (False, sqlite3.OperationalError("fixture failure")):
            with self.subTest(result=type(result).__name__):
                view = c._workspace_view
                assert view is not None and view.composer is not None
                view.composer.set_value("latest unsaved text")
                await c.request_delete_chat(self.first)
                with patch.object(f.chat_repository, "delete_chat") as delete:
                    if isinstance(result, Exception):
                        delete.side_effect = result
                    else:
                        delete.return_value = result
                    await c.confirm_delete_chat(self.first)
                self.assertIsNotNone(f.chat_repository.get_chat(self.first))
                self.assertEqual(
                    f.draft_repository.get_draft(self.first).text, "latest unsaved text"
                )
                self.assertIn("Не удалось удалить", view.composer.status.value)
                self.assertTrue(c.session_active)

    async def test_send_busy_disables_actions_but_unknown_reserve_allows_them(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        blocker = fixtures.BlockingCompletionClient(fixtures._timeout())
        c.dispose()
        self.controller, _ = f._controller([], completion_client=blocker)
        c = self.controller
        await f._activate(c)
        await c.select_chat(self.first)
        task = asyncio.create_task(c.submit_message("unknown result"))
        await asyncio.wait_for(blocker.started.wait(), 3)
        view = c._workspace_view
        assert (
            view is not None
            and view.rename_button is not None
            and view.delete_button is not None
        )
        self.assertTrue(view.rename_button.disabled)
        self.assertTrue(view.delete_button.disabled)
        await self._click(view.rename_button)
        await self._click(view.delete_button)
        self.assertEqual(f.page.dialogs, [])
        blocker.release.set()
        await asyncio.wait_for(task, 3)
        self.assertEqual(blocker.calls, 1)
        self.assertFalse(view.rename_button.disabled)
        self.assertFalse(view.delete_button.disabled)
        budget = f.message_repository.get_chat_budget(self.first)
        assert budget is not None
        reserve = budget.reserved_tokens
        self.assertGreater(reserve, 0)
        await self._click(view.rename_button)
        await c.confirm_rename_chat(self.first, "Unknown preserved")
        budget = f.message_repository.get_chat_budget(self.first)
        assert budget is not None
        self.assertEqual(budget.reserved_tokens, reserve)
        await self._click(view.delete_button)
        await c.confirm_delete_chat(self.first)
        self.assertIsNone(f.chat_repository.get_chat(self.first))

    async def test_stale_dialog_callbacks_after_navigation_or_relogin_cannot_touch_new_dialog(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        for action in ("rename", "delete"):
            for relogin in (False, True):
                with self.subTest(action=action, relogin=relogin):
                    await c.select_chat(self.first)
                    await getattr(c, f"request_{action}_chat")(self.first)
                    old = f.page.dialogs[-1]
                    assert isinstance(old, ft.AlertDialog)
                    if relogin:
                        await c.lock_application()
                        await f._activate(c)
                    else:
                        await c.select_chat(self.second)
                    await c.select_chat(self.first)
                    await getattr(c, f"request_{action}_chat")(self.first)
                    current = f.page.dialogs[-1]
                    before = f.chat_repository.get_chat(self.first)
                    await self._click(old.actions[-1])
                    await self._click(old.actions[0])
                    self.assertEqual(f.chat_repository.get_chat(self.first), before)
                    self.assertEqual(f.page.dialogs, [current])
                    c._dismiss_chat_dialog()

    async def test_late_action_read_error_does_not_lock_new_workspace(self) -> None:
        c, f = self.controller, self.fixture
        entered, release = asyncio.Event(), asyncio.Event()
        original = f.chat_service.get_chat

        async def delayed(_chat_id):
            entered.set()
            await release.wait()
            raise sqlite3.OperationalError("fixture late failure")

        with patch.object(f.chat_service, "get_chat", delayed):
            task = asyncio.create_task(c.request_rename_chat(self.first))
            await asyncio.wait_for(entered.wait(), 3)
            with patch.object(f.chat_service, "get_chat", original):
                await c.select_chat(self.second)
            view = c._workspace_view
            foreign = ft.AlertDialog(title=ft.Text("Окно текущего чата"))
            f.page.show_dialog(foreign)
            release.set()
            await asyncio.wait_for(task, 3)
        self.assertTrue(c.session_active)
        self.assertIs(c._workspace_view, view)
        self.assertEqual(f.page.dialogs, [foreign])
        foreign.open = False
        await c.submit_message("still works")
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(len(f.message_repository.list_turns(self.second)), 1)

    async def test_late_save_and_delete_completion_never_refresh_or_close_new_workspace(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        for action in ("rename", "delete"):
            for relogin in (False, True):
                for failure in (False, True):
                    with self.subTest(action=action, relogin=relogin, failure=failure):
                        target = await f._create_chat(ChatMode.FREE)
                        await c.select_chat(target)
                        await getattr(c, f"request_{action}_chat")(target)
                        entered, release = asyncio.Event(), asyncio.Event()
                        original = getattr(f.chat_service, f"{action}_chat")

                        async def delayed(*args):
                            if failure:
                                result = False
                            else:
                                result = await original(*args)
                            entered.set()
                            await release.wait()
                            if failure:
                                raise sqlite3.OperationalError("fixture late failure")
                            return result

                        with patch.object(f.chat_service, f"{action}_chat", delayed):
                            args = (
                                (target, "saved old title")
                                if action == "rename"
                                else (target,)
                            )
                            task = asyncio.create_task(
                                getattr(c, f"confirm_{action}_chat")(*args)
                            )
                            await asyncio.wait_for(entered.wait(), 3)
                            if relogin:
                                await c.lock_application()
                                await f._activate(c)
                            await c.select_chat(self.second)
                            await c.request_rename_chat(self.second)
                            current = c._rename_dialog
                            view = c._workspace_view
                            assert (
                                current is not None
                                and view is not None
                                and view.composer is not None
                            )
                            view.composer.set_value("new workspace editor")
                            release.set()
                            await asyncio.wait_for(task, 3)
                        self.assertIs(c._rename_dialog, current)
                        self.assertEqual(f.page.dialogs, [current.control])
                        self.assertIs(c._workspace_view, view)
                        self.assertEqual(view.editor_value, "new workspace editor")
                        self.assertEqual(view.composer.status.value, "")
                        target_chat = f.chat_repository.get_chat(target)
                        if action == "delete" and not failure:
                            self.assertIsNone(target_chat)
                        else:
                            assert target_chat is not None
                            self.assertEqual(
                                target_chat.title,
                                "saved old title" if not failure else "Новый чат",
                            )
                        c.cancel_rename_chat()
        self.client.results = [fixtures._success("final new answer")]
        await c.submit_message("new send after all completed actions")
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(len(f.message_repository.list_turns(self.second)), 1)

    async def test_failed_draft_flush_prevents_rename_and_delete(self) -> None:
        c, f = self.controller, self.fixture
        for action in ("rename", "delete"):
            with self.subTest(action=action):
                await getattr(c, f"request_{action}_chat")(self.first)
                view = c._workspace_view
                assert view is not None and view.composer is not None
                view.composer.set_value("must survive draft failure")
                before = f.chat_repository.get_chat(self.first)
                with patch.object(
                    f.draft_repository,
                    "save_draft",
                    side_effect=sqlite3.OperationalError("fixture failure"),
                ):
                    args = (
                        (self.first, "must not save")
                        if action == "rename"
                        else (self.first,)
                    )
                    await getattr(c, f"confirm_{action}_chat")(*args)
                self.assertEqual(f.chat_repository.get_chat(self.first), before)
                self.assertEqual(view.editor_value, "must survive draft failure")
                c._dismiss_chat_dialog()

    async def test_rename_flushes_latest_editor_before_workspace_refresh(self) -> None:
        c, f = self.controller, self.fixture
        await c.request_rename_chat(self.first)
        view = c._workspace_view
        assert view is not None and view.composer is not None
        view.composer.set_value("last edit without on_change")
        await c.confirm_rename_chat(self.first, "My title")
        self.assertEqual(
            f.draft_repository.get_draft(self.first).text, "last edit without on_change"
        )
        self.assertEqual(view.editor_value, "last edit without on_change")

    async def test_late_action_read_preserves_limits_dialog_opened_from_menu(
        self,
    ) -> None:
        c, f = self.controller, self.fixture
        for action in ("rename", "delete"):
            with self.subTest(action=action):
                view = c._workspace_view
                assert view is not None
                button = (
                    view.rename_button if action == "rename" else view.delete_button
                )
                assert button is not None
                entered, release = asyncio.Event(), asyncio.Event()
                original = f.chat_service.get_chat
                calls = 0

                async def delayed(chat_id):
                    nonlocal calls
                    calls += 1
                    chat = await original(chat_id)
                    if calls == 1:
                        entered.set()
                        await release.wait()
                    return chat

                with patch.object(f.chat_service, "get_chat", delayed):
                    task = asyncio.create_task(self._click(button))
                    await asyncio.wait_for(entered.wait(), 3)
                    await self._click(view.menu_button)
                    assert view.limits_button is not None
                    await self._click(view.limits_button)
                    self.assertTrue(c._workspace_controller.has_dialog())
                    limits = f.page.dialogs[-1]
                    release.set()
                    await asyncio.wait_for(task, 3)
                dialogs = f.page.dialogs
                c._dismiss_chat_dialog()
                c._workspace_controller.dismiss_dialogs()
                self.assertEqual(dialogs, [limits])


if __name__ == "__main__":
    unittest.main()
