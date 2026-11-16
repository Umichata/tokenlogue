"""Offline provider isolation and truthful usage/balance contract tests."""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import ChatCompletionsClient  # noqa: E402
from api.models import ModelCatalogClient, ModelCatalogService  # noqa: E402
from api.openrouter import (  # noqa: E402
    CreditsStatus,
    KeyValidationStatus,
    OpenRouterClient,
)
from api.provider_router import ProviderRouter  # noqa: E402
from api.vsegpt import VsegptClient  # noqa: E402
from chat.context import ContextMessage  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import MessageRole, ProviderPriceLimit, is_free_model  # noqa: E402
from providers.models import (  # noqa: E402
    Currency,
    PriceUnit,
    ProviderId,
    detect_key,
    provider_spec,
)

OPENROUTER_KEY = "sk-or-v1-offline-only-fixture"
VSEGPT_KEY = "sk-or-vv-offline-only-fixture"
VSEGPT_VIS_KEYS = ("sk-or-vis-local-fixture", "sk-or-visLOCAL_TEST")
MESSAGES = (ContextMessage(MessageRole.USER, "fixture message"),)


def _completion(usage: dict | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "fixture-generation",
            "model": "openai/gpt-4o-mini",
            "choices": [
                {"finish_reason": "stop", "message": {"content": "fixture reply"}}
            ],
            "usage": usage,
        },
    )


def _balance(
    *, credits: object = "10.752448", status=0, subscription="ok"
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "ok",
            "data": {
                "credits": credits,
                "user_status": status,
                "subscription_status": subscription,
                "user_status_text": "private diagnostic must never appear",
            },
        },
    )


