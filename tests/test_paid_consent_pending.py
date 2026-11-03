"""A queued policy write cannot mint replacement paid-dispatch permissions."""

from __future__ import annotations

import asyncio
import threading
import unittest
from unittest.mock import patch

from tests import test_message_sending as sending
from tests import test_paid_chat_policy as policy_fixtures


class PaidConsentPendingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = policy_fixtures.PaidChatPolicyTests()
        await self.fx.asyncSetUp()
        self.addCleanup(self.fx.doCleanups)
        await self.fx.enable()

    async def test_queued_opt_out_cannot_mint_new_token_or_send_automatically(self):
        entered, release = threading.Event(), threading.Event()
        setter = self.fx.chats.set_paid_without_confirmation

        def blocked(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic test barrier timeout")
            return setter(*args)

        with patch.object(self.fx.chats, "set_paid_without_confirmation", blocked):
            changing = asyncio.create_task(
                self.fx.service.set_paid_without_confirmation("a", False)
            )
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            try:
                current = await self.fx.saved_chat("a")
                self.assertTrue(current.paid_without_confirmation)
                replacement = self.fx.service.paid_consent(current)
                self.assertIsNone(replacement)
                client = sending.FakeCompletionClient([sending._success(cost="0.01")])
                outcome = await self.fx.send(
                    self.fx.sender(client), consent=replacement
                )
                self.assertFalse(outcome.successful)
                self.assertEqual(client.calls, [])
            finally:
                release.set()
                await changing

    async def test_two_writers_keep_fence_until_both_settle(self):
        entered = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        counter, mutex = 0, threading.Lock()
        setter = self.fx.chats.set_paid_without_confirmation

        def blocked(*args):
            nonlocal counter
            with mutex:
                index = counter
                counter += 1
            entered[index].set()
            if not release[index].wait(3):
                raise RuntimeError("synthetic test barrier timeout")
            return setter(*args)

        with patch.object(self.fx.chats, "set_paid_without_confirmation", blocked):
            first = asyncio.create_task(
                self.fx.service.set_paid_without_confirmation("a", True)
            )
            self.assertTrue(await asyncio.to_thread(entered[0].wait, 2))
            second = asyncio.create_task(
                self.fx.service.set_paid_without_confirmation("a", True)
            )
            self.assertTrue(await asyncio.to_thread(entered[1].wait, 2))
            try:
                release[0].set()
                await first
                current = await self.fx.saved_chat("a")
                self.assertTrue(current.paid_without_confirmation)
                self.assertIsNone(self.fx.service.paid_consent(current))
            finally:
                release[0].set()
                release[1].set()
                await asyncio.gather(first, second)
        current = await self.fx.saved_chat("a")
        self.assertIsNotNone(self.fx.service.paid_consent(current))

    async def test_cancelled_setting_owner_drains_worker_before_releasing_fence(self):
        entered, release = threading.Event(), threading.Event()
        setter = self.fx.chats.set_paid_without_confirmation

        def blocked(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic test barrier timeout")
            return setter(*args)

        with patch.object(self.fx.chats, "set_paid_without_confirmation", blocked):
            changing = asyncio.create_task(
                self.fx.service.set_paid_without_confirmation("a", False)
            )
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            changing.cancel()
            await asyncio.sleep(0)
            try:
                self.assertFalse(changing.done())
                current = await self.fx.saved_chat("a")
                self.assertIsNone(self.fx.service.paid_consent(current))
            finally:
                release.set()
                try:
                    await changing
                except asyncio.CancelledError:
                    pass
        self.assertFalse((await self.fx.saved_chat("a")).paid_without_confirmation)
        await self.fx.enable()
        self.assertIsNotNone(
            self.fx.service.paid_consent(await self.fx.saved_chat("a"))
        )

    async def test_fence_remains_during_post_write_readback(self):
        entered, release = threading.Event(), threading.Event()
        getter = self.fx.chats.get_chat
        counter, mutex = 0, threading.Lock()

        def blocked(chat_id):
            nonlocal counter
            with mutex:
                counter += 1
                first = counter == 1
            if first:
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("synthetic test barrier timeout")
            return getter(chat_id)

        with patch.object(self.fx.chats, "get_chat", blocked):
            changing = asyncio.create_task(
                self.fx.service.set_paid_without_confirmation("a", True)
            )
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            try:
                current = await self.fx.saved_chat("a")
                self.assertTrue(current.paid_without_confirmation)
                self.assertIsNone(self.fx.service.paid_consent(current))
            finally:
                release.set()
                await changing
        self.assertIsNotNone(
            self.fx.service.paid_consent(await self.fx.saved_chat("a"))
        )

    async def test_pending_chat_a_does_not_revoke_chat_b_permission(self):
        consent_b = await self.fx.enable("b")
        entered, release = threading.Event(), threading.Event()
        setter = self.fx.chats.set_paid_without_confirmation

        def blocked(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic test barrier timeout")
            return setter(*args)

        with patch.object(self.fx.chats, "set_paid_without_confirmation", blocked):
            changing = asyncio.create_task(
                self.fx.service.set_paid_without_confirmation("a", False)
            )
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            try:
                self.assertTrue(self.fx.service.paid_consent_is_current(consent_b))
                client = sending.FakeCompletionClient([sending._success(cost="0.01")])
                result = await self.fx.send(
                    self.fx.sender(client), chat="b", consent=consent_b
                )
                self.assertTrue(result.successful)
                self.assertEqual(len(client.calls), 1)
            finally:
                release.set()
                await changing
