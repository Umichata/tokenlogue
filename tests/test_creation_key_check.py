"""Captured connection choices check their own slots and skip VSEGPT mode UI."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import KeyValidationResult, KeyValidationStatus  # noqa: E402
from auth.key_validation import interpret_key_validation  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.models import ChatMode, ModelCatalog  # noqa: E402
from chat_controller import ProviderProfiles as ProfilesContract  # noqa: E402
from providers.creation import NewChatPolicy  # noqa: E402
from providers.models import Currency, PriceUnit, ProviderId  # noqa: E402
from providers.session import ProviderProfiles  # noqa: E402
from storage.secure_credentials import FletSecureCredentials  # noqa: E402
from tests import test_chat_connection_controller as connection_fixtures  # noqa: E402
from tests.test_provider_sending import FakeProviderProfiles  # noqa: E402
from tests.test_provider_sessions import MemoryStorage  # noqa: E402
from ui.model_selection_view import ModelSelectionView, ModeSelectionView  # noqa: E402


class _CheckingProfiles(FakeProviderProfiles):
    def __init__(self):
        super().__init__()
        self.creation_policy = NewChatPolicy.MANUAL
        self.limits = {p: self.key_limit_for(p) for p in ProviderId}
        self.validation_calls = []
        self.result = KeyValidationResult(KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT)
        self.hold = False
        self.ignore_cancellation = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.validate_finished = asyncio.Event()

    def key_limit_for(self, provider):
        if hasattr(self, "limits"):
            return self.limits[provider]
        return super().key_limit_for(provider)

    async def refresh(self, provider, *, after_response=False, validate_key=False):
        if not validate_key:
            return None
        key, revision = self.key_for(provider), self.credential_revision(provider)
        self.validation_calls.append((provider, key))
        self.entered.set()
        if self.hold:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                if not self.ignore_cancellation:
                    raise
                await self.release.wait()
        if (
            self.key_for(provider) != key
            or self.credential_revision(provider) != revision
        ):
            return None
        result = replace(self.result, provider_id=provider)
        self.validity[provider], self.limits[provider] = interpret_key_validation(
            result
        )
        self.validate_finished.set()
        return result


class CreationKeyCheckTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = connection_fixtures.ChatConnectionControllerTests("runTest")
        await self.fixture.asyncSetUp()
        self.controller = self.fixture.controller
        self.or_paid_model = replace(
            self.fixture.catalogues.vsegpt,
            id="only/openrouter-paid",
            provider_id=ProviderId.OPENROUTER,
            currency=Currency.USD,
            pricing_unit=PriceUnit.TOKEN,
            pricing_is_complete=True,
            prompt_price_per_token=Decimal("0.001"),
            completion_price_per_token=Decimal("0.002"),
        )
        self.fixture.catalogues.rows[ProviderId.OPENROUTER] += (self.or_paid_model,)
        self.fixture.catalog.clear_cache()
        self.profiles = _CheckingProfiles()
        self.profiles.keys = dict(self.fixture.profiles.keys)
        self.controller._provider_profiles = cast(ProfilesContract, self.profiles)
        for callback, args, kwargs in getattr(self.fixture, "_cleanups"):
            self.addCleanup(callback, *args, **kwargs)
        getattr(self.fixture, "_cleanups").clear()
        self.addAsyncCleanup(self.fixture.asyncTearDown)

    async def choose_new(self, provider):
        await self.controller.request_new_chat()
        await self.controller.select_creation_provider(provider)

    async def assert_no_chat_or_send(self):
        self.assertEqual(len(await self.fixture.chats.list_chats()), 2)
        self.assertEqual(self.fixture.completion.calls, 0)
        self.assertEqual(
            self.fixture.drafts_repo.get_draft(self.fixture.original.id).text,
            "Keep this draft exact.  ",
        )

    async def test_manual_vsegpt_opens_models_without_ever_mounting_mode_and_back_preserves_home(
        self,
    ):
        with patch(
            "chat_controller.ModeSelectionView", wraps=ModeSelectionView
        ) as mode:
            await self.choose_new(ProviderId.VSEGPT)
            mode.assert_not_called()
            self.assertIsInstance(self.controller._selection_view, ModelSelectionView)
            self.assertEqual(self.controller._screen.value, "model_selection")
            self.assertIs(self.controller._pending_mode, ChatMode.PAID)
            await self.controller.handle_application_back()
            mode.assert_not_called()
        self.assertIsNotNone(self.controller._creation_selector)
        self.assertIs(self.profiles.creation_policy, NewChatPolicy.MANUAL)
        await self.controller.handle_application_back()
        self.assertEqual(self.controller.selected_chat_id, self.fixture.original.id)
        await self.assert_no_chat_or_send()

    async def test_fixed_vsegpt_model_back_cancels_directly_and_refresh_and_limits_back_never_show_modes(
        self,
    ):
        self.profiles.creation_policy = NewChatPolicy.VSEGPT
        with patch(
            "chat_controller.ModeSelectionView", wraps=ModeSelectionView
        ) as mode:
            await self.controller.request_new_chat()
            await self.controller.refresh_chat_catalog()
            self.assertEqual(self.controller._screen.value, "model_selection")
            await self.controller.select_chat_model(self.fixture.catalogues.vsegpt)
            self.assertEqual(self.controller._screen.value, "limits_selection")
            self.assertIsNotNone(self.controller._new_limits_view)
            await self.controller.handle_application_back()
            self.assertEqual(self.controller._screen.value, "model_selection")
            await self.controller.handle_application_back()
            mode.assert_not_called()
        self.assertIsNone(self.controller._chat_creation)
        self.assertIsNone(self.controller._creation_selector)
        await self.assert_no_chat_or_send()

    async def test_connection_vsegpt_back_restores_provider_chooser_without_changing_connection(
        self,
    ):
        with patch(
            "chat_controller.ModeSelectionView", wraps=ModeSelectionView
        ) as mode:
            await self.controller.request_change_provider(self.fixture.original.id)
            await self.controller.select_connection_provider(ProviderId.VSEGPT)
            self.assertIsInstance(self.controller._selection_view, ModelSelectionView)
            await self.controller.refresh_chat_catalog()
            await self.controller.handle_application_back()
            mode.assert_not_called()
        self.assertIsNotNone(self.controller._provider_switch_dialog)
        await self.controller.cancel_connection_change()
        await self.fixture.assert_original()
        await self.assert_no_chat_or_send()

    async def test_missing_vsegpt_key_can_be_configured_and_explicitly_resumed_into_models(
        self,
    ):
        self.profiles.keys.pop(ProviderId.VSEGPT)
        await self.choose_new(ProviderId.VSEGPT)
        dialog = self.controller._creation_dialog
        assert dialog is not None
        await self.fixture.click(dialog.actions[-1])
        self.assertEqual(self.fixture.settings, [ProviderId.VSEGPT])
        self.profiles.keys[ProviderId.VSEGPT] = "sk-or-vis-only-local-replacement"
        self.profiles.revisions[ProviderId.VSEGPT] += 1
        await self.controller.resume_home()
        self.assertIsNotNone(self.controller._creation_selector)
        await self.controller.select_creation_provider(ProviderId.VSEGPT)
        self.assertEqual(self.controller._screen.value, "model_selection")
        await self.assert_no_chat_or_send()

    async def test_empty_unavailable_invalid_and_unknown_vsegpt_stay_on_actionable_models_surface(
        self,
    ):
        for validity in (
            KeyValidityState.INVALID,
            KeyValidityState.UNKNOWN,
            KeyValidityState.UNVERIFIED,
        ):
            for available in (True, False):
                with self.subTest(validity=validity, available=available):
                    self.profiles.validity[ProviderId.VSEGPT] = validity
                    with patch.object(
                        self.controller._catalog_service,
                        "get_catalog",
                        return_value=ModelCatalog((), (), available=available),
                    ):
                        await self.choose_new(ProviderId.VSEGPT)
                    self.assertIsInstance(
                        self.controller._selection_view, ModelSelectionView
                    )
                    self.assertEqual(self.controller._screen.value, "model_selection")
                    await self.controller.request_key_revalidation()
                    await self.controller.cancel_new_chat()
        await self.assert_no_chat_or_send()

    async def test_openrouter_keeps_both_mode_choices_and_check_uses_selected_saved_slot(
        self,
    ):
        self.profiles.validity[ProviderId.OPENROUTER] = KeyValidityState.UNKNOWN
        await self.choose_new(ProviderId.OPENROUTER)
        view = self.controller._selection_view
        assert isinstance(view, ModeSelectionView)
        self.assertIsNotNone(view.free_button)
        self.assertTrue(view.paid_button.disabled)
        assert view.check_key_button is not None
        await self.fixture.click(view.check_key_button)
        self.assertIs(self.controller._selection_view, view)
        self.assertFalse(view.paid_button.disabled)
        self.assertEqual(
            self.profiles.validation_calls,
            [(ProviderId.OPENROUTER, self.profiles.keys[ProviderId.OPENROUTER])],
        )
        self.assertEqual(self.controller._screen.value, "mode_selection")
        await self.assert_no_chat_or_send()

    async def test_vsegpt_check_in_existing_or_chat_uses_vsegpt_and_updates_current_model_view(
        self,
    ):
        await self.choose_new(ProviderId.VSEGPT)
        view = self.controller._selection_view
        assert isinstance(view, ModelSelectionView)
        self.profiles.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT, provider_id=ProviderId.VSEGPT
        )
        assert view.check_key_button is not None
        await self.fixture.click(view.check_key_button)
        self.assertIs(self.controller._selection_view, view)
        self.assertIs(self.controller.key_validity, KeyValidityState.VALID)
        self.assertEqual(
            self.profiles.validation_calls,
            [(ProviderId.VSEGPT, self.profiles.keys[ProviderId.VSEGPT])],
        )
        self.assertEqual(self.controller._screen.value, "model_selection")
        await self.assert_no_chat_or_send()

    async def test_check_busy_precedes_network_duplicate_click_and_cancel_are_safe(
        self,
    ):
        await self.choose_new(ProviderId.OPENROUTER)
        self.profiles.hold = True
        task = asyncio.create_task(self.controller.request_key_revalidation())
        await self.profiles.entered.wait()
        self.assertIsNotNone(self.controller._selection_key_task)
        view = self.controller._selection_view
        assert isinstance(view, ModeSelectionView)
        self.assertTrue(view.free_button.disabled)
        await self.controller.request_key_revalidation()
        await self.controller.select_chat_mode(ChatMode.FREE)
        self.assertEqual(self.controller._screen.value, "mode_selection")
        self.assertEqual(len(self.profiles.validation_calls), 1)
        await self.controller.handle_application_back()
        await task
        self.assertEqual(self.controller._screen.value, "workspace")
        self.assertIsNone(self.controller._selection_key_task)
        await self.assert_no_chat_or_send()

    async def test_each_safe_error_keeps_retry_and_does_not_select_a_mode_or_leak_raw_error(
        self,
    ):
        await self.choose_new(ProviderId.OPENROUTER)
        notices = set()
        for status in (
            KeyValidationStatus.INVALID,
            KeyValidationStatus.RESTRICTED,
            KeyValidationStatus.TIMEOUT,
            KeyValidationStatus.NETWORK_ERROR,
            KeyValidationStatus.TLS_ERROR,
            KeyValidationStatus.RATE_LIMITED,
            KeyValidationStatus.UNVERIFIED,
        ):
            self.profiles.result = KeyValidationResult(status)
            await self.controller.request_key_revalidation()
            notices.add(self.controller._selection_key_notice)
            self.assertIsNone(self.controller._selection_key_task)
            self.assertEqual(self.controller._screen.value, "mode_selection")
            self.assertIsNone(self.controller._pending_mode)
        self.assertEqual(len(notices), 7)
        await self.assert_no_chat_or_send()

    async def test_late_old_check_does_not_clear_new_busy_or_reopen_cancelled_screen(
        self,
    ):
        await self.choose_new(ProviderId.OPENROUTER)
        self.profiles.hold = self.profiles.ignore_cancellation = True
        old = asyncio.create_task(self.controller.request_key_revalidation())
        await self.profiles.entered.wait()
        await self.controller.cancel_new_chat()
        new_profiles = _CheckingProfiles()
        new_profiles.keys = dict(self.profiles.keys)
        new_profiles.hold = True
        self.controller._provider_profiles = cast(ProfilesContract, new_profiles)
        await self.choose_new(ProviderId.VSEGPT)
        new = asyncio.create_task(self.controller.request_key_revalidation())
        await new_profiles.entered.wait()
        self.profiles.release.set()
        await old
        self.assertIs(self.controller._selection_key_task, new)
        self.assertEqual(self.controller._screen.value, "model_selection")
        new_profiles.release.set()
        await new
        self.assertIsNone(self.controller._selection_key_task)
        await self.assert_no_chat_or_send()

    async def test_replaced_key_and_lock_revoke_late_check_context(self):
        for action in ("replace", "lock"):
            with self.subTest(action=action):
                await self.choose_new(ProviderId.VSEGPT)
                self.profiles.hold = self.profiles.ignore_cancellation = True
                self.profiles.entered.clear()
                self.profiles.release.clear()
                task = asyncio.create_task(self.controller.request_key_revalidation())
                await self.profiles.entered.wait()
                if action == "replace":
                    self.profiles.keys[ProviderId.VSEGPT] = (
                        "sk-or-vis-new-only-local-key"
                    )
                    self.profiles.revisions[ProviderId.VSEGPT] += 1
                    await self.controller.refresh_provider_state()
                else:
                    self.controller.deactivate()
                self.profiles.release.set()
                await task
                self.assertIsNone(self.controller._selection_key_task)
                self.assertIsNone(self.controller._chat_creation)
                self.assertIsNone(self.controller._catalog)
                if action == "replace":
                    self.assertEqual(self.controller._screen.value, "workspace")

    async def test_stale_check_button_cannot_validate_a_new_provider_context(self):
        await self.choose_new(ProviderId.OPENROUTER)
        old = self.controller._selection_view
        assert isinstance(old, ModeSelectionView)
        assert old.check_key_button is not None
        await self.controller.cancel_new_chat()
        await self.choose_new(ProviderId.VSEGPT)
        await self.fixture.click(old.check_key_button)
        self.assertEqual(self.profiles.validation_calls, [])
        self.assertEqual(self.controller._screen.value, "model_selection")
        await self.assert_no_chat_or_send()

    async def test_check_timeout_and_unexpected_error_release_busy_and_allow_a_retry(
        self,
    ):
        await self.choose_new(ProviderId.OPENROUTER)
        timeout = asyncio.timeout
        self.profiles.hold = True
        with patch(
            "chat_controller.asyncio.timeout",
            side_effect=lambda _seconds: timeout(0.005),
        ):
            await self.controller.request_key_revalidation()
        self.assertIsNone(self.controller._selection_key_task)
        timeout_notice = self.controller._selection_key_notice
        self.assertIsNotNone(timeout_notice)
        with patch.object(
            self.profiles,
            "refresh",
            side_effect=RuntimeError("synthetic-raw-response-never-display"),
        ):
            await self.controller.request_key_revalidation()
        self.assertIsNone(self.controller._selection_key_task)
        self.assertNotIn(
            "synthetic-raw-response", self.controller._selection_key_notice or ""
        )
        self.assertNotEqual(self.controller._selection_key_notice, timeout_notice)
        self.profiles.hold = False
        await self.controller.request_key_revalidation()
        self.assertIs(self.controller.key_validity, KeyValidityState.VALID)
        self.assertIsNone(self.controller._pending_mode)
        await self.assert_no_chat_or_send()

    async def test_profile_deletion_waits_for_cancelled_choice_validation_cleanup(self):
        await self.choose_new(ProviderId.OPENROUTER)
        entered, cleanup_started, cleanup_allowed = (asyncio.Event() for _ in range(3))

        async def refresh(_provider, *, validate_key=False):
            self.assertTrue(validate_key)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await cleanup_allowed.wait()

        with patch.object(self.profiles, "refresh", side_effect=refresh):
            check = asyncio.create_task(self.controller.request_key_revalidation())
            await entered.wait()
            self.controller.begin_profile_deletion()
            waiting = asyncio.create_task(self.controller.wait_profile_deletion())
            await cleanup_started.wait()
            await asyncio.sleep(0)
            self.assertFalse(waiting.done())
            self.assertIsNone(self.controller._selection_view)
            cleanup_allowed.set()
            await waiting
            await check
            self.assertTrue(check.done())
        self.assertIsNone(self.controller._chat_creation)
        self.assertIsNone(self.controller._catalog)
        await self.assert_no_chat_or_send()

    async def test_real_profiles_check_the_saved_selected_slot_without_candidate_reentry(
        self,
    ):
        storage = MemoryStorage()
        credentials = FletSecureCredentials(storage)
        for provider, key in self.profiles.keys.items():
            await credentials.save_provider_key(
                provider, key, authorization_confirmed=True
            )

        class API:
            calls = []

            async def validate_key(self, api_key: str):
                self.calls.append(api_key)
                return KeyValidationResult(
                    KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT,
                    provider_id=ProviderId.VSEGPT,
                )

            async def get_credits(self, api_key: str, /):
                from api.openrouter import CreditsResult, CreditsStatus
                from providers.models import Currency

                return CreditsResult(
                    CreditsStatus.BALANCE_DISABLED,
                    provider_id=ProviderId.VSEGPT,
                    currency=Currency.RUB,
                )

        await credentials.set_new_chat_policy(NewChatPolicy.MANUAL)
        api = API()
        profiles = ProviderProfiles(credentials, api)
        self.addCleanup(profiles.deactivate)
        await profiles.activate(
            self.profiles.keys[ProviderId.OPENROUTER],
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(None),
        )
        self.controller._provider_profiles = cast(ProfilesContract, profiles)
        await self.choose_new(ProviderId.VSEGPT)
        await self.controller.request_key_revalidation()
        self.assertEqual(api.calls, [self.profiles.keys[ProviderId.VSEGPT]])
        self.assertIs(self.controller.key_validity, KeyValidityState.VALID)
        self.assertEqual(self.controller._screen.value, "model_selection")
        await self.assert_no_chat_or_send()
