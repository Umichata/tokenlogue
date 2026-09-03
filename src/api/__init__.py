"""Клиенты внешних API приложения."""

from .chat_completions import ChatCompletionResult, ChatCompletionsClient
from .models import ModelCatalogClient, ModelCatalogService
from .openrouter import KeyValidationResult, KeyValidationStatus, OpenRouterClient

__all__ = [
    "KeyValidationResult",
    "KeyValidationStatus",
    "ModelCatalogClient",
    "ModelCatalogService",
    "OpenRouterClient",
    "ChatCompletionResult",
    "ChatCompletionsClient",
]
