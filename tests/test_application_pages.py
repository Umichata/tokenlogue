"""App composition with fake secure storage and temporary request journals."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, call, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import (  # noqa: E402
    CreditsResult,
    CreditsStatus,
    KeyValidationResult,
    KeyValidationStatus,
)
from app import AppController  # noqa: E402
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import InitialRoute, KeyLimitInfo, KeyValidityState  # noqa: E402
from auth.service import AuthService  # noqa: E402
from chat.analytics import AnalyticsFilter  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.models import ChatMode  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from providers.models import Currency, ProviderId, detect_key  # noqa: E402
from providers.session import ProviderProfiles  # noqa: E402
from storage.analytics_repository import SqliteAnalyticsRepository  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests import test_app as app_fixtures  # noqa: E402
from tests import test_chat_ui_integration as chat_fixtures  # noqa: E402
from tests.test_secure_credentials import FakeSecureStorage  # noqa: E402
from ui.workspace_shell import WorkspacePage  # noqa: E402

FAKE_OPENROUTER = "sk-or-v1-offline-application-pages"
FAKE_VSEGPT = "sk-or-vv-offline-application-pages"


class ApplicationPage(app_fixtures.FakePage):
    platform = ft.PagePlatform.ANDROID

    def __init__(self) -> None:
        super().__init__()
        self.height = 700
        self.root_view = SimpleNamespace(
            can_pop=True, on_confirm_pop=None, confirm_pop=AsyncMock()
        )
        self.views = [cast(ft.View, self.root_view)]


class OfflineProviderAPI:
    async def validate_key(self, api_key: str) -> KeyValidationResult:
        provider = detect_key(api_key)
        assert provider is not None
        return KeyValidationResult(
            KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT, provider_id=provider
        )

    async def get_credits(self, api_key: str) -> CreditsResult:
        provider = detect_key(api_key)
        assert provider is not None
        return CreditsResult(
            CreditsStatus.RESTRICTED,
            provider_id=provider,
            currency=Currency.USD
            if provider is ProviderId.OPENROUTER
            else Currency.RUB,
        )


class ApplicationPagesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.fx = chat_fixtures.ChatUiIntegrationTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.temp_dir.cleanup)
        updates = patch.object(ft.Control, "update", return_value=None)
        updates.start()
        self.addCleanup(updates.stop)
        self.chat_id = await self.fx._create_chat(ChatMode.FREE)
        self.page = ApplicationPage()
        self.auth = app_fixtures.FakeAuthService(initial_route=InitialRoute.PIN)
        self.credentials = FletSecureCredentials(FakeSecureStorage())
        await self.credentials.save_provider_key(
            ProviderId.OPENROUTER, FAKE_OPENROUTER, authorization_confirmed=True
        )
        await self.credentials.save_provider_key(
            ProviderId.VSEGPT, FAKE_VSEGPT, authorization_confirmed=False
        )
        self.profiles = ProviderProfiles(self.credentials, OfflineProviderAPI())
        self.client = chat_fixtures.BlockingCompletionClient(
            chat_fixtures._success("reply")
        )
        validator = chat_fixtures.FakeKeyValidator()
        catalog = ModelCatalogService(
            chat_fixtures.FakeCatalogClient((self.fx.paid_model,))
        )
        sending = MessageSendingService(
            self.fx.chat_service,
            self.fx.message_repository,
            self.client,
            chat_fixtures.FakeCatalogClient((self.fx.paid_model,)),
            validator,
            now=lambda: chat_fixtures.NOW,
        )
        self.drafts = ChatDraftService(self.fx.draft_repository)
        self.analytics = SqliteAnalyticsRepository(self.fx.chat_repository.path)
        self.app = AppController(
            cast(ft.Page, self.page),
            cast(AuthService, self.auth),
            cast(KeyValidator, validator),
            self.fx.chat_service,
            catalog,
            self.fx.budget_service,
            sending,
            self.drafts,
            provider_profiles=self.profiles,
            analytics_repository=self.analytics,
        )
        self.addCleanup(self.app.dispose)
        await self.app._activate_session(
            FAKE_OPENROUTER,
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )
        await self.app._chat_controller.select_chat(self.chat_id)

    def shell(self):
        shell = self.app._workspace_shell
        assert shell is not None
        return shell

    def home(self):
        home = self.app._chat_controller._workspace_view
        assert home is not None
        return home

    async def test_real_app_composes_four_pages_and_navigation_flushes_exact_draft(
        self,
    ):
        shell, home = self.shell(), self.home()
        assert home.composer is not None
        draft = " Exact draft\nЮникод 👋 "
        home.composer.message_field.value = draft
        prepare = self.app._chat_controller.prepare_navigation
        with patch.object(
            self.app._chat_controller, "prepare_navigation", wraps=prepare
        ) as navigation:
            for destination in (
                WorkspacePage.PROVIDERS,
                WorkspacePage.TOKENS,
                WorkspacePage.SPENDING,
            ):
                self.assertTrue(await shell.select(destination))
                self.assertEqual(shell.selected_page, destination)
                self.assertIs(self.home(), home)
                self.assertIs(self.app._workspace_shell, shell)
            self.assertEqual(navigation.await_count, 3)
        self.assertEqual(self.fx.draft_repository.get_draft(self.chat_id).text, draft)
        self.assertEqual(self.client.calls, 0)
        self.assertEqual(self.fx.chat_repository.list_messages(self.chat_id), [])
        assert (
            self.app._token_usage_page is not None
            and self.app._spending_page is not None
        )
        self.assertIsNotNone(self.app._token_usage_page._snapshot)
        self.assertIsNotNone(self.app._spending_page._snapshot)
        await shell.select(WorkspacePage.HOME)
        self.assertEqual(self.home().editor_value, draft)
        self.assertFalse(self.app._chat_controller._navigation_hidden)

    async def test_background_completion_updates_once_without_stealing_spending_page(
        self,
    ):
        shell, home = self.shell(), self.home()
        operation = asyncio.create_task(
            self.app._chat_controller.submit_message("send once")
        )
        try:
            await asyncio.wait_for(self.client.started.wait(), 3)
            await shell.select(WorkspacePage.SPENDING)
            spending_control = shell._content.content
            self.app._present_home(home.control)
            self.assertIs(shell._content.content, spending_control)
        finally:
            self.client.release.set()
            await asyncio.wait_for(operation, 3)
        self.assertEqual(shell.selected_page, WorkspacePage.SPENDING)
        self.assertIs(shell._content.content, spending_control)
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(len(self.analytics.list_attempts()), 1)
        self.assertEqual(len(self.fx.chat_repository.list_messages(self.chat_id)), 2)
        await self.app._load_spending(
            AnalyticsFilter(period="all", timezone_name="UTC")
        )
        assert self.app._spending_page is not None
        snapshot = self.app._spending_page._snapshot
        assert snapshot is not None
        self.assertEqual(sum(row.requests for row in snapshot.usage_rows), 1)

    async def test_lock_wipes_all_private_pages_before_slow_draft_flush(self):
        shell = self.shell()
        providers, tokens, spending = (
            self.app._provider_page,
            self.app._token_usage_page,
            self.app._spending_page,
        )
        assert providers is not None and tokens is not None and spending is not None
        await shell.select(WorkspacePage.TOKENS)
        await shell.select(WorkspacePage.SPENDING)
        card = providers.cards[ProviderId.VSEGPT]
        card.key_field.value = FAKE_VSEGPT + "-candidate"
        card.key_field.password = False
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_flush() -> bool:
            started.set()
            await release.wait()
            return True

        with patch.object(self.app._chat_controller, "flush_drafts", delayed_flush):
            self.app.prepare_system_lock("screen_lock")
            self.assertFalse(self.profiles.active)
            self.assertIsNone(self.app._workspace_shell)
            self.assertEqual(card.key_field.value, "")
            self.assertTrue(card.key_field.password)
            self.assertEqual(tokens._body.controls, [])
            self.assertEqual(spending._body.controls, [])
            self.assertIsNone(shell._content.content)
            self.assertIsNone(self.page.root_view.on_confirm_pop)
            await started.wait()
            release.set()
            await self.app.wait_system_lock()
        self.assertFalse(self.app._chat_controller.session_active)
        self.assertIsNotNone(self.app._pin_login_view)

    async def test_late_analytics_result_cannot_restore_locked_page(self):
        tokens = self.app._token_usage_page
        assert tokens is not None
        entered, release = threading.Event(), threading.Event()
        original = self.analytics.list_attempts

        def blocked_read():
            entered.set()
            if not release.wait(3):
                raise TimeoutError("offline analytics fixture release missing")
            return original()

        with patch.object(self.analytics, "list_attempts", side_effect=blocked_read):
            loading = asyncio.create_task(
                self.app._load_token_usage(AnalyticsFilter(period="all"))
            )
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                self.app.prepare_system_lock("screen_lock")
                self.assertIsNone(self.app._token_usage_page)
                self.assertIsNone(tokens._snapshot)
            finally:
                release.set()
                await asyncio.wait_for(loading, 3)
                await self.app.wait_system_lock()
        self.assertIsNone(tokens._snapshot)
        self.assertEqual(tokens._body.controls, [])
        self.assertFalse(tokens.progress.visible)

    async def test_android_back_resolves_page_dialog_drawer_then_exit(self):
        shell = self.shell()
        event = ft.Event(
            name="confirm_pop", control=cast(ft.Control, self.page.views[0])
        )
        await shell.select(WorkspacePage.PROVIDERS)
        await self.app._application_back(event)
        self.assertEqual(shell.selected_page, WorkspacePage.HOME)
        self.page.root_view.confirm_pop.assert_awaited_with(False)
        self.assertIsNotNone(self.page.drawer)
        home = self.home()
        await home.open_menu()
        await self.app._application_back(event)
        self.assertFalse(home.menu_open)
        self.page.root_view.confirm_pop.assert_awaited_with(False)
        await home._show_drawer()
        self.assertTrue(home.drawer_open)
        await self.app._application_back(event)
        self.assertFalse(home.drawer_open)
        self.page.root_view.confirm_pop.assert_awaited_with(False)
        await self.app._application_back(event)
        self.page.root_view.confirm_pop.assert_awaited_with(True)
        self.assertEqual(
            self.page.root_view.confirm_pop.await_args_list,
            [call(False), call(False), call(False), call(True)],
        )

    async def test_android_background_clears_private_pages_and_resume_requires_pin(
        self,
    ):
        providers = self.app._provider_page
        assert providers is not None
        card = providers.cards[ProviderId.OPENROUTER]
        card.key_field.value = FAKE_OPENROUTER + "-candidate"
        await self.shell().select(WorkspacePage.PROVIDERS)
        await self.app.handle_lifecycle_change(
            cast(
                ft.AppLifecycleStateChangeEvent,
                SimpleNamespace(state=ft.AppLifecycleState.HIDE),
            )
        )
        self.assertEqual(card.key_field.value, "")
        self.assertIsNone(self.app._workspace_shell)
        self.assertFalse(self.profiles.active)
        self.assertIsNotNone(self.app._pin_login_view)
        await self.app.handle_lifecycle_change(
            cast(
                ft.AppLifecycleStateChangeEvent,
                SimpleNamespace(state=ft.AppLifecycleState.RESUME),
            )
        )
        self.assertIsNone(self.app._workspace_shell)
        self.assertFalse(self.app._chat_controller.session_active)

    async def test_activation_without_shell_does_not_schedule_competing_home_refresh(
        self,
    ):
        self.app._clear_application_pages()
        with patch.object(
            self.app._chat_controller, "refresh_provider_state", new=AsyncMock()
        ) as refresh:
            self.app._providers_changed()
            await asyncio.sleep(0)
            refresh.assert_not_awaited()

        async def finished() -> None:
            return None

        task = asyncio.create_task(finished())
        await task
        self.app._provider_ui_refresh = task
        with patch(
            "app.asyncio.current_task",
            side_effect=RuntimeError("no running event loop"),
        ):
            self.app._clear_application_pages()
        self.assertIsNone(self.app._provider_ui_refresh)

    async def test_successful_provider_save_returns_true_and_clears_candidate(self):
        page = self.app._provider_page
        assert page is not None
        card = page.cards[ProviderId.VSEGPT]
        replacement = FAKE_VSEGPT + "-replacement"
        card.key_field.value = replacement
        await page.check_candidate(ProviderId.VSEGPT)
        await page.save_candidate(ProviderId.VSEGPT)
        self.assertEqual(self.profiles.key_for(ProviderId.VSEGPT), replacement)
        self.assertEqual(card.key_field.value, "")
        self.assertTrue(card.key_field.password)


if __name__ == "__main__":
    unittest.main()
