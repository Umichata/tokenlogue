"""Стабильные безопасные категории ошибок внутреннего механизма чата."""

from __future__ import annotations

from enum import Enum

from i18n import fresh_text, tr


class ChatErrorType(str, Enum):
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    PAYMENT_REQUIRED = "payment_required"
    PERMISSION_DENIED = "permission_denied"
    CONTENT_POLICY_VIOLATION = "content_policy_violation"
    REFUSAL = "refusal"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_OVERLOADED = "provider_overloaded"
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    MAX_TOKENS_EXCEEDED = "max_tokens_exceeded"
    TOKEN_LIMIT_EXCEEDED = "token_limit_exceeded"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    KEY_LIMIT_EXCEEDED = "key_limit_exceeded"
    KEY_NOT_VALID = "key_not_valid"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_PRICE_UNSAFE = "model_price_unsafe"
    PRICE_RECONFIRMATION_REQUIRED = "price_reconfirmation_required"
    PAID_CONFIRMATION_REQUIRED = "paid_confirmation_required"
    LIMITS_NOT_CONFIGURED = "limits_not_configured"
    TURN_ALREADY_ACTIVE = "turn_already_active"
    TURN_NOT_RETRYABLE = "turn_not_retryable"
    MALFORMED_RESPONSE = "malformed_response"
    ACCOUNTING_UNKNOWN = "accounting_unknown"
    INTERRUPTED = "interrupted"


SAFE_ERROR_MESSAGES: dict[ChatErrorType, str] = {
    ChatErrorType.INVALID_REQUEST: tr("service.error.invalid_request"),
    ChatErrorType.AUTHENTICATION: tr("service.error.authentication"),
    ChatErrorType.PAYMENT_REQUIRED: (tr("service.error.payment")),
    ChatErrorType.PERMISSION_DENIED: tr("service.error.permission"),
    ChatErrorType.CONTENT_POLICY_VIOLATION: tr("service.error.policy"),
    ChatErrorType.REFUSAL: tr("service.error.refusal"),
    ChatErrorType.TIMEOUT: tr("service.error.timeout"),
    ChatErrorType.NETWORK_ERROR: tr("service.error.network"),
    ChatErrorType.RATE_LIMIT_EXCEEDED: tr("service.error.rate"),
    ChatErrorType.PROVIDER_UNAVAILABLE: tr("service.error.unavailable"),
    ChatErrorType.PROVIDER_OVERLOADED: tr("service.error.overloaded"),
    ChatErrorType.CONTEXT_LENGTH_EXCEEDED: tr("service.error.context"),
    ChatErrorType.MAX_TOKENS_EXCEEDED: tr("service.error.completion"),
    ChatErrorType.TOKEN_LIMIT_EXCEEDED: tr("service.error.tokens"),
    ChatErrorType.COST_LIMIT_EXCEEDED: tr("service.error.cost"),
    ChatErrorType.KEY_LIMIT_EXCEEDED: tr("service.error.key_limit"),
    ChatErrorType.KEY_NOT_VALID: tr("service.error.key_state"),
    ChatErrorType.MODEL_UNAVAILABLE: tr("service.error.model_missing"),
    ChatErrorType.MODEL_PRICE_UNSAFE: tr("service.error.price_unsafe"),
    ChatErrorType.PRICE_RECONFIRMATION_REQUIRED: (tr("service.error.price_confirm")),
    ChatErrorType.PAID_CONFIRMATION_REQUIRED: (tr("service.error.paid_confirm")),
    ChatErrorType.LIMITS_NOT_CONFIGURED: tr("service.error.limits"),
    ChatErrorType.TURN_ALREADY_ACTIVE: tr("service.error.turn_active"),
    ChatErrorType.TURN_NOT_RETRYABLE: tr("service.error.retry"),
    ChatErrorType.MALFORMED_RESPONSE: tr("service.response_format"),
    ChatErrorType.ACCOUNTING_UNKNOWN: tr("service.error.unknown"),
    ChatErrorType.INTERRUPTED: tr("service.error.interrupted"),
}


def safe_error_message(error_type: ChatErrorType) -> str:
    return fresh_text(SAFE_ERROR_MESSAGES[error_type])
