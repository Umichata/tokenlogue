"""Signal subscription ACK and sanitized protocol errors have explicit provenance."""

from __future__ import annotations

import ctypes
import sys
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from platform_security.linux_dbus import (  # noqa: E402
    BusConnection,
    DBusError,
    DBusReply,
)


class DBusSubscriptionTests(unittest.IsolatedAsyncioTestCase):
    def test_message_serial_is_preserved_separately_from_reply_to_serial(self):
        library = Mock()
        for field, value in {
            "sender": b":1.77",
            "signature": b"",
            "path": b"/synthetic",
            "interface": b"org.synthetic",
            "member": b"ActiveChanged",
        }.items():
            getattr(library, "dbus_message_get_" + field).return_value = value
        library.dbus_message_iter_get_arg_type.return_value = 0
        library.dbus_message_get_serial.return_value = 987
        library.dbus_message_get_reply_serial.return_value = 123
        bus = BusConnection.__new__(BusConnection)
        bus._lib = cast(ctypes.CDLL, library)
        message = object()
        reply = bus._decode(message)
        self.assertEqual(reply.serial, 987)
        self.assertEqual(reply.sender, ":1.77")
        self.assertEqual(reply.member, "ActiveChanged")
        library.dbus_message_get_serial.assert_called_once_with(message)
        library.dbus_message_get_reply_serial.assert_not_called()

    async def test_add_match_requires_empty_ack_from_actual_bus_daemon(self):
        bus = BusConnection.__new__(BusConnection)
        bus.call = AsyncMock(return_value=DBusReply("org.freedesktop.DBus", "", []))
        await bus.add_match("type='signal'")
        bus.call.assert_awaited_once_with(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "AddMatch",
            "s",
            ["type='signal'"],
        )

    async def test_forged_or_malformed_subscription_ack_is_rejected(self):
        for reply in (
            DBusReply(":1.999", "", []),
            DBusReply("org.freedesktop.DBus", "b", [True]),
            DBusReply("org.freedesktop.DBus", "", [True]),
        ):
            with self.subTest(reply=reply):
                bus = BusConnection.__new__(BusConnection)
                bus.call = AsyncMock(return_value=reply)
                with self.assertRaisesRegex(DBusError, "untrusted_add_match_reply"):
                    await bus.add_match("type='signal'")

    def test_protocol_error_keeps_sender_separate_from_public_sanitized_name(self):
        error = DBusError("org.freedesktop.login1.NoSessionForPID", sender=":1.10")
        self.assertEqual(str(error), "org.freedesktop.login1.NoSessionForPID")
        self.assertEqual(error.name, str(error))
        self.assertEqual(error.sender, ":1.10")
        self.assertEqual(DBusError("transport_error").sender, "")
