"""Офлайн-тесты каталога и классификации моделей OpenRouter."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import (  # noqa: E402
    OPENROUTER_MODELS_URL,
    ModelCatalogClient,
    ModelCatalogService,
)
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.accounting import estimate_max_cost  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, ChatMode, is_free_model  # noqa: E402
from chat.service import ChatService  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402

TEST_CREDENTIAL = "catalog-test-credential"


class MutableClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class ModelCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_decimal_prices_and_classifies_models(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "data": [
                        _model("vendor/free-model", "Free", "0", "0"),
                        _model(
                            "vendor/paid-model",
                            "Paid",
                            "0.00000125",
                            "0.0000025",
                        ),
                        _model(
                            "openrouter/free",
                            "Forged paid router",
                            "1",
                            "2",
                        ),
                    ]
                },
            )

        catalog = await _catalog_from_handler(handler)

        self.assertTrue(catalog.available)
        self.assertEqual(catalog.free_models[0], FREE_ROUTER_MODEL)
        self.assertTrue(catalog.free_models[0].recommended)
        self.assertEqual(catalog.free_models[1].id, "vendor/free-model")
        self.assertEqual(catalog.paid_models[0].id, "vendor/paid-model")
        self.assertEqual(len(catalog.paid_models), 1)
        self.assertEqual(
            catalog.paid_models[0].prompt_price_per_token,
            Decimal("0.00000125"),
        )
        self.assertEqual(
            catalog.paid_models[0].prompt_price_per_million,
            Decimal("1.25000000"),
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), OPENROUTER_MODELS_URL)
        self.assertEqual(requests[0].method, "GET")
        self.assertEqual(
            requests[0].headers["Authorization"],
            f"Bearer {TEST_CREDENTIAL}",
        )

    async def test_discards_damaged_and_non_chat_items(self) -> None:
        payload = {
            "data": [
                _model("vendor/valid", "Valid", "0", "0"),
                _model("vendor/negative", "Negative", "-0.1", "0"),
                _model("vendor/nan", "NaN", "NaN", "0"),
                _model("vendor/infinite", "Infinite", "Infinity", "0"),
                _model(
                    "vendor/image-only",
                    "Image",
                    "0",
                    "0",
                    input_modalities=["image"],
                ),
                _model(
                    "vendor/audio-output",
                    "Audio",
                    "0",
                    "0",
                    output_modalities=["audio"],
                ),
                _model("vendor/model:online", "Online", "0", "0"),
                _model("vendor/model-batch", "Batch", "0", "0"),
                {"id": "missing-fields"},
                "not-an-object",
            ]
        }

        catalog = await _catalog_from_payload(payload)

        self.assertEqual(
            [model.id for model in catalog.free_models],
            ["openrouter/free", "vendor/valid"],
        )
        self.assertEqual(catalog.paid_models, ())

    async def test_accepts_json_number_without_float_conversion(self) -> None:
        content = (
            b'{"data":[{"id":"vendor/numeric","name":"Numeric",'
            b'"architecture":{"input_modalities":["text"],'
            b'"output_modalities":["text"]},'
            b'"pricing":{"prompt":0.0000001,"completion":0.0000002}}]}'
        )

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=content)

        catalog = await _catalog_from_handler(handler)

        self.assertEqual(
            catalog.paid_models[0].prompt_price_per_token,
            Decimal("0.0000001"),
        )

    async def test_parses_canonical_cache_pricing_and_uses_it_in_reserve(
        self,
    ) -> None:
        model = _model("vendor/full", "Full", "0", "0")
        pricing = model["pricing"]
        assert isinstance(pricing, dict)
        pricing.update(
            {
                "request": "0",
                "internal_reasoning": "0",
                "input_cache_read": "0.000001",
                "input_cache_write": "0",
            }
        )
        model["context_length"] = 32768
        model["top_provider"] = {"max_completion_tokens": 4096}

        catalog = await _catalog_from_payload({"data": [model]})
        parsed = catalog.paid_models[0]

        self.assertEqual(parsed.request_price, Decimal("0"))
        self.assertEqual(
            parsed.internal_reasoning_price_per_token,
            Decimal("0"),
        )
        self.assertEqual(parsed.input_cache_read_price_per_token, Decimal("0.000001"))
        self.assertEqual(parsed.input_cache_write_price_per_token, Decimal("0"))
        self.assertFalse(is_free_model(parsed))
        self.assertEqual(
            estimate_max_cost(parsed.all_pricing, prompt_tokens=3, completion_tokens=0),
            Decimal("0.000003"),
        )
        self.assertEqual(parsed.context_length, 32768)
        self.assertEqual(parsed.provider_max_completion_tokens, 4096)

        with tempfile.TemporaryDirectory() as temp_dir:
            database = AuthDatabase(temp_dir)
            repository = SqliteChatRepository(database.path)
            service = ChatService(
                repository,
                now=lambda: datetime(2026, 5, 1, tzinfo=UTC),
                uuid_factory=lambda: UUID(int=1),
            )
            created = await service.create_chat(
                ChatMode.PAID,
                parsed,
                catalog=catalog,
                key_validity=KeyValidityState.VALID,
                key_limit=KeyLimitInfo.from_validated_remaining(None),
                paid_confirmed=True,
            )

            restored = repository.get_chat(created.id)

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(
            restored.input_cache_read_price_per_token,
            Decimal("0.000001"),
        )
        self.assertEqual(restored.input_cache_write_price_per_token, Decimal("0"))

    async def test_each_positive_canonical_cache_component_prevents_free_mode(
        self,
    ) -> None:
        for field in ("input_cache_read", "input_cache_write"):
            with self.subTest(field=field):
                model = _model(f"vendor/{field}", field, "0", "0")
                pricing = model["pricing"]
                assert isinstance(pricing, dict)
                pricing[field] = "0.000001"

                catalog = await _catalog_from_payload({"data": [model]})

                self.assertEqual(
                    [item.id for item in catalog.free_models],
                    ["openrouter/free"],
                )
                self.assertEqual(
                    [item.id for item in catalog.paid_models],
                    [f"vendor/{field}"],
                )

    async def test_canonical_cache_override_is_paid_and_conservative(self) -> None:
        model = _model("vendor/cache-override", "Cache override", "0", "0")
        pricing = model["pricing"]
        assert isinstance(pricing, dict)
        pricing["overrides"] = [{"input_cache_write": "0.000002"}]

        catalog = await _catalog_from_payload({"data": [model]})
        parsed = catalog.paid_models[0]

        self.assertEqual(
            [item.id for item in catalog.free_models],
            ["openrouter/free"],
        )
        self.assertEqual(parsed.id, "vendor/cache-override")
        self.assertEqual(
            parsed.pricing_overrides[0].input_cache_write,
            Decimal("0.000002"),
        )
        self.assertEqual(
            estimate_max_cost(parsed.all_pricing, prompt_tokens=4, completion_tokens=0),
            Decimal("0.000008"),
        )

    async def test_missing_cache_prices_are_zero_but_not_damaged(self) -> None:
        catalog = await _catalog_from_payload(
            {"data": [_model("vendor/no-cache-price", "No cache price", "0", "0")]}
        )

        parsed = catalog.free_models[1]
        self.assertTrue(parsed.pricing_is_complete)
        self.assertEqual(parsed.input_cache_read_price_per_token, Decimal("0"))
        self.assertEqual(parsed.input_cache_write_price_per_token, Decimal("0"))
        self.assertTrue(is_free_model(parsed))
        self.assertTrue(is_free_model(FREE_ROUTER_MODEL))

    async def test_damaged_canonical_cache_prices_fail_closed(self) -> None:
        invalid_values: tuple[object, ...] = (
            "-0.000001",
            "NaN",
            "Infinity",
            "not-a-price",
            True,
            {"value": "0.000001"},
        )
        for field in ("input_cache_read", "input_cache_write"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    model = _model("vendor/damaged-cache", "Damaged", "0", "0")
                    pricing = model["pricing"]
                    assert isinstance(pricing, dict)
                    pricing[field] = value

                    catalog = await _catalog_from_payload({"data": [model]})

                    self.assertTrue(catalog.available)
                    self.assertEqual(catalog.free_models, (FREE_ROUTER_MODEL,))
                    self.assertEqual(catalog.paid_models, ())

    async def test_damaged_canonical_cache_overrides_fail_closed(self) -> None:
        invalid_values: tuple[object, ...] = (
            "-0.000001",
            "NaN",
            "Infinity",
            "not-a-price",
            True,
            {"value": "0.000001"},
        )
        for field in ("input_cache_read", "input_cache_write"):
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    model = _model("vendor/damaged-override", "Damaged", "0", "0")
                    pricing = model["pricing"]
                    assert isinstance(pricing, dict)
                    pricing["overrides"] = [{field: value}]

                    catalog = await _catalog_from_payload({"data": [model]})

                    self.assertTrue(catalog.available)
                    self.assertEqual(catalog.free_models, (FREE_ROUTER_MODEL,))
                    self.assertEqual(catalog.paid_models, ())

    async def test_noncanonical_external_cache_names_fail_closed(self) -> None:
        for field in ("cache_read", "cache_write"):
            with self.subTest(field=field):
                model = _model("vendor/noncanonical-cache", "Noncanonical", "0", "0")
                pricing = model["pricing"]
                assert isinstance(pricing, dict)
                pricing[field] = "0.000001"

                catalog = await _catalog_from_payload({"data": [model]})

                self.assertTrue(catalog.available)
                self.assertEqual(catalog.free_models, (FREE_ROUTER_MODEL,))
                self.assertEqual(catalog.paid_models, ())

    async def test_noncanonical_conflict_never_selects_lower_price(self) -> None:
        model = _model("vendor/cache-conflict", "Conflict", "0", "0")
        pricing = model["pricing"]
        assert isinstance(pricing, dict)
        pricing["input_cache_read"] = "0.000002"
        pricing["cache_read"] = "0"

        catalog = await _catalog_from_payload({"data": [model]})

        self.assertTrue(catalog.available)
        self.assertEqual(catalog.free_models, (FREE_ROUTER_MODEL,))
        self.assertEqual(catalog.paid_models, ())

    async def test_zero_prompt_and_completion_with_request_price_is_not_free(
        self,
    ) -> None:
        model = _model("vendor/request-priced", "Request priced", "0", "0")
        pricing = model["pricing"]
        assert isinstance(pricing, dict)
        pricing["request"] = "0.01"

        catalog = await _catalog_from_payload({"data": [model]})

        self.assertEqual(
            [item.id for item in catalog.free_models],
            ["openrouter/free"],
        )
        self.assertEqual(
            [item.id for item in catalog.paid_models],
            ["vendor/request-priced"],
        )

    async def test_positive_override_prevents_free_classification(self) -> None:
        model = _model("vendor/override", "Override", "0", "0")
        model["pricing_overrides"] = [
            {
                "provider": "provider-a",
                "pricing": {"request": "0.02"},
            }
        ]

        catalog = await _catalog_from_payload({"data": [model]})

        self.assertEqual(len(catalog.free_models), 1)
        self.assertEqual(catalog.paid_models[0].id, "vendor/override")
        self.assertEqual(
            catalog.paid_models[0].pricing_overrides[0].request,
            Decimal("0.02"),
        )

    async def test_unknown_override_condition_is_not_safely_classified(self) -> None:
        model = _model("vendor/unknown", "Unknown", "0", "0")
        model["pricing_overrides"] = [
            {"future_unknown_condition": True, "pricing": {"prompt": "0"}}
        ]

        catalog = await _catalog_from_payload({"data": [model]})

        self.assertEqual(len(catalog.free_models), 1)
        self.assertEqual(catalog.paid_models, ())

    async def test_malformed_json_falls_back_only_to_free_router(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not-json")

        catalog = await _catalog_from_handler(handler)

        _assert_closed_fallback(self, catalog)

    async def test_http_error_falls_back_only_to_free_router(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, content=b"service unavailable")

        catalog = await _catalog_from_handler(handler)

        _assert_closed_fallback(self, catalog)

    async def test_timeout_falls_back_only_to_free_router(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("injected timeout", request=request)

        catalog = await _catalog_from_handler(handler)

        _assert_closed_fallback(self, catalog)

    async def test_unexpected_transport_failure_also_fails_closed(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise RuntimeError("injected transport failure")

        catalog = await _catalog_from_handler(handler)

        _assert_closed_fallback(self, catalog)

    async def test_memory_cache_honors_ttl_and_can_be_cleared(self) -> None:
        calls = 0
        clock = MutableClock()

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                json={"data": [_model("vendor/free", "Free", "0", "0")]},
            )

        service = ModelCatalogService(
            ModelCatalogClient(transport=httpx.MockTransport(handler)),
            ttl_seconds=30,
            clock=clock,
        )

        first = await service.get_catalog(TEST_CREDENTIAL)
        second = await service.get_catalog(TEST_CREDENTIAL)
        self.assertIs(first, second)
        self.assertEqual(calls, 1)

        clock.value += 31
        await service.get_catalog(TEST_CREDENTIAL)
        self.assertEqual(calls, 2)

        service.clear_cache()
        await service.get_catalog(TEST_CREDENTIAL)
        self.assertEqual(calls, 3)


async def _catalog_from_payload(payload: object):
    content = json.dumps(payload).encode()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    return await _catalog_from_handler(handler)


async def _catalog_from_handler(handler):
    service = ModelCatalogService(
        ModelCatalogClient(transport=httpx.MockTransport(handler))
    )
    return await service.get_catalog(TEST_CREDENTIAL)


def _model(
    model_id: str,
    name: str,
    prompt: object,
    completion: object,
    *,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": model_id,
        "name": name,
        "architecture": {
            "input_modalities": input_modalities or ["text"],
            "output_modalities": output_modalities or ["text"],
        },
        "pricing": {"prompt": prompt, "completion": completion},
    }


def _assert_closed_fallback(
    testcase: unittest.TestCase,
    catalog,
) -> None:
    testcase.assertFalse(catalog.available)
    testcase.assertEqual(catalog.free_models, (FREE_ROUTER_MODEL,))
    testcase.assertEqual(catalog.paid_models, ())
    testcase.assertIsNotNone(catalog.warning)


if __name__ == "__main__":
    unittest.main()
