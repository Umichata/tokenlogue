"""Нестриминговый клиент OpenRouter Chat Completions без UI-зависимостей."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from math import ceil
from typing import Any

import httpx

from api.openrouter import _contains_tls_error
from chat.context import ContextMessage
from chat.errors import ChatErrorType
from chat.models import ProviderPriceLimit
from providers.models import Currency, ProviderId, detect_key, provider_spec

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
VSEGPT_CHAT_URL = "https://api.vsegpt.ru/v1/chat/completions"
DEFAULT_CHAT_TIMEOUT = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)
MAX_RETRY_AFTER_SECONDS = 86_400
TOKENS_PER_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str | None = field(repr=False)
    generation_id: str | None = field(repr=False)
    requested_model_id: str
    actual_model_id: str | None
    finish_reason: str | None = field(repr=False)
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: Decimal | None
    error_type: ChatErrorType | None
    retry_after: int | None = None
    accounting_unknown: bool = False
    provider_id: ProviderId = ProviderId.OPENROUTER
    currency: Currency = Currency.USD
    cost_amount: Decimal | None = None
    usage_source: str = "unknown"
    cost_source: str = "unknown"
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.currency is Currency.USD and self.cost_amount is None:
            object.__setattr__(self, "cost_amount", self.cost_usd)
        if self.currency is not Currency.USD and self.cost_usd is not None:
            raise ValueError("USD amount requires USD currency")
        if self.usage_source == "unknown" and self.has_token_usage:
            object.__setattr__(self, "usage_source", "api")
        if self.cost_source == "unknown" and self.cost_amount is not None:
            object.__setattr__(self, "cost_source", "api")

    @property
    def successful(self) -> bool:
        return self.error_type is None and self.finish_reason in {"stop", "length"}

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length" and self.error_type is None

    @property
    def has_complete_usage(self) -> bool:
        return (
            self.prompt_tokens is not None
            and self.completion_tokens is not None
            and self.total_tokens is not None
            and self.cost_amount is not None
        )

    @property
    def has_token_usage(self) -> bool:
        return any(
            value is not None
            for value in (self.prompt_tokens, self.completion_tokens, self.total_tokens)
        )


class ChatCompletionsClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = DEFAULT_CHAT_TIMEOUT,
        provider_id: ProviderId = ProviderId.OPENROUTER,
    ) -> None:
        self._transport = transport
        self._timeout = timeout
        self.provider_id = ProviderId(provider_id)

    async def complete(
        self,
        api_key: str,
        requested_model_id: str,
        messages: tuple[ContextMessage, ...],
        max_completion_tokens: int,
        provider_price_limit: ProviderPriceLimit,
    ) -> ChatCompletionResult:
        result = await self._complete(
            api_key,
            requested_model_id,
            messages,
            max_completion_tokens,
            provider_price_limit,
        )
        return replace(
            result,
            provider_id=self.provider_id,
            currency=provider_spec(self.provider_id).currency,
            cost_usd=result.cost_usd
            if self.provider_id is ProviderId.OPENROUTER
            else None,
            cost_amount=result.cost_amount
            if self.provider_id is ProviderId.OPENROUTER
            else None,
            cost_source=(
                "api"
                if result.cost_usd is not None
                and self.provider_id is ProviderId.OPENROUTER
                else "unknown"
            ),
            accounting_unknown=(
                result.accounting_unknown
                or (
                    self.provider_id is ProviderId.VSEGPT
                    and (
                        result.successful
                        or result.has_token_usage
                        or result.cost_usd is not None
                    )
                )
            ),
        )

    async def _complete(
        self,
        api_key: str,
        requested_model_id: str,
        messages: tuple[ContextMessage, ...],
        max_completion_tokens: int,
        provider_price_limit: ProviderPriceLimit,
    ) -> ChatCompletionResult:
        normalized_key = api_key.strip()
        if detect_key(normalized_key) is not self.provider_id:
            return _error_result(
                requested_model_id,
                ChatErrorType.AUTHENTICATION,
                accounting_unknown=False,
            )
        if (
            not requested_model_id.strip()
            or max_completion_tokens < 16
            or not messages
            or not provider_price_limit.valid
        ):
            return _error_result(
                requested_model_id,
                ChatErrorType.INVALID_REQUEST,
                accounting_unknown=False,
            )
        payload: dict[str, Any] = {
            "model": requested_model_id,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in messages
            ],
            "stream": False,
        }
        if self.provider_id is ProviderId.OPENROUTER:
            payload["max_completion_tokens"] = max_completion_tokens
            payload["provider"] = {
                # Резервируется только провайдер того же единственного model.
                "allow_fallbacks": True,
                "max_price": _wire_max_price(provider_price_limit),
            }
        else:
            payload["max_tokens"] = max_completion_tokens
        try:
            encoded_payload = _encode_json(payload)
        except (TypeError, ValueError):
            return _error_result(
                requested_model_id,
                ChatErrorType.INVALID_REQUEST,
                accounting_unknown=False,
            )

        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.post(
                    provider_spec(self.provider_id).base_url + "/chat/completions",
                    content=encoded_payload,
                    headers={
                        "Authorization": f"Bearer {normalized_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException:
            return _error_result(
                requested_model_id,
                ChatErrorType.TIMEOUT,
                accounting_unknown=True,
            )
        except httpx.ConnectError as error:
            return _error_result(
                requested_model_id,
                ChatErrorType.TLS_ERROR
                if _contains_tls_error(error)
                else ChatErrorType.NETWORK_ERROR,
                accounting_unknown=True,
            )
        except httpx.HTTPError:
            return _error_result(
                requested_model_id,
                ChatErrorType.NETWORK_ERROR,
                accounting_unknown=True,
            )
        except ImportError:
            return _error_result(
                requested_model_id,
                ChatErrorType.NETWORK_ERROR,
                accounting_unknown=True,
            )

        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        content_type = response.headers.get("Content-Type", "")
        is_json = content_type.split(";", 1)[0].strip().lower() == "application/json"
        if not is_json:
            if response.status_code == 200:
                return _error_result(
                    requested_model_id,
                    ChatErrorType.MALFORMED_RESPONSE,
                    accounting_unknown=True,
                )
            return _error_result(
                requested_model_id,
                _http_error_type(response.status_code, None),
                retry_after=retry_after,
                accounting_unknown=_ambiguous_http_status(response.status_code),
            )

        response_payload = _decode_json(response.content)
        if response_payload is None:
            return _error_result(
                requested_model_id,
                (
                    ChatErrorType.MALFORMED_RESPONSE
                    if response.status_code == 200
                    else _http_error_type(response.status_code, None)
                ),
                retry_after=retry_after,
                accounting_unknown=(
                    response.status_code == 200
                    or _ambiguous_http_status(response.status_code)
                ),
            )
        if response.status_code != 200:
            return _parse_http_error(
                requested_model_id,
                response.status_code,
                response_payload,
                retry_after,
                provider_id=self.provider_id,
            )
        result = _parse_success_response(
            requested_model_id, response_payload, provider_id=self.provider_id
        )
        return (
            replace(result, retry_after=retry_after)
            if result.error_type is not None and retry_after is not None
            else result
        )


@dataclass(frozen=True)
class _Usage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost_usd: Decimal | None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None


def _parse_success_response(
    requested_model_id: str,
    payload: dict[str, Any],
    *,
    provider_id: ProviderId = ProviderId.OPENROUTER,
) -> ChatCompletionResult:
    usage = _parse_usage(payload.get("usage"))
    if payload.get("error") is not None:
        error_type = _provider_payload_error_type(
            payload.get("error"), 200, provider_id
        )
        return _result_with_usage(
            requested_model_id,
            error_type,
            usage,
            accounting_unknown=usage is None,
        )

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return _result_with_usage(
            requested_model_id,
            ChatErrorType.MALFORMED_RESPONSE,
            usage,
            accounting_unknown=usage is None,
        )
    choice = choices[0]
    if choice.get("error") is not None:
        return _result_with_usage(
            requested_model_id,
            _provider_payload_error_type(choice.get("error"), 200, provider_id),
            usage,
            accounting_unknown=usage is None,
        )
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    generation_id = payload.get("id")
    actual_model_id = payload.get("model")
    finish_reason = choice.get("finish_reason")
    if finish_reason in {"content_filter", "refusal"} and content is None:
        content = ""
    if (
        not isinstance(content, str)
        or not isinstance(generation_id, str)
        or not generation_id
        or not isinstance(actual_model_id, str)
        or not actual_model_id
        or not isinstance(finish_reason, str)
    ):
        return _result_with_usage(
            requested_model_id,
            ChatErrorType.MALFORMED_RESPONSE,
            usage,
            accounting_unknown=usage is None,
        )

    error_type: ChatErrorType | None
    if finish_reason in {"stop", "length"}:
        error_type = None
    elif finish_reason == "content_filter":
        error_type = ChatErrorType.CONTENT_POLICY_VIOLATION
    elif finish_reason == "refusal":
        error_type = ChatErrorType.REFUSAL
    elif finish_reason == "error":
        error_type = ChatErrorType.PROVIDER_UNAVAILABLE
    else:
        error_type = ChatErrorType.MALFORMED_RESPONSE
    return ChatCompletionResult(
        content=content,
        generation_id=generation_id,
        requested_model_id=requested_model_id,
        actual_model_id=actual_model_id,
        finish_reason=finish_reason,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        cost_usd=usage.cost_usd if usage else None,
        error_type=error_type,
        accounting_unknown=usage is None or usage.cost_usd is None,
        usage_source="api" if usage and _has_tokens(usage) else "unknown",
        cached_tokens=usage.cached_tokens if usage else None,
        reasoning_tokens=usage.reasoning_tokens if usage else None,
    )


def _parse_http_error(
    requested_model_id: str,
    status_code: int,
    payload: dict[str, Any],
    retry_after: int | None,
    *,
    provider_id: ProviderId = ProviderId.OPENROUTER,
) -> ChatCompletionResult:
    usage = _parse_usage(payload.get("usage"))
    error_type = _provider_payload_error_type(
        payload.get("error"), status_code, provider_id
    )
    return _result_with_usage(
        requested_model_id,
        error_type,
        usage,
        retry_after=retry_after,
        accounting_unknown=(usage is None and _ambiguous_http_status(status_code)),
    )


def _parse_usage(value: Any) -> _Usage | None:
    if not isinstance(value, dict):
        return None
    prompt_tokens = _parse_nonnegative_int(value.get("prompt_tokens"))
    completion_tokens = _parse_nonnegative_int(value.get("completion_tokens"))
    reported_total = _parse_nonnegative_int(value.get("total_tokens"))
    cost = _parse_nonnegative_decimal(value.get("cost"))
    if all(
        value is None
        for value in (prompt_tokens, completion_tokens, reported_total, cost)
    ):
        return None
    prompt_details = value.get("prompt_tokens_details")
    completion_details = value.get("completion_tokens_details")
    return _Usage(
        prompt_tokens,
        completion_tokens,
        reported_total,
        cost,
        _parse_nonnegative_int(prompt_details.get("cached_tokens"))
        if isinstance(prompt_details, dict)
        else None,
        _parse_nonnegative_int(completion_details.get("reasoning_tokens"))
        if isinstance(completion_details, dict)
        else None,
    )


def _has_tokens(usage: _Usage) -> bool:
    return any(
        value is not None
        for value in (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)
    )


def _payload_error_type(value: Any, status_code: int) -> ChatErrorType:
    code: str | None = None
    if isinstance(value, dict):
        raw_code = value.get("code")
        if isinstance(raw_code, str):
            code = raw_code.strip().lower()
        elif isinstance(raw_code, (int, Decimal)) and not isinstance(raw_code, bool):
            code = str(raw_code)
    code_mapping = {
        "invalid_request": ChatErrorType.INVALID_REQUEST,
        "authentication": ChatErrorType.AUTHENTICATION,
        "refusal": ChatErrorType.REFUSAL,
        "payment_required": ChatErrorType.PAYMENT_REQUIRED,
        "permission_denied": ChatErrorType.PERMISSION_DENIED,
        "content_policy_violation": ChatErrorType.CONTENT_POLICY_VIOLATION,
        "rate_limit_exceeded": ChatErrorType.RATE_LIMIT_EXCEEDED,
        "provider_unavailable": ChatErrorType.PROVIDER_UNAVAILABLE,
        "provider_overloaded": ChatErrorType.PROVIDER_OVERLOADED,
        "context_length_exceeded": ChatErrorType.CONTEXT_LENGTH_EXCEEDED,
        "max_tokens_exceeded": ChatErrorType.MAX_TOKENS_EXCEEDED,
        "token_limit_exceeded": ChatErrorType.TOKEN_LIMIT_EXCEEDED,
        "insufficient_quota": ChatErrorType.QUOTA_EXHAUSTED,
        "quota_exceeded": ChatErrorType.QUOTA_EXHAUSTED,
        "daily_quota_exceeded": ChatErrorType.QUOTA_EXHAUSTED,
        "key_limit_exceeded": ChatErrorType.KEY_LIMIT_EXCEEDED,
        "budget_exceeded": ChatErrorType.KEY_LIMIT_EXCEEDED,
        "model_not_found": ChatErrorType.MODEL_UNAVAILABLE,
        "no_available_endpoints": ChatErrorType.MODEL_UNAVAILABLE,
        "no_endpoints_found": ChatErrorType.MODEL_UNAVAILABLE,
        "timeout": ChatErrorType.TIMEOUT,
        "server": ChatErrorType.PROVIDER_UNAVAILABLE,
        "not_found": ChatErrorType.MODEL_UNAVAILABLE,
        "insufficient_credits": ChatErrorType.PAYMENT_REQUIRED,
    }
    if code in code_mapping:
        return code_mapping[code]
    if code is not None and code.isascii() and code.isdigit():
        return _http_error_type(int(code), code)
    return _http_error_type(status_code, code)


def _provider_payload_error_type(
    value: Any, status_code: int, provider_id: ProviderId
) -> ChatErrorType:
    if provider_id is ProviderId.OPENROUTER and isinstance(value, dict):
        # Structured fields only. Provider message/raw strings may contain
        # request fragments, so they are neither retained nor displayed.
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            for code in (402, 403, 429):
                if value.get("code") in (code, str(code)):
                    status_code = code
                    break
            limit_source = metadata.get("limit_source")
            if (
                status_code in {402, 403}
                and isinstance(limit_source, str)
                and limit_source
                in {
                    "key_limit",
                    "api_key",
                    "key_budget",
                    "guardrail",
                    "workspace",
                    "organization",
                    "member",
                    "workspace_default_member",
                    "workspace_default_key",
                    "openrouter_key_limit",
                    "openrouter_guardrail_budget",
                    "openrouter_workspace_budget",
                }
            ):
                return ChatErrorType.KEY_LIMIT_EXCEEDED
            error_type = metadata.get("error_type")
            if isinstance(error_type, str) and error_type in {
                "invalid_request",
                "authentication",
                "payment_required",
                "permission_denied",
                "content_policy_violation",
                "refusal",
                "rate_limit_exceeded",
                "provider_unavailable",
                "provider_overloaded",
                "context_length_exceeded",
                "max_tokens_exceeded",
                "token_limit_exceeded",
                "insufficient_quota",
                "quota_exceeded",
                "daily_quota_exceeded",
                "key_limit_exceeded",
                "budget_exceeded",
                "model_not_found",
                "no_available_endpoints",
                "no_endpoints_found",
                "timeout",
                "server",
                "not_found",
                "insufficient_credits",
            }:
                return _payload_error_type({"code": error_type}, status_code)
            limit_type = metadata.get("limit_type")
            if (
                status_code == 429
                and isinstance(limit_type, str)
                and limit_type
                in {
                    "free_model_daily_requests",
                    "daily_quota",
                    "daily_requests",
                }
            ):
                return ChatErrorType.QUOTA_EXHAUSTED
    if provider_id is ProviderId.VSEGPT:
        # VSEGPT's official /Docs/API/Errors documents several unrelated
        # failures as HTTP 400. Inspect only known categories and discard text.
        message = value.get("message") if isinstance(value, dict) else None
        if isinstance(message, str):
            lowered = message.lower()
            if "api key" in lowered and (
                "not found" in lowered or "original openai" in lowered
            ):
                return ChatErrorType.AUTHENTICATION
            if "out of budget" in lowered:
                return ChatErrorType.PAYMENT_REQUIRED
            if "subscription" in lowered and "not available" in lowered:
                return ChatErrorType.SUBSCRIPTION_REQUIRED
            if "soft user limit" in lowered:
                return ChatErrorType.KEY_LIMIT_EXCEEDED
            if "context length" in lowered or "maxTokens".lower() in lowered:
                return ChatErrorType.CONTEXT_LENGTH_EXCEEDED
        if status_code == 403:
            return ChatErrorType.CONTENT_POLICY_VIOLATION
    return _payload_error_type(value, status_code)


def _http_error_type(status_code: int, _code: str | None) -> ChatErrorType:
    if status_code == 400:
        return ChatErrorType.INVALID_REQUEST
    if status_code == 401:
        return ChatErrorType.AUTHENTICATION
    if status_code == 402:
        return ChatErrorType.PAYMENT_REQUIRED
    if status_code == 403:
        return ChatErrorType.PERMISSION_DENIED
    if status_code == 404:
        return ChatErrorType.MODEL_UNAVAILABLE
    if status_code in {408, 524}:
        return ChatErrorType.TIMEOUT
    if status_code == 429:
        return ChatErrorType.RATE_LIMIT_EXCEEDED
    if status_code in {502, 503}:
        return ChatErrorType.PROVIDER_UNAVAILABLE
    if status_code == 529:
        return ChatErrorType.PROVIDER_OVERLOADED
    return ChatErrorType.PROVIDER_UNAVAILABLE


def _result_with_usage(
    requested_model_id: str,
    error_type: ChatErrorType,
    usage: _Usage | None,
    *,
    retry_after: int | None = None,
    accounting_unknown: bool,
) -> ChatCompletionResult:
    return ChatCompletionResult(
        content=None,
        generation_id=None,
        requested_model_id=requested_model_id,
        actual_model_id=None,
        finish_reason=None,
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        total_tokens=usage.total_tokens if usage else None,
        cost_usd=usage.cost_usd if usage else None,
        error_type=error_type,
        retry_after=retry_after,
        accounting_unknown=(
            accounting_unknown or (usage is not None and usage.cost_usd is None)
        ),
        usage_source="api" if usage and _has_tokens(usage) else "unknown",
        cached_tokens=usage.cached_tokens if usage else None,
        reasoning_tokens=usage.reasoning_tokens if usage else None,
    )


def _error_result(
    requested_model_id: str,
    error_type: ChatErrorType,
    *,
    retry_after: int | None = None,
    accounting_unknown: bool,
) -> ChatCompletionResult:
    return _result_with_usage(
        requested_model_id,
        error_type,
        None,
        retry_after=retry_after,
        accounting_unknown=accounting_unknown,
    )


def _decode_json(content: bytes) -> dict[str, Any] | None:
    try:
        payload = json.loads(content, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _parse_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, Decimal) and value.is_finite():
        if value >= 0 and value == value.to_integral_value():
            try:
                return int(value)
            except (OverflowError, ValueError):
                return None
    return None


def _parse_nonnegative_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, Decimal):
            parsed = value
        elif isinstance(value, int):
            parsed = Decimal(value)
        elif isinstance(value, str):
            parsed = Decimal(value.strip())
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _parse_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        seconds = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        remaining = ceil((retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds())
        return min(max(0, remaining), MAX_RETRY_AFTER_SECONDS)
    if not seconds.is_finite() or seconds < 0:
        return None
    rounded = int(seconds.to_integral_value(rounding=ROUND_CEILING))
    return min(rounded, MAX_RETRY_AFTER_SECONDS)


def _ambiguous_http_status(status_code: int) -> bool:
    return status_code >= 500 or status_code in {408, 524}


def _wire_max_price(limit: ProviderPriceLimit) -> dict[str, Decimal]:
    """Единственная граница пересчёта token-цен в USD за 1 млн токенов."""
    return {
        "prompt": limit.prompt_per_token * TOKENS_PER_MILLION,
        "completion": limit.completion_per_token * TOKENS_PER_MILLION,
        "request": limit.request,
    }


def _encode_json(value: Any) -> bytes:
    return _encode_json_value(value).encode("utf-8")


def _encode_json_value(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("JSON не поддерживает неконечный Decimal")
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_encode_json_value(item) for item in value) + "]"
    if isinstance(value, tuple):
        return "[" + ",".join(_encode_json_value(item) for item in value) + "]"
    if isinstance(value, dict):
        encoded_items = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Ключ JSON должен быть строкой")
            encoded_items.append(
                f"{json.dumps(key, ensure_ascii=False)}:{_encode_json_value(item)}"
            )
        return "{" + ",".join(encoded_items) + "}"
    raise TypeError("Неподдерживаемый тип JSON")
