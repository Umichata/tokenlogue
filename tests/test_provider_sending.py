"""Unknown-price VSEGPT dispatches require fresh exact request consent."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionResult  # noqa: E402
from api.models import ModelCatalogService  # noqa: E402
from api.openrouter import KeyValidationResult  # noqa: E402
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.account_balance import AccountBalanceSnapshot  # noqa: E402
from chat.accounting import (  # noqa: E402
    AccountingStatus,
    BudgetState,
    ChatBudgetService,
)
from chat.budget_consent import BudgetConsent, BudgetConsentRevoked  # noqa: E402
from chat.drafts import ChatDraft, ChatDraftService  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import ChatMode  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from chat_controller import ChatSessionController  # noqa: E402
from providers.models import Currency, PriceUnit, ProviderId  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests.test_chat_ui_integration import FakePage  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    BlockingCompletionClient,
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
    _chat,
    _paid_model,
)

KEY = "sk-or-vv-offline-sending-fixture"


class FakeProviderProfiles:
    def __init__(self):
        self.default_provider = ProviderId.OPENROUTER
        self.active = True
        self.keys = {
            ProviderId.VSEGPT: KEY,
            ProviderId.OPENROUTER: "sk-or-v1-offline-controller-fixture",
        }
        self.validity = {
            ProviderId.VSEGPT: KeyValidityState.UNVERIFIED,
            ProviderId.OPENROUTER: KeyValidityState.VALID,
        }
        self.refreshes: list[tuple[ProviderId, bool]] = []
        self.revisions = {provider: 1 for provider in ProviderId}

    def key_for(self, provider: ProviderId) -> str | None:
        return self.keys.get(provider)

    def key_validity_for(self, provider: ProviderId) -> KeyValidityState:
        return self.validity[provider]

    def key_limit_for(self, provider: ProviderId) -> KeyLimitInfo:
        return (
            KeyLimitInfo.unknown()
            if provider is ProviderId.VSEGPT
            else KeyLimitInfo.from_validated_remaining(None)
        )

    def balance_for(self, provider: ProviderId) -> AccountBalanceSnapshot:
        return AccountBalanceSnapshot(
            provider_id=provider,
            currency=Currency.RUB if provider is ProviderId.VSEGPT else Currency.USD,
        )

    def credential_revision(self, provider: ProviderId) -> object:
        return self.revisions[provider]

    def apply_validation(
        self, provider: ProviderId, key: str, result: KeyValidationResult
    ) -> None:
        if key == self.key_for(provider) and result.status.value == "invalid":
            self.validity[provider] = KeyValidityState.INVALID

    async def refresh(
        self,
        provider: ProviderId,
        *,
        after_response: bool = False,
        validate_key: bool = False,
    ) -> None:
        self.refreshes.append((provider, after_response))


def _unknown_reply(*, partial_usage: bool = False) -> ChatCompletionResult:
    return ChatCompletionResult(
        content="fixture answer",
        generation_id="fixture-generation",
        requested_model_id="vendor/paid-model",
        actual_model_id="vendor/paid-model",
        finish_reason="stop",
        prompt_tokens=20,
        completion_tokens=None if partial_usage else 10,
        total_tokens=None if partial_usage else 30,
        cost_usd=None,
        error_type=None,
        accounting_unknown=True,
        provider_id=ProviderId.VSEGPT,
        currency=Currency.RUB,
    )


class ProviderSendingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = AuthDatabase(temporary.name)
        self.chats = SqliteChatRepository(self.database.path)
        self.messages = SqliteMessageRepository(self.database.path)
        self.chat_service = ChatService(self.chats)
        self.model = replace(
            _paid_model(),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
            pricing_is_complete=False,
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
        )
        chat = replace(
            _chat("rub", ChatMode.PAID, self.model),
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            pricing_unit=PriceUnit.UNKNOWN,
            pricing_snapshot_complete=False,
        )
        self.chats.create_chat_with_limits(
            chat, token_limit=8192, max_completion_tokens=64, cost_limit=Decimal("100")
        )
        self.client = FakeCompletionClient([_unknown_reply(), _unknown_reply()])
        self.catalog = FakeCatalogClient((self.model,))
        self.validator = FakeKeyValidator()
        self.sender = self.make_sender(self.client)

    def make_sender(self, client):
        return MessageSendingService(
            self.chat_service, self.messages, client, self.catalog, self.validator
        )

    async def preview(self, text="hello", *, key=KEY):
        preview = await self.sender.preview_message(
            "rub",
            text,
            api_key=key,
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
        )
        self.assertTrue(preview.allowed, preview.error_type)
        return preview

    async def send(self, text="hello", *, consent=None, key=KEY, **kwargs):
        return await self.sender.send_message(
            "rub",
            text,
            api_key=key,
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
            paid_confirmed=True,
            unknown_price_consent=consent,
            **kwargs,
        )

    async def test_preview_and_normal_paid_confirmation_never_imply_known_or_zero_cost(
        self,
    ):
        preview = await self.preview()
        self.assertTrue(preview.unknown_pricing)
        self.assertEqual(preview.currency, Currency.RUB)
        self.assertIsNone(preview.reserved_cost)
        self.assertIsNone(preview.reserved_cost_usd)
        assert preview.budget_warning is not None
        self.assertIsNone(preview.budget_warning.estimated_cost)
        self.assertEqual(preview.budget_warning.limit, Decimal("100"))
        self.assertIsNone(preview.budget_warning.limit_usd)
        self.assertEqual(self.validator.calls, 0)
        blocked = await self.send()
        self.assertFalse(blocked.successful)
        self.assertEqual(blocked.error_type, ChatErrorType.COST_LIMIT_EXCEEDED)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.messages.list_turns("rub"), [])
        with self.assertRaises(BudgetConsentRevoked):
            self.sender.confirm_budget_warning(preview)
        assert preview.budget_consent_basis is not None
        ordinary = await self.send(
            budget_consent=BudgetConsent(preview.budget_consent_basis)
        )
        self.assertFalse(ordinary.successful)
        self.assertEqual(self.client.calls, [])

    async def test_reply_and_tokens_persist_unknown_money_and_fresh_ack_allows_next_request(
        self,
    ):
        preview = await self.preview()
        first = await self.send(consent=self.sender.confirm_unknown_price(preview))
        self.assertTrue(first.successful, first.error_type)
        self.assertEqual(first.key_validity_update, KeyValidityState.VALID)
        self.assertEqual(first.content, "fixture answer")
        self.assertTrue(first.accounting_unknown)
        budget = self.messages.get_chat_budget("rub")
        assert budget is not None
        self.assertEqual(budget.state, BudgetState.ACCOUNTING_UNKNOWN)
        self.assertEqual(budget.total_tokens_used, 30)
        self.assertEqual(budget.cost_reserved, Decimal("100"))
        self.assertEqual(budget.cost_reserved_usd, Decimal("0"))
        self.assertIsNone(budget.cost_limit_usd)
        self.assertFalse((await self.send("second")).successful)
        second_preview = await self.preview("second")
        second = await self.send(
            "second", consent=self.sender.confirm_unknown_price(second_preview)
        )
        self.assertTrue(second.successful, second.error_type)
        self.assertEqual(len(self.client.calls), 2)
        budget = self.messages.get_chat_budget("rub")
        assert budget is not None
        self.assertEqual(budget.total_tokens_used, 60)
        self.assertEqual(budget.cost_reserved, Decimal("100"))
        self.assertEqual(len(self.messages.list_turns("rub")), 2)
        for turn in self.messages.list_turns("rub"):
            self.assertEqual(turn.accounting_status, AccountingStatus.UNKNOWN)
            self.assertEqual(turn.currency, Currency.RUB)
            self.assertIsNone(turn.cost)
            self.assertIsNone(turn.cost_usd)

    async def test_ack_is_single_use_and_changes_to_text_or_key_revoke_it(self):
        for changed in ("text", "key"):
            preview = await self.preview()
            consent = self.sender.confirm_unknown_price(preview)
            result = await self.send(
                "changed" if changed == "text" else "hello",
                consent=consent,
                key="sk-or-vv-replacement-fixture" if changed == "key" else KEY,
            )
            self.assertFalse(result.successful)
        self.assertEqual(self.client.calls, [])
        preview = await self.preview()
        consent = self.sender.confirm_unknown_price(preview)
        self.assertTrue((await self.send(consent=consent)).successful)
        self.assertFalse((await self.send(consent=consent)).successful)
        self.assertEqual(len(self.client.calls), 1)

    async def test_same_key_credential_revision_change_revokes_unused_ack(self):
        revision = [1]
        self.sender.set_credential_revision_reader(lambda _: revision[0])
        preview = await self.preview()
        consent = self.sender.confirm_unknown_price(preview)
        revision[0] += 1
        result = await self.send(consent=consent)
        self.assertFalse(result.successful)
        self.assertEqual(self.client.calls, [])

    async def test_replacement_after_reservation_stops_http_and_releases_unsent_hold(
        self,
    ):
        current = [True]
        self.sender.set_credential_current_check(lambda provider, key: current[0])
        preview = await self.preview()
        result = await self.send(
            consent=self.sender.confirm_unknown_price(preview),
            on_reserved=lambda _: current.__setitem__(0, False),
        )
        self.assertFalse(result.successful)
        self.assertEqual(result.error_type, ChatErrorType.INTERRUPTED)
        self.assertEqual(self.client.calls, [])
        budget = self.messages.get_chat_budget("rub")
        assert budget is not None
        self.assertEqual(budget.cost_reserved, Decimal("0"))
        self.assertEqual(budget.total_tokens_used, 0)

    async def test_replacement_after_dispatch_preserves_original_reply_and_attempt(
        self,
    ):
        current = [True]
        client = BlockingCompletionClient(_unknown_reply())
        self.sender = self.make_sender(client)
        self.sender.set_credential_current_check(lambda provider, key: current[0])
        preview = await self.preview()
        task = asyncio.create_task(
            self.send(consent=self.sender.confirm_unknown_price(preview))
        )
        await client.started.wait()
        current[0] = False
        client.release.set()
        result = await task
        self.assertTrue(result.successful)
        budget = self.messages.get_chat_budget("rub")
        assert budget is not None
        self.assertEqual(budget.total_tokens_used, 30)
        self.assertEqual(len(self.messages.list_turns("rub")), 1)

    async def test_same_model_id_from_other_provider_never_matches_current_chat(self):
        self.catalog.models = (
            replace(
                self.model, provider_id=ProviderId.OPENROUTER, currency=Currency.USD
            ),
        )
        preview = await self.sender.preview_message(
            "rub",
            "hello",
            api_key=KEY,
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
        )
        self.assertEqual(preview.error_type, ChatErrorType.MODEL_UNAVAILABLE)
        self.assertEqual(self.client.calls, [])

    async def test_partial_known_tokens_are_saved_even_without_total_or_money(self):
        self.client.results = [_unknown_reply(partial_usage=True)]
        preview = await self.preview()
        result = await self.send(consent=self.sender.confirm_unknown_price(preview))
        self.assertTrue(result.successful)
        turn = self.messages.list_turns("rub")[0]
        self.assertEqual(turn.prompt_tokens, 20)
        self.assertIsNone(turn.completion_tokens)
        self.assertIsNone(turn.total_tokens)
        self.assertIsNone(turn.cost)
        self.assertEqual(turn.usage_source, "api")

    async def test_first_real_auth_failure_keeps_profile_and_revision_safe_draft(self):
        drafts = SqliteDraftRepository(self.database.path)
        drafts.save_draft(ChatDraft("rub", 1, "hello"))
        self.client.results = [
            replace(
                _unknown_reply(),
                content=None,
                generation_id=None,
                actual_model_id=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                usage_source="unknown",
                error_type=ChatErrorType.AUTHENTICATION,
                accounting_unknown=False,
            )
        ]
        preview = await self.sender.preview_message(
            "rub",
            "hello",
            api_key=KEY,
            key_validity=KeyValidityState.UNVERIFIED,
            key_limit=KeyLimitInfo.unknown(),
            draft_revision=1,
        )
        result = await self.send(
            consent=self.sender.confirm_unknown_price(preview),
            draft_revision=1,
        )
        self.assertEqual(result.error_type, ChatErrorType.AUTHENTICATION)
        self.assertEqual(drafts.get_draft("rub"), ChatDraft("rub", 1, "hello"))
        self.assertIsNotNone(self.chats.get_chat("rub"))

    async def controller(self):
        page = FakePage()
        profiles = FakeProviderProfiles()
        presented: list[ft.Control] = []
        opened: list[bool] = []

        async def noop():
            pass

        async def settings():
            opened.append(True)

        controller = ChatSessionController(
            cast(ft.Page, page),
            self.validator,
            self.chat_service,
            ModelCatalogService(self.catalog),
            ChatBudgetService(self.messages),
            self.sender,
            ChatDraftService(SqliteDraftRepository(self.database.path)),
            on_lock=noop,
            on_replace_key=noop,
            on_storage_error=lambda _: None,
            provider_profiles=profiles,
            on_provider_settings=settings,
            present_content=presented.append,
        )
        self.addCleanup(controller.dispose)
        await controller.activate(
            KEY, KeyValidityState.UNVERIFIED, KeyLimitInfo.unknown()
        )
        return controller, profiles, page, presented, opened

    async def test_controller_existing_chat_uses_own_provider_despite_global_default(
        self,
    ):
        controller, profiles, _, _, _ = await self.controller()
        self.assertEqual(profiles.default_provider, ProviderId.OPENROUTER)
        context = controller._session_context()
        assert context is not None
        self.assertEqual(context.provider_id, ProviderId.VSEGPT)
        self.assertEqual(context.api_key, KEY)
        profiles.default_provider = ProviderId.VSEGPT
        await controller.request_new_chat()
        self.assertEqual(controller._creation_provider, ProviderId.VSEGPT)
        await controller.select_chat_mode(ChatMode.PAID)
        await controller.select_chat_model(self.model)
        await controller.submit_new_chat_limits("8192", "64", "50")
        created_id = controller.selected_chat_id
        assert created_id is not None
        created = self.chats.get_chat(created_id)
        assert created is not None
        self.assertEqual(created.provider_id, ProviderId.VSEGPT)
        self.assertEqual(created.currency, Currency.RUB)
        created_budget = self.messages.get_chat_budget(created.id)
        assert created_budget is not None
        self.assertEqual(created_budget.cost_limit, Decimal("50"))
        self.assertIsNone(created_budget.cost_limit_usd)

    async def test_navigation_preserves_bound_draft_and_missing_provider_opens_settings(
        self,
    ):
        controller, profiles, _, presented, opened = await self.controller()
        view = controller._workspace_view
        assert view is not None
        await controller._workspace_controller.update_draft("rub", "unsent fixture")
        view.restore_editor("unsent fixture")
        self.assertTrue(await controller.prepare_navigation())
        self.assertIs(controller._workspace_view, view)
        self.assertEqual(
            SqliteDraftRepository(self.database.path).get_draft("rub").text,
            "unsent fixture",
        )
        count = len(presented)
        await controller.refresh_provider_state()
        self.assertEqual(len(presented), count)
        await controller.resume_home()
        self.assertIs(controller._workspace_view, view)
        self.assertEqual(view.editor_value, "unsent fixture")
        profiles.keys.pop(ProviderId.VSEGPT)
        await controller.submit_message("unsent fixture")
        self.assertEqual(opened, [True])
        self.assertEqual(self.client.calls, [])

    async def test_dispatch_provider_receipt_ignores_late_replacement_and_refreshes_origin(
        self,
    ):
        controller, profiles, _, _, _ = await self.controller()
        context = controller._session_context()
        assert context is not None
        assert context.request_finished is not None
        assert context.apply_key_state is not None
        profiles.keys[ProviderId.VSEGPT] = "sk-or-vv-replacement-controller"
        profiles.revisions[ProviderId.VSEGPT] += 1
        context.apply_key_state(KeyValidityState.INVALID, KeyLimitInfo.unknown())
        self.assertEqual(
            profiles.validity[ProviderId.VSEGPT], KeyValidityState.UNVERIFIED
        )
        controller._selected_provider = ProviderId.OPENROUTER
        context.request_finished()
        await asyncio.gather(*controller._provider_tasks)
        self.assertIn((ProviderId.VSEGPT, True), profiles.refreshes)

    async def test_android_back_consumes_new_chat_form_and_keeps_existing_home(self):
        controller, profiles, _, _, _ = await self.controller()
        profiles.default_provider = ProviderId.VSEGPT
        await controller.request_new_chat()
        self.assertTrue(await controller.handle_application_back())
        self.assertIsNotNone(controller._workspace_view)
        self.assertFalse(await controller.handle_application_back())

    async def test_controller_first_auth_failure_preserves_editor_and_marks_only_origin_key(
        self,
    ):
        self.client.results = [
            replace(
                _unknown_reply(),
                content=None,
                generation_id=None,
                actual_model_id=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                usage_source="unknown",
                error_type=ChatErrorType.AUTHENTICATION,
                accounting_unknown=False,
            )
        ]
        controller, profiles, _, _, _ = await self.controller()
        view = controller._workspace_view
        assert view is not None
        await controller._workspace_controller.update_draft("rub", "hello")
        view.restore_editor("hello")
        await controller.submit_message("hello")
        self.assertEqual(self.client.calls, [])
        await controller.confirm_paid_request()
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(view.editor_value, "hello")
        self.assertEqual(profiles.validity[ProviderId.VSEGPT], KeyValidityState.INVALID)
        self.assertEqual(
            profiles.validity[ProviderId.OPENROUTER], KeyValidityState.VALID
        )

    async def test_page_navigation_during_dispatch_keeps_one_attempt_and_current_page(
        self,
    ):
        self.client = BlockingCompletionClient(_unknown_reply())
        self.sender = self.make_sender(self.client)
        controller, _, _, presented, _ = await self.controller()
        view = controller._workspace_view
        assert view is not None
        await controller._workspace_controller.update_draft("rub", "hello")
        view.restore_editor("hello")
        await controller.submit_message("hello")
        send = asyncio.create_task(controller.confirm_paid_request())
        await self.client.started.wait()
        self.assertTrue(await controller.prepare_navigation())
        count = len(presented)
        self.client.release.set()
        await send
        self.assertEqual(len(presented), count)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(len(self.messages.list_turns("rub")), 1)
        await controller.resume_home()
        self.assertIs(controller._workspace_view, view)
        self.assertEqual(len(self.client.calls), 1)
        state = controller._workspace_state
        assert state is not None
        self.assertEqual(state.budget.total_tokens_used, 30)
