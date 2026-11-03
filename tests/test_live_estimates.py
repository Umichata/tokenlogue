"""Read-only local estimates agree with the real send planner and stay cheap."""

from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import (  # noqa: E402
    BudgetState,
    ChatBudget,
    ChatBudgetService,
    estimate_max_cost,
)
from chat.context import (  # noqa: E402
    REQUEST_OVERHEAD_TOKENS,
    build_conversation_context,
    estimate_message_tokens,
    prepare_history,
    select_conversation_context,
)
from chat.errors import ChatErrorType  # noqa: E402
from chat.estimates import (  # noqa: E402
    EstimateState,
    PreparedEstimateSnapshot,
    calculate_request_plan,
    estimate_draft,
)
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    Chat,
    ChatMode,
    Message,
    MessageRole,
    MessageStatus,
    PriceComponents,
)
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests.test_message_sending import (  # noqa: E402
    FakeCatalogClient,
    FakeCompletionClient,
    FakeKeyValidator,
    _success,
)

NOW = datetime(2026, 11, 1, tzinfo=UTC)


class LiveEstimateTests(unittest.TestCase):
    def test_empty_or_whitespace_draft_is_not_a_request(self) -> None:
        for text in ("", "  \t\n", "\u2003"):
            with self.subTest(length=len(text)):
                result = estimate_draft(_snapshot(), text)
                self.assertEqual(result.state, EstimateState.EMPTY)
                self.assertIsNone(result.prompt_tokens)
                self.assertIsNone(result.max_completion_tokens)
                self.assertIsNone(result.cost_upper_usd)

    def test_typing_deleting_replacing_pasting_unicode_and_undo_use_current_text(
        self,
    ) -> None:
        snapshot = _snapshot()
        # Each item represents a new TextField value, without debounce or save.
        values = (
            "a",
            "ab",
            "a",
            "selection replacement",
            "pasted\nsecond line🙂",
            "Привет é 👩🏽‍💻",
            "pasted\nsecond line🙂",
            "",
        )
        for text in values:
            result = estimate_draft(snapshot, text)
            if text:
                self.assertEqual(result.state, EstimateState.READY)
                self.assertEqual(
                    result.prompt_tokens,
                    REQUEST_OVERHEAD_TOKENS + estimate_message_tokens(text.strip()),
                )
                self.assertEqual(result.cost_upper_usd, Decimal("0"))
            else:
                self.assertEqual(result.state, EstimateState.EMPTY)

    def test_normalization_and_only_complete_authorized_history_match_send(
        self,
    ) -> None:
        history = [
            _message("one", MessageRole.USER, "q"),
            _message("one", MessageRole.ASSISTANT, "a🙂"),
            _message("two", MessageRole.USER, "failed", MessageStatus.FAILED),
            _message("three", MessageRole.USER, "incomplete"),
        ]
        snapshot = replace(_snapshot(), history=prepare_history(history))
        text = " \n next\nline🙂  "
        result = estimate_draft(snapshot, text)
        context = build_conversation_context(
            history,
            text.strip(),
            context_length=8192,
            completion_reserve=16,
            require_full_history=True,
        )
        self.assertEqual(result.prompt_tokens, context.estimated_prompt_tokens)
        self.assertEqual(
            [item.content for item in context.messages], ["q", "a🙂", text.strip()]
        )
        self.assertTrue(result.free_router)

    def test_prepared_history_is_immutable_and_not_recounted_per_character(
        self,
    ) -> None:
        source = [
            _message("one", MessageRole.USER, "cached question"),
            _message("one", MessageRole.ASSISTANT, "cached answer"),
        ]
        prepared = prepare_history(source)
        snapshot = replace(_snapshot(), history=prepared)
        before = prepared.estimated_tokens
        source.clear()
        with patch(
            "chat.context.estimate_message_tokens", wraps=estimate_message_tokens
        ) as counted:
            for value in ("a", "ab", "a", "xyz"):
                estimate_draft(snapshot, value)
        # Only the current text is counted in the shared planner. History is not.
        self.assertEqual(counted.call_count, 4)
        self.assertEqual(prepared.estimated_tokens, before)
        with self.assertRaises(FrozenInstanceError):
            prepared.pairs = ()  # type: ignore[misc]

    def test_cached_truncation_selects_same_recent_pairs_at_each_boundary(self) -> None:
        history = [
            item
            for index in range(5)
            for item in (
                _message(str(index), MessageRole.USER, "q" * (index + 1)),
                _message(str(index), MessageRole.ASSISTANT, "a" * (index + 2)),
            )
        ]
        prepared = prepare_history(history)
        for limit in (60, 80, 100, 140, 200):
            with self.subTest(limit=limit):
                selected = select_conversation_context(
                    prepared, "x", context_length=limit, completion_reserve=16
                ).materialize()
                # Independent original suffix-loop policy, including exact fits.
                estimated = REQUEST_OVERHEAD_TOKENS + estimate_message_tokens("x")
                pairs = []
                for user, assistant in reversed(prepared.pairs):
                    cost = estimate_message_tokens(
                        user.content
                    ) + estimate_message_tokens(assistant.content)
                    if estimated + cost > limit - 16:
                        break
                    pairs.insert(0, (user, assistant))
                    estimated += cost
                self.assertEqual(selected.estimated_prompt_tokens, estimated)
                self.assertEqual(
                    [item.content for item in selected.messages],
                    [item.content for pair in pairs for item in pair] + ["x"],
                )

    def test_full_history_is_not_silently_truncated_to_show_affordable_estimate(
        self,
    ) -> None:
        snapshot = replace(
            _snapshot(),
            history=prepare_history(
                [
                    _message("one", MessageRole.USER, "q" * 8100),
                    _message("one", MessageRole.ASSISTANT, "a" * 100),
                ]
            ),
        )
        result = estimate_draft(snapshot, "x")
        self.assertEqual(result.state, EstimateState.OVER_LIMIT)
        self.assertEqual(result.error, ChatErrorType.CONTEXT_LENGTH_EXCEEDED)
        self.assertIsNone(result.cost_upper_usd)

    def test_effective_cap_uses_provider_budget_reservations_and_context(self) -> None:
        snapshot = _snapshot(paid=True)
        assert snapshot.budget is not None and snapshot.model is not None
        snapshot = replace(
            snapshot,
            model=replace(snapshot.model, provider_max_completion_tokens=101),
            budget=replace(
                snapshot.budget,
                token_limit=400,
                total_tokens_used=100,
                reserved_tokens=80,
            ),
        )
        result = estimate_draft(snapshot, "x" * 90)
        self.assertEqual(result.prompt_tokens, 130)
        self.assertEqual(result.max_completion_tokens, 90)
        assert snapshot.model is not None
        changed = estimate_draft(
            replace(snapshot, model=replace(snapshot.model, context_length=150)),
            "x" * 90,
        )
        self.assertEqual(changed.max_completion_tokens, 20)

    def test_price_components_and_provider_overrides_are_decimal_not_discounts(
        self,
    ) -> None:
        snapshot = _snapshot(paid=True)
        assert snapshot.model is not None
        override = PriceComponents(
            prompt=Decimal("0.000006"),
            completion=Decimal("0.000007"),
            request=Decimal("0.001"),
            internal_reasoning=Decimal("0.000003"),
            input_cache_read=Decimal("0.000002"),
            input_cache_write=Decimal("0.000004"),
        )
        model = replace(snapshot.model, pricing_overrides=(override,))
        snapshot = replace(snapshot, chat=_chat(model), model=model)
        result = estimate_draft(snapshot, "tiny")
        assert (
            result.prompt_tokens is not None
            and result.max_completion_tokens is not None
        )
        expected = estimate_max_cost(
            model.all_pricing, result.prompt_tokens, result.max_completion_tokens
        )
        self.assertEqual(result.cost_upper_usd, expected)
        self.assertIsInstance(result.cost_upper_usd, Decimal)
        self.assertGreater(
            expected, override.request + override.prompt * result.prompt_tokens
        )

    def test_cost_and_key_limit_reduce_the_same_completion_cap(self) -> None:
        snapshot = _snapshot(paid=True)
        assert snapshot.budget is not None and snapshot.model is not None
        price = PriceComponents(completion=Decimal("0.001"))
        model = replace(
            snapshot.model,
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=price.completion,
            request_price=Decimal("0"),
        )
        snapshot = replace(
            snapshot,
            chat=_chat(model),
            model=model,
            budget=replace(snapshot.budget, cost_limit_usd=Decimal("0.050")),
        )
        self.assertEqual(estimate_draft(snapshot, "x").max_completion_tokens, 50)
        snapshot = replace(
            snapshot, key_limit=KeyLimitInfo.from_validated_remaining(Decimal("0.025"))
        )
        result = estimate_draft(snapshot, "x")
        self.assertEqual(result.max_completion_tokens, 25)
        self.assertEqual(result.cost_upper_usd, Decimal("0.025"))
        self.assertEqual(
            estimate_draft(
                replace(
                    snapshot,
                    key_limit=KeyLimitInfo.from_validated_remaining(Decimal("0.015")),
                ),
                "x",
            ).error,
            ChatErrorType.KEY_LIMIT_EXCEEDED,
        )

    def test_unknown_missing_or_invalid_paid_price_never_becomes_zero(self) -> None:
        snapshot = _snapshot(paid=True)
        assert snapshot.model is not None
        candidates = (
            None,
            replace(snapshot.model, pricing_is_complete=False),
            replace(snapshot.model, request_price=Decimal("NaN")),
            replace(snapshot.model, id="different/model"),
        )
        for model in candidates:
            with self.subTest(model_present=model is not None):
                result = estimate_draft(replace(snapshot, model=model), "x")
                self.assertEqual(result.state, EstimateState.UNAVAILABLE)
                self.assertIsNone(result.cost_upper_usd)
                self.assertIsNone(result.max_completion_tokens)
                self.assertIsNotNone(result.prompt_tokens)

    def test_free_zero_requires_a_confirmed_free_model(self) -> None:
        snapshot = _snapshot()
        self.assertEqual(estimate_draft(snapshot, "x").cost_upper_usd, Decimal("0"))
        model = replace(
            FREE_ROUTER_MODEL, id="vendor/free:free", pricing_is_complete=False
        )
        snapshot = replace(snapshot, chat=_chat(model, ChatMode.FREE), model=model)
        result = estimate_draft(snapshot, "x")
        self.assertEqual(result.state, EstimateState.UNAVAILABLE)
        self.assertIsNone(result.cost_upper_usd)

    def test_manual_policy_keeps_confirmed_schedule_until_a_price_increase(
        self,
    ) -> None:
        snapshot = _snapshot(paid=True)
        assert snapshot.model is not None
        lower = replace(
            snapshot.model,
            prompt_price_per_token=Decimal("0"),
            completion_price_per_token=Decimal("0"),
            request_price=Decimal("0"),
        )
        initial = estimate_draft(snapshot, "x")
        self.assertEqual(
            estimate_draft(replace(snapshot, model=lower), "x").cost_upper_usd,
            initial.cost_upper_usd,
        )
        automatic = replace(
            snapshot,
            chat=replace(snapshot.chat, paid_without_confirmation=True),
            model=lower,
        )
        self.assertEqual(estimate_draft(automatic, "x").cost_upper_usd, Decimal("0"))
        increased = replace(snapshot.model, request_price=Decimal("0.01"))
        higher = estimate_draft(replace(snapshot, model=increased), "x")
        assert higher.cost_upper_usd is not None and initial.cost_upper_usd is not None
        self.assertGreater(
            higher.cost_upper_usd,
            initial.cost_upper_usd,
        )

    def test_tiny_positive_money_remains_exactly_positive(self) -> None:
        model = CatalogModel(
            "vendor/tiny",
            "Tiny",
            Decimal("1e-20"),
            Decimal("1e-20"),
            context_length=8192,
        )
        snapshot = replace(_snapshot(paid=True), chat=_chat(model), model=model)
        result = estimate_draft(snapshot, "x")
        assert result.cost_upper_usd is not None
        self.assertGreater(result.cost_upper_usd, Decimal("0"))
        self.assertLess(result.cost_upper_usd, Decimal("0.0001"))

    def test_unknown_accounting_unconfigured_budget_and_invalid_text_are_safe(
        self,
    ) -> None:
        snapshot = _snapshot()
        assert snapshot.budget is not None
        for budget, error in (
            (None, ChatErrorType.LIMITS_NOT_CONFIGURED),
            (
                replace(snapshot.budget, state=BudgetState.ACCOUNTING_UNKNOWN),
                ChatErrorType.ACCOUNTING_UNKNOWN,
            ),
            (
                replace(snapshot.budget, limits_configured=False),
                ChatErrorType.LIMITS_NOT_CONFIGURED,
            ),
        ):
            result = estimate_draft(replace(snapshot, budget=budget), "x")
            self.assertEqual(result.state, EstimateState.UNAVAILABLE)
            self.assertEqual(result.error, error)
            self.assertIsNone(result.cost_upper_usd)
        invalid = estimate_draft(snapshot, "\ud800")
        self.assertEqual(invalid.state, EstimateState.UNAVAILABLE)
        self.assertEqual(invalid.error, ChatErrorType.INVALID_REQUEST)

    def test_local_calculations_have_no_network_repository_or_send_side_effects(
        self,
    ) -> None:
        snapshot = _snapshot(paid=True)
        with (
            patch("httpx.AsyncClient.request", side_effect=AssertionError("HTTP")),
            patch("sqlite3.connect", side_effect=AssertionError("database")),
            patch.object(
                MessageSendingService,
                "preview_message",
                side_effect=AssertionError("preview"),
            ),
            patch.object(
                MessageSendingService,
                "send_message",
                side_effect=AssertionError("send"),
            ),
            patch.object(
                ChatService, "paid_consent", side_effect=AssertionError("consent")
            ),
            patch.object(
                SqliteMessageRepository,
                "reserve_turn",
                side_effect=AssertionError("reserve"),
            ),
            patch.object(
                SqliteMessageRepository,
                "update_price_snapshot",
                side_effect=AssertionError("price write"),
            ),
        ):
            results = [
                estimate_draft(snapshot, "synthetic" + "x" * index)
                for index in range(200)
            ]
        self.assertTrue(all(item.state is EstimateState.READY for item in results))
        self.assertFalse(snapshot.chat.paid_without_confirmation)
        self.assertEqual(snapshot.budget, _budget())


class EstimatePreflightParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_and_historical_requests_match_real_free_and_paid_preflight(
        self,
    ) -> None:
        for mode in (ChatMode.FREE, ChatMode.PAID):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as directory:
                    database = AuthDatabase(directory)
                    chats = SqliteChatRepository(database.path)
                    messages = SqliteMessageRepository(database.path)
                    model = FREE_ROUTER_MODEL if mode is ChatMode.FREE else _model()
                    chat = _chat(model, mode)
                    chats.create_chat(chat)
                    budgets = ChatBudgetService(messages)
                    await budgets.configure_chat_limits(
                        chat.id,
                        token_limit=2000,
                        max_completion_tokens=256,
                        cost_limit_usd=None if mode is ChatMode.FREE else Decimal("1"),
                        cost_increase_confirmed=mode is ChatMode.PAID,
                        updated_at=NOW,
                    )
                    catalog = FakeCatalogClient((model,))
                    validator = FakeKeyValidator()
                    client = FakeCompletionClient(
                        [_success(cost="0" if mode is ChatMode.FREE else "0.0001")]
                    )
                    service = MessageSendingService(
                        ChatService(chats),
                        messages,
                        client,
                        catalog,
                        validator,
                        now=lambda: NOW,
                    )
                    for has_history in (False, True):
                        if has_history:
                            sent = await service.send_message(
                                chat.id,
                                "public synthetic question🙂",
                                api_key="synthetic-estimate-only",
                                key_validity=KeyValidityState.VALID,
                                key_limit=KeyLimitInfo.from_validated_remaining(None),
                                paid_confirmed=True,
                            )
                            self.assertTrue(sent.successful)
                        budget = messages.get_chat_budget(chat.id)
                        assert budget is not None
                        snapshot = PreparedEstimateSnapshot(
                            chat,
                            budget,
                            model,
                            prepare_history(chats.list_messages(chat.id)),
                        )
                        local = estimate_draft(snapshot, " \n current text é🙂  ")
                        count = (
                            len(messages.list_turns(chat.id)),
                            catalog.calls,
                            validator.calls,
                            len(client.calls),
                        )
                        # Repeated typing is read-only even with real temporary ledgers.
                        for _ in range(20):
                            self.assertEqual(
                                estimate_draft(snapshot, " \n current text é🙂  "),
                                local,
                            )
                        self.assertEqual(
                            (
                                len(messages.list_turns(chat.id)),
                                catalog.calls,
                                validator.calls,
                                len(client.calls),
                            ),
                            count,
                        )
                        preview = await service.preview_message(
                            chat.id,
                            " \n current text é🙂  ",
                            api_key="synthetic-estimate-only",
                            key_validity=KeyValidityState.VALID,
                            key_limit=KeyLimitInfo.from_validated_remaining(None),
                        )
                        self.assertTrue(preview.allowed)
                        self.assertEqual(local.state, EstimateState.READY)
                        self.assertEqual(
                            local.prompt_tokens, preview.estimated_prompt_tokens
                        )
                        self.assertEqual(
                            local.max_completion_tokens, preview.max_completion_tokens
                        )
                        self.assertEqual(
                            local.cost_upper_usd, preview.reserved_cost_usd
                        )
                        plan = calculate_request_plan(
                            chat=chat,
                            budget=budget,
                            model=model,
                            history=snapshot.history,
                            text=" \n current text é🙂  ",
                            pricing=model.all_pricing,
                            key_limit=KeyLimitInfo.from_validated_remaining(None),
                        )
                        self.assertEqual(plan.reserved_tokens, preview.reserved_tokens)
                        self.assertEqual(
                            plan.remaining_tokens_after_reservation,
                            preview.remaining_tokens_after_reservation,
                        )
                        self.assertEqual(
                            plan.remaining_cost_after_reservation,
                            preview.remaining_cost_after_reservation,
                        )
                        self.assertEqual(
                            plan.context.materialize().messages[-1].content,
                            "current text é🙂",
                        )


