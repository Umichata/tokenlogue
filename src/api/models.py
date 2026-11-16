"""Безопасная загрузка и memory-кэш каталога моделей OpenRouter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any, Protocol

import httpx

from api.chat_completions import _parse_retry_after
from api.openrouter import _contains_tls_error
from chat.catalog import CatalogFetchResult, CatalogStatus
from chat.models import (
    FREE_ROUTER_MODEL,
    CatalogModel,
    ModelCatalog,
    PriceComponents,
    is_free_model,
    is_paid_model,
    is_standard_text_chat_model,
)
from i18n import tr
from providers.models import Currency, PriceUnit, ProviderId, detect_key, provider_spec

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
VSEGPT_MODELS_URL = "https://api.vsegpt.ru/v1/models"
DEFAULT_CATALOG_TTL_SECONDS = 300.0
CATALOG_WARNING = tr("service.catalog_warning")
# Text model namespaces verified in the official text-model catalogue. Unknown
# categories are not assumed to accept chat just because they have token limits.
VSEGPT_TEXT_VENDORS = frozenset(
    {
        "openai",
        "anthropic",
        "gryphe",
        "google",
        "amazon",
        "qwen",
        "x-ai",
        "perplexity",
        "mistralai",
        "microsoft",
        "nvidia",
        "meta-llama",
        "nousresearch",
        "sao10k",
        "thedrummer",
        "cohere",
        "deepseek",
        "minimax",
        "moonshotai",
        "z-ai",
        "aion",
        "xiaomi",
    }
)
# Канонические ключи внешнего pricing из GET /api/v1/models.
PRICE_FIELDS = {
    "prompt",
    "completion",
    "request",
    "internal_reasoning",
    "input_cache_read",
    "input_cache_write",
}
IGNORED_NON_TEXT_PRICE_FIELDS = {
    "image",
    "audio",
    "input_audio",
    "output_audio",
    "web_search",
}
OVERRIDE_CONDITION_FIELDS = {
    "name",
    "provider",
    "providers",
    "quantization",
    "region",
    "condition",
    "pricing",
}


class ModelCatalogClient:
    """Получает один снимок каталога без повторов и без логирования ответа."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout | float = 10.0,
        provider_id: ProviderId = ProviderId.OPENROUTER,
    ) -> None:
        self._transport = transport
        self._timeout = timeout
        self.provider_id = ProviderId(provider_id)

    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...] | None:
        """Compatibility projection for callers which only need model prices."""
        result = await self.fetch_catalog(api_key)
        return result.models if result.available else None

    async def fetch_catalog(self, api_key: str) -> CatalogFetchResult:
        normalized_key = api_key.strip()
        if detect_key(normalized_key) is not self.provider_id:
            return CatalogFetchResult(CatalogStatus.KEY_MISMATCH)
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    provider_spec(self.provider_id).base_url + "/models",
                    headers=(
                        {"Authorization": f"Bearer {normalized_key}"}
                        if self.provider_id is ProviderId.OPENROUTER
                        else {}
                    ),
                )
        except httpx.TimeoutException:
            return CatalogFetchResult(CatalogStatus.TIMEOUT)
        except httpx.ConnectError as error:
            return CatalogFetchResult(
                CatalogStatus.TLS_ERROR
                if _contains_tls_error(error)
                else CatalogStatus.NETWORK_ERROR
            )
        except (httpx.HTTPError, ImportError, ValueError):
            return CatalogFetchResult(CatalogStatus.NETWORK_ERROR)

        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        if response.status_code != 200:
            return CatalogFetchResult(
                CatalogStatus.HTTP_ERROR,
                http_status=response.status_code,
                retry_after=retry_after,
            )
        models = (
            _parse_catalog(response.content)
            if self.provider_id is ProviderId.OPENROUTER
            else _parse_vsegpt_catalog(response.content)
        )
        if models is None:
            return CatalogFetchResult(CatalogStatus.INVALID_RESPONSE)
        return CatalogFetchResult(
            CatalogStatus.SUCCESS if models else CatalogStatus.EMPTY, models
        )


class CatalogReader(Protocol):
    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...] | None: ...


