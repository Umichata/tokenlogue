"""Короткие подписи независимых результатов экрана и сна."""

from datetime import datetime
from typing import Literal

from i18n import tr
from platform_security.local_protection import (
    CheckResult,
    CheckState,
    ProtectionSnapshot,
)

_SCREEN_REASON_MESSAGES = {
    "screen_test_preparing": "preparing",
    "preparation_timeout": "preparation_timeout",
    "activation_unavailable": "preparation_unavailable",
    "activation_untrusted": "preparation_unavailable",
    "locker_contract_unavailable": "locker_unconfirmed",
    "already_locked_or_unconfirmed": "already_locked",
    "observation_unavailable": "observation_unavailable",
    "request_unavailable": "request_unavailable",
    "timeout": "lock_timeout",
    "unlock_timeout": "unlock_timeout",
    "pin_timeout": "pin_unconfirmed",
    "normal_reaction_unproven": "normal_unconfirmed",
    "locked_state_unproven": "locker_unconfirmed",
    "observer_changed": "observer_changed_notice",
    "windows_port_required": "unsupported_notice",
    "contract_changed": "contract_changed",
}


def untested_protection(system_events: bool, screen_events: bool) -> ProtectionSnapshot:
    return ProtectionSnapshot(
        CheckResult(), CheckResult(), screen_events, system_events, False
    )


def mechanism_ready(
    snapshot: ProtectionSnapshot, mechanism: Literal["screen", "sleep"]
) -> bool:
    connected = (
        snapshot.screen_connected if mechanism == "screen" else snapshot.sleep_connected
    )
    stale = snapshot.screen_stale if mechanism == "screen" else snapshot.sleep_stale
    return connected and not stale


def mechanism_monitor_notice(
    snapshot: ProtectionSnapshot, mechanism: Literal["screen", "sleep"]
) -> str:
    if mechanism_ready(snapshot, mechanism):
        state = "available"
    else:
        history = (
            snapshot.screen_history if mechanism == "screen" else snapshot.sleep_history
        )
        result = snapshot.screen if mechanism == "screen" else snapshot.sleep
        state = (
            "warning"
            if history is not None or result.state is CheckState.CONFIRMED
            else "unavailable"
        )
    return tr("local_protection." + mechanism + "_monitor_" + state)


def protection_ready(snapshot: ProtectionSnapshot) -> bool:
    """Past evidence alone never claims a disconnected watcher is protecting now."""
    if (
        snapshot.has_problem
        or snapshot.persistence_error
        or snapshot.test_running
        or snapshot.screen_stale
        or snapshot.sleep_stale
    ):
        return False
    confirmed = []
    for name in ("screen", "sleep"):
        result = snapshot.screen if name == "screen" else snapshot.sleep
        if result.state is CheckState.CONFIRMED:
            confirmed.append(mechanism_ready(snapshot, name))
    return bool(confirmed) and all(confirmed)


def protection_label(snapshot: ProtectionSnapshot) -> str:
    if snapshot.has_problem:
        return tr("local_protection.problem_short")
    if snapshot.test_running:
        if snapshot.sleep_test_running:
            return tr("local_protection.sleep_running")
        return tr(
            "local_protection.preparing"
            if snapshot.screen_attempt.code == "screen_test_preparing"
            else "local_protection.running"
        )
    if snapshot.persistence_error:
        return tr("local_protection.save_failed_short")
    if snapshot.screen_stale or snapshot.sleep_stale:
        return tr("local_protection.check_required_short")
    if (
        snapshot.screen.state is CheckState.CONFIRMED
        and not mechanism_ready(snapshot, "screen")
    ) or (
        snapshot.sleep.state is CheckState.CONFIRMED
        and not mechanism_ready(snapshot, "sleep")
    ):
        return tr("local_protection.monitor_not_ready_short")
    if snapshot.screen.state is CheckState.CONFIRMED:
        return tr(
            "local_protection.both_confirmed"
            if snapshot.sleep.state is CheckState.CONFIRMED
            else "local_protection.screen_confirmed"
        )
    if snapshot.sleep.state is CheckState.CONFIRMED:
        return tr("local_protection.sleep_confirmed")
    return tr("local_protection.screen_untested")


