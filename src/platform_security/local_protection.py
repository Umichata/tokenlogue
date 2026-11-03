"""Independent device check history and current trusted protection trials."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol


class CheckState(StrEnum):
    UNTESTED = "untested"
    RUNNING = "running"
    CONFIRMED = "confirmed"
    PROBLEM = "problem"


@dataclass(frozen=True)
class ObserverContext:
    platform: str
    session_id: str
    generation: int
    source: str


@dataclass(frozen=True)
class AppLockState:
    application_session: int
    session_open: bool
    data_open: bool
    pin_visible: bool

    @property
    def opened(self) -> bool:
        return self.session_open and self.data_open and not self.pin_visible

    @property
    def revoked(self) -> bool:
        return not self.session_open and not self.data_open

    @property
    def sealed_pin(self) -> bool:
        return self.revoked and self.pin_visible


@dataclass(frozen=True)
class CheckResult:
    state: CheckState = CheckState.UNTESTED
    code: str = "not_checked"


SCREEN_CONTRACT = "linux-screen-v2"
SLEEP_CONTRACT = "linux-sleep-v2"


@dataclass(frozen=True)
class DeviceCheckRecord:
    state: CheckState
    checked_at: int
    last_success_at: int | None
    contract: str
    origin: str = "manual"


@dataclass(frozen=True)
class DeviceProtectionHistory:
    screen: DeviceCheckRecord | None = None
    sleep: DeviceCheckRecord | None = None


@dataclass(frozen=True)
class ProtectionSnapshot:
    screen: CheckResult
    sleep: CheckResult
    screen_connected: bool
    sleep_connected: bool
    screen_test_running: bool
    sleep_test_running: bool = False
    screen_history: DeviceCheckRecord | None = None
    sleep_history: DeviceCheckRecord | None = None
    screen_attempt: CheckResult = CheckResult()
    sleep_attempt: CheckResult = CheckResult()
    screen_stale: bool = False
    sleep_stale: bool = False
    persistence_error: bool = False

    @property
    def test_running(self) -> bool:
        return self.screen_test_running or self.sleep_test_running

    @property
    def has_problem(self) -> bool:
        return CheckState.PROBLEM in {self.screen.state, self.sleep.state}


@dataclass(frozen=True)
class ScreenState:
    context: ObserverContext
    # None means that a visible screensaver is not proven to be a locked OS.
    locked: bool | None


class ScreenLockUnavailable(RuntimeError):
    """A safe protocol code, never a raw OS exception or command line."""


_SAFE_CODES = frozenset(
    {
        "not_checked",
        "observer_changed",
        "cancelled",
        "closed",
        "screen_test_preparing",
        "screen_test_running",
        "screen_confirmed",
        "sleep_cycle_running",
        "sleep_confirmed",
        "preparation_timeout",
        "activation_unavailable",
        "activation_untrusted",
        "locker_contract_unavailable",
        "already_locked_or_unconfirmed",
        "session_changed",
        "state_unavailable",
        "request_unavailable",
        "observation_unavailable",
        "timeout",
        "unlock_timeout",
        "pin_timeout",
        "app_state_unavailable",
        "normal_seal_failed",
        "normal_reaction_unproven",
        "locked_state_unproven",
        "actual_suspend_unproven",
        "sleep_test_preparing",
        "sleep_request_running",
        "sleep_unavailable",
        "sleep_permission_required",
        "sleep_inhibited",
        "contract_changed",
    }
)


class ScreenLockAdapter(Protocol):
    @property
    def screen_context(self) -> ObserverContext | None: ...

    async def read_screen_state(self, context: ObserverContext) -> ScreenState: ...

    async def request_screen_lock(self, context: ObserverContext) -> None: ...


class SleepAdapter(Protocol):
    @property
    def sleep_context(self) -> ObserverContext | None: ...

    async def prepare_sleep_test(self, *, timeout: float = 8.0) -> ObserverContext: ...

    def bind_sleep_test(self, context: ObserverContext, test_id: int) -> None: ...

    async def request_sleep(self, context: ObserverContext) -> None: ...


@dataclass(eq=False)
class _ScreenTrial:
    context: ObserverContext
    application_session: int
    deadline: float
    normal_receipt: bool = False
    locked_at: float | None = None
    ambiguous_seen: bool = False
    unlocked: bool = False
    pin_seen: bool = False
    request_complete: bool = False
    identifier: int = 0
    tagged_events: bool = False


@dataclass(eq=False)
class _SleepCycle:
    context: ObserverContext
    deadline: float
    application_session: int = 0
    identifier: int | None = None
    origin: str = "observed"
    started: bool = False
    normal_receipt: bool = False
    pin_seen: bool = False
    resumed: bool = False
    actual_suspend: bool = False
    presealed_generation: int | None = None
    presealed_screen_context: ObserverContext | None = None
    unbind: Callable[[], None] | None = None


def _current_task() -> asyncio.Task | None:
    try:
        return asyncio.current_task()
    except RuntimeError:
        return None


class LocalProtectionChecks:
    """Consumes trusted OS readback plus real application state, never focus loss.

    The caller records normal_reaction ONLY after the ordinary watcher handler.
    The emergency callback is deliberately separate and can never create a normal
    receipt. UI rendering alone cannot satisfy the actual access/session probe.
    """

    def __init__(
        self,
        probe: Callable[[], AppLockState],
        emergency_lock: Callable[[], None],
        on_change: Callable[[ProtectionSnapshot], None] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        request_timeout: float = 5.0,
        cycle_timeout: float = 90.0,
        preparation_timeout: float = 8.0,
        unlock_timeout: float = 900.0,
        pin_timeout: float = 5.0,
        reaction_grace: float = 1.0,
        poll_interval: float = 0.1,
        history: DeviceProtectionHistory | None = None,
        on_completed: Callable[[str, DeviceCheckRecord], None] | None = None,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._probe = probe
        self._emergency_lock = emergency_lock
        self._on_change = on_change
        self._clock = clock
        self._request_timeout = request_timeout
        self._cycle_timeout = cycle_timeout
        self._preparation_timeout = preparation_timeout
        self._unlock_timeout = unlock_timeout
        self._pin_timeout = pin_timeout
        self._reaction_grace = reaction_grace
        self._poll_interval = poll_interval
        self._history = history or DeviceProtectionHistory()
        self._on_completed = on_completed
        self._wall_clock = wall_clock
        self._persistence_error = False
        self._screen_context: ObserverContext | None = None
        self._sleep_context: ObserverContext | None = None
        self._screen_compatible = True
        self._sleep_compatible = True
        self._screen = CheckResult()
        self._sleep = CheckResult()
        self._trial: _ScreenTrial | None = None
        self._sleep_cycle: _SleepCycle | None = None
        self._screen_task: asyncio.Task[None] | None = None
        self._sleep_task: asyncio.Task[None] | None = None
        self._sleep_request_task: asyncio.Task[None] | None = None
        self._sleep_preparation_task: asyncio.Task[ObserverContext] | None = None
        self._sleep_starting = False
        self._sleep_cancel_revision = 0
        self._request_task: asyncio.Task[None] | None = None
        self._preparation_task: asyncio.Task[ObserverContext] | None = None
        self._cancel_revision = 0
        self._starting = False
        self._closed = False
        self._trace_sink: Callable[[dict[str, object]], None] | None = None
        self._test_counter = 0

    def set_trace(self, sink: Callable[[dict[str, object]], None] | None) -> None:
        """Install a private, opt-in metadata-only diagnostic sink."""
        self._trace_sink = sink

    def set_completion_callback(
        self, callback: Callable[[str, DeviceCheckRecord], None] | None
    ) -> None:
        self._on_completed = callback

    def _trace(self, event: str, *, reason: str | None = None) -> None:
        sink = self._trace_sink
        if sink is None:
            return
        state = self._state()
        trial = self._trial
        record: dict[str, object] = {
            "event": event,
            "test": self._test_counter,
            "generation": self._screen_context.generation
            if self._screen_context
            else -1,
            "state": self._screen.state.value,
            "normal_receipt": trial.normal_receipt if trial else False,
        }
        if reason in _SAFE_CODES:
            record["reason"] = reason
        if state is not None:
            record.update(
                app_generation=state.application_session,
                session_open=state.session_open,
                data_open=state.data_open,
                pin_visible=state.pin_visible,
            )
        try:
            sink(record)
        except Exception:
            pass

    @property
    def snapshot(self) -> ProtectionSnapshot:
        screen_stale = self._history.screen is not None and (
            self._history.screen.contract != SCREEN_CONTRACT
            or not self._screen_compatible
        )
        sleep_stale = self._history.sleep is not None and (
            self._history.sleep.contract != SLEEP_CONTRACT or not self._sleep_compatible
        )
        return ProtectionSnapshot(
            self._effective("screen"),
            self._effective("sleep"),
            self._screen_context is not None,
            self._sleep_context is not None,
            self._starting or self._trial is not None,
            self._sleep_starting or self._sleep_cycle is not None,
            self._history.screen,
            self._history.sleep,
            self._screen,
            self._sleep,
            screen_stale,
            sleep_stale,
            self._persistence_error,
        )

    def _effective(self, mechanism: str) -> CheckResult:
        attempt = self._screen if mechanism == "screen" else self._sleep
        record = self._history.screen if mechanism == "screen" else self._history.sleep
        contract = SCREEN_CONTRACT if mechanism == "screen" else SLEEP_CONTRACT
        compatible = (
            self._screen_compatible if mechanism == "screen" else self._sleep_compatible
        )
        if attempt.state in {CheckState.RUNNING, CheckState.PROBLEM}:
            return attempt
        if attempt.state is CheckState.CONFIRMED:
            return (
                attempt
                if compatible
                else CheckResult(CheckState.UNTESTED, "contract_changed")
            )
        if record is not None:
            if record.state is CheckState.PROBLEM:
                return CheckResult(CheckState.PROBLEM, "normal_seal_failed")
            if record.contract != contract or not compatible:
                return CheckResult(CheckState.UNTESTED, "contract_changed")
            return CheckResult(
                record.state,
                mechanism + "_confirmed"
                if record.state is CheckState.CONFIRMED
                else "normal_seal_failed",
            )
        return attempt

    @property
    def history(self) -> DeviceProtectionHistory:
        return self._history

    def set_history(
        self, history: DeviceProtectionHistory, *, persistence_error: bool = False
    ) -> None:
        """Apply validated device-bound metadata, never grant authentication."""
        self._history = history
        self._persistence_error = persistence_error
        self._publish()

    def set_persistence_error(self, failed: bool) -> None:
        self._persistence_error = failed
        self._publish()

    def _record_completed(
        self, mechanism: str, state: CheckState, *, origin: str = "manual"
    ) -> None:
        if state not in {CheckState.CONFIRMED, CheckState.PROBLEM}:
            return
        previous = (
            self._history.screen if mechanism == "screen" else self._history.sleep
        )
        now = max(1, int(self._wall_clock()), previous.checked_at if previous else 1)
        record = DeviceCheckRecord(
            state,
            now,
            now
            if state is CheckState.CONFIRMED
            else previous.last_success_at
            if previous
            else None,
            SCREEN_CONTRACT if mechanism == "screen" else SLEEP_CONTRACT,
            origin,
        )
        self._history = (
            DeviceProtectionHistory(record, self._history.sleep)
            if mechanism == "screen"
            else DeviceProtectionHistory(self._history.screen, record)
        )
        if self._on_completed is not None:
            try:
                self._on_completed(mechanism, record)
            except Exception:
                self._persistence_error = True

    def _publish(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change(self.snapshot)
            except Exception:
                # A disconnected UI must not prevent a synchronous safety seal.
                pass

    def _state(self) -> AppLockState | None:
        try:
            return self._probe()
        except Exception:
            return None

    def _emergency(self) -> None:
        try:
            self._emergency_lock()
        except Exception:
            pass

    def update_observers(
        self,
        screen_context: ObserverContext | None,
        sleep_context: ObserverContext | None,
        *,
        screen_compatible: bool = True,
        sleep_compatible: bool = True,
    ) -> None:
        if self._closed:
            return
        self._screen_compatible = screen_compatible
        self._sleep_compatible = sleep_compatible
        if screen_context != self._screen_context:
            cycle = self._sleep_cycle
            if cycle is not None and not cycle.started:
                cycle.presealed_generation = None
                cycle.presealed_screen_context = None
                cycle.pin_seen = False
            # Bootstrap has not bound a trial or sent an OS request yet. A newly
            # attested lazy service is its expected output, not lost evidence.
            if not (self._starting and self._trial is None):
                code = (
                    "observer_changed"
                    if self._trial is not None
                    else self._screen.code
                    if self._screen.state is CheckState.UNTESTED
                    else "not_checked"
                )
                self._finish_screen(CheckState.UNTESTED, code)
            self._screen_context = screen_context
            self._trace("observer_changed", reason="observer_changed")
        if sleep_context != self._sleep_context:
            if not (self._sleep_starting and self._sleep_cycle is None):
                code = (
                    "observer_changed"
                    if self._sleep_cycle is not None
                    else self._sleep.code
                    if self._sleep.state is CheckState.UNTESTED
                    else "not_checked"
                )
                self._finish_sleep(CheckState.UNTESTED, code)
            self._sleep_context = sleep_context
        self._publish()

    def _cancel_request(self) -> None:
        self._cancel_revision += 1
        task = self._request_task
        if task is not None and not task.done() and task is not _current_task():
            task.cancel()
        preparation = self._preparation_task
        if (
            preparation is not None
            and not preparation.done()
            and preparation is not _current_task()
        ):
            preparation.cancel()

    def preparation_unavailable(self, code: str = "request_unavailable") -> None:
        """Report an explicit failed start rather than silently ignoring a click."""
        if not self._closed and not self.snapshot.test_running:
            self._finish_screen(CheckState.UNTESTED, code)

    def sleep_preparation_unavailable(self, code: str = "sleep_unavailable") -> None:
        if not self._closed and not self.snapshot.test_running:
            self._finish_sleep(CheckState.UNTESTED, code)

    def cancel_sleep_test(self) -> None:
        self._sleep_cancel_revision += 1
        self._cancel_sleep_request()
        if self._sleep.state is not CheckState.PROBLEM:
            self._finish_sleep(CheckState.UNTESTED, "cancelled")

    def _cancel_sleep_request(self) -> None:
        for task in (self._sleep_request_task, self._sleep_preparation_task):
            if task is not None and not task.done() and task is not _current_task():
                task.cancel()

    def cancel_screen_test(self) -> None:
        """Cancel pending work, without pretending an already sent OS request is reversible."""
        self._cancel_request()
        if self._screen.state is not CheckState.PROBLEM:
            self._finish_screen(CheckState.UNTESTED, "cancelled")

    def _finish_screen(self, state: CheckState, code: str) -> None:
        code = code if code in _SAFE_CODES else "request_unavailable"
        self._screen = CheckResult(state, code)
        self._record_completed("screen", state)
        self._trace("screen_finished", reason=code)
        self._cancel_request()
        self._trial = None
        task, self._screen_task = self._screen_task, None
        if task is not None and task is not _current_task():
            task.cancel()
        self._publish()

    def _finish_sleep(self, state: CheckState, code: str) -> None:
        self._sleep_cancel_revision += 1
        cycle = self._sleep_cycle
        code = code if code in _SAFE_CODES else "sleep_unavailable"
        self._sleep = CheckResult(state, code)
        self._record_completed(
            "sleep", state, origin=cycle.origin if cycle else "manual"
        )
        self._trace_sleep("sleep_finished", reason=code)
        self._unbind_sleep_trial()
        self._sleep_cycle = None
        task, self._sleep_task = self._sleep_task, None
        if task is not None and task is not _current_task():
            task.cancel()
        self._cancel_sleep_request()
        self._publish()

    def _unbind_sleep_trial(self) -> None:
        cycle = self._sleep_cycle
        if cycle is not None and cycle.unbind is not None:
            callback, cycle.unbind = cycle.unbind, None
            try:
                callback()
            except Exception:
                pass

    async def start_screen_test(
        self, adapter: ScreenLockAdapter, application_session: int
    ) -> bool:
        if self._closed or self.snapshot.test_running:
            return False
        state = self._state()
        if (
            state is None
            or not state.opened
            or state.application_session != application_session
        ):
            return False
        self._starting = True
        self._test_counter += 1
        self._screen = CheckResult(CheckState.RUNNING, "screen_test_preparing")
        self._trace("prepare_started", reason="screen_test_preparing")
        revision = self._cancel_revision
        context: ObserverContext | None = None
        self._publish()
        try:
            prepare = getattr(adapter, "prepare_screen_test", None)
            if prepare is not None:

                async def prepare_once() -> ObserverContext:
                    return await prepare(timeout=self._preparation_timeout)

                self._preparation_task = asyncio.create_task(prepare_once())
                context = await asyncio.wait_for(
                    self._preparation_task, self._preparation_timeout
                )
            else:
                context = adapter.screen_context
            if context is None:
                raise ScreenLockUnavailable("request_unavailable")
            if self._screen_context != context:
                self.update_observers(context, self._sleep_context)
            self._trace("prepare_finished")
            initial = await asyncio.wait_for(
                adapter.read_screen_state(context), self._request_timeout
            )
            state = self._state()
            if (
                self._closed
                or revision != self._cancel_revision
                or self._screen_context != context
                or adapter.screen_context != context
                or initial.context != context
                or initial.locked is not False
                or state is None
                or not state.opened
                or state.application_session != application_session
            ):
                if revision == self._cancel_revision:
                    self._finish_screen(
                        CheckState.UNTESTED, "already_locked_or_unconfirmed"
                    )
                return False
            trial = _ScreenTrial(
                context,
                application_session,
                self._clock() + self._cycle_timeout,
                identifier=self._test_counter,
            )
            bind = getattr(adapter, "bind_screen_test", None)
            if bind is not None:
                bind(context, trial.identifier)
                trial.tagged_events = True
            self._trial = trial
            self._trace("trial_started")
            self._screen = CheckResult(CheckState.RUNNING, "screen_test_running")
            self._screen_task = asyncio.create_task(
                self._monitor_screen(adapter, trial)
            )
            self._publish()

            if (
                self._closed
                or self._trial is not trial
                or self._screen_context != context
            ):
                return False
            self._request_task = asyncio.create_task(
                adapter.request_screen_lock(context)
            )
            self._trace("request_started", reason="screen_test_running")
            await asyncio.wait_for(self._request_task, self._request_timeout)
            trial.request_complete = True
            self._trace("request_finished")
            self.app_state_changed()
            return self._trial is trial or self._screen.state is CheckState.CONFIRMED
        except asyncio.CancelledError:
            if (
                self._closed
                or (context is not None and self._screen_context != context)
                or revision != self._cancel_revision
            ):
                return self._screen.state is CheckState.CONFIRMED
            if self._screen.state is not CheckState.PROBLEM:
                self._finish_screen(CheckState.UNTESTED, "cancelled")
            raise
        except Exception as error:
            if (
                self._closed
                or (context is not None and self._screen_context != context)
                or revision != self._cancel_revision
            ):
                return False
            if self._screen.state is not CheckState.PROBLEM:
                code = (
                    str(error)
                    if isinstance(error, ScreenLockUnavailable)
                    else (
                        "preparation_timeout"
                        if isinstance(error, TimeoutError) and context is None
                        else "request_unavailable"
                    )
                )
                self._finish_screen(CheckState.UNTESTED, code)
            return False
        finally:
            self._request_task = None
            self._preparation_task = None
            self._starting = False
            self._publish()

    def _trace_sleep(self, event: str, *, reason: str | None = None) -> None:
        sink = self._trace_sink
        if sink is None:
            return
        cycle = self._sleep_cycle
        state = self._state()
        record: dict[str, object] = {
            "event": event,
            "mechanism": "sleep",
            "test": cycle.identifier if cycle and cycle.identifier else 0,
            "generation": self._sleep_context.generation if self._sleep_context else 0,
            "state": self._sleep.state.value,
            "normal_receipt": cycle.normal_receipt if cycle else False,
            "actual_suspend": cycle.actual_suspend if cycle else False,
        }
        if reason in _SAFE_CODES:
            record["reason"] = reason
        if state is not None:
            record.update(
                app_generation=state.application_session,
                session_open=state.session_open,
                data_open=state.data_open,
                pin_visible=state.pin_visible,
            )
        try:
            sink(record)
        except Exception:
            pass

    async def start_sleep_test(
        self, adapter: SleepAdapter, application_session: int
    ) -> bool:
        """A one-shot explicit request. The ordinary trusted handler must seal first."""
        if self._closed or self.snapshot.test_running:
            return False
        state = self._state()
        if (
            state is None
            or not state.opened
            or state.application_session != application_session
        ):
            return False
        self._sleep_starting = True
        self._test_counter += 1
        identifier = self._test_counter
        revision = self._sleep_cancel_revision
        self._sleep = CheckResult(CheckState.RUNNING, "sleep_test_preparing")
        self._trace_sleep("sleep_prepare_started", reason="sleep_test_preparing")
        self._publish()
        context = None
        try:
            self._sleep_preparation_task = asyncio.create_task(
                adapter.prepare_sleep_test(timeout=self._preparation_timeout)
            )
            context = await asyncio.wait_for(
                self._sleep_preparation_task, self._preparation_timeout
            )
            state = self._state()
            if (
                self._closed
                or revision != self._sleep_cancel_revision
                or context != adapter.sleep_context
                or state is None
                or not state.opened
                or state.application_session != application_session
            ):
                return False
            if self._sleep_context != context:
                self.update_observers(self._screen_context, context)
            cycle = _SleepCycle(
                context,
                self._clock() + self._request_timeout,
                application_session=application_session,
                identifier=identifier,
                origin="manual",
            )
            adapter.bind_sleep_test(context, identifier)
            unbind = getattr(adapter, "unbind_sleep_test", None)
            if callable(unbind):

                def unbind_once() -> None:
                    unbind(context, identifier)

                cycle.unbind = unbind_once
            self._sleep_cycle = cycle
            self._sleep = CheckResult(CheckState.RUNNING, "sleep_request_running")
            self._sleep_task = asyncio.create_task(self._monitor_sleep())
            self._sleep_request_task = asyncio.create_task(
                adapter.request_sleep(context)
            )
            request = self._sleep_request_task
            self._trace_sleep("sleep_request_started", reason="sleep_request_running")
            self._publish()
            # CLOCK_MONOTONIC excludes suspend. Once trusted PrepareForSleep is
            # received, request acceptance and waiting for the user are separate.
            while self._sleep_cycle is cycle and not request.done():
                if cycle.started:
                    request.add_done_callback(
                        lambda task: self._sleep_request_done(task, cycle)
                    )
                    return True
                if self._clock() >= cycle.deadline:
                    self._finish_sleep(CheckState.UNTESTED, "request_unavailable")
                    return False
                await asyncio.sleep(self._poll_interval)
            if request.done():
                await request
                self._trace_sleep("sleep_request_finished")
            return (
                self._sleep_cycle is cycle or self._sleep.state is CheckState.CONFIRMED
            )
        except asyncio.CancelledError:
            if (
                self._closed
                or revision != self._sleep_cancel_revision
                or (context is not None and self._sleep_context != context)
            ):
                return self._sleep.state is CheckState.CONFIRMED
            self._finish_sleep(CheckState.UNTESTED, "cancelled")
            raise
        except Exception as error:
            if (
                not self._closed
                and revision == self._sleep_cancel_revision
                and (context is None or context == self._sleep_context)
            ):
                if self._sleep.state is not CheckState.PROBLEM:
                    self._finish_sleep(
                        CheckState.UNTESTED,
                        str(error)
                        if isinstance(error, ScreenLockUnavailable)
                        else "request_unavailable",
                    )
            return False
        finally:
            self._sleep_preparation_task = None
            self._sleep_starting = False
            self._publish()

    def _sleep_request_done(self, task: asyncio.Task[None], cycle: _SleepCycle) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if self._sleep_request_task is task:
            self._sleep_request_task = None
        if self._closed or self._sleep_cycle is not cycle:
            return
        if error is not None and not cycle.started:
            self._finish_sleep(
                CheckState.UNTESTED,
                str(error)
                if isinstance(error, ScreenLockUnavailable)
                else "request_unavailable",
            )
        else:
            self._trace_sleep("sleep_request_finished")

    def normal_reaction(
        self,
        mechanism: Literal["screen", "sleep"],
        context: ObserverContext | None,
        application_session: int,
        was_open: bool,
    ) -> None:
        """Record only the ordinary trusted watcher reaction, after its sync seal."""
        if self._closed:
            return
        state = self._state()
        if mechanism == "screen":
            cycle = self._sleep_cycle
            if (
                was_open
                and cycle is not None
                and cycle.origin == "manual"
                and not cycle.started
                and context is not None
                and context == self._screen_context
                and context.platform == cycle.context.platform
                and context.session_id == cycle.context.session_id
                and cycle.context == self._sleep_context
                and application_session == cycle.application_session
                and state is not None
                and state.revoked
            ):
                # Some desktops lock before logind broadcasts PrepareForSleep.
                # Only the ordinary trusted handler for this open trial can
                # supply this chain. A caller merely displaying PIN cannot.
                cycle.presealed_generation = state.application_session
                cycle.presealed_screen_context = context
                cycle.pin_seen |= state.sealed_pin
            if not was_open:
                return
            trial = self._trial
            if (
                trial is None
                or context != trial.context
                or context != self._screen_context
                or application_session != trial.application_session
            ):
                return
            trial.normal_receipt = state is not None and state.revoked
            trial.pin_seen |= state is not None and state.sealed_pin
            self._trace("normal_reaction")
            if trial.locked_at is not None and not trial.normal_receipt:
                self._finish_screen(CheckState.PROBLEM, "normal_seal_failed")
                self._emergency()
            self._complete_screen_if_ready(trial)
        elif (
            mechanism == "sleep"
            and context is not None
            and context == self._sleep_context
        ):
            cycle = self._sleep_cycle
            if cycle is None:
                if not was_open:
                    return
                cycle = _SleepCycle(
                    context,
                    self._clock() + self._unlock_timeout,
                    application_session=application_session,
                )
                self._sleep_cycle = cycle
            else:
                original_open = (
                    was_open and cycle.application_session == application_session
                )
                normal_preseal = (
                    not was_open
                    and cycle.presealed_generation == application_session
                    and cycle.presealed_screen_context is not None
                    and cycle.presealed_screen_context == self._screen_context
                    and state is not None
                    and state.revoked
                )
                if cycle.context != context or not (original_open or normal_preseal):
                    return
            # PrepareForSleep can still be followed by cancellation/inhibition.
            # A missing seal is a definitive FAIL only once actual suspend is proven.
            cycle.started = True
            cycle.normal_receipt = state is not None and state.revoked
            cycle.pin_seen |= state is not None and state.sealed_pin
            if not cycle.normal_receipt:
                self._emergency()
            cycle.deadline = self._clock() + self._unlock_timeout
            self._sleep = CheckResult(CheckState.RUNNING, "sleep_cycle_running")
            self._trace_sleep("sleep_normal_reaction")
            if self._sleep_task is None or self._sleep_task.done():
                self._sleep_task = asyncio.create_task(self._monitor_sleep())
            self._publish()

    def _locked_screen(self, trial: _ScreenTrial) -> None:
        if trial.locked_at is None:
            trial.locked_at = self._clock()
            trial.deadline = self._clock() + self._unlock_timeout
        self._trace("screen_locked")

    def observe_screen_transition(
        self,
        context: ObserverContext | None,
        locked: bool,
        *,
        test_id: int | None = None,
    ) -> None:
        """Consume scoped attested transitions, including cycles faster than polling.

        The adapter emits locked only for its verified platform lock contract.
        A generic screensaver active signal is not this evidence channel.
        """
        trial = self._trial
        if (
            self._closed
            or trial is None
            or context != trial.context
            or context != self._screen_context
        ):
            return
        if test_id is not None and test_id != trial.identifier:
            return
        if trial.tagged_events and test_id != trial.identifier:
            return
        if locked:
            self._locked_screen(trial)
        elif trial.locked_at is not None:
            trial.unlocked = True
            trial.deadline = self._clock() + self._pin_timeout
            self._trace("screen_inactive")
        self._complete_screen_if_ready(trial)

    def _complete_screen_if_ready(self, trial: _ScreenTrial) -> None:
        if self._trial is not trial:
            return
        state = self._state()
        if state is not None and state.sealed_pin:
            trial.pin_seen = True
        if not trial.unlocked:
            return
        # A readback may beat the dispatch of the ordinary observer callback.
        # Give that callback the same short bounded grace as the locked phase.
        reaction_pending = (
            not trial.normal_receipt
            and trial.locked_at is not None
            and self._clock() - trial.locked_at < self._reaction_grace
        )
        if reaction_pending:
            return
        if state is None:
            self._finish_screen(CheckState.UNTESTED, "app_state_unavailable")
            self._emergency()
        elif not state.revoked and not (trial.normal_receipt and trial.pin_seen):
            self._finish_screen(CheckState.PROBLEM, "normal_seal_failed")
            self._emergency()
        elif trial.normal_receipt and trial.pin_seen:
            self._finish_screen(CheckState.CONFIRMED, "screen_confirmed")
        elif not trial.normal_receipt:
            self._finish_screen(CheckState.UNTESTED, "normal_reaction_unproven")

    async def _monitor_screen(
        self, adapter: ScreenLockAdapter, trial: _ScreenTrial
    ) -> None:
        try:
            while not self._closed and self._trial is trial:
                if (
                    trial.context != self._screen_context
                    or adapter.screen_context != trial.context
                ):
                    self._finish_screen(CheckState.UNTESTED, "observer_changed")
                    return
                if self._clock() >= trial.deadline:
                    code = (
                        "pin_timeout"
                        if trial.unlocked
                        else "unlock_timeout"
                        if trial.locked_at is not None
                        else "timeout"
                    )
                    self._finish_screen(CheckState.UNTESTED, code)
                    return
                reading = await asyncio.wait_for(
                    adapter.read_screen_state(trial.context), self._request_timeout
                )
                if self._trial is not trial:
                    return
                if reading.context != trial.context:
                    self._finish_screen(CheckState.UNTESTED, "observer_changed")
                    return
                state = self._state()
                if reading.locked is True:
                    if trial.locked_at is None:
                        self._locked_screen(trial)
                    assert trial.locked_at is not None
                    if state is None:
                        self._finish_screen(
                            CheckState.UNTESTED, "app_state_unavailable"
                        )
                        self._emergency()
                        return
                    if not state.revoked and (
                        trial.normal_receipt
                        or self._clock() - trial.locked_at >= self._reaction_grace
                    ):
                        self._finish_screen(CheckState.PROBLEM, "normal_seal_failed")
                        self._emergency()
                        return
                elif reading.locked is None:
                    trial.ambiguous_seen = True
                elif reading.locked is False and trial.locked_at is not None:
                    if not trial.unlocked:
                        trial.unlocked = True
                        trial.deadline = self._clock() + self._pin_timeout
                    self._complete_screen_if_ready(trial)
                    if self._trial is not trial:
                        return
                elif (
                    reading.locked is False
                    and trial.ambiguous_seen
                    and trial.request_complete
                ):
                    self._finish_screen(CheckState.UNTESTED, "locked_state_unproven")
                    return
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._trial is trial:
                self._finish_screen(CheckState.UNTESTED, "observation_unavailable")

    def observe_sleep_resume(
        self,
        context: ObserverContext | None,
        suspended: bool,
        *,
        test_id: int | None = None,
    ) -> None:
        cycle = self._sleep_cycle
        if cycle is not None and context == cycle.context == self._sleep_context:
            if cycle.identifier is not None and test_id != cycle.identifier:
                return
            if cycle.identifier is None and test_id is not None:
                return
            if not cycle.started:
                return
            cycle.resumed = True
            cycle.actual_suspend = suspended
            cycle.deadline = self._clock() + self._pin_timeout
            self._trace_sleep("sleep_resume")
            self.app_state_changed()

    def app_state_changed(self) -> None:
        if self._trial is not None:
            self._trace("app_state")
            self._complete_screen_if_ready(self._trial)
        cycle = self._sleep_cycle
        if self._closed or cycle is None:
            return
        state = self._state()
        if state is not None and state.sealed_pin:
            cycle.pin_seen = True
        if not cycle.resumed:
            return
        if not cycle.actual_suspend:
            self._finish_sleep(CheckState.UNTESTED, "actual_suspend_unproven")
        elif state is None:
            self._finish_sleep(CheckState.UNTESTED, "app_state_unavailable")
            self._emergency()
        elif not cycle.normal_receipt or (not state.revoked and not cycle.pin_seen):
            self._finish_sleep(CheckState.PROBLEM, "normal_seal_failed")
            self._emergency()
        elif state.sealed_pin or cycle.pin_seen:
            self._finish_sleep(CheckState.CONFIRMED, "sleep_confirmed")

    async def _monitor_sleep(self) -> None:
        cycle = self._sleep_cycle
        try:
            while not self._closed and cycle is self._sleep_cycle:
                if cycle is None:
                    return
                if cycle.context != self._sleep_context:
                    self._finish_sleep(CheckState.UNTESTED, "observer_changed")
                    return
                self.app_state_changed()
                if self._sleep_cycle is not cycle:
                    return
                if self._clock() >= cycle.deadline:
                    self._finish_sleep(
                        CheckState.UNTESTED,
                        "pin_timeout" if cycle.resumed else "timeout",
                    )
                    return
                await asyncio.sleep(self._poll_interval)
        except asyncio.CancelledError:
            raise

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        tasks: list[asyncio.Task] = [
            t
            for t in (
                self._screen_task,
                self._sleep_task,
                self._request_task,
                self._preparation_task,
                self._sleep_request_task,
                self._sleep_preparation_task,
            )
            if t is not None and t is not _current_task()
        ]
        self._trial = None
        self._unbind_sleep_trial()
        self._sleep_cycle = None
        self._screen_context = self._sleep_context = None
        self._screen = self._sleep = CheckResult(CheckState.UNTESTED, "closed")
        self._starting = False
        self._sleep_starting = False
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._screen_task = self._sleep_task = None
        self._request_task = None
        self._preparation_task = None
        self._sleep_request_task = None
        self._sleep_preparation_task = None
        self._publish()
