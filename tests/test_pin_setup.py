"""Выбранный PIN проходит через настоящие сервис и временную SQLite без сети."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import AuthResult, AuthStatus  # noqa: E402
from auth.pin import PinHasher  # noqa: E402
from auth.service import AuthService  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from tests.test_app import FakeAuthService, _make_controller  # noqa: E402
from tests.test_app_lifecycle import AndroidPage, lifecycle  # noqa: E402
from tests.test_auth_service import (  # noqa: E402
    MemoryCredentials,
    StubValidator,
    _accepted_key,
)
from ui.auth_view import PinSetupView  # noqa: E402


class PinSetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = AuthDatabase(directory.name)
        self.credentials = MemoryCredentials()
        self.hasher = PinHasher(iterations=1_000, randbelow=lambda _: 7)
        self.service = AuthService(
            StubValidator(_accepted_key()),
            self.credentials,
            self.database,
            pin_hasher=self.hasher,
        )
        self.page = AndroidPage()
        self.controller = _make_controller(
            self.page, cast(FakeAuthService, self.service)
        )
        self.addCleanup(self.controller.dispose)
        self.updates = patch.object(ft.Control, "update", return_value=None)
        self.updates.start()
        self.addCleanup(self.updates.stop)
        await self.controller.start()

    async def setup_view(self) -> PinSetupView:
        await self.controller.submit_key("synthetic-unit-key")
        view = self.controller._pin_setup_view
        assert view is not None
        return view

    def fill(self, view: PinSetupView, pin: str, repeated: str) -> None:
        view.pin_field.value = pin
        view._pin_changed(ft.Event(name="change", control=view.pin_field))
        view.repeat_field.value = repeated
        view._repeat_changed(ft.Event(name="change", control=view.repeat_field))

    async def test_manual_leading_zero_pin_traverses_controller_and_real_service(
        self,
    ) -> None:
        view = await self.setup_view()
        self.assertTrue(view.confirm_button.disabled)
        self.fill(view, "0042", "0042")
        self.assertFalse(view.confirm_button.disabled)
        await view._submit_value()
        stored = self.database.get_auth_state()
        assert stored is not None
        self.assertTrue(self.hasher.verify("0042", stored.pin_record))
        self.assertFalse(self.hasher.verify("0007", stored.pin_record))
        self.assertEqual(view.pin_field.value, "")
        self.assertEqual(view.repeat_field.value, "")
        self.assertTrue(self.controller._chat_controller.session_active)

    async def test_suggestion_and_any_edit_require_fresh_confirmation(self) -> None:
        view = await self.setup_view()
        view._suggest(ft.Event(name="click", control=view.suggest_button))
        self.assertEqual(view.pin_field.value, "0007")
        self.assertEqual(view.repeat_field.value, "")
        self.assertTrue(view.confirm_button.disabled)
        self.fill(view, "0007", "0007")
        view._suggest(ft.Event(name="click", control=view.suggest_button))
        self.assertEqual(view.pin_field.value, "0007")
        self.assertEqual(view.repeat_field.value, "")
        self.assertTrue(view.confirm_button.disabled)
        self.fill(view, "0028", "0028")
        view.pin_field.value = "0064"
        view._pin_changed(ft.Event(name="change", control=view.pin_field))
        self.assertEqual(view.repeat_field.value, "")
        self.assertTrue(view.confirm_button.disabled)
        self.fill(view, "0064", "0064")
        await view._submit_value()
        self.assertEqual(
            (await self.service.login("0064")).status, AuthStatus.AUTHENTICATED
        )
        self.assertEqual(
            (await self.service.login("0007")).status, AuthStatus.INVALID_PIN
        )

    async def test_mismatch_unicode_spaces_and_lengths_never_confirm(self) -> None:
        view = await self.setup_view()
        with patch.object(
            self.service, "complete_setup", wraps=self.service.complete_setup
        ) as complete:
            for pin, repeated in (
                ("0042", "0043"),
                ("", ""),
                ("123", "123"),
                ("12345", "12345"),
                ("１２３４", "１２３４"),
                ("١٢٣٤", "١٢٣٤"),
                (" 1234", " 1234"),
                ("1234 ", "1234 "),
                ("12a4", "12a4"),
            ):
                self.fill(view, pin, repeated)
                self.assertTrue(view.confirm_button.disabled)
                await view._submit_value()
            complete.assert_not_called()
        self.assertIsNone(self.database.get_auth_state())

    async def test_busy_submission_calls_handler_once(self) -> None:
        started, release = asyncio.Event(), asyncio.Event()
        submitted = []

        async def confirm(pin: str) -> None:
            submitted.append(pin)
            started.set()
            await release.wait()

        async def cancel() -> None:
            return None

        view = PinSetupView("", confirm, lambda: "0007", cancel)
        self.fill(view, "0042", "0042")
        first = asyncio.create_task(view._submit_value())
        await started.wait()
        self.assertTrue(view.confirm_button.disabled)
        self.assertTrue(view.suggest_button.disabled)
        await view._submit_value()
        view._suggest(ft.Event(name="click", control=view.suggest_button))
        release.set()
        await first
        self.assertEqual(submitted, ["0042"])

    async def test_cancel_clears_both_inputs_without_persistence(self) -> None:
        view = await self.setup_view()
        token = self.controller._pending_setup_token or ""
        self.fill(view, "0042", "0042")
        await view._cancel(ft.Event(name="click", control=view.cancel_button))
        self.assertEqual(view.pin_field.value, "")
        self.assertEqual(view.repeat_field.value, "")
        self.assertIsNotNone(self.controller._key_view)
        self.assertIsNone(self.controller._pending_setup_token)
        self.assertEqual(
            (await self.service.complete_setup("0042", token)).status,
            AuthStatus.INVALID_STATE,
        )
        self.assertIsNone(self.database.get_auth_state())
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)

    async def test_background_discards_setup_and_late_view_cannot_register(
        self,
    ) -> None:
        view = await self.setup_view()
        token = self.controller._pending_setup_token or ""
        self.fill(view, "0042", "0042")
        await self.controller.handle_lifecycle_change(
            lifecycle(ft.AppLifecycleState.PAUSE)
        )
        self.assertEqual(view.pin_field.value, "")
        self.assertEqual(view.repeat_field.value, "")
        self.assertIsNone(self.controller._pending_setup_token)
        await view._submit_value()
        await self.controller.confirm_pin_setup("0042", token)
        await self.controller.submit_key("synthetic-late-key")
        self.assertIsNone(self.controller._pin_setup_view)
        self.assertIsNone(self.database.get_auth_state())
        await self.controller.handle_lifecycle_change(
            lifecycle(ft.AppLifecycleState.RESUME)
        )
        current = await self.setup_view()
        await self.controller.confirm_pin_setup("0042", token)
        self.assertIs(self.controller._pin_setup_view, current)
        self.fill(current, "0284", "0284")
        await current._submit_value()
        self.assertEqual(
            (await self.service.login("0284")).status, AuthStatus.AUTHENTICATED
        )

    async def test_background_during_kdf_cancels_uncommitted_setup(self) -> None:
        view = await self.setup_view()
        self.fill(view, "0042", "0042")
        started, release = threading.Event(), threading.Event()
        create_record = self.hasher.create_record

        def delayed(pin: str):
            started.set()
            if not release.wait(3):
                raise TimeoutError("Тест не освободил вычисление verifier")
            return create_record(pin)

        with patch.object(self.hasher, "create_record", delayed):
            saving = asyncio.create_task(view._submit_value())
            self.assertTrue(await asyncio.to_thread(started.wait, 1))
            hiding = asyncio.create_task(
                self.controller.handle_lifecycle_change(
                    lifecycle(ft.AppLifecycleState.PAUSE)
                )
            )
            await asyncio.sleep(0)
            self.assertIsNone(self.controller._pin_setup_view)
            release.set()
            await asyncio.gather(saving, hiding)
        self.assertIsNone(self.database.get_auth_state())
        self.assertFalse((await self.credentials.inspect_state()).has_artifacts)
        self.assertIsNotNone(self.controller._key_view)
        self.assertFalse(self.controller._chat_controller.session_active)

    async def test_background_during_confirmed_commit_requires_pin_for_complete_pair(
        self,
    ) -> None:
        view = await self.setup_view()
        self.fill(view, "0042", "0042")
        started, release = asyncio.Event(), asyncio.Event()
        save_credentials = self.credentials.save_credentials

        async def delayed(api_key: str, registration_id: str) -> None:
            started.set()
            await release.wait()
            await save_credentials(api_key, registration_id)

        with patch.object(self.credentials, "save_credentials", delayed):
            saving = asyncio.create_task(view._submit_value())
            await started.wait()
            hiding = asyncio.create_task(
                self.controller.handle_lifecycle_change(
                    lifecycle(ft.AppLifecycleState.PAUSE)
                )
            )
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(saving, hiding)
        self.assertTrue((await self.credentials.inspect_state()).complete)
        self.assertIsNotNone(self.database.get_auth_state())
        self.assertIsNotNone(self.controller._pin_login_view)
        self.assertFalse(self.controller._chat_controller.session_active)
        await self.controller.submit_pin("0042")
        self.assertFalse(self.controller._chat_controller.session_active)
        await self.controller.handle_lifecycle_change(
            lifecycle(ft.AppLifecycleState.RESUME)
        )
        await self.controller.submit_pin("0042")
        self.assertTrue(self.controller._chat_controller.session_active)

    async def test_secret_fields_and_pending_token_do_not_appear_in_repr(self) -> None:
        view = await self.setup_view()
        marker = "synthetic-sensitive-marker"
        view.pin_field.value = marker
        view.repeat_field.value = marker
        for control in (view.pin_field, view.repeat_field):
            self.assertNotIn(marker, repr(control))
            self.assertTrue(control.password)
            self.assertTrue(control.can_reveal_password)
            self.assertFalse(control.autocorrect)
            self.assertFalse(control.enable_suggestions)
            self.assertFalse(control.enable_ime_personalized_learning)
            self.assertFalse(control.enable_stylus_handwriting)
        result = AuthResult(AuthStatus.PIN_CHOICE_REQUIRED, pending_setup_token=marker)
        self.assertNotIn(marker, repr(result))
