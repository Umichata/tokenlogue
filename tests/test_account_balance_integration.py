"""Account credits lifecycle through real encrypted session/chat controllers."""

from __future__ import annotations

import asyncio
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import CreditsResult, CreditsStatus  # noqa: E402
from chat.account_balance import AccountBalanceState  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, ChatMode  # noqa: E402
from tests import test_message_sending as sending  # noqa: E402
from tests.test_budget_warning_ui import UiHarness  # noqa: E402


def success(value: str) -> CreditsResult:
    return CreditsResult(CreditsStatus.SUCCESS, balance_usd=Decimal(value))


class DelayedCredits:
    def __init__(self):
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def get_credits(self, api_key: str, /) -> CreditsResult:
        self.calls += 1
        if self.calls == 1:
            return success("2")
        self.started.set()
        await self.release.wait()
        return success("1.99")


class FailingCredits:
    def __init__(self):
        self.calls = 0

    async def get_credits(self, api_key: str, /) -> CreditsResult:
        self.calls += 1
        if self.calls == 1:
            return success("2")
        return CreditsResult(CreditsStatus.RESTRICTED)


class AccountBalanceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def settle(self, h):
        task = h.controller._balance_task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=2)

    async def test_response_finishes_and_refresh_survives_navigation_without_waiting_for_credits(
        self,
    ):
        reader = DelayedCredits()
        completion = sending.BlockingCompletionClient(sending._success(cost="0.01"))
        h = await UiHarness().setup(self, credits_reader=reader, client=completion)
        await self.settle(h)
        service = h.controller._balance_service
        assert service is not None
        service._post_response_delay = 0
        self.assertEqual(service.snapshot.balance_usd, Decimal("2"))
        await h.controller.submit_message("synthetic navigation request")
        pending = asyncio.create_task(h.click(h.warning_buttons()[1]))
        await asyncio.wait_for(completion.started.wait(), timeout=1)
        await h.controller.select_chat("b")
        completion.release.set()
        await asyncio.wait_for(pending, timeout=1)
        await asyncio.wait_for(reader.started.wait(), timeout=1)
        self.assertEqual(h.controller.selected_chat_id, "b")
        self.assertEqual(len(completion.calls), 1)
        self.assertEqual(h.fx.chats.list_messages("a")[-1].content, "answer")
        self.assertEqual(service.snapshot.balance_usd, Decimal("2"))
        assert h.controller._balance_task is not None
        self.assertFalse(h.controller._balance_task.done())
        reader.release.set()
        await self.settle(h)
        self.assertEqual(service.snapshot.balance_usd, Decimal("1.99"))
        self.assertEqual(service.snapshot.state, AccountBalanceState.CURRENT)
        self.assertEqual(reader.calls, 3)
        self.assertEqual(len(completion.calls), 1)

    async def test_credits_failure_leaves_saved_answer_and_stale_value_without_repeating_generation(
        self,
    ):
        reader = FailingCredits()
        h = await UiHarness().setup(self, credits_reader=reader)
        await self.settle(h)
        service = h.controller._balance_service
        assert service is not None
        service._post_response_delay = 0
        await h.controller.submit_message("synthetic restricted credits")
        await h.click(h.warning_buttons()[1])
        await self.settle(h)
        self.assertEqual(len(h.client.calls), 1)
        self.assertEqual(h.fx.chats.list_messages("a")[-1].content, "answer")
        self.assertEqual(service.snapshot.state, AccountBalanceState.STALE)
        self.assertEqual(service.snapshot.balance_usd, Decimal("2"))
        self.assertEqual(h.controller.key_validity, sending.KeyValidityState.VALID)
        self.assertEqual(h.budget("a").cost_limit_usd, Decimal("0.011"))

    async def test_lock_clears_balance_and_revokes_inflight_account_read(self):
        reader = DelayedCredits()
        h = await UiHarness().setup(self, credits_reader=reader)
        await self.settle(h)
        service = h.controller._balance_service
        assert service is not None
        h.controller._start_balance_refresh()
        await asyncio.wait_for(reader.started.wait(), timeout=1)
        await h.controller.lock_application()
        reader.release.set()
        await asyncio.sleep(0)
        self.assertEqual(service.snapshot.state, AccountBalanceState.UNAVAILABLE)
        self.assertIsNone(service.snapshot.balance_usd)
        self.assertIsNone(h.controller._session_api_key)
        self.assertEqual(h.client.calls, [])

    async def test_account_balance_is_present_in_free_chat_and_does_not_replace_budgets(
        self,
    ):
        reader = FailingCredits()
        h = await UiHarness().setup(self, credits_reader=reader)
        await self.settle(h)
        h.fx.chats.create_chat_with_limits(
            sending._chat("free", ChatMode.FREE, FREE_ROUTER_MODEL),
            token_limit=8192,
            max_completion_tokens=64,
            cost_limit_usd=Decimal("0"),
        )
        await h.controller.select_chat("free")
        service = h.controller._balance_service
        assert service is not None
        self.assertEqual(service.snapshot.balance_usd, Decimal("2"))
        self.assertEqual(
            h.controller._workspace_controller._account_balance.balance_usd,
            Decimal("2"),
        )
        self.assertEqual(h.budget("free").cost_limit_usd, Decimal("0"))
        await h.controller.select_chat("a")
        self.assertEqual(service.snapshot.balance_usd, Decimal("2"))
        self.assertEqual(h.budget("a").cost_limit_usd, Decimal("0.011"))
