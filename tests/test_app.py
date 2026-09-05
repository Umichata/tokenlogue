"""Тесты переходов, конкуренции и очистки UI-сессии."""

from __future__ import annotations

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from app import AppController  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import (  # noqa: E402
    AuthResult,
    AuthStatus,
    InitialRoute,
    KeyLimitInfo,
    KeyValidityState,
)
from auth.service import AuthService  # noqa: E402
from chat.accounting import ChatBudgetService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from tests.draft_fakes import MemoryDraftRepository  # noqa: E402
from ui.auth_view import KeyEntryView, PinDisplayView, PinLoginView  # noqa: E402


class FakePage:
    def __init__(self) -> None:
        self.controls: list[ft.Control] = []
        self.dialogs: list[ft.DialogControl] = []
        self.update_calls = 0
        self.width = 400
        self.drawer: ft.NavigationDrawer | None = None
        self.drawer_open = False

    def add(self, control: ft.Control) -> None:
        self.controls.append(control)

    def update(self) -> None:
        self.update_calls += 1

    def show_dialog(self, dialog: ft.DialogControl) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> ft.DialogControl | None:
        return self.dialogs.pop() if self.dialogs else None

    def run_task(self, handler: Any, *args: Any) -> asyncio.Task[Any]:
        return asyncio.create_task(handler(*args))

    async def show_drawer(self) -> None:
        self.drawer_open = True

    async def close_drawer(self) -> None:
        self.drawer_open = False


class FakeAuthService:
    def __init__(self, *, initial_route: InitialRoute = InitialRoute.SETUP) -> None:
        self.initial_route = initial_route
        self.key_calls = 0
        self.reset_calls = 0
        self.cancel_calls = 0
        self.login_result = AuthResult(AuthStatus.INVALID_PIN, "Неверный PIN")
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def initialize(self) -> AuthResult:
        status = (
            AuthStatus.PIN_REQUIRED
            if self.initial_route is InitialRoute.PIN
            else AuthStatus.SETUP_REQUIRED
        )
        return AuthResult(status, initial_route=self.initial_route)

    async def start_setup(self, _api_key: str) -> AuthResult:
        self.key_calls += 1
        self.started.set()
        await self.release.wait()
        return AuthResult(AuthStatus.INVALID_KEY, "Проверка завершена")

    async def login(self, _pin: str) -> AuthResult:
        return self.login_result

    async def complete_setup(self) -> AuthResult:
        return AuthResult(AuthStatus.INVALID_STATE)

    async def reset_authentication(self) -> AuthResult:
        self.reset_calls += 1
        return AuthResult(
            AuthStatus.SETUP_REQUIRED,
            initial_route=InitialRoute.SETUP,
        )

    def cancel_pending_setup(self) -> None:
        self.cancel_calls += 1


class FakeChatService:
    def __init__(self) -> None:
        self.chats: list[Any] = []
        self.delete_calls = 0

    async def list_chats(self) -> list[Any]:
        return list(self.chats)

    async def get_chat(self, chat_id: str) -> Any:
        return next((chat for chat in self.chats if chat.id == chat_id), None)

    async def delete_chat(self, _chat_id: str) -> bool:
        self.delete_calls += 1
        return True


class FakeCatalogService:
    def __init__(self) -> None:
        self.clear_calls = 0

    def clear_cache(self) -> None:
        self.clear_calls += 1


class FakeKeyValidator:
    async def validate_key(self, _api_key: str) -> KeyValidationResult:
        return KeyValidationResult(KeyValidationStatus.NETWORK_ERROR)


class BlockingFakeKeyValidator(FakeKeyValidator):
    def __init__(self, *, ignore_cancellation: bool = False) -> None:
        self.ignore_cancellation = ignore_cancellation
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def validate_key(self, _api_key: str) -> KeyValidationResult:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            if not self.ignore_cancellation:
                raise
            await self.release.wait()
        return KeyValidationResult(
            KeyValidationStatus.ACCEPTED,
            limit_remaining=Decimal("5"),
        )


class AppControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_key_submission_runs_only_one_request(self) -> None:
        page = FakePage()
        service = FakeAuthService()
        controller = _make_controller(page, service)
        await controller.start()

        first = asyncio.create_task(controller.submit_key("test-value"))
        await service.started.wait()
        await controller.submit_key("test-value")
        service.release.set()
        await first

        self.assertEqual(service.key_calls, 1)

    async def test_late_response_does_not_update_replaced_view(self) -> None:
        page = FakePage()
        service = FakeAuthService()
        controller = _make_controller(page, service)
        await controller.start()

        first = asyncio.create_task(controller.submit_key("test-value"))
        await service.started.wait()
        controller._show_pin_login()
        expected_control = page.controls[0]
        service.release.set()
        await first

        self.assertIs(page.controls[0], expected_control)
        self.assertGreater(service.cancel_calls, 0)

    async def test_cancel_reset_does_not_call_business_reset(self) -> None:
        page = FakePage()
        service = FakeAuthService(initial_route=InitialRoute.PIN)
        controller = _make_controller(page, service)
        await controller.start()

        await controller.request_reset()
        controller.cancel_reset()

        self.assertEqual(service.reset_calls, 0)
        self.assertEqual(page.dialogs, [])

    async def test_confirm_reset_calls_business_reset_once(self) -> None:
        page = FakePage()
        service = FakeAuthService(initial_route=InitialRoute.PIN)
        chat_service = FakeChatService()
        controller = _make_controller(page, service, chat_service=chat_service)
        await controller.start()

        await controller.request_reset()
        await controller.confirm_reset()

        self.assertEqual(service.reset_calls, 1)
        self.assertEqual(chat_service.delete_calls, 0)
        self.assertEqual(page.dialogs, [])

    async def test_dispose_clears_input_and_pending_state(self) -> None:
        page = FakePage()
        service = FakeAuthService()
        controller = _make_controller(page, service)
        await controller.start()
        view = controller._key_view
        self.assertIsNotNone(view)
        assert view is not None
        view.key_field.value = "test-value"

        controller.dispose()

        self.assertEqual(view.key_field.value, "")
        self.assertGreater(service.cancel_calls, 0)

    async def test_secret_controls_redact_repr(self) -> None:
        async def text_callback(_value: str) -> None:
            return None

        async def callback() -> None:
            return None

        marker = "sensitive-test-marker"
        key_view = KeyEntryView(text_callback)
        key_view.key_field.value = marker
        pin_view = PinDisplayView(marker, "", callback)

        self.assertNotIn(marker, repr(key_view.key_field))
        self.assertNotIn(marker, repr(pin_view.pin_text))

    async def test_pin_confirmation_button_has_visible_control_states(self) -> None:
        async def callback() -> None:
            return None

        view = PinDisplayView("0000", "", callback)
        style = view.confirm_button.style
        assert style is not None
        colors = style.bgcolor
        assert isinstance(colors, dict)

        self.assertNotEqual(
            colors[ft.ControlState.DEFAULT],
            colors[ft.ControlState.DISABLED],
        )
        self.assertNotEqual(
            colors[ft.ControlState.DEFAULT],
            colors[ft.ControlState.PRESSED],
        )
        view.set_busy(True)
        self.assertTrue(view.confirm_button.disabled)

    async def test_key_button_follows_text_and_submits_current_value(self) -> None:
        submitted = 0

        async def text_callback(_value: str) -> None:
            nonlocal submitted
            submitted += 1

        view = KeyEntryView(text_callback)
        self.assertTrue(view.submit_button.disabled)
        self.assertIsNotNone(view.key_field.on_change)

        view.key_field.value = "test-value"
        view._apply_key_state()
        self.assertFalse(view.submit_button.disabled)
        view.set_busy(True)
        self.assertTrue(view.submit_button.disabled)
        view.set_busy(False)
        self.assertFalse(view.submit_button.disabled)
        await view._submit_value()
        self.assertEqual(submitted, 1)

        view.clear_key()
        self.assertTrue(view.submit_button.disabled)

    async def test_pin_button_requires_exactly_four_ascii_digits(self) -> None:
        async def text_callback(_value: str) -> None:
            return None

        async def callback() -> None:
            return None

        view = PinLoginView(text_callback, callback)
        self.assertTrue(view.submit_button.disabled)
        self.assertIsNotNone(view.pin_field.on_change)

        for value in ("1", "123", "１２３４", "12a4"):
            view.pin_field.value = value
            view._apply_pin_state()
            self.assertTrue(view.submit_button.disabled)

        view.pin_field.value = "1234"
        view._apply_pin_state()
        self.assertFalse(view.submit_button.disabled)

    async def test_lock_clears_only_session_and_returns_to_pin(self) -> None:
        page = FakePage()
        service = FakeAuthService(initial_route=InitialRoute.PIN)
        chat_service = FakeChatService()
        catalog_service = FakeCatalogService()
        controller = _make_controller(
            page,
            service,
            chat_service=chat_service,
            catalog_service=catalog_service,
        )

        await controller._activate_session(
            "session-test-credential",
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )
        self.assertTrue(controller._chat_controller.workspace_visible)

        await controller.lock_application()

        self.assertFalse(controller._chat_controller.session_active)
        self.assertFalse(controller._chat_controller.workspace_visible)
        self.assertIsNotNone(controller._pin_login_view)
        self.assertEqual(chat_service.delete_calls, 0)
        self.assertGreaterEqual(catalog_service.clear_calls, 2)

    async def test_correct_pin_opens_before_background_key_check_finishes(
        self,
    ) -> None:
        page = FakePage()
        service = FakeAuthService(initial_route=InitialRoute.PIN)
        service.login_result = AuthResult(
            AuthStatus.AUTHENTICATED,
            api_key="session-test-credential",
            key_validity=KeyValidityState.UNKNOWN,
            key_limit=KeyLimitInfo.unknown(),
        )
        key_validator = BlockingFakeKeyValidator()
        controller = _make_controller(
            page,
            service,
            key_validator=key_validator,
        )
        await controller.start()

        await asyncio.wait_for(controller.submit_pin("1234"), timeout=0.2)

        self.assertTrue(controller._chat_controller.workspace_visible)
        self.assertTrue(controller._chat_controller.key_validation_in_progress)
        await asyncio.wait_for(key_validator.started.wait(), timeout=0.2)
        self.assertFalse(key_validator.release.is_set())
        key_validator.release.set()
        while controller._chat_controller.key_validation_in_progress:
            await asyncio.sleep(0)
        controller.dispose()

    async def test_replacing_invalid_key_requires_confirmed_reset(self) -> None:
        page = FakePage()
        service = FakeAuthService(initial_route=InitialRoute.PIN)
        controller = _make_controller(page, service)
        await controller._activate_session(
            "session-test-credential",
            KeyValidityState.INVALID,
            KeyLimitInfo.unknown(),
        )

        await controller._chat_controller.request_key_replacement()
        controller.cancel_reset()

        self.assertEqual(service.reset_calls, 0)
        self.assertTrue(controller._chat_controller.session_active)

        await controller._chat_controller.request_key_replacement()
        await controller.confirm_reset()

        self.assertEqual(service.reset_calls, 1)
        self.assertFalse(controller._chat_controller.session_active)
        self.assertIsNotNone(controller._key_view)

    async def test_background_result_is_ignored_after_confirmed_reset(self) -> None:
        page = FakePage()
        service = FakeAuthService(initial_route=InitialRoute.PIN)
        key_validator = BlockingFakeKeyValidator(ignore_cancellation=True)
        controller = _make_controller(
            page,
            service,
            key_validator=key_validator,
        )
        await controller._activate_session(
            "session-test-credential",
            KeyValidityState.UNKNOWN,
            KeyLimitInfo.unknown(),
        )
        await asyncio.wait_for(key_validator.started.wait(), timeout=0.2)

        await controller.request_reset()
        await controller.confirm_reset()
        key_validator.release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertEqual(service.reset_calls, 1)
        self.assertFalse(controller._chat_controller.session_active)
        self.assertEqual(
            controller._chat_controller.key_validity,
            KeyValidityState.UNKNOWN,
        )
        self.assertIsNotNone(controller._key_view)


def _make_controller(
    page: FakePage,
    service: FakeAuthService,
    *,
    key_validator: FakeKeyValidator | None = None,
    chat_service: FakeChatService | None = None,
    catalog_service: FakeCatalogService | None = None,
) -> AppController:
    return AppController(
        cast(ft.Page, page),
        cast(AuthService, service),
        cast(KeyValidator, key_validator or FakeKeyValidator()),
        cast(ChatService, chat_service or FakeChatService()),
        cast(ModelCatalogService, catalog_service or FakeCatalogService()),
        cast(ChatBudgetService, object()),
        cast(MessageSendingService, object()),
        ChatDraftService(MemoryDraftRepository()),
    )


if __name__ == "__main__":
    unittest.main()
