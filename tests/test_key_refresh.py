"""Проверка обновления ключа без сети с сохранением открытого меню."""

from __future__ import annotations

import asyncio
import sys
import unittest
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import cast

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.models import KeyValidityState  # noqa: E402
from tests import test_chat_controller as controller_fakes  # noqa: E402


class KeyRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_refresh_runs_once_and_updates_open_menu_and_draft(
        self,
    ) -> None:
        for result, expected in (
            (controller_fakes._available_key(), KeyValidityState.VALID),
            (
                KeyValidationResult(KeyValidationStatus.TIMEOUT),
                KeyValidityState.UNKNOWN,
            ),
        ):
            with self.subTest(expected=expected):
                fixture = controller_fakes.ChatControllerTests()
                fixture.setUp()
                fixture.chat_service.chats = [controller_fakes._existing_chat()]
                validator = controller_fakes.BlockingKeyValidator(result)
                fixture.key_validator = validator
                controller = fixture._controller()
                try:
                    await controller.activate(
                        "synthetic-session",
                        KeyValidityState.VALID,
                        fixture.available_limit,
                    )
                    view = controller._workspace_view
                    assert view is not None
                    view.restore_editor("  Тестовый черновик\\n🙂  ")
                    await view.open_menu()
                    dialog, menu_list = view._menu_dialog, view._menu_list
                    replace_button = view.replace_key_button
                    assert replace_button is not None
                    await controller.request_key_revalidation()
                    self.assertTrue(controller.key_validation_in_progress)
                    await asyncio.wait_for(validator.started.wait(), timeout=1)
                    await asyncio.gather(
                        controller.request_key_revalidation(),
                        controller.request_key_revalidation(),
                    )
                    self.assertEqual(validator.calls, 1)
                    self.assertIs(controller._workspace_view, view)
                    self.assertIs(view._menu_dialog, dialog)
                    self.assertIs(view._menu_list, menu_list)
                    self.assertTrue(view.menu_open)
                    assert view.retry_key_button is not None
                    self.assertTrue(view.retry_key_button.disabled)
                    self.assertIs(view.replace_key_button, replace_button)
                    self.assertTrue(replace_button.visible)
                    self.assertTrue(replace_button.disabled)
                    await controller.request_key_replacement()
                    self.assertEqual(fixture.replace_calls, 0)
                    validation_task = controller._key_validation_task
                    assert validation_task is not None
                    validator.release.set()
                    await controller_fakes._wait_for_key_validation(controller)
                    await validation_task
                    self.assertEqual(controller.key_validity, expected)
                    self.assertIs(controller._workspace_view, view)
                    self.assertIs(view._menu_dialog, dialog)
                    self.assertIs(view._menu_list, menu_list)
                    self.assertTrue(view.menu_open)
                    self.assertFalse(view.retry_key_button.disabled)
                    self.assertIs(view.replace_key_button, replace_button)
                    self.assertFalse(replace_button.disabled)
                    self.assertEqual(view.editor_value, "  Тестовый черновик\\n🙂  ")
                    if expected is KeyValidityState.VALID:
                        self.assertEqual(controller.key_limit.remaining, Decimal("5"))
                    callback = replace_button.on_click
                    assert callback is not None
                    await cast(Callable[[ft.Event], Awaitable[None]], callback)(
                        ft.Event(name="click", control=replace_button)
                    )
                    self.assertEqual(fixture.replace_calls, 1)
                    self.assertFalse(view.menu_open)
                finally:
                    validator.release.set()
                    controller.dispose()
                    await asyncio.sleep(0)


if __name__ == "__main__":
    unittest.main()