class ModelCatalogService:
    """Кэширует классифицированный каталог только в памяти процесса."""

    def __init__(
        self,
        client: CatalogReader,
        *,
        ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._clock = clock
        self._cached: ModelCatalog | None = None
        self._expires_at = 0.0
        self._generation = 0
        self._lock = asyncio.Lock()
        self._identity: tuple[ProviderId | None, bytes] | None = None
        self._refresh_not_before: dict[tuple[ProviderId | None, bytes], float] = {}
        self._entries: dict[
            tuple[ProviderId | None, bytes], tuple[ModelCatalog, float]
        ] = {}

    def peek_catalog(self, api_key: str | None = None) -> ModelCatalog | None:
        """Return only a still-current in-memory snapshot, without any request."""
        identity = self._identity if api_key is None else _catalog_identity(api_key)
        if identity is not None:
            entry = self._entries.get(identity)
            if entry is not None and self._clock() < entry[1]:
                return entry[0]
        return None

    def cache_remaining_seconds(self) -> float | None:
        """Expose cache age for an idle UI timer, without retaining a key."""
        if self._identity is None or self._identity not in self._entries:
            return None
        return max(0.0, self._entries[self._identity][1] - self._clock())

    async def get_catalog(
        self, api_key: str, *, force_refresh: bool = False
    ) -> ModelCatalog:
        generation = self._generation
        provider_id = detect_key(api_key)
        identity = _catalog_identity(api_key)
        self._identity = identity
        if not force_refresh:
            cached = self.peek_catalog(api_key)
            if cached is not None:
                return cached

        async with self._lock:
            # A waiter from an old protected session must not fetch with its
            # previous credential or consume the next session's cache.
            if generation != self._generation:
                return _classify_result(
                    CatalogFetchResult(CatalogStatus.NETWORK_ERROR), provider_id
                )
            entry = self._entries.get(identity)
            now = self._clock()
            remaining = self._refresh_not_before.get(identity, 0.0) - now
            if not force_refresh and entry is not None and now < entry[1]:
                return entry[0]
            if entry is not None and remaining > 0:
                return replace(entry[0], retry_after=ceil(remaining))
            try:
                typed_fetch = getattr(self._client, "fetch_catalog", None)
                if typed_fetch is not None:
                    result = await typed_fetch(api_key)
                else:
                    models = await self._client.fetch_models(api_key)
                    result = CatalogFetchResult(
                        CatalogStatus.NETWORK_ERROR
                        if models is None
                        else (CatalogStatus.SUCCESS if models else CatalogStatus.EMPTY),
                        models or (),
                    )
                if not isinstance(result, CatalogFetchResult):
                    result = CatalogFetchResult(CatalogStatus.INVALID_RESPONSE)
            except Exception:
                result = CatalogFetchResult(CatalogStatus.NETWORK_ERROR)
            catalog = _classify_result(result, provider_id)
            if generation != self._generation:
                return _classify_result(
                    CatalogFetchResult(CatalogStatus.NETWORK_ERROR), provider_id
                )
            self._cached = catalog
            self._expires_at = self._clock() + self._ttl_seconds
            self._entries[identity] = catalog, self._expires_at
            # Explicit retries bypass the negative TTL, but neither rapid taps
            # nor a provider Retry-After are allowed to start another request.
            self._refresh_not_before[identity] = self._clock() + max(
                2.0, result.retry_after or 0
            )
            return catalog

    def clear_cache(self, *, preserve_backoff: bool = False) -> None:
        # A new selection may require a fresh price snapshot, but must not
        # defeat a provider's refusal interval. Lock/session teardown uses the
        # default and removes even these credential-hash-only entries.
        now = self._clock()
        blocked = (
            {
                identity: entry
                for identity, entry in self._entries.items()
                if not entry[0].available
                and self._refresh_not_before.get(identity, 0.0) > now
            }
            if preserve_backoff
            else {}
        )
        backoff = {identity: self._refresh_not_before[identity] for identity in blocked}
        self._generation += 1
        self._cached = None
        self._expires_at = 0.0
        self._identity = None
        self._entries = blocked
        self._refresh_not_before = backoff


def _parse_vsegpt_catalog(content: bytes) -> tuple[CatalogModel, ...] | None:
    """Catalog rates have no machine-readable billing units or complete extras.

    Do not place RUB/character (or unknown per-model units) in token price fields.
    https://vsegpt.ru/Docs/Tariffs/Example and /Docs/ModelsNew differ by model.
    """
    try:
        payload = json.loads(content, parse_float=Decimal, parse_int=Decimal)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None
    models: list[CatalogModel] = []
    for item in payload["data"]:
        if not isinstance(item, dict):
            continue
        model_id, name = item.get("id"), item.get("name")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        # /Docs/ModelsNew documents these namespaces as ordinary text models;
        # /Docs/API/Code separately documents image/audio/embeddings endpoints.
        # A nonzero context_length is also present on embeddings/image models.
        category = model_id.split("/", 1)[0].lower()
        if category not in VSEGPT_TEXT_VENDORS:
            continue
        raw_context = item.get("context_length")
        if isinstance(raw_context, str):
            try:
                raw_context = Decimal(raw_context)
            except Exception:
                raw_context = None
        context_length = _parse_positive_int(raw_context)
        if context_length is None:
            continue
        models.append(
            CatalogModel(
                id=model_id.strip(),
                name=name.strip(),
                prompt_price_per_token=Decimal("0"),
                completion_price_per_token=Decimal("0"),
                pricing_is_complete=False,
                context_length=context_length,
                provider_id=ProviderId.VSEGPT,
                currency=Currency.RUB,
                pricing_unit=PriceUnit.UNKNOWN,
            )
        )
    return tuple(models)


def _catalog_identity(api_key: str) -> tuple[ProviderId | None, bytes]:
    return detect_key(api_key), hashlib.sha256(api_key.strip().encode("utf-8")).digest()


def _parse_catalog(content: bytes) -> tuple[CatalogModel, ...] | None:
    try:
        payload = json.loads(content, parse_float=Decimal, parse_int=Decimal)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None

    models: list[CatalogModel] = []
    for item in payload["data"]:
        model = _parse_model(item)
        if model is not None and is_standard_text_chat_model(model):
            models.append(model)
    return tuple(models)


def _parse_model(item: Any) -> CatalogModel | None:
    if not isinstance(item, dict):
        return None
    model_id = item.get("id")
    name = item.get("name")
    architecture = item.get("architecture")
    pricing = item.get("pricing")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(architecture, dict) or not isinstance(pricing, dict):
        return None

    input_modalities = _parse_modalities(architecture.get("input_modalities"))
    output_modalities = _parse_modalities(architecture.get("output_modalities"))
    base_pricing, pricing_complete = _parse_base_pricing(pricing)
    overrides_value = item.get("pricing_overrides", pricing.get("overrides"))
    pricing_overrides, overrides_complete = _parse_pricing_overrides(
        overrides_value,
        base_pricing,
    )
    context_length = _parse_positive_int(item.get("context_length"))
    top_provider = item.get("top_provider")
    provider_max_completion_tokens = (
        _parse_positive_int(top_provider.get("max_completion_tokens"))
        if isinstance(top_provider, dict)
        else None
    )
    if input_modalities is None or output_modalities is None or base_pricing is None:
        return None

    return CatalogModel(
        id=model_id.strip(),
        name=name.strip(),
        prompt_price_per_token=base_pricing.prompt,
        completion_price_per_token=base_pricing.completion,
        input_modalities=input_modalities,
        output_modalities=output_modalities,
        request_price=base_pricing.request,
        internal_reasoning_price_per_token=base_pricing.internal_reasoning,
        input_cache_read_price_per_token=base_pricing.input_cache_read,
        input_cache_write_price_per_token=base_pricing.input_cache_write,
        pricing_overrides=pricing_overrides,
        pricing_is_complete=pricing_complete and overrides_complete,
        context_length=context_length,
        provider_max_completion_tokens=provider_max_completion_tokens,
    )


def _parse_modalities(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item.strip() for item in value):
        return None
    return tuple(item.strip().lower() for item in value)


def _parse_price(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, Decimal):
            price = value
        elif isinstance(value, int):
            price = Decimal(value)
        elif isinstance(value, str):
            price = Decimal(value.strip())
        else:
            return None
    except (InvalidOperation, ValueError):
        return None
    return price if price.is_finite() and price >= 0 else None


def _parse_base_pricing(
    value: dict[Any, Any],
) -> tuple[PriceComponents | None, bool]:
    if "prompt" not in value or "completion" not in value:
        return None, False
    components = _parse_price_components(value, inherit=None)
    known_fields = PRICE_FIELDS | IGNORED_NON_TEXT_PRICE_FIELDS | {"overrides"}
    complete = all(isinstance(key, str) and key in known_fields for key in value)
    return components, complete


def _parse_pricing_overrides(
    value: Any,
    base: PriceComponents | None,
) -> tuple[tuple[PriceComponents, ...], bool]:
    if value is None:
        return (), True
    if base is None or not isinstance(value, list):
        return (), False

    parsed: list[PriceComponents] = []
    for override in value:
        if not isinstance(override, dict):
            return (), False
        if not all(
            isinstance(key, str)
            and (
                key in OVERRIDE_CONDITION_FIELDS
                or key in PRICE_FIELDS
                or key in IGNORED_NON_TEXT_PRICE_FIELDS
            )
            for key in override
        ):
            return (), False
        pricing = (
            override["pricing"]
            if "pricing" in override
            else {
                key: item
                for key, item in override.items()
                if key in PRICE_FIELDS or key in IGNORED_NON_TEXT_PRICE_FIELDS
            }
        )
        if not isinstance(pricing, dict):
            return (), False
        if not all(
            isinstance(key, str)
            and (key in PRICE_FIELDS or key in IGNORED_NON_TEXT_PRICE_FIELDS)
            for key in pricing
        ):
            return (), False
        components = _parse_price_components(pricing, inherit=base)
        if components is None:
            return (), False
        parsed.append(components)
    return tuple(parsed), True


def _parse_price_components(
    value: dict[Any, Any],
    *,
    inherit: PriceComponents | None,
) -> PriceComponents | None:
    def component(name: str) -> Decimal | None:
        if name in value:
            return _parse_price(value[name])
        if inherit is not None:
            return getattr(inherit, name)
        return Decimal("0")

    prompt = component("prompt")
    completion = component("completion")
    request = component("request")
    internal_reasoning = component("internal_reasoning")
    input_cache_read = component("input_cache_read")
    input_cache_write = component("input_cache_write")
    if None in {
        prompt,
        completion,
        request,
        internal_reasoning,
        input_cache_read,
        input_cache_write,
    }:
        return None
    assert prompt is not None
    assert completion is not None
    assert request is not None
    assert internal_reasoning is not None
    assert input_cache_read is not None
    assert input_cache_write is not None
    return PriceComponents(
        prompt=prompt,
        completion=completion,
        request=request,
        internal_reasoning=internal_reasoning,
        input_cache_read=input_cache_read,
        input_cache_write=input_cache_write,
    )


def _parse_positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, Decimal) and value == value.to_integral_value() and value > 0:
        try:
            return int(value)
        except (OverflowError, ValueError):
            return None
    return None


