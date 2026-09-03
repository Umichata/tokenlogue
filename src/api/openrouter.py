"""Асинхронная проверка пользовательского ключа OpenRouter."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

import httpx

OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"


class KeyValidationStatus(str, Enum):
    """Безопасные результаты проверки ключа без данных запроса."""

    ACCEPTED = "accepted"
    ACCEPTED_WITHOUT_LIMIT = "accepted_without_limit"
    ACCEPTED_LIMIT_EXHAUSTED = "accepted_limit_exhausted"
    INVALID = "invalid"
    RESTRICTED = "restricted"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    TLS_ERROR = "tls_error"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    UNEXPECTED_STATUS = "unexpected_status"


@dataclass(frozen=True)
class KeyValidationResult:
    """Результат проверки ключа, пригодный для передачи в интерфейс."""

    status: KeyValidationStatus
    limit_remaining: Decimal | None = None

    @property
    def accepted(self) -> bool:
        """Возвращает True, если ключ разрешено сохранить после создания PIN."""
        return self.status in {
            KeyValidationStatus.ACCEPTED,
            KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT,
            KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
        }


class OpenRouterClient:
    """Проверяет ключ через пользовательский endpoint OpenRouter."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout | float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        """Проверяет ключ без сохранения и без раскрытия сетевых исключений."""
        normalized_key = api_key.strip()
        if not normalized_key:
            return KeyValidationResult(KeyValidationStatus.INVALID)

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    OPENROUTER_KEY_URL,
                    headers={"Authorization": f"Bearer {normalized_key}"},
                )
        except httpx.TimeoutException:
            return KeyValidationResult(KeyValidationStatus.TIMEOUT)
        except httpx.ConnectError as error:
            status = (
                KeyValidationStatus.TLS_ERROR
                if _contains_tls_error(error)
                else KeyValidationStatus.NETWORK_ERROR
            )
            return KeyValidationResult(status)
        except httpx.NetworkError:
            return KeyValidationResult(KeyValidationStatus.NETWORK_ERROR)
        except httpx.HTTPError:
            return KeyValidationResult(KeyValidationStatus.NETWORK_ERROR)
        except ImportError:
            return KeyValidationResult(KeyValidationStatus.NETWORK_ERROR)

        if response.status_code == 401:
            return KeyValidationResult(KeyValidationStatus.INVALID)
        if response.status_code == 403:
            return KeyValidationResult(KeyValidationStatus.RESTRICTED)
        if response.status_code == 429:
            return KeyValidationResult(KeyValidationStatus.RATE_LIMITED)
        if 500 <= response.status_code <= 599:
            return KeyValidationResult(KeyValidationStatus.SERVER_ERROR)
        if response.status_code != 200:
            return KeyValidationResult(KeyValidationStatus.UNEXPECTED_STATUS)

        return _parse_key_response(response.content)


def _parse_key_response(content: bytes) -> KeyValidationResult:
    """Разбирает денежные значения как Decimal без float-арифметики."""
    try:
        payload = json.loads(
            content,
            parse_float=Decimal,
            parse_int=Decimal,
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return KeyValidationResult(KeyValidationStatus.INVALID_RESPONSE)

    if not isinstance(payload, dict):
        return KeyValidationResult(KeyValidationStatus.INVALID_RESPONSE)

    data = payload.get("data")
    if not isinstance(data, dict) or "limit_remaining" not in data:
        return KeyValidationResult(KeyValidationStatus.INVALID_RESPONSE)

    raw_limit = data["limit_remaining"]
    if raw_limit is None:
        return KeyValidationResult(KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT)

    limit = _as_decimal(raw_limit)
    if limit is None:
        return KeyValidationResult(KeyValidationStatus.INVALID_RESPONSE)
    if limit <= Decimal("0"):
        return KeyValidationResult(
            KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
            limit_remaining=limit,
        )
    return KeyValidationResult(
        KeyValidationStatus.ACCEPTED,
        limit_remaining=limit,
    )


def _as_decimal(value: Any) -> Decimal | None:
    """Преобразует поддерживаемое числовое значение в конечный Decimal."""
    if isinstance(value, bool):
        return None

    try:
        if isinstance(value, Decimal):
            number = value
        elif isinstance(value, int):
            number = Decimal(value)
        elif isinstance(value, str):
            number = Decimal(value.strip())
        else:
            return None
    except (InvalidOperation, ValueError):
        return None

    return number if number.is_finite() else None


def _contains_tls_error(error: BaseException) -> bool:
    """Определяет TLS-причину без преобразования исключения в строку."""
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, ssl.SSLError):
            return True
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return False
