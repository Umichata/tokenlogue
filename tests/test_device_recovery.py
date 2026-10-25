"""Проверки принадлежности и отмены системного подтверждения устройства."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import flet as ft
import msgpack
from flet.messaging.protocol import configure_encode_object_for_msgpack

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.device_recovery import (  # noqa: E402
    DeviceRecovery,
    RecoveryRequest,
    RecoveryStatus,
)


class DeviceRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def request(self, attempt: str = "attempt-one") -> RecoveryRequest:
        return RecoveryRequest(attempt, "database-one", 7, "Reason", "Title", "Cancel")

    def reply(self, request: RecoveryRequest, status: str = "success") -> dict:
        return {
            "attempt_id": request.attempt_id,
            "database_id": request.database_id,
            "epoch": request.epoch,
            "status": status,
        }

    def test_flet_transport_does_not_serialize_private_attempt_state(self):
        service = DeviceRecovery()
        service._active_attempt = "private-attempt"
        service._used_attempts.add("private-used-attempt")
        data = msgpack.packb(
            service, default=configure_encode_object_for_msgpack(ft.BaseControl)
        )
        assert isinstance(data, bytes)
        result = msgpack.unpackb(data)
        assert isinstance(result, dict)
        self.assertEqual(result["_c"], "TokenlogueDeviceRecovery")
        self.assertNotIn(b"private", data)
        self.assertNotIn("_active_attempt", result)
        self.assertNotIn("_used_attempts", result)

    async def test_recovery_capability_requires_android_api_30_and_never_authenticates(
        self,
    ):
        for api, native_supported, expected in (
            (29, True, False),
            (30, True, True),
            (36, True, True),
            (36, False, False),
            (True, True, False),
        ):
            with self.subTest(api=api, supported=native_supported):
                service = DeviceRecovery()
                service._invoke_method = AsyncMock(
                    return_value={
                        "api_level": api,
                        "recovery_supported": native_supported,
                    }
                )
                self.assertEqual(await service.supports_recovery(), expected)
                service._invoke_method.assert_awaited_once_with(
                    "capabilities", timeout=10
                )
                self.assertFalse(service.challenge_in_progress)

    async def test_recovery_capability_failure_is_closed(self):
        service = DeviceRecovery()
        service._invoke_method = AsyncMock(
            side_effect=RuntimeError("private platform details")
        )
        self.assertFalse(await service.supports_recovery())
        self.assertFalse(service.challenge_in_progress)

    async def test_secure_storage_barrier_requires_exact_true(self):
        service = DeviceRecovery()
        service._invoke_method = AsyncMock(return_value=True)
        await service.sync_secure_storage()
        service._invoke_method.assert_awaited_once_with(
            "sync_secure_storage", timeout=30
        )
        for value in (False, None, "true", 1):
            with self.subTest(value=value):
                service._invoke_method = AsyncMock(return_value=value)
                with self.assertRaisesRegex(RuntimeError, "secure_storage_sync_failed"):
                    await service.sync_secure_storage()

    async def test_secure_storage_barrier_hides_backend_exception(self):
        service = DeviceRecovery()
        service._invoke_method = AsyncMock(
            side_effect=RuntimeError("private storage value")
        )
        with self.assertRaisesRegex(
            RuntimeError, "secure_storage_sync_failed"
        ) as caught:
            await service.sync_secure_storage()
        self.assertNotIn("private", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    async def test_valid_native_result_is_bound_to_request_and_cannot_be_reused(self):
        service = DeviceRecovery()
        request = self.request()
        service._invoke_method = AsyncMock(return_value=self.reply(request))
        result = await service.authenticate(request)
        self.assertEqual(result.status, RecoveryStatus.SUCCESS)
        self.assertEqual(result.request, request)
        repeated = await service.authenticate(request)
        self.assertEqual(repeated.status, RecoveryStatus.EXPIRED)
        self.assertEqual(service._invoke_method.await_count, 1)

    async def test_mismatched_fields_never_authorize(self):
        for key, value in (
            ("attempt_id", "other"),
            ("database_id", "other"),
            ("epoch", 8),
        ):
            with self.subTest(key=key):
                service = DeviceRecovery()
                request = self.request()
                reply = self.reply(request)
                reply[key] = value
                service._invoke_method = AsyncMock(return_value=reply)
                self.assertEqual(
                    (await service.authenticate(request)).status, RecoveryStatus.EXPIRED
                )

    async def test_unrecognized_native_error_is_safe(self):
        service = DeviceRecovery()
        service._invoke_method = AsyncMock(
            side_effect=RuntimeError("private provider text")
        )
        result = await service.authenticate(self.request())
        self.assertEqual(result.status, RecoveryStatus.ERROR)
        self.assertNotIn("private", repr(result))

    async def test_cancel_invalidates_before_native_await_and_drops_late_success(self):
        request = self.request()
        service = DeviceRecovery()
        started = asyncio.Event()
        finish = asyncio.Event()

        async def invoke(name, arguments=None, **kwargs):
            if name == "authenticate":
                started.set()
                await finish.wait()
                return self.reply(request)
            finish.set()
            await asyncio.sleep(0)
            return True

        service._invoke_method = AsyncMock(side_effect=invoke)
        pending = asyncio.create_task(service.authenticate(request))
        await started.wait()
        await service.cancel(request.attempt_id)
        self.assertEqual((await pending).status, RecoveryStatus.EXPIRED)

    async def test_overlap_refused_without_starting_second_prompt(self):
        service = DeviceRecovery()
        request = self.request()
        gate = asyncio.Event()

        async def invoke(*args, **kwargs):
            await gate.wait()
            return self.reply(request)

        service._invoke_method = AsyncMock(side_effect=invoke)
        pending = asyncio.create_task(service.authenticate(request))
        await asyncio.sleep(0)
        self.assertEqual(
            (await service.authenticate(self.request("two"))).status,
            RecoveryStatus.BUSY,
        )
        gate.set()
        await pending
        self.assertEqual(service._invoke_method.await_count, 1)

    async def test_timeout_cancels_native_and_does_not_authorize(self):
        service = DeviceRecovery()
        calls = []

        async def invoke(name, arguments=None, **kwargs):
            calls.append(name)
            if name == "authenticate":
                await asyncio.Event().wait()
            return True

        service._invoke_method = AsyncMock(side_effect=invoke)
        result = await service.authenticate(self.request(), timeout=0.01)
        self.assertEqual(result.status, RecoveryStatus.TIMEOUT)
        self.assertEqual(calls, ["authenticate", "cancel"])

    async def test_native_capability_is_never_success(self):
        service = DeviceRecovery()
        service._invoke_method = AsyncMock(return_value=True)
        self.assertEqual(
            (await service.authenticate(self.request())).status, RecoveryStatus.ERROR
        )


if __name__ == "__main__":
    unittest.main()
