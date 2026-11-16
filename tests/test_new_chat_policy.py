"""Creation policy and actual new-chat navigation never become an auth provider."""

from __future__ import annotations

import asyncio
import sys
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogService  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.catalog import CatalogFetchResult, CatalogStatus  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, CatalogModel, ChatMode  # noqa: E402
from i18n import get_language, localize_tree, set_language, tr  # noqa: E402
from providers.creation import NewChatPolicy  # noqa: E402
from providers.models import ProviderId  # noqa: E402
from providers.session import ProviderProfiles, ProviderSessionExpired  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.secure_credentials import (  # noqa: E402
    DEFAULT_PROVIDER_STORAGE_NAME,
    NEW_CHAT_POLICY_STORAGE_NAME,
    PROVIDER_KEY_STORAGE_NAMES,
    FletSecureCredentials,
    SecureCredentialsError,
)
from tests import test_provider_sending as sending_fixtures  # noqa: E402
from tests.test_provider_sessions import (  # noqa: E402
    OR_OLD,
    VV_OLD,
    FakeAPI,
    MemoryStorage,
)
from ui.model_selection_view import ModeSelectionView  # noqa: E402
from ui.provider_page import ProviderCheckResult, ProviderPage  # noqa: E402


class CreationPolicyStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = MemoryStorage()
        self.credentials = FletSecureCredentials(self.storage)

    async def test_new_registration_is_manual_but_pin_auth_still_reads_a_real_slot(
        self,
    ):
        await self.credentials.save_credentials(VV_OLD, "synthetic-registration")
        self.assertIs(
            await self.credentials.get_new_chat_policy(), NewChatPolicy.MANUAL
        )
        self.assertIs(await self.credentials.get_default_provider(), ProviderId.VSEGPT)
        self.assertEqual(await self.credentials.get_api_key(), VV_OLD)
        self.assertNotIn("manual", PROVIDER_KEY_STORAGE_NAMES)

    async def test_explicit_legacy_preferences_survive_and_absence_is_manual(self):
        for provider in ProviderId:
            with self.subTest(provider=provider):
                self.storage.values = {DEFAULT_PROVIDER_STORAGE_NAME: provider.value}
                self.assertIs(
                    await self.credentials.get_new_chat_policy(),
                    NewChatPolicy.for_provider(provider),
                )
        self.storage.values = {
            PROVIDER_KEY_STORAGE_NAMES[ProviderId.OPENROUTER]: OR_OLD
        }
        self.assertIs(
            await self.credentials.get_new_chat_policy(), NewChatPolicy.MANUAL
        )
        self.assertEqual(await self.credentials.get_api_key(), OR_OLD)

    async def test_policy_can_choose_an_unconfigured_service_without_moving_login_slot(
        self,
    ):
        await self.credentials.save_credentials(OR_OLD, "synthetic-registration")
        await self.credentials.set_new_chat_policy(NewChatPolicy.VSEGPT)
        self.assertEqual(await self.credentials.get_api_key(), OR_OLD)
        self.assertIsNone(await self.credentials.get_provider_key(ProviderId.VSEGPT))
        self.assertIs(
            await self.credentials.get_new_chat_policy(), NewChatPolicy.VSEGPT
        )

    async def test_key_replacement_preserves_the_creation_policy(self):
        for policy in NewChatPolicy:
            with self.subTest(policy=policy):
                await self.credentials.save_credentials(
                    OR_OLD, "synthetic-registration"
                )
                await self.credentials.set_new_chat_policy(policy)
                await self.credentials.replace_api_key(VV_OLD)
                self.assertIs(await self.credentials.get_new_chat_policy(), policy)
                self.assertEqual(await self.credentials.get_api_key(), VV_OLD)
                self.assertEqual(
                    await self.credentials.get_provider_key(ProviderId.OPENROUTER),
                    OR_OLD,
                )

    async def test_corrupt_or_failed_metadata_never_silently_replaces_preference(self):
        self.storage.values[NEW_CHAT_POLICY_STORAGE_NAME] = "not-a-provider-or-policy"
        with self.assertRaises(SecureCredentialsError):
            await self.credentials.get_new_chat_policy()
        self.storage.values[NEW_CHAT_POLICY_STORAGE_NAME] = NewChatPolicy.MANUAL.value
        self.storage.bad_read_after_write = NEW_CHAT_POLICY_STORAGE_NAME
        with self.assertRaises(SecureCredentialsError):
            await self.credentials.set_new_chat_policy(NewChatPolicy.VSEGPT)
        self.storage.bad_read_after_write = None
        self.assertIs(
            await self.credentials.get_new_chat_policy(), NewChatPolicy.MANUAL
        )

    async def test_legacy_combined_default_write_rolls_back_both_metadata_on_failure(
        self,
    ):
        await self.credentials.save_credentials(OR_OLD, "synthetic-registration")
        await self.credentials.save_provider_key(
            ProviderId.VSEGPT, VV_OLD, authorization_confirmed=False
        )
        self.storage.bad_read_after_write = NEW_CHAT_POLICY_STORAGE_NAME
        with self.assertRaises(SecureCredentialsError):
            await self.credentials.set_default_provider(
                ProviderId.VSEGPT, creation_policy=NewChatPolicy.VSEGPT
            )
        self.storage.bad_read_after_write = None
        self.assertIs(
            await self.credentials.get_default_provider(), ProviderId.OPENROUTER
        )
        self.assertIs(
            await self.credentials.get_new_chat_policy(), NewChatPolicy.MANUAL
        )
        self.assertEqual(await self.credentials.get_api_key(), OR_OLD)

    async def test_profiles_reload_policy_after_lock_without_changing_auth_key_or_network(
        self,
    ):
        await self.credentials.save_credentials(OR_OLD, "synthetic-registration")
        api = FakeAPI()
        profiles = ProviderProfiles(self.credentials, api)
        self.addCleanup(profiles.deactivate)
        await profiles.activate(OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown())
        self.assertIs(getattr(profiles, "creation_policy"), NewChatPolicy.MANUAL)
        await profiles.set_creation_policy(NewChatPolicy.VSEGPT)
        self.assertIs(profiles.default_provider, ProviderId.OPENROUTER)
        profiles.deactivate()
        await profiles.activate(OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown())
        self.assertIs(profiles.creation_policy, NewChatPolicy.VSEGPT)
        self.assertEqual(profiles.key_for(ProviderId.OPENROUTER), OR_OLD)
        self.assertIsNone(profiles.key_for(ProviderId.VSEGPT))
        self.assertEqual(api.validations, [])
        self.assertEqual(api.balances, [])

    async def test_late_policy_write_cannot_publish_into_a_locked_session(self):
        await self.credentials.save_credentials(OR_OLD, "synthetic-registration")
        profiles = ProviderProfiles(self.credentials, FakeAPI())
        self.addCleanup(profiles.deactivate)
        await profiles.activate(OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown())
        self.storage.pause_value = NewChatPolicy.VSEGPT.value
        task = asyncio.create_task(profiles.set_creation_policy(NewChatPolicy.VSEGPT))
        await self.storage.write_gate.entered.wait()
        profiles.deactivate()
        self.storage.write_gate.release.set()
        with self.assertRaises(ProviderSessionExpired):
            await task
        self.assertFalse(profiles.active)
        self.assertIsNone(profiles.key_for(ProviderId.OPENROUTER))
        await profiles.activate(OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown())
        self.assertIs(profiles.creation_policy, NewChatPolicy.VSEGPT)


