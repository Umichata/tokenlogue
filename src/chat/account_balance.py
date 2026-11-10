"""Session-only account totals, independent of chat budgets and UI lifetime."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Protocol

from api.openrouter import CreditsResult, CreditsStatus


class CreditsReader(Protocol):
    async def get_credits(self, api_key: str, /) -> CreditsResult: ...


class AccountBalanceState(str, Enum):
    LOADING = "loading"
    CURRENT = "current"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AccountBalanceSnapshot:
    state: AccountBalanceState = AccountBalanceState.UNAVAILABLE
    balance_usd: Decimal | None = field(default=None, repr=False)
    fetched_at: datetime | None = None
    error: CreditsStatus | None = None


class AccountBalanceService:
    """Publish only the newest read from the currently unlocked session."""

    def __init__(
        self,
        client: CreditsReader,
        on_change: Callable[[AccountBalanceSnapshot], None],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        stale_after: timedelta = timedelta(minutes=5),
        post_response_delay: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._client = client
        self._on_change = on_change
        self._clock = clock
        self._stale_after = stale_after
        self._post_response_delay = max(0.0, post_response_delay)
        self._sleep = sleep
        self._active = False
        self._generation = 0
        self._request = 0
        self._snapshot = AccountBalanceSnapshot()

    @property
    def snapshot(self) -> AccountBalanceSnapshot:
        """Reading an old successful value must never present it as current."""
        return self._aged_snapshot()

    def begin_session(self) -> None:
        self._generation += 1
        self._request += 1
        self._active = True
        self._publish(AccountBalanceSnapshot())

    def invalidate(self) -> None:
        """Forget amounts and revoke all outstanding reads without storing a key."""
        self._active = False
        self._generation += 1
        self._request += 1
        self._publish(AccountBalanceSnapshot())

    def expire_if_needed(self) -> AccountBalanceSnapshot:
        aged = self._aged_snapshot()
        if aged != self._snapshot:
            self._publish(aged)
        return aged

    async def refresh(
        self, api_key: str, *, after_response: bool = False
    ) -> AccountBalanceSnapshot:
        """A completion can schedule this read without waiting for account I/O.

        One delayed read accommodates server-side billing lag. A newer manual
        read or session revocation also supersedes that delayed read.
        """
        if not self._active:
            return self.snapshot
        self._request += 1
        ticket = self._generation, self._request
        previous = self.snapshot
        self._publish(replace(previous, state=AccountBalanceState.LOADING, error=None))
        try:
            await self._read(api_key, ticket)
            if after_response and self._is_current(ticket):
                await self._sleep(self._post_response_delay)
                if self._is_current(ticket):
                    await self._read(api_key, ticket)
        except asyncio.CancelledError:
            if (
                self._is_current(ticket)
                and self._snapshot.state is AccountBalanceState.LOADING
            ):
                self._publish_failure(None)
            raise
        return self.snapshot

    async def _read(self, api_key: str, ticket: tuple[int, int]) -> None:
        try:
            result = await self._client.get_credits(api_key)
        except Exception:
            # Neither transport exceptions nor credentials enter UI or logs.
            result = CreditsResult(CreditsStatus.NETWORK_ERROR)
        if not self._is_current(ticket):
            return
        if result.status is CreditsStatus.SUCCESS and result.balance_usd is not None:
            self._publish(
                AccountBalanceSnapshot(
                    AccountBalanceState.CURRENT,
                    result.balance_usd,
                    self._clock(),
                )
            )
        else:
            self._publish_failure(result.status)

    def _publish_failure(self, error: CreditsStatus | None) -> None:
        previous = self._snapshot
        self._publish(
            replace(
                previous,
                state=(
                    AccountBalanceState.STALE
                    if previous.balance_usd is not None
                    else AccountBalanceState.UNAVAILABLE
                ),
                error=error,
            )
        )

    def _aged_snapshot(self) -> AccountBalanceSnapshot:
        current = self._snapshot
        if (
            current.state is AccountBalanceState.CURRENT
            and current.fetched_at is not None
            and self._clock() - current.fetched_at >= self._stale_after
        ):
            return replace(current, state=AccountBalanceState.STALE)
        return current

    def _is_current(self, ticket: tuple[int, int]) -> bool:
        return self._active and ticket == (self._generation, self._request)

    def _publish(self, snapshot: AccountBalanceSnapshot) -> None:
        self._snapshot = snapshot
        try:
            self._on_change(snapshot)
        except Exception:
            # Rendering a disposed control must not turn account I/O into a send.
            pass
