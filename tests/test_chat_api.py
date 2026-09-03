"""Офлайн-тесты нестримингового клиента Chat Completions."""

from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.chat_completions import (  # noqa: E402
    DEFAULT_CHAT_TIMEOUT,
    OPENROUTER_CHAT_URL,
    ChatCompletionsClient,
)
from chat.context import ContextMessage  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import MessageRole, ProviderPriceLimit  # noqa: E402

TEST_CREDENTIAL = "completion-test-credential"
MODEL_ID = "vendor/test-model"


class ChatCompletionsClientTests(unittest.IsolatedAsyncioTestCase):
    def test_all_timeout_phases_are_bounded(self) -> None:
        self.assertEqual(DEFAULT_CHAT_TIMEOUT.connect, 5.0)
        self.assertEqual(DEFAULT_CHAT_TIMEOUT.read, 45.0)
        self.assertEqual(DEFAULT_CHAT_TIMEOUT.write, 10.0)
        self.assertEqual(DEFAULT_CHAT_TIMEOUT.pool, 5.0)

    async def test_single_model_payload_allows_only_provider_fallback(self) -> None:
        observed: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["method"] = request.method
            observed["url"] = str(request.url)
            observed["headers"] = dict(request.headers)
            observed["payload"] = json.loads(
                request.content,
                parse_float=Decimal,
                parse_int=Decimal,
            )
            return _success_response()

        result = await _client(handler).complete(
            TEST_CREDENTIAL,
            MODEL_ID,
            (ContextMessage(MessageRole.USER, "hello"),),
            128,
            ProviderPriceLimit.zero(),
        )

        self.assertTrue(result.successful)
        self.assertEqual(observed["method"], "POST")
        self.assertEqual(observed["url"], OPENROUTER_CHAT_URL)
        payload = observed["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(
            set(payload),
            {"model", "messages", "max_completion_tokens", "stream", "provider"},
        )
        self.assertEqual(payload["max_completion_tokens"], Decimal("128"))
        self.assertEqual(payload["model"], MODEL_ID)
        self.assertNotIn("max_tokens", payload)
        self.assertNotIn("models", payload)
        for forbidden in (
            "tools",
            "plugins",
            "web_search",
            "models",
            "fallbacks",
            "metadata",
            "user",
            "session_id",
        ):
            self.assertNotIn(forbidden, payload)
        self.assertEqual(
            payload["provider"],
            {
                "allow_fallbacks": True,
                "max_price": {
                    "prompt": Decimal("0"),
                    "completion": Decimal("0"),
                    "request": Decimal("0"),
                },
            },
        )
        headers = observed["headers"]
        assert isinstance(headers, dict)
        self.assertNotIn("http-referer", headers)
        self.assertNotIn("x-title", headers)

    async def test_paid_max_price_preserves_decimal_values(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(
                json.loads(
                    request.content,
                    parse_float=Decimal,
                    parse_int=Decimal,
                )
            )
            return _success_response()

        await _client(handler).complete(
            TEST_CREDENTIAL,
            MODEL_ID,
            (ContextMessage(MessageRole.USER, "hello"),),
            32,
            ProviderPriceLimit(
                prompt_per_token=Decimal("0.000003"),
                completion_per_token=Decimal("0.000015"),
                request=Decimal("0.001"),
            ),
        )

        provider = captured["provider"]
        assert isinstance(provider, dict)
        self.assertEqual(
            provider["max_price"],
            {
                "prompt": Decimal("3"),
                "completion": Decimal("15"),
                "request": Decimal("0.001"),
            },
        )

    async def test_wire_prices_cover_small_large_and_trailing_zero_decimals(
        self,
    ) -> None:
        cases = (
            ProviderPriceLimit(
                Decimal("0.000000000000000003"),
                Decimal("0.000000000000000015"),
                Decimal("0.000000000000000001"),
            ),
            ProviderPriceLimit(
                Decimal("123456789.123456789"),
                Decimal("987654321.987654321"),
                Decimal("123456789.0001000"),
            ),
            ProviderPriceLimit(
                Decimal("0.000003000"),
                Decimal("0.000015000"),
                Decimal("0.001000"),
            ),
        )
        multiplier = Decimal("1000000")
        for price_limit in cases:
            with self.subTest(price_limit=price_limit):
                captured: dict[str, object] = {}

                def handler(request: httpx.Request) -> httpx.Response:
                    captured.update(
                        json.loads(
                            request.content,
                            parse_float=Decimal,
                            parse_int=Decimal,
                        )
                    )
                    return _success_response()

                await _client(handler).complete(
                    TEST_CREDENTIAL,
                    MODEL_ID,
                    (ContextMessage(MessageRole.USER, "hello"),),
                    32,
                    price_limit,
                )

                provider = captured["provider"]
                assert isinstance(provider, dict)
                wire = provider["max_price"]
                assert isinstance(wire, dict)
                self.assertEqual(
                    wire["prompt"],
                    price_limit.prompt_per_token * multiplier,
                )
                self.assertEqual(
                    wire["completion"],
                    price_limit.completion_per_token * multiplier,
                )
                self.assertEqual(wire["request"], price_limit.request)
                self.assertIsInstance(wire["prompt"], Decimal)
                self.assertIsInstance(wire["completion"], Decimal)
                self.assertIsInstance(wire["request"], Decimal)

    async def test_nonfinite_and_negative_wire_prices_never_reach_http(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return _success_response()

        invalid_limits = (
            ProviderPriceLimit(Decimal("-0.1"), Decimal("0"), Decimal("0")),
            ProviderPriceLimit(Decimal("NaN"), Decimal("0"), Decimal("0")),
            ProviderPriceLimit(Decimal("Infinity"), Decimal("0"), Decimal("0")),
        )
        for price_limit in invalid_limits:
            with self.subTest(price_limit=price_limit):
                result = await _client(handler).complete(
                    TEST_CREDENTIAL,
                    MODEL_ID,
                    (ContextMessage(MessageRole.USER, "hello"),),
                    32,
                    price_limit,
                )
                self.assertEqual(result.error_type, ChatErrorType.INVALID_REQUEST)
        self.assertEqual(calls, 0)

    async def test_parses_success_and_exact_usage_cost(self) -> None:
        content = (
            b'{"id":"generation-1","model":"vendor/actual",'
            b'"choices":[{"finish_reason":"stop",'
            b'"message":{"content":"answer"}}],'
            b'"usage":{"prompt_tokens":7,"completion_tokens":3,'
            b'"total_tokens":8,"cost":0.000000123456789}}'
        )

        result = await self._complete_with_response(
            httpx.Response(
                200,
                content=content,
                headers={"Content-Type": "application/json"},
            )
        )

        self.assertEqual(result.content, "answer")
        self.assertEqual(result.generation_id, "generation-1")
        self.assertEqual(result.actual_model_id, "vendor/actual")
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.prompt_tokens, 7)
        self.assertEqual(result.completion_tokens, 3)
        self.assertEqual(result.total_tokens, 10)
        self.assertEqual(result.cost_usd, Decimal("0.000000123456789"))
        self.assertTrue(result.successful)
        self.assertNotIn("answer", repr(result))

    async def test_length_is_successful_but_truncated(self) -> None:
        response = _success_response(finish_reason="length")
        result = await self._complete_with_response(response)

        self.assertTrue(result.successful)
        self.assertTrue(result.truncated)
        self.assertIsNone(result.error_type)

    async def test_partial_finish_error_is_preserved_but_not_successful(self) -> None:
        result = await self._complete_with_response(
            _success_response(finish_reason="error", content="partial answer")
        )

        self.assertEqual(result.content, "partial answer")
        self.assertEqual(result.finish_reason, "error")
        self.assertFalse(result.successful)
        self.assertEqual(result.error_type, ChatErrorType.PROVIDER_UNAVAILABLE)
        self.assertTrue(result.has_complete_usage)

    async def test_refusal_without_content_has_separate_safe_state(self) -> None:
        response = _success_response(finish_reason="refusal")
        payload = json.loads(response.content)
        payload["choices"][0]["message"]["content"] = None

        result = await self._complete_with_response(httpx.Response(200, json=payload))

        self.assertEqual(result.error_type, ChatErrorType.REFUSAL)
        self.assertEqual(result.content, "")
        self.assertTrue(result.has_complete_usage)

    async def test_top_level_error_at_200_without_usage_is_accounting_unknown(
        self,
    ) -> None:
        result = await self._complete_with_response(
            httpx.Response(
                200,
                json={"error": {"code": "provider_overloaded", "message": "hidden"}},
            )
        )

        self.assertEqual(result.error_type, ChatErrorType.PROVIDER_OVERLOADED)
        self.assertTrue(result.accounting_unknown)
        self.assertNotIn("hidden", repr(result))

    async def test_top_level_numeric_402_is_payment_required(self) -> None:
        result = await self._complete_with_response(
            httpx.Response(200, json={"error": {"code": 402}})
        )

        self.assertEqual(result.error_type, ChatErrorType.PAYMENT_REQUIRED)
        self.assertTrue(result.accounting_unknown)

    async def test_missing_choices_is_malformed(self) -> None:
        result = await self._complete_with_response(
            httpx.Response(200, json={"id": "generation", "usage": _usage()})
        )

        self.assertEqual(result.error_type, ChatErrorType.MALFORMED_RESPONSE)
        self.assertTrue(result.has_complete_usage)
        self.assertFalse(result.accounting_unknown)

    async def test_success_requires_json_content_type(self) -> None:
        result = await self._complete_with_response(
            httpx.Response(
                200,
                content=b"not-json",
                headers={"Content-Type": "text/plain"},
            )
        )

        self.assertEqual(result.error_type, ChatErrorType.MALFORMED_RESPONSE)
        self.assertTrue(result.accounting_unknown)

    async def test_http_error_categories_and_retry_after(self) -> None:
        cases = (
            (400, None, ChatErrorType.INVALID_REQUEST),
            (401, None, ChatErrorType.AUTHENTICATION),
            (402, None, ChatErrorType.PAYMENT_REQUIRED),
            (403, None, ChatErrorType.PERMISSION_DENIED),
            (408, None, ChatErrorType.TIMEOUT),
            (429, None, ChatErrorType.RATE_LIMIT_EXCEEDED),
            (502, None, ChatErrorType.PROVIDER_UNAVAILABLE),
            (503, None, ChatErrorType.PROVIDER_UNAVAILABLE),
            (529, None, ChatErrorType.PROVIDER_OVERLOADED),
            (400, "context_length_exceeded", ChatErrorType.CONTEXT_LENGTH_EXCEEDED),
            (400, "max_tokens_exceeded", ChatErrorType.MAX_TOKENS_EXCEEDED),
            (400, "token_limit_exceeded", ChatErrorType.TOKEN_LIMIT_EXCEEDED),
        )
        for status, code, expected in cases:
            with self.subTest(status=status, code=code):
                error = {"message": "provider detail"}
                if code is not None:
                    error["code"] = code
                result = await self._complete_with_response(
                    httpx.Response(
                        status,
                        json={"error": error},
                        headers={"Retry-After": "2.1"},
                    )
                )
                self.assertEqual(result.error_type, expected)
                self.assertEqual(result.retry_after, 3)
                self.assertNotIn("provider detail", repr(result))

    async def test_403_content_policy_does_not_become_authentication_error(
        self,
    ) -> None:
        result = await self._complete_with_response(
            httpx.Response(
                403,
                json={"error": {"code": "content_policy_violation"}},
            )
        )

        self.assertEqual(result.error_type, ChatErrorType.CONTENT_POLICY_VIOLATION)

    async def test_invalid_usage_is_not_invented(self) -> None:
        response = _success_response()
        payload = json.loads(response.content)
        payload["usage"]["cost"] = "NaN"

        result = await self._complete_with_response(httpx.Response(200, json=payload))

        self.assertIsNone(result.prompt_tokens)
        self.assertIsNone(result.completion_tokens)
        self.assertIsNone(result.total_tokens)
        self.assertIsNone(result.cost_usd)
        self.assertTrue(result.accounting_unknown)

    async def test_5xx_without_usage_is_unknown_but_429_is_released(self) -> None:
        unavailable = await self._complete_with_response(
            httpx.Response(503, json={"error": {"code": "provider_unavailable"}})
        )
        rate_limited = await self._complete_with_response(
            httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}})
        )

        self.assertTrue(unavailable.accounting_unknown)
        self.assertFalse(rate_limited.accounting_unknown)

    async def test_timeout_is_ambiguous_and_does_not_retry(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("injected", request=request)

        result = await _client(handler).complete(
            TEST_CREDENTIAL,
            MODEL_ID,
            (ContextMessage(MessageRole.USER, "hello"),),
            16,
            ProviderPriceLimit.zero(),
        )

        self.assertEqual(calls, 1)
        self.assertEqual(result.error_type, ChatErrorType.TIMEOUT)
        self.assertTrue(result.accounting_unknown)

    async def _complete_with_response(
        self,
        response: httpx.Response,
    ):
        return await _client(lambda _request: response).complete(
            TEST_CREDENTIAL,
            MODEL_ID,
            (ContextMessage(MessageRole.USER, "hello"),),
            32,
            ProviderPriceLimit.zero(),
        )


def _client(handler) -> ChatCompletionsClient:
    return ChatCompletionsClient(transport=httpx.MockTransport(handler))


def _success_response(
    *,
    finish_reason: str = "stop",
    content: str = "answer",
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "generation-1",
            "model": "vendor/actual",
            "choices": [
                {
                    "finish_reason": finish_reason,
                    "message": {"content": content},
                }
            ],
            "usage": _usage(),
        },
    )


def _usage() -> dict[str, object]:
    return {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
        "cost": "0.0001",
    }


if __name__ == "__main__":
    unittest.main()