class CreationPolicyControllerTests(unittest.IsolatedAsyncioTestCase):
    chats: SqliteChatRepository
    database: AuthDatabase
    model: CatalogModel
    asyncSetUp = sending_fixtures.ProviderSendingTests.asyncSetUp
    make_sender = sending_fixtures.ProviderSendingTests.make_sender
    controller = sending_fixtures.ProviderSendingTests.controller

    async def manual_controller(self):
        controller, profiles, page, presented, opened = await self.controller()
        setattr(profiles, "creation_policy", NewChatPolicy.MANUAL)
        view = controller._workspace_view
        assert view is not None
        await controller._workspace_controller.update_draft(
            "rub", "Existing unsent draft"
        )
        view.restore_editor("Existing unsent draft")
        return controller, profiles, page, presented, opened

    def assert_original_chat_and_draft(self, controller):
        self.assertEqual(controller.selected_chat_id, "rub")
        self.assertEqual(len(self.chats.list_chats()), 1)
        self.assertEqual(
            SqliteDraftRepository(self.database.path).get_draft("rub").text,
            "Existing unsent draft",
        )
        chat = self.chats.get_chat("rub")
        assert chat is not None
        self.assertIs(chat.provider_id, ProviderId.VSEGPT)

    async def test_manual_picker_opens_once_before_any_catalogue_read_and_back_preserves_home(
        self,
    ):
        controller, _, page, _, _ = await self.manual_controller()
        with patch.object(
            controller._catalog_service,
            "get_catalog",
            wraps=controller._catalog_service.get_catalog,
        ) as get_catalog:
            await asyncio.gather(
                controller.request_new_chat(), controller.request_new_chat()
            )
            self.assertEqual(len(page.dialogs), 1)
            selector = controller._creation_selector
            assert selector is not None
            self.assertEqual(set(selector.provider_buttons), set(ProviderId))
            get_catalog.assert_not_awaited()
            self.assertTrue(await controller.handle_application_back())
            self.assertEqual(page.dialogs, [])
            self.assert_original_chat_and_draft(controller)

    async def test_consecutive_chats_can_use_different_services_without_changing_manual_policy(
        self,
    ):
        controller, profiles, _, _, _ = await self.manual_controller()
        await controller.request_new_chat()
        await controller.select_creation_provider(ProviderId.OPENROUTER)
        await controller.select_chat_mode(ChatMode.FREE)
        await controller.select_chat_model(FREE_ROUTER_MODEL)
        await controller.submit_new_chat_limits("8192", "64", None)
        first_id = controller.selected_chat_id
        assert first_id is not None
        first = self.chats.get_chat(first_id)
        assert first is not None
        self.assertIs(first.provider_id, ProviderId.OPENROUTER)
        await controller.request_new_chat()
        self.assertIsNotNone(controller._creation_dialog)
        await controller.select_creation_provider(ProviderId.VSEGPT)
        await controller.select_chat_mode(ChatMode.PAID)
        await controller.select_chat_model(self.model)
        await controller.submit_new_chat_limits("8192", "64", "50")
        second_id = controller.selected_chat_id
        assert second_id is not None
        second = self.chats.get_chat(second_id)
        assert second is not None
        self.assertNotEqual(first.id, second.id)
        self.assertIs(second.provider_id, ProviderId.VSEGPT)
        self.assertIs(getattr(profiles, "creation_policy"), NewChatPolicy.MANUAL)
        self.assertIs(profiles.default_provider, ProviderId.OPENROUTER)
        self.assertEqual(len(self.chats.list_chats()), 3)
        self.assertEqual(
            SqliteDraftRepository(self.database.path).get_draft("rub").text,
            "Existing unsent draft",
        )

    async def test_explicit_policy_skips_question_and_missing_key_never_falls_back(
        self,
    ):
        controller, profiles, page, _, _ = await self.manual_controller()
        setattr(profiles, "creation_policy", NewChatPolicy.VSEGPT)
        profiles.keys.pop(ProviderId.VSEGPT)
        await controller.request_new_chat()
        self.assertIsNone(controller._creation_selector)
        self.assertIsNotNone(controller._creation_dialog)
        self.assertEqual(len(page.dialogs), 1)
        creation = controller._chat_creation
        assert creation is not None
        self.assertIs(creation.provider, ProviderId.VSEGPT)
        self.assertIsNone(controller._catalog)
        self.assert_original_chat_and_draft(controller)
        await controller.cancel_new_chat()
        profiles.keys[ProviderId.VSEGPT] = sending_fixtures.KEY
        await controller.request_new_chat()
        self.assertIsNone(controller._creation_dialog)
        self.assertIs(controller._creation_provider, ProviderId.VSEGPT)
        self.assertIsNotNone(controller._catalog)
        await controller.cancel_new_chat()
        self.assert_original_chat_and_draft(controller)

    async def test_missing_key_returns_to_exact_provider_and_requires_explicit_resume(
        self,
    ):
        controller, profiles, _, _, _ = await self.manual_controller()
        profiles.keys.pop(ProviderId.VSEGPT)
        settings = []

        async def configure(provider):
            settings.append(provider)
            await controller.prepare_navigation()

        controller._on_provider_settings_for = configure
        await controller.request_new_chat()
        await controller.select_creation_provider(ProviderId.VSEGPT)
        dialog = controller._creation_dialog
        assert dialog is not None
        button = dialog.actions[-1]
        assert isinstance(button, ft.Button)
        handler = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
        await handler(cast(ft.Event, None))
        self.assertEqual(settings, [ProviderId.VSEGPT])
        self.assertTrue(controller._creation_waiting_for_key)
        self.assert_original_chat_and_draft(controller)
        profiles.keys[ProviderId.VSEGPT] = sending_fixtures.KEY
        profiles.revisions[ProviderId.VSEGPT] += 1
        await controller.resume_home()
        selector = controller._creation_selector
        assert selector is not None
        self.assertEqual(set(selector.provider_buttons), {ProviderId.VSEGPT})
        self.assertIsNone(controller._catalog)
        await controller.handle_application_back()
        self.assert_original_chat_and_draft(controller)

    async def test_cancel_each_creation_phase_keeps_existing_connection_and_draft(self):
        controller, _, _, _, _ = await self.manual_controller()
        for phase in ("mode", "model", "limits"):
            with self.subTest(phase=phase):
                await controller.request_new_chat()
                await controller.select_creation_provider(ProviderId.VSEGPT)
                if phase in {"model", "limits"}:
                    await controller.select_chat_mode(ChatMode.PAID)
                if phase == "limits":
                    await controller.select_chat_model(self.model)
                while await controller.handle_application_back():
                    pass
                self.assert_original_chat_and_draft(controller)
                self.assertIsNone(controller._chat_creation)

    async def test_empty_profile_and_both_missing_keys_do_not_create_an_empty_chat(
        self,
    ):
        controller, profiles, _, _, _ = await self.controller()
        controller.deactivate()
        self.chats.delete_chat("rub")
        setattr(profiles, "creation_policy", NewChatPolicy.MANUAL)
        profiles.keys.clear()
        await controller.activate(
            sending_fixtures.KEY, KeyValidityState.UNVERIFIED, KeyLimitInfo.unknown()
        )
        for provider in ProviderId:
            await controller.request_new_chat()
            self.assertIsNotNone(controller._creation_selector)
            await controller.select_creation_provider(provider)
            self.assertIsNone(controller._catalog)
            await controller.cancel_new_chat()
            self.assertEqual(self.chats.list_chats(), [])
            self.assertIsNone(controller.selected_chat_id)

    async def test_late_catalogue_after_lock_or_cancellation_cannot_reopen_creation(
        self,
    ):
        for action in ("cancel", "lock"):
            with self.subTest(action=action):
                controller, _, _, presented, _ = await self.manual_controller()
                entered, release = asyncio.Event(), asyncio.Event()
                get_catalog = controller._catalog_service.get_catalog

                async def delayed(key):
                    entered.set()
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        await release.wait()
                    return await get_catalog(key)

                with patch.object(
                    controller._catalog_service, "get_catalog", side_effect=delayed
                ):
                    await controller.request_new_chat()
                    task = asyncio.create_task(
                        controller.select_creation_provider(ProviderId.VSEGPT)
                    )
                    await entered.wait()
                    if action == "cancel":
                        await controller.cancel_new_chat()
                    else:
                        controller.deactivate()
                    count = len(presented)
                    release.set()
                    await task
                    self.assertEqual(len(presented), count)
                    self.assertIsNone(controller._catalog)
                    self.assertIsNone(controller._chat_creation)
                    self.assertEqual(len(self.chats.list_chats()), 1)

    async def test_explicit_refresh_bypasses_negative_ttl_but_respects_cooldown(self):
        controller, _, _, _, _ = await self.manual_controller()
        clock = [0.0]

        model = self.model

        class Catalogue:
            calls = 0

            async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...]:
                raise AssertionError("Use the typed result")

            async def fetch_catalog(self, api_key: str) -> CatalogFetchResult:
                self.calls += 1
                return (
                    CatalogFetchResult(CatalogStatus.NETWORK_ERROR)
                    if self.calls == 1
                    else CatalogFetchResult(CatalogStatus.SUCCESS, (model,))
                )

        client = Catalogue()
        controller._catalog_service = ModelCatalogService(
            client, clock=lambda: clock[0]
        )
        await controller.request_new_chat()
        await controller.select_creation_provider(ProviderId.VSEGPT)
        failed = controller._catalog
        assert failed is not None
        self.assertIs(failed.status, CatalogStatus.NETWORK_ERROR)
        await controller.refresh_chat_catalog()
        self.assertEqual(client.calls, 1)
        clock[0] = 3.0
        await controller.refresh_chat_catalog()
        self.assertEqual(client.calls, 2)
        refreshed = controller._catalog
        assert refreshed is not None
        self.assertIs(refreshed.status, CatalogStatus.SUCCESS)
        self.assert_original_chat_and_draft(controller)
        await controller.cancel_new_chat()

    async def test_retained_mode_callback_cannot_act_on_a_later_creation_using_same_cache(
        self,
    ):
        controller, _, _, _, _ = await self.manual_controller()
        views = []

        def mode_view(*args, **kwargs):
            view = ModeSelectionView(*args, **kwargs)
            views.append(view)
            return view

        with patch("chat_controller.ModeSelectionView", side_effect=mode_view):
            await controller.request_new_chat()
            await controller.select_creation_provider(ProviderId.VSEGPT)
            old_catalog = controller._catalog
            old_button = views[-1].paid_button
            await controller.cancel_new_chat()
            await controller.request_new_chat()
            await controller.select_creation_provider(ProviderId.VSEGPT)
            self.assertIs(controller._catalog, old_catalog)
            callback = cast(Callable[[ft.Event], Awaitable[None]], old_button.on_click)
            await callback(cast(ft.Event, None))
            self.assertIsNone(controller._pending_mode)
            self.assertIsNone(controller._pending_model)
            self.assert_original_chat_and_draft(controller)


class CreationPolicyPresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_policy_localization_preserves_choice_and_is_not_a_view_filter(self):
        original = get_language()
        self.addCleanup(set_language, original)
        selected = []

        async def noop(*_args):
            return None

        async def check(*_args):
            return ProviderCheckResult(False)

        async def save(*_args):
            return False

        async def choose(policy):
            selected.append(policy)

        page = ProviderPage(
            on_check=check, on_save=save, on_refresh=noop, on_default=choose
        )
        self.assertEqual(page.default_selector.value, NewChatPolicy.MANUAL.value)
        await page.set_filter(ProviderId.VSEGPT)
        for language in ("en", "ru"):
            for option in page.default_selector.options:
                object.__setattr__(option, "_frozen", True)
            set_language(language)
            localize_tree(page.control)
            page.sync_language()
            self.assertEqual(
                page.default_selector.options[0].text, tr("creation.manual")
            )
            self.assertEqual(page.default_help.value, tr("creation.manual_help"))
            self.assertEqual(page.default_selector.value, NewChatPolicy.MANUAL.value)
            self.assertIs(page.provider_filter.value, ProviderId.VSEGPT)
        page.default_selector.value = NewChatPolicy.OPENROUTER.value
        await page._default_changed(cast(ft.Event, None))
        self.assertEqual(selected, [NewChatPolicy.OPENROUTER])
        self.assertIn("OpenRouter", page.default_help.value)
        page.clear_private()
        await page._default_changed(cast(ft.Event, None))
        self.assertEqual(selected, [NewChatPolicy.OPENROUTER])