def _attempt_notice(mechanism: Literal["screen", "sleep"], result: CheckResult) -> str:
    if mechanism == "sleep":
        messages = {
            "sleep_test_preparing": "sleep_preparing",
            "sleep_request_unavailable": "sleep_request_unavailable",
            "sleep_request_running": "sleep_running",
            "sleep_unavailable": "sleep_not_supported",
            "sleep_permission_required": "sleep_permission_denied",
            "sleep_not_supported": "sleep_not_supported",
            "sleep_permission_denied": "sleep_permission_denied",
            "sleep_inhibited": "sleep_inhibited",
            "actual_suspend_unproven": "sleep_unproven",
            "normal_reaction_unproven": "normal_unconfirmed",
            "pin_timeout": "sleep_pin_unconfirmed",
            "timeout": "sleep_timeout",
            "request_unavailable": "sleep_request_unavailable",
            "preparation_timeout": "sleep_preparation_timeout",
            "observer_changed": "sleep_observer_changed",
            "contract_changed": "contract_changed",
            "cancelled": "attempt_cancelled",
        }
        key = messages.get(result.code, "unconfirmed_notice")
    else:
        key = _SCREEN_REASON_MESSAGES.get(result.code, "unconfirmed_notice")
    return tr("local_protection." + key)


def protection_notice(snapshot: ProtectionSnapshot) -> str:
    if snapshot.has_problem:
        return tr("local_protection.problem_notice")
    pieces = []
    if CheckState.CONFIRMED in {snapshot.screen.state, snapshot.sleep.state}:
        pieces.append(
            tr(
                "local_protection.confirmed_with_sleep",
                screen=mechanism_label("screen", snapshot.screen),
                sleep=mechanism_label("sleep", snapshot.sleep),
            )
        )
        for mechanism in ("screen", "sleep"):
            result = snapshot.screen if mechanism == "screen" else snapshot.sleep
            if result.state is CheckState.CONFIRMED and not mechanism_ready(
                snapshot, mechanism
            ):
                pieces.append(tr("local_protection." + mechanism + "_monitor_warning"))
    elif snapshot.test_running:
        pieces.append(protection_label(snapshot))
    elif snapshot.screen.code != "not_checked":
        pieces.append(_attempt_notice("screen", snapshot.screen))
    else:
        pieces.append(
            tr(
                "local_protection.untested_notice"
                if snapshot.screen_connected
                else "local_protection.unavailable_notice"
            )
        )
    if snapshot.persistence_error:
        pieces.append(tr("local_protection.save_failed"))
    return " ".join(pieces)


def mechanism_label(mechanism: str, result: CheckResult) -> str:
    return tr("local_protection." + mechanism + "_" + result.state.value)


def _check_time(timestamp: int) -> str | None:
    try:
        return (
            datetime.fromtimestamp(timestamp).astimezone().strftime("%Y-%m-%d %H:%M %Z")
        )
    except (ValueError, OSError, OverflowError):
        # Stored metadata must never prevent the PIN or protection UI rendering.
        return None


def previous_result_label(
    snapshot: ProtectionSnapshot, mechanism: Literal["screen", "sleep"]
) -> str | None:
    history = (
        snapshot.screen_history if mechanism == "screen" else snapshot.sleep_history
    )
    stale = snapshot.screen_stale if mechanism == "screen" else snapshot.sleep_stale
    if history is None or not stale:
        return None
    return tr(
        "local_protection.previous_result",
        result=mechanism_label(mechanism, CheckResult(history.state)),
    )


def mechanism_details(
    snapshot: ProtectionSnapshot, mechanism: Literal["screen", "sleep"]
) -> list[str]:
    """Small public metadata only, kept separate from present watcher readiness."""
    history = (
        snapshot.screen_history if mechanism == "screen" else snapshot.sleep_history
    )
    attempt = (
        snapshot.screen_attempt if mechanism == "screen" else snapshot.sleep_attempt
    )
    stale = snapshot.screen_stale if mechanism == "screen" else snapshot.sleep_stale
    lines = []
    if history is not None:
        checked = _check_time(history.checked_at)
        lines.append(
            tr("local_protection.checked_at", time=checked)
            if checked is not None
            else tr("local_protection.check_time_unavailable")
        )
        if previous := previous_result_label(snapshot, mechanism):
            lines.append(previous)
        if history.origin == "observed":
            lines.append(tr("local_protection." + mechanism + "_observed"))
        if history.state is CheckState.PROBLEM and history.last_success_at is not None:
            success = _check_time(history.last_success_at)
            lines.append(
                tr("local_protection.last_success_at", time=success)
                if success is not None
                else tr("local_protection.success_time_unavailable")
            )
    if stale:
        lines.append(tr("local_protection.contract_changed"))
    if attempt.state is CheckState.RUNNING:
        lines.append(_attempt_notice(mechanism, attempt))
    elif attempt.state is CheckState.UNTESTED and attempt.code not in {
        "not_checked",
        "closed",
    }:
        lines.append(tr("local_protection.attempt_unconfirmed"))
        lines.append(_attempt_notice(mechanism, attempt))
    return lines


def session_watch_details(system_events: bool, screen_events: bool) -> str:
    # Connection availability alone is never a confirmed protection result.
    return protection_notice(untested_protection(system_events, screen_events))