class ProviderIdentityTests(unittest.TestCase):
    def test_only_exact_complete_prefixes_are_recognized(self) -> None:
        self.assertIs(detect_key("  " + OPENROUTER_KEY + "\n"), ProviderId.OPENROUTER)
        self.assertIs(detect_key(VSEGPT_KEY), ProviderId.VSEGPT)
        for candidate in VSEGPT_VIS_KEYS:
            with self.subTest(candidate=candidate):
                self.assertIs(detect_key(candidate), ProviderId.VSEGPT)
                self.assertIs(detect_key(" \t" + candidate + "\n"), ProviderId.VSEGPT)
        for candidate in (
            "",
            "sk-or-v1-",
            "sk-or-vv-",
            "sk-or-vis",
            "sk-or-vis-",
            "sk-or-vis--",
            "sk-or-vi",
            "sk-or-v",
            "sk-or-",
            "other",
            "SK-or-v1-x",
            "sk-or-vv-a b",
            "sk-or-vis-a b",
            "sk-or-vis-a\tb",
            "sk-or-vis-a\x00b",
            "sk-or-vis-a\x1fb",
            "sk-or-vis-a\x7fb",
            "sk-or-vis-тест",
            "sk-or-vis-a\u00a0b",
        ):
            with self.subTest(candidate=candidate):
                self.assertIsNone(detect_key(candidate))

    def test_provider_specs_have_fixed_hosts_and_separate_currencies(self) -> None:
        self.assertEqual(
            provider_spec(ProviderId.OPENROUTER).base_url,
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(
            provider_spec(ProviderId.VSEGPT).base_url, "https://api.vsegpt.ru/v1"
        )
        self.assertEqual(provider_spec(ProviderId.OPENROUTER).currency, Currency.USD)
        self.assertEqual(provider_spec(ProviderId.VSEGPT).currency, Currency.RUB)
        with self.assertRaises(ValueError):
            provider_spec("https://attacker.invalid")


class ProviderRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_truncated_or_mismatched_selection_never_calls_network(
        self,
    ) -> None:
        requests: list[httpx.Request] = []
        router = ProviderRouter(
            transport=httpx.MockTransport(
                lambda request: requests.append(request) or httpx.Response(500)
            )
        )
        for key, selected in (
            ("unknown", None),
            ("sk-or-vv-", None),
            ("sk-or-vis", None),
            ("sk-or-vis-", None),
            ("sk-or-vis-a b", None),
            ("sk-or-vis-a\x00b", None),
            ("sk-or-vis-тест", None),
            (OPENROUTER_KEY, ProviderId.VSEGPT),
            (VSEGPT_KEY, ProviderId.OPENROUTER),
            *((key, ProviderId.OPENROUTER) for key in VSEGPT_VIS_KEYS),
        ):
            with self.subTest(selected=selected):
                validation = await router.validate_key(key, selected_provider=selected)
                self.assertIs(validation.status, KeyValidationStatus.INVALID)
                self.assertIsNone(
                    await router.fetch_models(key, selected_provider=selected)
                )
                await router.get_credits(key, selected_provider=selected)
                result = await router.complete(
                    key,
                    "openai/gpt-4o-mini",
                    MESSAGES,
                    32,
                    ProviderPriceLimit.zero(),
                    selected_provider=selected,
                )
                self.assertIs(result.error_type, ChatErrorType.AUTHENTICATION)
        self.assertEqual(requests, [])

    async def test_fixed_adapters_also_reject_other_provider_keys(self) -> None:
        requests: list[httpx.Request] = []
        transport = httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(500)
        )
        self.assertFalse(
            (
                await OpenRouterClient(transport=transport).validate_key(VSEGPT_KEY)
            ).accepted
        )
        for key in VSEGPT_VIS_KEYS:
            self.assertFalse(
                (await OpenRouterClient(transport=transport).validate_key(key)).accepted
            )
            await OpenRouterClient(transport=transport).get_credits(key)
        await OpenRouterClient(transport=transport).get_credits(VSEGPT_KEY)
        await VsegptClient(transport=transport).validate_key(OPENROUTER_KEY)
        for provider_id, wrong_key in (
            (ProviderId.OPENROUTER, VSEGPT_KEY),
            (ProviderId.VSEGPT, OPENROUTER_KEY),
            *((ProviderId.OPENROUTER, key) for key in VSEGPT_VIS_KEYS),
        ):
            await ModelCatalogClient(
                transport=transport, provider_id=provider_id
            ).fetch_models(wrong_key)
            await ChatCompletionsClient(
                transport=transport, provider_id=provider_id
            ).complete(
                wrong_key, "vendor/model", MESSAGES, 32, ProviderPriceLimit.zero()
            )
        self.assertEqual(requests, [])

    async def test_vis_credentials_keep_original_bytes_on_fixed_vsegpt_endpoints(
        self,
    ) -> None:
        for key in VSEGPT_VIS_KEYS:
            with self.subTest(key=key):
                requests: list[httpx.Request] = []

                def handler(request: httpx.Request) -> httpx.Response:
                    requests.append(request)
                    if request.url.path.endswith("/balance"):
                        return _balance()
                    if request.url.path.endswith("/models"):
                        return httpx.Response(200, json={"data": []})
                    return _completion({"prompt_tokens": 3, "completion_tokens": 2})

                router = ProviderRouter(transport=httpx.MockTransport(handler))
                padded = " \t" + key + "\n"
                validation = await router.validate_key(padded)
                balance = await router.get_credits(padded)
                self.assertEqual(await router.fetch_models(padded), ())
                reply = await router.complete(
                    padded, "vendor/model", MESSAGES, 32, ProviderPriceLimit.zero()
                )
                self.assertTrue(validation.accepted)
                self.assertEqual(validation.provider_id, ProviderId.VSEGPT)
                self.assertEqual(balance.currency, Currency.RUB)
                self.assertTrue(reply.successful)
                self.assertEqual(reply.provider_id, ProviderId.VSEGPT)
                self.assertEqual(reply.currency, Currency.RUB)
                self.assertEqual(
                    [str(request.url) for request in requests],
                    [
                        "https://api.vsegpt.ru/v1/balance",
                        "https://api.vsegpt.ru/v1/balance",
                        "https://api.vsegpt.ru/v1/models",
                        "https://api.vsegpt.ru/v1/chat/completions",
                    ],
                )
                for request in requests:
                    if request.url.path.endswith("/models"):
                        self.assertNotIn("Authorization", request.headers)
                    else:
                        self.assertEqual(
                            request.headers["Authorization"], f"Bearer {key}"
                        )
                    self.assertNotIn("HTTP-Referer", request.headers)
                    self.assertNotIn("X-Title", request.headers)
                self.assertEqual(
                    set(json.loads(requests[-1].content)),
                    {"model", "messages", "max_tokens", "stream"},
                )

    async def test_vsegpt_payload_has_no_openrouter_routing_or_cost_assumptions(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _completion(
                {
                    "prompt_tokens": 17,
                    "completion_tokens": 3,
                    "total_tokens": 20,
                    "cost": "0.9",
                    "total_cost": "123.4",
                    "prompt_tokens_details": {"cached_tokens": 4},
                    "completion_tokens_details": {"reasoning_tokens": 2},
                }
            )

        result = await ProviderRouter(transport=httpx.MockTransport(handler)).complete(
            VSEGPT_KEY, "openai/gpt-4o-mini", MESSAGES, 64, ProviderPriceLimit.zero()
        )
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(str(request.url), "https://api.vsegpt.ru/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], f"Bearer {VSEGPT_KEY}")
        payload = json.loads(request.content)
        self.assertEqual(set(payload), {"model", "messages", "max_tokens", "stream"})
        self.assertEqual(payload["max_tokens"], 64)
        self.assertTrue(result.successful)
        self.assertTrue(result.has_token_usage)
        self.assertEqual(result.total_tokens, 20)
        self.assertEqual(result.cached_tokens, 4)
        self.assertEqual(result.reasoning_tokens, 2)
        self.assertEqual(result.currency, Currency.RUB)
        self.assertIsNone(result.cost_amount)
        self.assertIsNone(result.cost_usd)
        self.assertEqual(result.usage_source, "api")
        self.assertEqual(result.cost_source, "unknown")
        self.assertTrue(result.accounting_unknown)

    async def test_no_redirect_or_service_fallback_for_any_endpoint(self) -> None:
        for key in (OPENROUTER_KEY, VSEGPT_KEY, *VSEGPT_VIS_KEYS):
            for operation in ("validate", "balance", "models", "completion"):
                with self.subTest(provider=detect_key(key), operation=operation):
                    requests: list[httpx.Request] = []

                    def handler(request: httpx.Request) -> httpx.Response:
                        requests.append(request)
                        return httpx.Response(
                            307, headers={"Location": "https://foreign.invalid/collect"}
                        )

                    router = ProviderRouter(transport=httpx.MockTransport(handler))
                    if operation == "validate":
                        await router.validate_key(key)
                    elif operation == "balance":
                        await router.get_credits(key)
                    elif operation == "models":
                        await router.fetch_models(key)
                    else:
                        await router.complete(
                            key, "vendor/model", MESSAGES, 32, ProviderPriceLimit.zero()
                        )
                    self.assertEqual(len(requests), 1)
                    expected_host = (
                        "openrouter.ai" if key == OPENROUTER_KEY else "api.vsegpt.ru"
                    )
                    self.assertEqual(requests[0].url.host, expected_host)

    async def test_timeout_dispatch_is_once_and_money_stays_unknown(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("fixture", request=request)

        result = await ProviderRouter(transport=httpx.MockTransport(handler)).complete(
            VSEGPT_KEY, "vendor/model", MESSAGES, 32, ProviderPriceLimit.zero()
        )
        self.assertEqual(calls, 1)
        self.assertIs(result.error_type, ChatErrorType.TIMEOUT)
        self.assertTrue(result.accounting_unknown)
        self.assertIsNone(result.cost_amount)

    async def test_vsegpt_documented_400_errors_have_safe_distinct_categories(
        self,
    ) -> None:
        cases = (
            ("User with this API key not found", ChatErrorType.AUTHENTICATION),
            ("Potentially out of budget: fixture", ChatErrorType.PAYMENT_REQUIRED),
            (
                "Model not available on your subscription",
                ChatErrorType.SUBSCRIPTION_REQUIRED,
            ),
            ("Exceeded soft user limit", ChatErrorType.KEY_LIMIT_EXCEEDED),
            ("Maximum context length exceeded", ChatErrorType.CONTEXT_LENGTH_EXCEEDED),
        )
        for message, expected in cases:
            with self.subTest(expected=expected):
                router = ProviderRouter(
                    transport=httpx.MockTransport(
                        lambda _, message=message: httpx.Response(
                            400, json={"error": {"code": 400, "message": message}}
                        )
                    )
                )
                result = await router.complete(
                    VSEGPT_KEY,
                    "openai/gpt-4o-mini",
                    MESSAGES,
                    32,
                    ProviderPriceLimit.zero(),
                )
                self.assertIs(result.error_type, expected)
                self.assertFalse(result.accounting_unknown)
                self.assertNotIn(message, repr(result))

    async def test_partial_reported_token_fields_survive_unknown_cost(self) -> None:
        router = ProviderRouter(
            transport=httpx.MockTransport(lambda _: _completion({"prompt_tokens": 9}))
        )
        result = await router.complete(
            OPENROUTER_KEY, "vendor/model", MESSAGES, 32, ProviderPriceLimit.zero()
        )
        self.assertEqual(result.prompt_tokens, 9)
        self.assertIsNone(result.completion_tokens)
        self.assertIsNone(result.total_tokens)
        self.assertIsNone(result.cost_amount)
        self.assertTrue(result.successful)
        self.assertTrue(result.accounting_unknown)


class ProviderBalanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_documented_400_invalid_key_cannot_replace_a_saved_credential(
        self,
    ) -> None:
        router = ProviderRouter(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    400,
                    json={
                        "error": {
                            "code": 400,
                            "message": "User with this API key not found",
                        }
                    },
                )
            )
        )
        result = await router.validate_key(VSEGPT_KEY)
        self.assertEqual(result.status, KeyValidationStatus.INVALID)
        self.assertFalse(result.accepted)
        self.assertFalse(result.save_allowed)

    async def test_unavailable_vsegpt_check_permits_only_explicit_local_unverified_save(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("fixture", request=request)

        router = ProviderRouter(transport=httpx.MockTransport(handler))
        result = await router.validate_key(VSEGPT_KEY)
        self.assertEqual(result.status, KeyValidationStatus.TIMEOUT)
        self.assertFalse(result.accepted)
        self.assertTrue(result.save_allowed)
        self.assertFalse((await router.validate_key(OPENROUTER_KEY)).save_allowed)

    async def test_openrouter_credits_permission_does_not_change_key_validation(
        self,
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/credits"):
                return httpx.Response(403)
            return httpx.Response(200, json={"data": {"limit_remaining": None}})

        router = ProviderRouter(transport=httpx.MockTransport(handler))
        self.assertTrue((await router.validate_key(OPENROUTER_KEY)).accepted)
        balance = await router.get_credits(OPENROUTER_KEY)
        self.assertIs(balance.status, CreditsStatus.RESTRICTED)
        self.assertIsNone(balance.balance_amount)

    async def test_balance_disabled_allows_explicit_unverified_save_only(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(403)

        result = await ProviderRouter(
            transport=httpx.MockTransport(handler)
        ).validate_key(VSEGPT_KEY)
        self.assertIs(result.status, KeyValidationStatus.UNVERIFIED)
        self.assertFalse(result.authorization_confirmed)
        self.assertFalse(result.accepted)
        self.assertTrue(result.save_allowed)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, "/v1/balance")

    async def test_warning_preserves_exact_rubles_and_confirmed_authorization(
        self,
    ) -> None:
        router = ProviderRouter(
            transport=httpx.MockTransport(
                lambda _: _balance(status=1, credits="0.000000000123456789")
            )
        )
        balance = await router.get_credits(VSEGPT_KEY)
        validation = await router.validate_key(VSEGPT_KEY)
        self.assertIs(balance.status, CreditsStatus.SUCCESS)
        self.assertEqual(balance.balance_amount, Decimal("0.000000000123456789"))
        self.assertIsNone(balance.balance_usd)
        self.assertTrue(balance.warning)
        self.assertTrue(validation.accepted)
        self.assertTrue(validation.warning)
        self.assertIsNone(validation.limit_remaining)
        self.assertNotIn("private diagnostic", repr(balance))

    async def test_subscription_funds_and_invalid_auth_are_separate(self) -> None:
        for response, expected in (
            (_balance(subscription="expired"), CreditsStatus.SUBSCRIPTION_REQUIRED),
            (_balance(credits="0", status=2), CreditsStatus.INSUFFICIENT_FUNDS),
            (_balance(credits="100", status=2), CreditsStatus.ACCOUNT_DISABLED),
            (httpx.Response(401), CreditsStatus.UNAUTHORIZED),
        ):
            router = ProviderRouter(
                transport=httpx.MockTransport(lambda _, response=response: response)
            )
            self.assertIs((await router.get_credits(VSEGPT_KEY)).status, expected)
            validation = await router.validate_key(VSEGPT_KEY)
            self.assertEqual(
                validation.accepted, expected is not CreditsStatus.UNAUTHORIZED
            )

    async def test_malformed_balance_never_becomes_zero_or_leaks_response(self) -> None:
        for credits in (None, "NaN", True, "bad"):
            result = await VsegptClient(
                transport=httpx.MockTransport(
                    lambda _, credits=credits: _balance(credits=credits)
                )
            ).get_credits(VSEGPT_KEY)
            self.assertIs(result.status, CreditsStatus.INVALID_RESPONSE)
            self.assertIsNone(result.balance_amount)


class ProviderCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_vsegpt_public_models_are_unverified_paid_units_not_token_rates(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "openai/gpt-4o-mini",
                            "name": "Text",
                            "pricing": {"prompt": "0.02", "completion": "0.08"},
                            "context_length": "128000",
                            "features": [],
                        },
                        {
                            "id": "emb-openai/embedding",
                            "name": "Embedding",
                            "context_length": "128000",
                        },
                        {
                            "id": "img-openai/image",
                            "name": "Image",
                            "context_length": "128000",
                        },
                        {
                            "id": "text-embedding-ada-002",
                            "name": "Embedding2",
                            "context_length": "128000",
                        },
                        {
                            "id": "unverified-vendor/model",
                            "name": "Unknown capabilities",
                            "context_length": "128000",
                        },
                    ]
                },
            )

        catalog = await ModelCatalogService(
            ProviderRouter(transport=httpx.MockTransport(handler))
        ).get_catalog(VSEGPT_KEY)
        self.assertTrue(catalog.available)
        self.assertEqual(catalog.free_models, ())
        self.assertEqual(len(catalog.paid_models), 1)
        model = catalog.paid_models[0]
        self.assertEqual(model.pricing_unit, PriceUnit.UNKNOWN)
        self.assertFalse(model.pricing_is_complete)
        self.assertFalse(is_free_model(model))
        self.assertEqual(model.currency, Currency.RUB)
        self.assertEqual(model.prompt_price_per_token, Decimal("0"))
        self.assertNotIn("Authorization", requests[0].headers)

    async def test_vsegpt_zero_price_aliases_and_media_are_not_free_text_contracts(
        self,
    ):
        # The public catalogue uses the same two pricing fields for aliases and
        # media. Neither declares complete zero-cost text-chat billing.
        items = [
            {
                "id": model_id,
                "name": model_id,
                "context_length": "128000",
                "pricing": {"prompt": "0", "completion": "0"},
                "features": [],
                "chat_na_msg": "",
            }
            for model_id in (
                "perplexity/latest-small-online",
                "perplexity/latest-large-online",
                "img-openai/image",
                "music-suno/song",
            )
        ]
        service = ModelCatalogService(
            ProviderRouter(
                transport=httpx.MockTransport(
                    lambda _request: httpx.Response(200, json={"data": items})
                )
            )
        )
        catalog = await service.get_catalog(VSEGPT_VIS_KEYS[0])
        self.assertTrue(catalog.available)
        self.assertEqual(catalog.free_models, ())
        self.assertEqual(len(catalog.paid_models), 2)
        for model in catalog.paid_models:
            self.assertEqual(model.provider_id, ProviderId.VSEGPT)
            self.assertEqual(model.currency, Currency.RUB)
            self.assertFalse(model.pricing_is_complete)
            self.assertFalse(is_free_model(model))

    async def test_cache_isolated_by_provider_and_credential_identity(self) -> None:
        calls: list[str] = []

        class Reader:
            async def fetch_models(self, api_key: str):
                calls.append(api_key)
                return ()

        service = ModelCatalogService(Reader())
        for key in (
            OPENROUTER_KEY,
            VSEGPT_KEY,
            "sk-or-v1-replacement-key",
            OPENROUTER_KEY,
        ):
            await service.get_catalog(key)
        self.assertEqual(len(calls), 3)
        self.assertIsNone(service.peek_catalog("sk-or-vv-unseen-key"))
        self.assertIsNotNone(service.peek_catalog(OPENROUTER_KEY))
        service.clear_cache()
        self.assertIsNone(service.peek_catalog(OPENROUTER_KEY))

    async def test_revoked_inflight_catalog_cannot_seed_replacement_cache(self) -> None:
        started, release = asyncio.Event(), asyncio.Event()

        class Reader:
            async def fetch_models(self, api_key: str):
                started.set()
                await release.wait()
                return ()

        service = ModelCatalogService(Reader())
        old = asyncio.create_task(service.get_catalog(VSEGPT_KEY))
        await started.wait()
        service.clear_cache()
        release.set()
        result = await old
        self.assertFalse(result.available)
        self.assertIsNone(service.peek_catalog())
        self.assertIsNone(service.peek_catalog(VSEGPT_KEY))
