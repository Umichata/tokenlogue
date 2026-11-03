"""One local worker and one latest pending edit, without storage or transport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from chat.estimates import (
    DraftEstimate,
    EstimateState,
    PreparedEstimateSnapshot,
    estimate_draft,
)


@dataclass(frozen=True)
class EstimateRevision:
    session: int
    workspace: int
    view: int
    context: int
    chat_id: str
    draft: int


@dataclass(frozen=True)
class _Request:
    revision: EstimateRevision
    snapshot: PreparedEstimateSnapshot = field(repr=False)
    text: str = field(repr=False)


Calculator = Callable[[PreparedEstimateSnapshot, str], DraftEstimate]


class LiveEstimateWorker:
    """Start immediately, coalesce busy frames, never queue old keystrokes.

    Revocation drops pending snapshots immediately. A running pure calculation
    can finish in its thread, but has no repository, credential or UI handle and
    can publish only while its complete revision is still current.
    """

    def __init__(
        self,
        is_current: Callable[[EstimateRevision], bool],
        publish: Callable[[EstimateRevision, DraftEstimate], None],
        *,
        calculate: Calculator = estimate_draft,
    ) -> None:
        self._is_current = is_current
        self._publish = publish
        self._calculate = calculate
        self._latest: EstimateRevision | None = None
        self._pending: _Request | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def pending_count(self) -> int:
        return int(self._pending is not None)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def submit(
        self,
        revision: EstimateRevision,
        snapshot: PreparedEstimateSnapshot,
        text: str,
    ) -> None:
        self._latest = revision
        request = _Request(revision, snapshot, text)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._deliver(request, self._calculate_safely(request))
            return
        self._pending = request
        if self._task is None or self._task.done():
            self._task = loop.create_task(self._run())

    def invalidate(self) -> None:
        self._latest = None
        self._pending = None

    async def wait_idle(self) -> None:
        task = self._task
        if task is not None:
            await asyncio.shield(task)

    def _calculate_safely(self, request: _Request) -> DraftEstimate:
        try:
            return self._calculate(request.snapshot, request.text)
        except Exception:
            # No exception text or request repr may enter a diagnostic stream.
            return DraftEstimate(EstimateState.UNAVAILABLE)

    def _deliver(self, request: _Request, result: DraftEstimate) -> None:
        if request.revision == self._latest and self._is_current(request.revision):
            self._publish(request.revision, result)

    async def _run(self) -> None:
        try:
            while self._pending is not None:
                request, self._pending = self._pending, None
                result = await asyncio.to_thread(self._calculate_safely, request)
                self._deliver(request, result)
        finally:
            self._task = None
