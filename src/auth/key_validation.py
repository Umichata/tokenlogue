"""Преобразование сетевого результата в два независимых состояния сессии."""

from __future__ import annotations

from api.openrouter import KeyValidationResult, KeyValidationStatus
from auth.models import KeyLimitInfo, KeyValidityState


def interpret_key_validation(
    validation: KeyValidationResult,
) -> tuple[KeyValidityState, KeyLimitInfo]:
    """Не использует состояние лимита для представления сетевых ошибок."""
    if validation.status is KeyValidationStatus.INVALID:
        return KeyValidityState.INVALID, KeyLimitInfo.unknown()
    if validation.status is KeyValidationStatus.RESTRICTED:
        return KeyValidityState.RESTRICTED, KeyLimitInfo.unknown()
    if not validation.accepted:
        return KeyValidityState.UNKNOWN, KeyLimitInfo.unknown()

    if validation.status is KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT:
        if validation.limit_remaining is None:
            return (
                KeyValidityState.VALID,
                KeyLimitInfo.from_validated_remaining(None),
            )
        return KeyValidityState.UNKNOWN, KeyLimitInfo.unknown()

    remaining = validation.limit_remaining
    if remaining is None or not remaining.is_finite():
        return KeyValidityState.UNKNOWN, KeyLimitInfo.unknown()
    if validation.status is KeyValidationStatus.ACCEPTED and remaining > 0:
        return (
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(remaining),
        )
    if (
        validation.status is KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED
        and remaining <= 0
    ):
        return (
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(remaining),
        )
    return KeyValidityState.UNKNOWN, KeyLimitInfo.unknown()
