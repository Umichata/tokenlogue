"""Централизованные правила доступа к бесплатному и платному режимам."""

from __future__ import annotations

from auth.models import KeyLimitInfo, KeyValidityState
from providers.models import ProviderId


def free_mode_allowed(key_validity: KeyValidityState) -> bool:
    """INVALID запрещает новые модельные запросы; остальные состояния — нет."""
    return key_validity in {
        KeyValidityState.UNKNOWN,
        KeyValidityState.VALID,
        KeyValidityState.RESTRICTED,
        KeyValidityState.UNVERIFIED,
    }


def paid_mode_allowed(
    key_validity: KeyValidityState,
    key_limit: KeyLimitInfo,
    provider_id: ProviderId = ProviderId.OPENROUTER,
) -> bool:
    """Paid требует подтверждённой валидности и подходящего лимита ключа."""
    if provider_id is ProviderId.VSEGPT:
        return key_validity in {KeyValidityState.VALID, KeyValidityState.UNVERIFIED}
    return key_validity is KeyValidityState.VALID and key_limit.paid_mode_allowed
