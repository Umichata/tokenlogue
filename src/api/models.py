"""Безопасная загрузка и memory-кэш каталога моделей OpenRouter."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from chat.models import (
    FREE_ROUTER_MODEL,
    CatalogModel,
    ModelCatalog,
    PriceComponents,
    is_free_model,
    is_paid_model,
    is_standard_text_chat_model,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_CATALOG_TTL_SECONDS = 300.0
CATALOG_WARNING = (
    "Список отдельных бесплатных моделей временно недоступен. Платный режим отключён."
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
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def fetch_models(self, api_key: str) -> tuple[CatalogModel, ...] | None:
        normalized_key = api_key.strip()
        if not normalized_key:
            return None
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = await client.get(
                    OPENROUTER_MODELS_URL,
                    headers={"Authorization": f"Bearer {normalized_key}"},
                )
        except (httpx.HTTPError, ImportError):
            return None

        if response.status_code != 200:
            return None
        return _parse_catalog(response.content)


class ModelCatalogService:
    """Кэширует классифицированный каталог только в памяти процесса."""

    def __init__(
        self,
        client: ModelCatalogClient,
        *,
        ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._ttl_seconds = max(0.0, ttl_seconds)
        self._clock = clock
        self._cached: ModelCatalog | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def get_catalog(self, api_key: str) -> ModelCatalog:
        now = self._clock()
        if self._cached is not None and now < self._expires_at:
            return self._cached

        async with self._lock:
            now = self._clock()
            if self._cached is not None and now < self._expires_at:
                return self._cached
            try:
                models = await self._client.fetch_models(api_key)
            except Exception:
                models = None
            catalog = _classify_catalog(models)
            self._cached = catalog
            self._expires_at = now + self._ttl_seconds
            return catalog

    def clear_cache(self) -> None:
        self._cached = None
        self._expires_at = 0.0


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


def _classify_catalog(models: tuple[CatalogModel, ...] | None) -> ModelCatalog:
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