def _model() -> CatalogModel:
    return CatalogModel(
        "vendor/paid",
        "Paid",
        Decimal("0.000001"),
        Decimal("0.000002"),
        request_price=Decimal("0.00001"),
        context_length=8192,
        provider_max_completion_tokens=128,
    )


def _chat(model: CatalogModel, mode: ChatMode = ChatMode.PAID) -> Chat:
    return Chat(
        "chat",
        "Public synthetic",
        mode,
        model.id,
        model.name,
        model.prompt_price_per_token,
        model.completion_price_per_token,
        NOW,
        NOW,
        request_price=model.request_price,
        internal_reasoning_price_per_token=model.internal_reasoning_price_per_token,
        input_cache_read_price_per_token=model.input_cache_read_price_per_token,
        input_cache_write_price_per_token=model.input_cache_write_price_per_token,
        pricing_overrides=model.pricing_overrides,
        pricing_snapshot_complete=model.pricing_is_complete,
    )


def _budget() -> ChatBudget:
    return ChatBudget(
        "chat",
        True,
        8192,
        1024,
        0,
        0,
        0,
        0,
        Decimal("1"),
        Decimal("0"),
        Decimal("0"),
        BudgetState.READY,
        NOW,
    )


def _snapshot(*, paid: bool = False) -> PreparedEstimateSnapshot:
    model = _model() if paid else FREE_ROUTER_MODEL
    return PreparedEstimateSnapshot(
        _chat(model, ChatMode.PAID if paid else ChatMode.FREE),
        _budget(),
        model,
        prepare_history([]),
    )


def _message(
    turn_id: str,
    role: MessageRole,
    content: str,
    status: MessageStatus = MessageStatus.SENT,
) -> Message:
    return Message(
        role.value + turn_id,
        "chat",
        turn_id,
        role,
        content,
        status,
        "vendor/paid",
        None,
        None,
        None,
        None,
        NOW,
    )


if __name__ == "__main__":
    unittest.main()
