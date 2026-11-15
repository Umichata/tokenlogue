"""VSEGPT balance/auth adapter; public models never validate a credential.

Contract evidence: https://vsegpt.ru/Docs/API/Code (balance settings opt-in,
string credits, separate subscription and user warning states).
"""

from __future__ import annotations

import json
from decimal import Decimal, DecimalException

import httpx

from api.openrouter import (
    CreditsResult,
    CreditsStatus,
    KeyValidationResult,
    KeyValidationStatus,
    _as_decimal,
    _contains_tls_error,
    _reject_json_constant,
)
from providers.models import Currency, ProviderId, detect_key

VSEGPT_BALANCE_URL = "https://api.vsegpt.ru/v1/balance"


class VsegptClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout | float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def get_credits(self, api_key: str) -> CreditsResult:
        if detect_key(api_key) is not ProviderId.VSEGPT:
            return _balance_result(CreditsStatus.UNAUTHORIZED)
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    VSEGPT_BALANCE_URL,
                    headers={"Authorization": f"Bearer {api_key.strip()}"},
                )
        except httpx.TimeoutException:
            return _balance_result(CreditsStatus.TIMEOUT)
        except httpx.ConnectError as error:
            return _balance_result(
                CreditsStatus.TLS_ERROR
                if _contains_tls_error(error)
                else CreditsStatus.NETWORK_ERROR
            )
        except (httpx.HTTPError, ImportError, ValueError):
            return _balance_result(CreditsStatus.NETWORK_ERROR)
        status = {
            401: CreditsStatus.UNAUTHORIZED,
            403: CreditsStatus.BALANCE_DISABLED,
            429: CreditsStatus.RATE_LIMITED,
        }.get(response.status_code)
        if status is not None:
            return _balance_result(status)
        if response.status_code >= 500:
            return _balance_result(CreditsStatus.SERVER_ERROR)
        if response.status_code != 200:
            if _known_invalid_key(response.content):
                return _balance_result(CreditsStatus.UNAUTHORIZED)
            return _balance_result(CreditsStatus.UNEXPECTED_STATUS)
        return _parse_balance(response.content)

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        """Only a successful authenticated balance read confirms authorization."""
        result = await self.get_credits(api_key)
        if result.status in {
            CreditsStatus.SUCCESS,
            CreditsStatus.SUBSCRIPTION_REQUIRED,
            CreditsStatus.INSUFFICIENT_FUNDS,
            CreditsStatus.ACCOUNT_DISABLED,
        }:
            return KeyValidationResult(
                KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT,
                provider_id=ProviderId.VSEGPT,
                warning=result.warning or result.status is not CreditsStatus.SUCCESS,
                subscription_active=result.subscription_active,
            )
        mapping = {
            CreditsStatus.UNAUTHORIZED: KeyValidationStatus.INVALID,
            CreditsStatus.BALANCE_DISABLED: KeyValidationStatus.UNVERIFIED,
            CreditsStatus.RESTRICTED: KeyValidationStatus.UNVERIFIED,
            CreditsStatus.TIMEOUT: KeyValidationStatus.TIMEOUT,
            CreditsStatus.NETWORK_ERROR: KeyValidationStatus.NETWORK_ERROR,
            CreditsStatus.TLS_ERROR: KeyValidationStatus.TLS_ERROR,
            CreditsStatus.RATE_LIMITED: KeyValidationStatus.RATE_LIMITED,
            CreditsStatus.SERVER_ERROR: KeyValidationStatus.SERVER_ERROR,
            CreditsStatus.INVALID_RESPONSE: KeyValidationStatus.INVALID_RESPONSE,
        }
        return KeyValidationResult(
            mapping.get(result.status, KeyValidationStatus.UNEXPECTED_STATUS),
            provider_id=ProviderId.VSEGPT,
        )


def _balance_result(status: CreditsStatus) -> CreditsResult:
    return CreditsResult(status, currency=Currency.RUB, provider_id=ProviderId.VSEGPT)


def _parse_balance(content: bytes) -> CreditsResult:
    try:
        payload = json.loads(
            content,
            parse_float=Decimal,
            parse_int=Decimal,
            parse_constant=_reject_json_constant,
        )
    except (ValueError, UnicodeDecodeError, DecimalException, RecursionError):
        return _balance_result(CreditsStatus.INVALID_RESPONSE)
    if not isinstance(payload, dict):
        return _balance_result(CreditsStatus.INVALID_RESPONSE)
    if payload.get("status") != "ok":
        if _known_invalid_key(content):
            return _balance_result(CreditsStatus.UNAUTHORIZED)
        # The documented endpoint can be disabled in account settings. An
        # application-level refusal cannot establish invalid authentication.
        return _balance_result(CreditsStatus.RESTRICTED)
    data = payload.get("data")
    if not isinstance(data, dict):
        return _balance_result(CreditsStatus.INVALID_RESPONSE)
    balance = _as_decimal(data.get("credits"))
    subscription = data.get("subscription_status")
    user_status = data.get("user_status")
    if (
        balance is None
        or not isinstance(subscription, str)
        or isinstance(user_status, bool)
        or user_status not in (0, 1, 2)
    ):
        return _balance_result(CreditsStatus.INVALID_RESPONSE)
    active = subscription == "ok"
    if not active:
        status = CreditsStatus.SUBSCRIPTION_REQUIRED
    elif user_status == 2:
        status = (
            CreditsStatus.INSUFFICIENT_FUNDS
            if balance <= 0
            else CreditsStatus.ACCOUNT_DISABLED
        )
    else:
        status = CreditsStatus.SUCCESS
    return CreditsResult(
        status,
        balance_amount=balance,
        currency=Currency.RUB,
        provider_id=ProviderId.VSEGPT,
        warning=user_status == 1,
        subscription_active=active,
    )


def _known_invalid_key(content: bytes) -> bool:
    """The official error guide documents invalid credentials under HTTP 400."""
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    if not isinstance(message, str):
        return False
    lowered = message.lower()
    return "api key" in lowered and (
        "not found" in lowered or "original openai" in lowered
    )
