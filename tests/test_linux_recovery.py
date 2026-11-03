"""Отказ по умолчанию и свежесть Linux polkit proof без настоящих credentials."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.device_recovery import (  # noqa: E402
    RecoveryRequest,
    RecoveryStatus,
)
from platform_security.linux_dbus import DBusError, DBusReply  # noqa: E402
from platform_security.linux_recovery import (  # noqa: E402
    ACTION_ID,
    LinuxRecovery,
    ProcessIdentity,
)


class FakeBus:
    def __init__(self):
        self.calls = []
        self.closed = False
        self.authority_owner = ":1.10"
        self.authority_uid = 990
        self.active = True
        self.remote = False
        self.session_uid = 1000
        self.policy = [0, 0, 1]
        self.annotations = {}
        self.preflight = [False, True, {}]
        self.interactive = [True, False, {}]
        self.temporaries = []
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.interactive_sender: str | None = None

    async def call(
        self, destination, path, interface, member, signature="", body=None, **kwargs
    ):
        self.calls.append((destination, member, signature, body))
        body = body or []
        if destination == "org.freedesktop.DBus":
            if member == "GetNameOwner":
                owner = (
                    self.authority_owner
                    if body[0] == "org.freedesktop.PolicyKit1"
                    else ":1.11"
                )
                return DBusReply("org.freedesktop.DBus", "s", [owner])
            if member == "GetConnectionUnixUser":
                return DBusReply(
                    "org.freedesktop.DBus",
                    "u",
                    [self.authority_uid if body[0] == self.authority_owner else 0],
                )
        if member == "GetSessionByPID":
            return DBusReply(":1.11", "o", ["/org/freedesktop/login1/session/c1"])
        if member == "GetAll":
            return DBusReply(
                ":1.11",
                "a{sv}",
                [
                    {
                        "Id": "c1",
                        "User": [self.session_uid, "/user"],
                        "Active": self.active,
                        "Remote": self.remote,
                        "LockedHint": False,
                        "Type": "x11",
                        "Class": "user",
                        "State": "active",
                    }
                ],
            )
        if member == "EnumerateActions":
            return DBusReply(
                destination,
                "a(ssssssuuua{ss})",
                [
                    [
                        [
                            ACTION_ID,
                            "description",
                            "message",
                            "vendor",
                            "url",
                            "icon",
                            *self.policy,
                            self.annotations,
                        ]
                    ]
                ],
            )
        if member == "EnumerateTemporaryAuthorizations":
            return DBusReply(destination, "a(ss(sa{sv})tt)", [self.temporaries])
        if member == "CancelCheckAuthorization":
            if self.release is not None:
                self.release.set()
            return DBusReply(destination, "", [])
        if member == "CheckAuthorization":
            if body[3] == 1:
                self.entered.set()
                if self.release is not None:
                    await self.release.wait()
                return DBusReply(
                    self.interactive_sender or destination,
                    "(bba{ss})",
                    [self.interactive],
                )
            return DBusReply(destination, "(bba{ss})", [self.preflight])
        raise AssertionError(member)

    def close(self):
        self.closed = True


class LinuxRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.identity = ProcessIdentity(1234, 5678, 1000)
        self.policy_patch = patch(
            "platform_security.linux_recovery._verify_installed_policy"
        )
        self.identity_patch = patch(
            "platform_security.linux_recovery._process_identity",
            return_value=self.identity,
        )
        self.uid_patch = patch(
            "platform_security.linux_recovery._authority_uids", return_value={0, 990}
        )
        self.attestation_patch = patch(
            "platform_security.linux_recovery.verify_system_service",
            new_callable=AsyncMock,
        )
        for fixture in (
            self.policy_patch,
            self.identity_patch,
            self.uid_patch,
            self.attestation_patch,
        ):
            fixture.start()
            self.addCleanup(fixture.stop)

    def service(self):
        return LinuxRecovery(_test_bus_factory=lambda: self.bus)

    def request(self, attempt="one"):
        return RecoveryRequest(attempt, "db-one", 7, "Reason", "Title", "Cancel")

    async def test_capabilities_is_noninteractive_and_does_not_access_storage(self):
        service = self.service()
        self.assertTrue(await service.supports_recovery())
        self.assertFalse(service.challenge_in_progress)
        self.assertTrue(self.bus.closed)
        for _, member, _, body in self.bus.calls:
            if member == "CheckAuthorization":
                self.assertEqual(body[3], 0)

    async def test_success_requires_fresh_pre_and_post_check_with_exact_process(self):
        result = await self.service().authenticate(self.request())
        self.assertEqual(result.status, RecoveryStatus.SUCCESS)
        checks = [call for call in self.bus.calls if call[1] == "CheckAuthorization"]
        self.assertEqual([call[3][3] for call in checks], [0, 1, 0])
        subject = checks[1][3][0]
        self.assertEqual(
            subject,
            [
                "unix-process",
                {
                    "pid": ("u", 1234),
                    "start-time": ("t", 5678),
                    "uid": ("i", 1000),
                },
            ],
        )
        self.assertEqual(checks[1][3][2], {})
        self.assertTrue(checks[1][3][4].startswith("tokenlogue-"))
        self.assertTrue(self.bus.closed)

    async def test_wrong_authority_uid_refuses_before_prompt(self):
        self.bus.authority_uid = 1000
        self.assertEqual(
            (await self.service().authenticate(self.request())).status,
            RecoveryStatus.UNAVAILABLE,
        )
        self.assertFalse(self.bus.entered.is_set())

    async def test_wrong_or_inactive_session_refuses_before_prompt(self):
        for key, value in (("active", False), ("remote", True), ("session_uid", 1001)):
            with self.subTest(key=key):
                self.bus = FakeBus()
                setattr(self.bus, key, value)
                self.assertEqual(
                    (await self.service().authenticate(self.request())).status,
                    RecoveryStatus.UNAVAILABLE,
                )
                self.assertFalse(self.bus.entered.is_set())

    async def test_unconditional_retained_admin_and_malformed_policy_refuse(self):
        for policy in ([0, 0, 5], [0, 0, 3], [0, 0, 2], [1, 0, 1], [0, 1, 1]):
            with self.subTest(policy=policy):
                self.bus = FakeBus()
                self.bus.policy = policy
                self.assertFalse(await self.service().supports_recovery())
                self.assertFalse(self.bus.entered.is_set())

    async def test_preexisting_or_retained_authorization_refuses_without_revocation(
        self,
    ):
        for reply in (
            [True, False, {}],
            [False, True, {"polkit.retains_authorization_after_challenge": "1"}],
            [False, True, {"polkit.temporary_authorization_id": "old"}],
        ):
            with self.subTest(reply=reply):
                self.bus = FakeBus()
                self.bus.preflight = reply
                self.assertFalse(await self.service().supports_recovery())
                self.assertFalse(self.bus.entered.is_set())
                self.assertFalse(any("Revoke" in x[1] for x in self.bus.calls))

    async def test_temporary_scope_authorization_refuses_but_foreign_is_untouched(self):
        self.bus.temporaries = [["foreign", "foreign.action", [], 0, 100]]
        self.assertTrue(await self.service().supports_recovery())
        self.bus.temporaries.append(["ours", ACTION_ID, [], 0, 100])
        self.assertFalse(await self.service().supports_recovery())
        self.assertFalse(any("Revoke" in x[1] for x in self.bus.calls))

    async def test_cancelled_wrong_and_missing_agent_do_not_authorize(self):
        for reply, expected in (
            ([False, False, {"polkit.dismissed": "true"}], RecoveryStatus.CANCELLED),
            ([False, False, {}], RecoveryStatus.ERROR),
            ([False, True, {}], RecoveryStatus.UNAVAILABLE),
            (
                [True, False, {"polkit.temporary_authorization_id": "bad"}],
                RecoveryStatus.UNAVAILABLE,
            ),
            ([True, False, {"unexpected": "ambiguous"}], RecoveryStatus.UNAVAILABLE),
            ([1, False, {}], RecoveryStatus.UNAVAILABLE),
        ):
            with self.subTest(reply=reply):
                self.bus = FakeBus()
                self.bus.interactive = reply
                result = await self.service().authenticate(self.request())
                self.assertEqual(result.status, expected)

    async def test_wrong_sender_and_owner_change_never_authorize(self):
        self.bus.interactive_sender = ":1.666"
        self.assertEqual(
            (await self.service().authenticate(self.request())).status,
            RecoveryStatus.UNAVAILABLE,
        )
        self.bus = FakeBus()
        self.bus.release = asyncio.Event()
        service = self.service()
        pending = asyncio.create_task(service.authenticate(self.request()))
        await self.bus.entered.wait()
        self.bus.authority_owner = ":1.99"
        self.bus.release.set()
        self.assertNotEqual((await pending).status, RecoveryStatus.SUCCESS)

    async def test_session_change_after_prompt_never_authorizes(self):
        self.bus.release = asyncio.Event()
        pending = asyncio.create_task(self.service().authenticate(self.request()))
        await self.bus.entered.wait()
        self.bus.active = False
        self.bus.release.set()
        self.assertNotEqual((await pending).status, RecoveryStatus.SUCCESS)

    async def test_cancel_invalidates_before_native_await_and_drops_late_success(self):
        self.bus.release = asyncio.Event()
        service = self.service()
        pending = asyncio.create_task(service.authenticate(self.request()))
        await self.bus.entered.wait()
        await service.cancel("one")
        self.assertEqual((await pending).status, RecoveryStatus.EXPIRED)
        cancellations = [
            x for x in self.bus.calls if x[1] == "CancelCheckAuthorization"
        ]
        checks = [x for x in self.bus.calls if x[1] == "CheckAuthorization"]
        self.assertEqual(cancellations[0][3], [checks[1][3][4]])
        self.assertEqual(cancellations[0][0], checks[1][0])

    async def test_timeout_cancels_native_on_same_connection(self):
        self.bus.release = asyncio.Event()
        service = self.service()
        result = await service.authenticate(self.request(), timeout=0.05)
        self.assertEqual(result.status, RecoveryStatus.TIMEOUT)
        self.assertTrue(any(x[1] == "CancelCheckAuthorization" for x in self.bus.calls))
        self.assertTrue(self.bus.closed)

    async def test_busy_and_reused_attempt_do_not_create_another_prompt(self):
        self.bus.release = asyncio.Event()
        service = self.service()
        pending = asyncio.create_task(service.authenticate(self.request()))
        await self.bus.entered.wait()
        self.assertEqual(
            (await service.authenticate(self.request("two"))).status,
            RecoveryStatus.BUSY,
        )
        self.bus.release.set()
        self.assertEqual((await pending).status, RecoveryStatus.SUCCESS)
        self.assertEqual(
            (await service.authenticate(self.request())).status,
            RecoveryStatus.EXPIRED,
        )

    async def test_missing_policy_no_prompt_and_no_private_error_text(self):
        with patch(
            "platform_security.linux_recovery._verify_installed_policy",
            side_effect=DBusError("policy_missing"),
        ):
            service = self.service()
            self.assertFalse(await service.supports_recovery())
            self.assertEqual(service.unavailable_reason, "policy_missing")
            result = await service.authenticate(self.request())
            self.assertEqual(result.status, RecoveryStatus.UNAVAILABLE)
            self.assertFalse(self.bus.entered.is_set())

    async def test_close_revokes_pending_and_cannot_start_another_challenge(self):
        self.bus.release = asyncio.Event()
        service = self.service()
        pending = asyncio.create_task(service.authenticate(self.request()))
        await self.bus.entered.wait()
        await service.aclose()
        self.assertEqual((await pending).status, RecoveryStatus.EXPIRED)
        await service.aclose()
        self.assertFalse(await service.supports_recovery())
        self.assertEqual(
            (await service.authenticate(self.request("closed"))).status,
            RecoveryStatus.UNAVAILABLE,
        )

    async def test_late_old_completion_does_not_close_new_challenge_transport(self):
        first, second = self.bus, FakeBus()
        first.release = asyncio.Event()
        second.release = asyncio.Event()
        sequence = iter((first, second))
        service = LinuxRecovery(_test_bus_factory=lambda: next(sequence))
        pending_old = asyncio.create_task(service.authenticate(self.request()))
        await first.entered.wait()
        # Отмена возвращает сразу, но предыдущий native callback ещё не доставлен.
        first_original = first.call

        async def delayed_cancel(*args, **kwargs):
            if args[3] == "CancelCheckAuthorization":
                return DBusReply(args[0], "", [])
            return await first_original(*args, **kwargs)

        first.call = delayed_cancel
        await service.cancel("one")
        pending_new = asyncio.create_task(service.authenticate(self.request("two")))
        await second.entered.wait()
        first.release.set()
        self.assertEqual((await pending_old).status, RecoveryStatus.EXPIRED)
        self.assertFalse(second.closed)
        self.assertTrue(service.challenge_in_progress)
        second.release.set()
        self.assertEqual((await pending_new).status, RecoveryStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
