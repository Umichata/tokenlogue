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
    CreditsResult,
    CreditsStatus,
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

    async def test_preserves_tiny_and_high_precision_limits_without_float_rounding(
        self,
    ) -> None:
        for raw, expected, status in (
            (
                b"0.000000000000000000000000123456789",
                Decimal("0.000000000000000000000000123456789"),
                KeyValidationStatus.ACCEPTED,
            ),
            (
                b'"123456789.123456789123456789"',
                Decimal("123456789.123456789123456789"),
                KeyValidationStatus.ACCEPTED,
            ),
            (
                b"-0.000000000000000000000000123456789",
                Decimal("-0.000000000000000000000000123456789"),
                KeyValidationStatus.ACCEPTED_LIMIT_EXHAUSTED,
            ),
        ):
            with self.subTest(status=status, negative=expected < 0):
                result = await self._validate(
                    lambda _, value=raw: httpx.Response(
                        200, content=b'{"data":{"limit_remaining":' + value + b"}}"
                    )
                )
                self.assertEqual(result.status, status)
                self.assertEqual(result.limit_remaining, expected)
                self.assertNotEqual(result.limit_remaining, Decimal("0"))
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

    async def test_invalid_limit_shapes_never_become_a_numeric_balance(self) -> None:
        for content in (
            b'{"data":{"limit_remaining":true}}',
            b'{"data":{"limit_remaining":false}}',
            b'{"data":{"limit_remaining":""}}',
            b'{"data":{"limit_remaining":"Infinity"}}',
            b'{"data":{"limit_remaining":"-Infinity"}}',
            b'{"data":{"limit_remaining":[]}}',
            b'{"data":{"limit_remaining":{}}}',
            b'{"data":[]}',
            b"[]",
        ):
            with self.subTest(content=content):
                result = await self._validate(
                    lambda _, body=content: httpx.Response(200, content=body)
                )
                self.assertEqual(result.status, KeyValidationStatus.INVALID_RESPONSE)
                self.assertIsNone(result.limit_remaining)
                self.assertFalse(result.accepted)

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


class OpenRouterCreditsTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_current_user_key_for_account_endpoint(self) -> None:
        observed: list[bool] = []

        def handler(request: httpx.Request) -> httpx.Response:
            observed.append(
                str(request.url) == "https://openrouter.ai/api/v1/credits"
                and request.headers.get("Authorization") == f"Bearer {TEST_CREDENTIAL}"
            )
            return httpx.Response(
                200, content=b'{"data":{"total_credits":100.50,"total_usage":25.75}}'
            )

        result = await self._credits(handler)

        self.assertEqual(observed, [True])
        self.assertEqual(result.status, CreditsStatus.SUCCESS)
        self.assertEqual(result.balance_usd, Decimal("74.75"))
        self.assertEqual(result.total_credits, Decimal("100.50"))
        self.assertEqual(result.total_usage, Decimal("25.75"))

    async def test_positive_zero_and_small_negative_balances_are_real_values(
        self,
    ) -> None:
        for credits, usage, expected in (
            (b"2.50", b"1.25", "1.25"),
            (b"1", b"1", "0"),
            (b"1", b"1.000123", "-0.000123"),
            (b"0", b"0.000000000000000000000000000001", "-1E-30"),
            (
                b"123456789012345678901234567890.12",
                b"0.01",
                "123456789012345678901234567890.11",
            ),
        ):
            with self.subTest(expected=expected):
                content = (
                    b'{"data":{"total_credits":'
                    + credits
                    + b',"total_usage":'
                    + usage
                    + b"}}"
                )
                result = await self._credits(
                    lambda _, body=content: httpx.Response(200, content=body)
                )
                self.assertEqual(result.status, CreditsStatus.SUCCESS)
                self.assertEqual(result.balance_usd, Decimal(expected))

    async def test_invalid_amount_in_either_field_never_becomes_zero(self) -> None:
        for field in ("total_credits", "total_usage"):
            for raw in (
                b"null",
                b"true",
                b"false",
                b'""',
                b'"bad"',
                b"[]",
                b"{}",
                b"NaN",
                b"Infinity",
                b"-Infinity",
                b'"NaN"',
                b'"sNaN"',
                b'"Infinity"',
            ):
                with self.subTest(field=field, raw=raw):
                    other = (
                        "total_usage" if field == "total_credits" else "total_credits"
                    )
                    content = (
                        b'{"data":{"'
                        + field.encode()
                        + b'":'
                        + raw
                        + b',"'
                        + other.encode()
                        + b'":1}}'
                    )
                    result = await self._credits(
                        lambda _, body=content: httpx.Response(200, content=body)
                    )
                    self.assertEqual(result.status, CreditsStatus.INVALID_RESPONSE)
                    self.assertIsNone(result.balance_usd)
                    self.assertIsNone(result.total_credits)
                    self.assertIsNone(result.total_usage)

    async def test_missing_fields_bad_json_and_wrong_shapes_are_unavailable(
        self,
    ) -> None:
        for content in (
            b"",
            b"not-json",
            b"\xff",
            b"[]",
            b'{"data":[]}',
            b'{"data":{}}',
            b'{"data":{"total_credits":1}}',
            b'{"data":{"total_usage":1}}',
        ):
            with self.subTest(content=content):
                result = await self._credits(
                    lambda _, body=content: httpx.Response(200, content=body)
                )
                self.assertEqual(result.status, CreditsStatus.INVALID_RESPONSE)
                self.assertIsNone(result.balance_usd)

    async def test_statuses_do_not_expose_response_body_or_invalidate_inference(
        self,
    ) -> None:
        for code, expected in (
            (401, CreditsStatus.UNAUTHORIZED),
            (403, CreditsStatus.RESTRICTED),
            (429, CreditsStatus.RATE_LIMITED),
            (500, CreditsStatus.SERVER_ERROR),
            (503, CreditsStatus.SERVER_ERROR),
            (302, CreditsStatus.UNEXPECTED_STATUS),
        ):
            with self.subTest(code=code):
                result = await self._credits(
                    lambda _, status=code: httpx.Response(
                        status, content=b"private-response-marker"
                    )
                )
                self.assertEqual(result.status, expected)
                self.assertIsNone(result.balance_usd)
                self.assertNotIn("private-response-marker", repr(result))
                self.assertNotIn(TEST_CREDENTIAL, repr(result))
        client = OpenRouterClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    403 if request.url.path.endswith("credits") else 200,
                    json={"data": {"limit_remaining": 10}},
                )
            )
        )
        self.assertEqual(
            (await client.get_credits(TEST_CREDENTIAL)).status, CreditsStatus.RESTRICTED
        )
        self.assertTrue((await client.validate_key(TEST_CREDENTIAL)).accepted)

    async def test_transport_errors_are_safe_unavailable_results(self) -> None:
        for error, status in (
            (httpx.ReadTimeout("private-timeout-marker"), CreditsStatus.TIMEOUT),
            (httpx.ConnectError("private-network-marker"), CreditsStatus.NETWORK_ERROR),
            (
                httpx.RemoteProtocolError("private-protocol-marker"),
                CreditsStatus.NETWORK_ERROR,
            ),
            (ImportError("private-import-marker"), CreditsStatus.NETWORK_ERROR),
        ):
            with self.subTest(status=status):

                def handler(_request: httpx.Request) -> httpx.Response:
                    raise error

                result = await self._credits(handler)
                self.assertEqual(result.status, status)
                self.assertIsNone(result.balance_usd)
                self.assertNotIn("private", repr(result))

    async def test_tls_failure_is_reported_without_exception_text(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            try:
                raise ssl.SSLError("private-tls-marker")
            except ssl.SSLError as cause:
                raise httpx.ConnectError("private-connection-marker") from cause

        result = await self._credits(handler)

        self.assertEqual(result.status, CreditsStatus.TLS_ERROR)
        self.assertNotIn("private", repr(result))

    async def test_preserves_http_client_policy_and_timeout(self) -> None:
        captured: dict[str, object] = {}

        class CapturingClient:
            def __init__(self, **kwargs) -> None:
                captured.update(kwargs)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args) -> None:
                return None

            async def get(self, *_args, **_kwargs) -> httpx.Response:
                return httpx.Response(403)

        timeout = httpx.Timeout(2.0)
        with patch("api.openrouter.httpx.AsyncClient", CapturingClient):
            result = await OpenRouterClient(timeout=timeout).get_credits(
                TEST_CREDENTIAL
            )
        self.assertEqual(result.status, CreditsStatus.RESTRICTED)
        self.assertIs(captured.get("trust_env"), False)
        self.assertIs(captured.get("follow_redirects"), False)
        self.assertIs(captured.get("timeout"), timeout)

    async def test_empty_key_does_not_send_a_request(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            self.fail("empty key must not reach transport")

        result = await self._credits(handler, key="  ")
        self.assertEqual(result.status, CreditsStatus.UNAUTHORIZED)

    async def _credits(self, handler, *, key=TEST_CREDENTIAL) -> CreditsResult:
        return await OpenRouterClient(
            transport=httpx.MockTransport(handler),
            timeout=0.1,
        ).get_credits(key)


if __name__ == "__main__":
    unittest.main()
