"""Стабильные безопасные категории ошибок внутреннего механизма чата."""

from __future__ import annotations

from enum import Enum


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
    ChatErrorType.INVALID_REQUEST: "OpenRouter отклонил параметры запроса.",
    ChatErrorType.AUTHENTICATION: "OpenRouter отклонил API-ключ.",
    ChatErrorType.PAYMENT_REQUIRED: (
        "OpenRouter сообщил о недостатке средств аккаунта или лимита ключа."
    ),
    ChatErrorType.PERMISSION_DENIED: "OpenRouter запретил этот запрос.",
    ChatErrorType.CONTENT_POLICY_VIOLATION: "Ответ остановлен политикой содержимого.",
    ChatErrorType.REFUSAL: "Модель отказалась сформировать ответ.",
    ChatErrorType.TIMEOUT: "OpenRouter не завершил запрос вовремя.",
    ChatErrorType.NETWORK_ERROR: "Не удалось завершить сетевой запрос.",
    ChatErrorType.RATE_LIMIT_EXCEEDED: "OpenRouter временно ограничил частоту запросов.",
    ChatErrorType.PROVIDER_UNAVAILABLE: "Провайдер модели временно недоступен.",
    ChatErrorType.PROVIDER_OVERLOADED: "Провайдер модели временно перегружен.",
    ChatErrorType.CONTEXT_LENGTH_EXCEEDED: "Контекст не помещается в окно модели.",
    ChatErrorType.MAX_TOKENS_EXCEEDED: "Превышено ограничение длины ответа модели.",
    ChatErrorType.TOKEN_LIMIT_EXCEEDED: "Токен-бюджет этого чата исчерпан.",
    ChatErrorType.COST_LIMIT_EXCEEDED: "Денежный бюджет этого чата исчерпан.",
    ChatErrorType.KEY_LIMIT_EXCEEDED: "Оценка превышает доступный лимит ключа.",
    ChatErrorType.KEY_NOT_VALID: "Состояние ключа не разрешает этот запрос.",
    ChatErrorType.MODEL_UNAVAILABLE: "Выбранная модель отсутствует в текущем каталоге.",
    ChatErrorType.MODEL_PRICE_UNSAFE: "Текущую цену модели нельзя безопасно оценить.",
    ChatErrorType.PRICE_RECONFIRMATION_REQUIRED: (
        "Цена модели изменилась и требует нового подтверждения."
    ),
    ChatErrorType.PAID_CONFIRMATION_REQUIRED: (
        "Платный запрос требует явного подтверждения."
    ),
    ChatErrorType.LIMITS_NOT_CONFIGURED: "Сначала настройте лимиты этого чата.",
    ChatErrorType.TURN_ALREADY_ACTIVE: "В этом чате уже выполняется запрос.",
    ChatErrorType.TURN_NOT_RETRYABLE: "Эту попытку нельзя повторить.",
    ChatErrorType.MALFORMED_RESPONSE: "OpenRouter вернул ответ неожиданного формата.",
    ChatErrorType.ACCOUNTING_UNKNOWN: "Токены или стоимость запроса неизвестны.",
    ChatErrorType.INTERRUPTED: "Запрос был прерван при завершении приложения.",
}


def safe_error_message(error_type: ChatErrorType) -> str:
    return SAFE_ERROR_MESSAGES[error_type]
