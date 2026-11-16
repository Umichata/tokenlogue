"""One application contract, with fixed and isolated provider adapters."""

from __future__ import annotations

import httpx

from api.chat_completions import (
    ChatCompletionResult,
    ChatCompletionsClient,
)
from api.models import ModelCatalogClient
from api.openrouter import (
    CreditsResult,
    CreditsStatus,
    KeyValidationResult,
    KeyValidationStatus,
    OpenRouterClient,
)
from api.vsegpt import VsegptClient
from chat.catalog import CatalogFetchResult, CatalogStatus
from chat.context import ContextMessage
from chat.errors import ChatErrorType
from chat.models import CatalogModel, ProviderPriceLimit
from providers.models import ProviderId, detect_key, provider_spec


class ProviderRouter:
    """A prefix selects one adapter; errors never trigger another service."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._accounts = {
            ProviderId.OPENROUTER: OpenRouterClient(transport=transport),
            ProviderId.VSEGPT: VsegptClient(transport=transport),
        }
        self._catalogs = {
            provider_id: ModelCatalogClient(
                transport=transport, provider_id=provider_id
            )
            for provider_id in ProviderId
        }
        self._completions = {
            provider_id: ChatCompletionsClient(
                transport=transport, provider_id=provider_id
            )
            for provider_id in ProviderId
        }

    async def validate_key(
        self, api_key: str, *, selected_provider: ProviderId | None = None
    ) -> KeyValidationResult:
        provider_id = _route(api_key, selected_provider)
        if provider_id is None:
            return KeyValidationResult(
                KeyValidationStatus.INVALID,
                provider_id=selected_provider or ProviderId.OPENROUTER,
            )
        return await self._accounts[provider_id].validate_key(api_key)

    async def get_credits(
        self, api_key: str, *, selected_provider: ProviderId | None = None
    ) -> CreditsResult:
        provider_id = _route(api_key, selected_provider)
        if provider_id is None:
            expected = selected_provider or ProviderId.OPENROUTER
            return CreditsResult(
                CreditsStatus.UNAUTHORIZED,
                provider_id=expected,
                currency=provider_spec(expected).currency,
            )
        return await self._accounts[provider_id].get_credits(api_key)

    async def fetch_models(
        self, api_key: str, *, selected_provider: ProviderId | None = None
    ) -> tuple[CatalogModel, ...] | None:
        provider_id = _route(api_key, selected_provider)
        if provider_id is None:
            return None
        return await self._catalogs[provider_id].fetch_models(api_key)

    async def fetch_catalog(
        self, api_key: str, *, selected_provider: ProviderId | None = None
    ) -> CatalogFetchResult:
        provider_id = _route(api_key, selected_provider)
        if provider_id is None:
            return CatalogFetchResult(CatalogStatus.KEY_MISMATCH)
        return await self._catalogs[provider_id].fetch_catalog(api_key)

    async def complete(
        self,
        api_key: str,
        requested_model_id: str,
        messages: tuple[ContextMessage, ...],
        max_completion_tokens: int,
        provider_price_limit: ProviderPriceLimit,
        *,
        selected_provider: ProviderId | None = None,
    ) -> ChatCompletionResult:
        provider_id = _route(api_key, selected_provider)
        if provider_id is None:
            expected = selected_provider or ProviderId.OPENROUTER
            return ChatCompletionResult(
                content=None,
                generation_id=None,
                requested_model_id=requested_model_id,
                actual_model_id=None,
                finish_reason=None,
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                cost_usd=None,
                error_type=ChatErrorType.AUTHENTICATION,
                provider_id=expected,
                currency=provider_spec(expected).currency,
            )
        return await self._completions[provider_id].complete(
            api_key,
            requested_model_id,
            messages,
            max_completion_tokens,
            provider_price_limit,
        )


def _route(api_key: str, selected_provider: ProviderId | None) -> ProviderId | None:
    detected = detect_key(api_key)
    if selected_provider is not None and detected != selected_provider:
        return None
    return detected
