"""Account refreshes use synthetic money and never issue completion requests."""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import CreditsResult, CreditsStatus  # noqa: E402
from chat.account_balance import (  # noqa: E402
    AccountBalanceService,
    AccountBalanceSnapshot,
    AccountBalanceState,
)


def success(balance: str) -> CreditsResult:
    return CreditsResult(CreditsStatus.SUCCESS, balance_usd=Decimal(balance))


class FakeCredits:
    def __init__(self, *results: CreditsResult) -> None:
        self.results = list(results)
        self.calls = 0

    async def get_credits(self, _api_key: str) -> CreditsResult:
        self.calls += 1
        return self.results.pop(0)


class PendingCredits:
    def __init__(self) -> None:
        self.pending: list[asyncio.Future[CreditsResult]] = []

    async def get_credits(self, _api_key: str) -> CreditsResult:
        future = asyncio.get_running_loop().create_future()
        self.pending.append(future)
        return await future


class AccountBalanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_loading_current_failure_and_unavailable_are_distinct(self) -> None:
        snapshots: list[AccountBalanceSnapshot] = []
        now = datetime(2026, 1, 1, tzinfo=UTC)
        client = FakeCredits(
            CreditsResult(CreditsStatus.RESTRICTED),
            success("-0.000123"),
            CreditsResult(CreditsStatus.TIMEOUT),
        )
        service = AccountBalanceService(client, snapshots.append, clock=lambda: now)
        service.begin_session()
        self.assertEqual(service.snapshot.state, AccountBalanceState.UNAVAILABLE)
        await service.refresh("synthetic-credential")
        self.assertEqual(service.snapshot.state, AccountBalanceState.UNAVAILABLE)
        self.assertIsNone(service.snapshot.balance_usd)
        self.assertIsNone(service.snapshot.fetched_at)
        await service.refresh("synthetic-credential")
        self.assertEqual(service.snapshot.state, AccountBalanceState.CURRENT)
        self.assertEqual(service.snapshot.balance_usd, Decimal("-0.000123"))
        self.assertEqual(service.snapshot.fetched_at, now)
        await service.refresh("synthetic-credential")
        self.assertEqual(service.snapshot.state, AccountBalanceState.STALE)
        self.assertEqual(service.snapshot.balance_usd, Decimal("-0.000123"))
        self.assertEqual(service.snapshot.fetched_at, now)
        self.assertEqual(service.snapshot.error, CreditsStatus.TIMEOUT)
        self.assertEqual(
            [snapshot.state for snapshot in snapshots],
            [
                AccountBalanceState.UNAVAILABLE,
                AccountBalanceState.LOADING,
                AccountBalanceState.UNAVAILABLE,
                AccountBalanceState.LOADING,
                AccountBalanceState.CURRENT,
                AccountBalanceState.LOADING,
                AccountBalanceState.STALE,
            ],
        )
        self.assertNotIn("-0.000123", repr(service.snapshot))

    async def test_zero_balance_survives_a_failed_refresh_as_stale(self) -> None:
        client = FakeCredits(success("0"), CreditsResult(CreditsStatus.SERVER_ERROR))
        service = AccountBalanceService(client, lambda _: None)
        service.begin_session()
        await service.refresh("synthetic-credential")
        await service.refresh("synthetic-credential")
        self.assertEqual(service.snapshot.state, AccountBalanceState.STALE)
        self.assertEqual(service.snapshot.balance_usd, Decimal("0"))

    async def test_newest_refresh_wins_when_old_response_arrives_last(self) -> None:
        client = PendingCredits()
        snapshots: list[AccountBalanceSnapshot] = []
        service = AccountBalanceService(client, snapshots.append)
        service.begin_session()
        first = asyncio.create_task(service.refresh("synthetic-credential"))
        await asyncio.sleep(0)
        second = asyncio.create_task(service.refresh("synthetic-credential"))
        await asyncio.sleep(0)
        client.pending[1].set_result(success("3"))
        await second
        client.pending[0].set_result(success("20"))
        await first
        self.assertEqual(service.snapshot.balance_usd, Decimal("3"))
        self.assertFalse(
            any(snapshot.balance_usd == Decimal("20") for snapshot in snapshots)
        )

    async def test_replaced_key_session_never_accepts_old_key_result(self) -> None:
        client = PendingCredits()
        snapshots: list[AccountBalanceSnapshot] = []
        service = AccountBalanceService(client, snapshots.append)
        service.begin_session()
        old = asyncio.create_task(service.refresh("old-synthetic-credential"))
        await asyncio.sleep(0)
        service.invalidate()
        self.assertIsNone(service.snapshot.balance_usd)
        service.begin_session()
        new = asyncio.create_task(service.refresh("new-synthetic-credential"))
        await asyncio.sleep(0)
        client.pending[1].set_result(success("2"))
        await new
        published = len(snapshots)
        client.pending[0].set_result(success("100"))
        await old
        self.assertEqual(len(snapshots), published)
        self.assertEqual(service.snapshot.balance_usd, Decimal("2"))

    async def test_lock_revokes_pending_value_and_disables_new_requests(self) -> None:
        client = PendingCredits()
        service = AccountBalanceService(client, lambda _: None)
        service.begin_session()
        task = asyncio.create_task(service.refresh("synthetic-credential"))
        await asyncio.sleep(0)
        service.invalidate()
        client.pending[0].set_result(success("100"))
        await task
        await service.refresh("synthetic-credential")
        self.assertEqual(len(client.pending), 1)
        self.assertEqual(service.snapshot.state, AccountBalanceState.UNAVAILABLE)
        self.assertIsNone(service.snapshot.balance_usd)

    async def test_age_marks_a_successful_snapshot_stale_without_zeroing(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        snapshots: list[AccountBalanceSnapshot] = []
        service = AccountBalanceService(
            FakeCredits(success("7")),
            snapshots.append,
            clock=lambda: now,
            stale_after=timedelta(minutes=5),
        )
        service.begin_session()
        await service.refresh("synthetic-credential")
        now += timedelta(minutes=5)
        self.assertEqual(service.snapshot.state, AccountBalanceState.STALE)
        self.assertEqual(service.snapshot.balance_usd, Decimal("7"))
        service.expire_if_needed()
        self.assertEqual(snapshots[-1].state, AccountBalanceState.STALE)
        published = len(snapshots)
        service.expire_if_needed()
        self.assertEqual(len(snapshots), published)

    async def test_post_response_refresh_is_bounded_and_does_not_generate(self) -> None:
        delays: list[float] = []

        async def sleep(delay: float) -> None:
            delays.append(delay)

        client = FakeCredits(success("10"), success("9.99"))
        service = AccountBalanceService(client, lambda _: None, sleep=sleep)
        service.begin_session()
        await service.refresh("synthetic-credential", after_response=True)
        self.assertEqual(client.calls, 2)
        self.assertEqual(delays, [1.0])
        self.assertEqual(service.snapshot.balance_usd, Decimal("9.99"))

    async def test_new_manual_refresh_supersedes_old_delayed_refresh(self) -> None:
        sleeping = asyncio.Event()
        resume = asyncio.Event()

        async def sleep(_delay: float) -> None:
            sleeping.set()
            await resume.wait()

        client = FakeCredits(success("10"), success("8"))
        service = AccountBalanceService(client, lambda _: None, sleep=sleep)
        service.begin_session()
        old = asyncio.create_task(
            service.refresh("synthetic-credential", after_response=True)
        )
        await sleeping.wait()
        await service.refresh("synthetic-credential")
        resume.set()
        await old
        self.assertEqual(client.calls, 2)
        self.assertEqual(service.snapshot.balance_usd, Decimal("8"))

    async def test_cancelled_read_does_not_leave_loading_or_clear_old_success(
        self,
    ) -> None:
        client = PendingCredits()
        service = AccountBalanceService(client, lambda _: None)
        service.begin_session()
        first = asyncio.create_task(service.refresh("synthetic-credential"))
        await asyncio.sleep(0)
        client.pending[0].set_result(success("5"))
        await first
        task = asyncio.create_task(service.refresh("synthetic-credential"))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(service.snapshot.state, AccountBalanceState.STALE)
        self.assertEqual(service.snapshot.balance_usd, Decimal("5"))

    async def test_disposed_render_callback_and_unexpected_failure_are_safe(
        self,
    ) -> None:
        class BrokenCredits:
            async def get_credits(self, _api_key: str) -> CreditsResult:
                raise RuntimeError("private-client-error")

        def disposed(_snapshot: AccountBalanceSnapshot) -> None:
            raise RuntimeError("private-render-error")

        service = AccountBalanceService(BrokenCredits(), disposed)
        service.begin_session()
        result = await service.refresh("synthetic-credential")
        self.assertEqual(result.state, AccountBalanceState.UNAVAILABLE)
        self.assertEqual(result.error, CreditsStatus.NETWORK_ERROR)
        self.assertNotIn("private", repr(result))


if __name__ == "__main__":
    unittest.main()
