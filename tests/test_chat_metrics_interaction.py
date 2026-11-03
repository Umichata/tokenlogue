"""Controller metrics follow the real temporary SQLite ledger without network."""

from __future__ import annotations

# ruff: noqa: E402
import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState
from chat.errors import ChatErrorType
from chat.metrics import LastRequestState
from chat_interaction_controller import ChatInteractionController, ChatSessionContext
from tests import test_message_sending as sending


class InteractionMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.fixture = sending.MessageSendingTests()
        await self.fixture.asyncSetUp()
        self.addCleanup(self.fixture.doCleanups)
        await self.fixture._create_and_configure_free("free")

    def controller(self, client) -> ChatInteractionController:
        controller = ChatInteractionController(
            self.fixture.chat_service,
            self.fixture.budget_service,
            self.fixture._service(client),
            session_provider=lambda: ChatSessionContext(
                sending.TEST_CREDENTIAL,
                KeyValidityState.VALID,
                KeyLimitInfo.from_validated_remaining(None),
            ),
            on_key_state_changed=lambda _validity, _limit: None,
        )
        controller.activate()
        return controller

    async def test_reservation_pending_and_final_snapshot_are_live(self) -> None:
        client = sending.BlockingCompletionClient(sending._success(cost="0"))
        controller = self.controller(client)
        first = await controller.select_chat("free")
        self.assertEqual(first.last_request.state, LastRequestState.NONE)
        reserved_states = []

        async def reserved(_turn_id: str) -> None:
            reserved_states.append(await controller.load_state("free"))

        task = asyncio.create_task(
            controller.send_message(
                "free",
                "Synthetic request",
                paid_confirmed=False,
                on_reserved=reserved,
            )
        )
        try:
            await asyncio.wait_for(client.started.wait(), 2)
            self.assertEqual(len(reserved_states), 1)
            reserved_state = reserved_states[0]
            self.assertTrue(reserved_state.sending)
            self.assertGreater(reserved_state.budget.reserved_tokens, 0)
            self.assertEqual(
                reserved_state.last_request.state, LastRequestState.PENDING
            )
            self.assertIsNone(reserved_state.last_request.cost_usd)
            active = await controller.load_state("free")
            self.assertEqual(active.last_request, reserved_state.last_request)
        finally:
            client.release.set()
            outcome = await task
        self.assertTrue(outcome.applied)
        self.assertTrue(outcome.result.successful)
        assert outcome.state is not None
        self.assertFalse(outcome.state.sending)
        self.assertEqual(outcome.state.budget.reserved_tokens, 0)
        self.assertEqual(outcome.state.last_request.state, LastRequestState.FINAL)
        self.assertEqual(outcome.state.last_request.total_tokens, 30)
        self.assertEqual(outcome.state.last_request.cost_usd, 0)

    async def test_unknown_then_manual_release_remains_unknown_not_zero(self) -> None:
        client = sending.FakeCompletionClient(
            [
                replace(
                    sending._known_error(ChatErrorType.TIMEOUT),
                    accounting_unknown=True,
                )
            ]
        )
        controller = self.controller(client)
        await controller.select_chat("free")
        outcome = await controller.send_message(
            "free", "Synthetic request", paid_confirmed=False
        )
        assert outcome.state is not None and outcome.result.turn_id is not None
        self.assertEqual(outcome.state.last_request.state, LastRequestState.UNKNOWN)
        self.assertIsNone(outcome.state.last_request.total_tokens)
        self.assertGreater(outcome.state.budget.reserved_tokens, 0)
        released = await controller.release_unknown(
            "free",
            outcome.result.turn_id,
            confirmed=True,
        )
        self.assertEqual(released.budget.reserved_tokens, 0)
        self.assertEqual(released.last_request.state, LastRequestState.UNKNOWN)
        self.assertIsNone(released.last_request.total_tokens)
        self.assertIsNone(released.last_request.cost_usd)

    async def test_failed_final_and_retry_old_turn_use_actual_dispatch_chronology(
        self,
    ) -> None:
        client = sending.FakeCompletionClient(
            [
                sending._known_error(ChatErrorType.RATE_LIMIT_EXCEEDED),
                sending._success(cost="0"),
                replace(sending._success(cost="0"), error_type=ChatErrorType.REFUSAL),
            ]
        )
        controller = self.controller(client)
        await controller.select_chat("free")
        old = await controller.send_message(
            "free", "Synthetic old request", paid_confirmed=False
        )
        assert old.result.turn_id is not None
        newer = await controller.send_message(
            "free", "Synthetic newer request", paid_confirmed=False
        )
        assert newer.state is not None
        self.assertEqual(newer.state.last_request.turn_id, newer.result.turn_id)
        retried = await controller.retry_turn(
            "free",
            old.result.turn_id,
            paid_confirmed=False,
        )
        assert retried.state is not None
        self.assertFalse(retried.result.successful)
        self.assertEqual(retried.result.error_type, ChatErrorType.REFUSAL)
        self.assertEqual(retried.state.last_request.turn_id, old.result.turn_id)
        self.assertEqual(retried.state.last_request.state, LastRequestState.FINAL)
        self.assertEqual(retried.state.last_request.total_tokens, 30)
        self.assertEqual(retried.state.last_request.cost_usd, 0)
        self.assertEqual(len(client.calls), 3)

    async def test_pre_http_cancel_after_reservation_preserves_last_actual(
        self,
    ) -> None:
        client = sending.FakeCompletionClient([sending._success(cost="0")])
        controller = self.controller(client)
        await controller.select_chat("free")
        original = await controller.send_message(
            "free", "Synthetic actual", paid_confirmed=False
        )
        assert original.state is not None

        async def cancel_before_http(_turn_id: str) -> None:
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await controller.send_message(
                "free",
                "Synthetic never dispatched",
                paid_confirmed=False,
                on_reserved=cancel_before_http,
            )
        current = await controller.load_state("free")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(current.last_request, original.state.last_request)
        self.assertEqual(current.budget.reserved_tokens, 0)

    async def test_local_invalid_message_does_not_replace_last_actual(self) -> None:
        client = sending.FakeCompletionClient([sending._success(cost="0")])
        controller = self.controller(client)
        await controller.select_chat("free")
        original = await controller.send_message(
            "free", "Synthetic actual", paid_confirmed=False
        )
        assert original.state is not None
        invalid = await controller.send_message("free", " \n ", paid_confirmed=False)
        assert invalid.state is not None
        self.assertEqual(invalid.result.error_type, ChatErrorType.INVALID_REQUEST)
        self.assertEqual(invalid.state.last_request, original.state.last_request)
        self.assertEqual(len(client.calls), 1)