def _classify_catalog(
    models: tuple[CatalogModel, ...] | None,
    provider_id: ProviderId | None = ProviderId.OPENROUTER,
) -> ModelCatalog:
    if provider_id is not ProviderId.OPENROUTER:
        return ModelCatalog(
            free_models=(),
            paid_models=tuple(
                sorted(
                    models or (), key=lambda model: (model.name.casefold(), model.id)
                )
            ),
            available=models is not None,
            warning=CATALOG_WARNING if models is None else None,
        )
    if models is None:
        return ModelCatalog(
            free_models=(FREE_ROUTER_MODEL,),
            paid_models=(),
            available=False,
            warning=CATALOG_WARNING,
        )

    free_models = sorted(
        (
            model
            for model in models
            if model.id != FREE_ROUTER_MODEL.id and is_free_model(model)
        ),
        key=lambda model: (model.name.casefold(), model.id),
    )
    paid_models = sorted(
        (
            model
            for model in models
            if model.id != FREE_ROUTER_MODEL.id and is_paid_model(model)
        ),
        key=lambda model: (model.name.casefold(), model.id),
    )
    return ModelCatalog(
        free_models=(FREE_ROUTER_MODEL, *free_models),
        paid_models=tuple(paid_models),
        available=True,
    )


def _classify_result(
    result: CatalogFetchResult, provider_id: ProviderId | None
) -> ModelCatalog:
    catalog = _classify_catalog(
        result.models if result.available else None, provider_id
    )
    warning = None
    if not result.available:
        message_key = {
            CatalogStatus.KEY_MISMATCH: "catalog.error.key_mismatch",
            CatalogStatus.NETWORK_ERROR: "catalog.error.network",
            CatalogStatus.TIMEOUT: "catalog.error.timeout",
            CatalogStatus.TLS_ERROR: "catalog.error.tls",
            CatalogStatus.INVALID_RESPONSE: "catalog.error.schema",
        }.get(result.status, "catalog.error.http")
        if result.status is CatalogStatus.HTTP_ERROR:
            message_key = {
                401: "catalog.error.auth",
                402: "catalog.error.balance",
                403: "catalog.error.policy",
                429: "catalog.error.rate",
            }.get(result.http_status or 0, "catalog.error.http")
        warning = tr(message_key)
    elif result.status is CatalogStatus.EMPTY:
        warning = tr("catalog.empty")
    return replace(
        catalog,
        warning=warning,
        status=result.status,
        http_status=result.http_status,
        retry_after=result.retry_after,
    )
