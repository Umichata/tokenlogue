"""Офлайн-тесты проверки OpenRouter API-ключа."""

from __future__ import annotations

import ssl
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import (  # noqa: E402
    KeyValidationResult,
    KeyValidationStatus,
    OpenRouterClient,
)

TEST_CREDENTIAL = "unit-test-credential"


class OpenRouterClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_positive_decimal_limit(self) -> None:
        observed_request = {"valid": False}

        def handler(request: httpx.Request) -> httpx.Response:
            observed_request["valid"] = (
                str(request.url) == "https://openrouter.ai/api/v1/key"
                and request.headers.get("Authorization") == f"Bearer {TEST_CREDENTIAL}"
            )
            return httpx.Response(200, json={"data": {"limit_remaining": 12.34}})

        result = await self._validate(handler)

        self.assertTrue(observed_request["valid"])
        self.assertEqual(result.status, KeyValidationStatus.ACCEPTED)
        self.assertEqual(result.limit_remaining, Decimal("12.34"))
        self.assertTrue(result.accepted)

    async def test_accepts_null_limit(self) -> None:
        result = await self._validate(
            lambda _: httpx.Response(200, json={"data": {"limit_remaining": None}})
        )

        self.assertEqual(result.status, KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT)
        self.assertIsNone(result.limit_remaining)
        self.assertTrue(result.accepted)

    async def test_accepts_valid_key_with_zero_limit(self) -> None:
        result = await self._validate(
            lambda _: httpx.Response(200, json={"data": {"limit_remaining": 0}})
        )

        self.assertEqual(
            result.status,
            KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
        )
        self.assertEqual(result.limit_remaining, Decimal("0"))
        self.assertTrue(result.accepted)

    async def test_accepts_valid_key_with_negative_key_limit(self) -> None:
        result = await self._validate(
            lambda _: httpx.Response(200, content=b'{"data":{"limit_remaining":-0.01}}')
        )

        self.assertEqual(
            result.status,
            KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
        )
        self.assertEqual(result.limit_remaining, Decimal("-0.01"))
        self.assertTrue(result.accepted)

    async def test_free_tier_flag_does_not_block_valid_key(self) -> None:
        result = await self._validate(
            lambda _: httpx.Response(
                200,
                json={
                    "data": {
                        "limit_remaining": 0,
                        "is_free_tier": True,
                    }
                },
            )
        )

        self.assertEqual(
            result.status,
            KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
        )
        self.assertTrue(result.accepted)

    async def test_rejects_unauthorized_key_with_401(self) -> None:
        result = await self._validate(lambda _: httpx.Response(401))

        self.assertEqual(result.status, KeyValidationStatus.INVALID)

    async def test_reports_permission_denial_with_403(self) -> None:
        result = await self._validate(lambda _: httpx.Response(403))

        self.assertEqual(result.status, KeyValidationStatus.RESTRICTED)

    async def test_reports_timeout_separately(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("test timeout", request=request)

        result = await self._validate(handler)

        self.assertEqual(result.status, KeyValidationStatus.TIMEOUT)

    async def test_reports_network_failure_separately(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("test connection failure", request=request)

        result = await self._validate(handler)

        self.assertEqual(result.status, KeyValidationStatus.NETWORK_ERROR)

    async def test_reports_tls_failure_separately(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            try:
                raise ssl.SSLError("injected TLS failure")
            except ssl.SSLError as cause:
                raise httpx.ConnectError(
                    "connection failed", request=request
                ) from cause

        result = await self._validate(handler)

        self.assertEqual(result.status, KeyValidationStatus.TLS_ERROR)

    async def test_reports_rate_limit_and_server_failure(self) -> None:
        for status_code, expected in (
            (429, KeyValidationStatus.RATE_LIMITED),
            (503, KeyValidationStatus.SERVER_ERROR),
        ):
            with self.subTest(status_code=status_code):
                result = await self._validate(
                    lambda _, code=status_code: httpx.Response(code)
                )
                self.assertEqual(result.status, expected)

    async def test_rejects_invalid_json(self) -> None:
        result = await self._validate(
            lambda _: httpx.Response(200, content=b"not-json")
        )

        self.assertEqual(result.status, KeyValidationStatus.INVALID_RESPONSE)

    async def test_rejects_invalid_data_shape(self) -> None:
        result = await self._validate(lambda _: httpx.Response(200, json={"data": {}}))

        self.assertEqual(result.status, KeyValidationStatus.INVALID_RESPONSE)

    async def test_rejects_non_finite_limit(self) -> None:
        result = await self._validate(
            lambda _: httpx.Response(
                200,
                content=b'{"data":{"limit_remaining":"NaN"}}',
            )
        )

        self.assertEqual(result.status, KeyValidationStatus.INVALID_RESPONSE)

    async def test_error_body_is_not_returned(self) -> None:
        marker = "private-error-body-marker"
        result = await self._validate(
            lambda _: httpx.Response(401, content=marker.encode("ascii"))
        )

        self.assertEqual(result.status, KeyValidationStatus.INVALID)
        self.assertNotIn(marker, repr(result))

    async def test_does_not_inherit_proxy_environment(self) -> None:
        captured: dict[str, object] = {}

        class CapturingClient:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args) -> None:
                return None

            async def get(self, *_args, **_kwargs) -> httpx.Response:
                return httpx.Response(401)

        with patch("api.openrouter.httpx.AsyncClient", CapturingClient):
            result = await OpenRouterClient().validate_key(TEST_CREDENTIAL)

        self.assertEqual(result.status, KeyValidationStatus.INVALID)
        self.assertIs(captured.get("trust_env"), False)

    async def test_missing_optional_transport_is_a_network_error(self) -> None:
        with patch("api.openrouter.httpx.AsyncClient", side_effect=ImportError):
            result = await OpenRouterClient().validate_key(TEST_CREDENTIAL)

        self.assertEqual(result.status, KeyValidationStatus.NETWORK_ERROR)

    async def _validate(self, handler) -> KeyValidationResult:
        client = OpenRouterClient(
            transport=httpx.MockTransport(handler),
            timeout=0.1,
        )
        return await client.validate_key(TEST_CREDENTIAL)


if __name__ == "__main__":
    unittest.main()
