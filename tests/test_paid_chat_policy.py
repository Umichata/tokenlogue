"""Encrypted per-chat paid consent, current pricing and revocation before HTTP."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.accounting import ChatBudgetService  # noqa: E402
from chat.drafts import ChatDraft, ChatDraftService  # noqa: E402
from chat.errors import ChatErrorType  # noqa: E402
from chat.models import FREE_ROUTER_MODEL, Chat, ChatMode  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from storage.chat_repository import SqliteChatRepository  # noqa: E402
from storage.data_access import DataAccess, DataAccessError  # noqa: E402
from storage.database import AuthDatabase  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from storage.encrypted_migration import migrate_database  # noqa: E402
from storage.field_cipher import FieldCipher  # noqa: E402
from storage.message_repository import SqliteMessageRepository  # noqa: E402
from tests import test_message_sending as fx  # noqa: E402


class PaidChatPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = AuthDatabase(self.temp.name)
        self.access = DataAccess()
        # Public synthetic fixture key, never any owner storage or credentials.
        self.cipher = FieldCipher(
            bytes(range(32)), "paid-test-database", "paid-test-key"
        )
        migrate_database(self.db.path, self.cipher)
        self.access.open(self.cipher)
        self.chats = SqliteChatRepository(self.db.path, self.access)
        self.messages = SqliteMessageRepository(self.db.path, self.access)
        self.drafts = SqliteDraftRepository(self.db.path, self.access)
        self.service = ChatService(self.chats, now=lambda: fx.NOW)
        self.budgets = ChatBudgetService(self.messages)
        self.model = fx._paid_model()
        self.catalog = fx.FakeCatalogClient((self.model,))
        self.validator = fx.FakeKeyValidator()
        for name in ("a", "b"):
            self.chats.create_chat_with_limits(
                fx._chat(name, ChatMode.PAID, self.model),
                token_limit=100_000,
                max_completion_tokens=64,
                cost_limit_usd=Decimal("10"),
            )

    def chat(self, name: str) -> Chat:
        result = self.chats.get_chat(name)
        assert result is not None
        return result

    async def saved_chat(self, name: str) -> Chat:
        result = await self.service.get_chat(name)
        assert result is not None
        return result

    def sender(self, client):
        return MessageSendingService(
            self.service,
            self.messages,
            client,
            self.catalog,
            self.validator,
            now=lambda: fx.NOW,
        )

    async def enable(self, chat="a"):
        state = await self.service.set_paid_without_confirmation(chat, True)
        token = self.service.paid_consent(state)
        assert token is not None
        return token

    async def send(self, sender, *, chat="a", consent=None, confirmed=False, **kwargs):
        return await sender.send_message(
            chat,
            "  synthetic unsent draft\n🙂  ",
            api_key=fx.TEST_CREDENTIAL,
            key_validity=fx.KeyValidityState.VALID,
            key_limit=fx.KeyLimitInfo.from_validated_remaining(None),
            paid_confirmed=confirmed,
            paid_consent=consent,
            **kwargs,
        )

    def raw(self, chat="a"):
        with sqlite3.connect(self.db.path) as c:
            return c.execute(
                "SELECT pricing_overrides_json FROM chats WHERE id=?", (chat,)
            ).fetchone()[0]

    async def test_existing_and_new_chat_default_off_without_schema_change(self):
        with sqlite3.connect(self.db.path) as c:
            ddl = list(c.execute("SELECT sql FROM sqlite_master ORDER BY name"))
        self.assertFalse(self.chat("a").paid_without_confirmation)
        await self.enable()
        with sqlite3.connect(self.db.path) as c:
            self.assertEqual(
                list(c.execute("SELECT sql FROM sqlite_master ORDER BY name")), ddl
            )
            self.assertEqual(c.execute("PRAGMA user_version").fetchone()[0], 7)
        self.assertFalse(self.chat("b").paid_without_confirmation)

    async def test_flag_is_encrypted_persistent_and_separate_for_each_chat(self):
        token = await self.enable()
        raw = json.loads(self.raw())
        self.assertIsInstance(raw["paid_confirmation"], str)
        self.assertNotIn('"enabled":true', self.raw())
        reopened = ChatService(SqliteChatRepository(self.db.path, self.access))
        chat = await reopened.get_chat("a")
        assert chat is not None
        self.assertTrue(chat.paid_without_confirmation)
        self.assertEqual(chat.paid_policy_revision, token.revision)
        self.assertFalse(self.chat("b").paid_without_confirmation)

    async def test_no_plaintext_permission_can_enable_protected_chat(self):
        values = [
            None,
            True,
            1,
            "true",
            {},
            {"version": 1, "enabled": True, "revision": "a" * 32},
        ]
        for value in values:
            with sqlite3.connect(self.db.path) as c:
                c.execute(
                    "UPDATE chats SET pricing_overrides_json=? WHERE id='a'",
                    (
                        json.dumps(
                            {"version": 1, "prices": [], "paid_confirmation": value}
                        ),
                    ),
                )
            chat = self.chat("a")
            assert chat is not None
            self.assertFalse(chat.paid_without_confirmation)
            self.assertEqual(chat.pricing_overrides, ())

    async def test_corrupt_or_foreign_chat_ciphertext_defaults_off(self):
        await self.enable()
        wrapper = json.loads(self.raw())
        for value in (wrapper["paid_confirmation"], "broken", '["TLG",999]'):
            with sqlite3.connect(self.db.path) as c:
                c.execute(
                    "UPDATE chats SET pricing_overrides_json=? WHERE id='b'",
                    (
                        json.dumps(
                            {"version": 1, "prices": [], "paid_confirmation": value}
                        ),
                    ),
                )
            self.assertFalse(self.chat("b").paid_without_confirmation)

    async def test_incompatible_policy_version_and_nonbool_are_off(self):
        for value in (
            {"version": 99, "enabled": True, "revision": "a" * 32},
            {"version": 1, "enabled": 1, "revision": "a" * 32},
        ):
            encrypted = self.cipher.encrypt(
                json.dumps(value),
                table="chats",
                field="paid_confirmation",
                record_id="a",
            )
            with sqlite3.connect(self.db.path) as c:
                c.execute(
                    "UPDATE chats SET pricing_overrides_json=? WHERE id='a'",
                    (
                        json.dumps(
                            {"version": 1, "prices": [], "paid_confirmation": encrypted}
                        ),
                    ),
                )
            self.assertFalse(self.chat("a").paid_without_confirmation)

    async def test_lock_and_reopen_preserve_saved_choice(self):
        await self.enable()
        self.access.lock()
        with self.assertRaises(DataAccessError):
            await self.service.get_chat("a")
        self.access.open(self.cipher)
        self.assertTrue((await self.saved_chat("a")).paid_without_confirmation)

    async def test_write_failure_preserves_actual_choice_but_revokes_pending_token(
        self,
    ):
        old = await self.enable()
        with patch.object(
            self.chats,
            "set_paid_without_confirmation",
            side_effect=OSError("synthetic"),
        ):
            with self.assertRaises(OSError):
                await self.service.set_paid_without_confirmation("a", False)
        current = await self.service.get_chat("a")
        assert current is not None
        self.assertTrue(current.paid_without_confirmation)
        self.assertFalse(self.service.paid_consent_is_current(old))
        renewed = self.service.paid_consent(current)
        assert renewed is not None
        self.assertTrue(self.service.paid_consent_matches(current, renewed))

    async def test_free_chat_has_no_setting_and_does_not_inherit(self):
        self.chats.create_chat(fx._chat("free", ChatMode.FREE, FREE_ROUTER_MODEL))
        with self.assertRaises(ValueError):
            await self.service.set_paid_without_confirmation("free", True)
        self.assertFalse(self.chat("free").paid_without_confirmation)

    async def test_off_requires_confirmation_every_time_after_previously_confirmed_send(
        self,
    ):
        client = fx.FakeCompletionClient([fx._success(cost="0.01")])
        sender = self.sender(client)
        self.assertEqual(
            (await self.send(sender)).error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )
        self.assertTrue((await self.send(sender, confirmed=True)).successful)
        self.assertEqual(
            (await self.send(sender)).error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(len(client.calls), 1)

    async def test_opt_in_sends_first_and_next_without_per_request_confirmation(self):
        token = await self.enable()
        client = fx.FakeCompletionClient(
            [fx._success(cost="0.01"), fx._success(cost="0.01")]
        )
        sender = self.sender(client)
        self.assertEqual(client.calls, [])
        self.assertTrue((await self.send(sender, consent=token)).successful)
        self.assertTrue((await self.send(sender, consent=token)).successful)
        self.assertEqual(len(client.calls), 2)
        await self.service.set_paid_without_confirmation("a", False)
        self.assertEqual(
            (await self.send(sender)).error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )

    async def test_opt_in_current_price_change_recalculates_reserve_without_reconfirmation(
        self,
    ):
        token = await self.enable()
        self.catalog.models = (replace(self.model, request_price=Decimal("0.5")),)
        client = fx.FakeCompletionClient([fx._success(cost="0.5")])
        result = await self.send(self.sender(client), consent=token)
        self.assertTrue(result.successful, result.error_type)
        turn = self.messages.get_turn(result.turn_id)
        assert turn is not None
        self.assertGreaterEqual(turn.reserved_cost_usd, Decimal("0.5"))
        current = self.chat("a")
        self.assertEqual(current.request_price, Decimal("0.5"))
        self.assertEqual(current.paid_policy_revision, token.revision)

    async def test_opt_in_never_bypasses_insufficient_budget_or_invalid_key(self):
        token = await self.enable()
        client = fx.FakeCompletionClient([])
        for condition, validation, price, expected in (
            (
                "insufficient_budget",
                fx.KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT,
                Decimal("11"),
                ChatErrorType.COST_LIMIT_EXCEEDED,
            ),
            (
                "invalid_key",
                fx.KeyValidationStatus.INVALID,
                self.model.request_price,
                ChatErrorType.KEY_NOT_VALID,
            ),
        ):
            with self.subTest(condition=condition):
                self.validator.result = fx.KeyValidationResult(validation)
                self.catalog.models = (replace(self.model, request_price=price),)
                result = await self.send(self.sender(client), consent=token)
                self.assertEqual(result.error_type, expected)
                self.assertEqual(client.calls, [])

    async def test_consent_for_a_or_other_service_cannot_authorize_b(self):
        token = await self.enable()
        client = fx.FakeCompletionClient([])
        self.assertEqual(
            (await self.send(self.sender(client), chat="b", consent=token)).error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )
        other = ChatService(self.chats)
        other_chat = await other.get_chat("a")
        assert other_chat is not None
        foreign = other.paid_consent(other_chat)
        self.assertEqual(
            (await self.send(self.sender(client), consent=foreign)).error_type,
            ChatErrorType.PAID_CONFIRMATION_REQUIRED,
        )
        self.assertEqual(client.calls, [])

    async def test_opt_out_while_preflight_waits_prevents_dispatch_and_keeps_draft(
        self,
    ):
        token = await self.enable()
        exact = "  synthetic unsent draft\n🙂  "
        self.drafts.save_draft(ChatDraft("a", 1, exact))
        entered, release = asyncio.Event(), asyncio.Event()
        validate = self.validator.validate_key

        async def delayed(value):
            entered.set()
            await release.wait()
            return await validate(value)

        client = fx.FakeCompletionClient([])
        with patch.object(self.validator, "validate_key", delayed):
            pending = asyncio.create_task(
                self.send(self.sender(client), consent=token, draft_revision=1)
            )
            await entered.wait()
            await self.service.set_paid_without_confirmation("a", False)
            release.set()
            result = await pending
        self.assertEqual(result.error_type, ChatErrorType.PAID_CONFIRMATION_REQUIRED)
        self.assertEqual(self.drafts.get_draft("a").text, exact)
        self.assertEqual(client.calls, [])

    async def test_revocation_after_reservation_restores_exact_draft_without_http(self):
        token = await self.enable()
        exact = "  synthetic unsent draft\n🙂  "
        self.drafts.save_draft(ChatDraft("a", 1, exact))

        async def reserved(_turn):
            await self.service.set_paid_without_confirmation("a", False)

        client = fx.FakeCompletionClient([])
        result = await self.send(
            self.sender(client), consent=token, draft_revision=1, on_reserved=reserved
        )
        self.assertEqual(result.error_type, ChatErrorType.PAID_CONFIRMATION_REQUIRED)
        self.assertEqual(self.drafts.get_draft("a").text, exact)
        self.assertEqual(self.drafts.get_draft("a").revision, 1)
        budget = self.messages.get_chat_budget("a")
        assert budget is not None
        self.assertEqual(budget.reserved_tokens, 0)
        self.assertEqual(client.calls, [])

    async def test_restore_does_not_overwrite_newer_draft_edit(self):
        token = await self.enable()
        self.drafts.save_draft(ChatDraft("a", 1, "old draft"))

        async def reserved(_turn):
            self.drafts.save_draft(ChatDraft("a", 8, "newer exact draft"))
            await self.service.set_paid_without_confirmation("a", False)

        client = fx.FakeCompletionClient([])
        await self.send(
            self.sender(client), consent=token, draft_revision=1, on_reserved=reserved
        )
        self.assertEqual(
            self.drafts.get_draft("a"), ChatDraft("a", 8, "newer exact draft")
        )
        self.assertEqual(client.calls, [])

    async def test_lock_after_reservation_uses_only_bounded_restore_and_never_http(
        self,
    ):
        token = await self.enable()
        exact = "  synthetic unsent draft\n🙂  "
        self.drafts.save_draft(ChatDraft("a", 1, exact))

        def reserved(_turn):
            self.access.lock()

        client = fx.FakeCompletionClient([])
        with self.assertRaises(DataAccessError):
            await self.send(
                self.sender(client),
                consent=token,
                draft_revision=1,
                on_reserved=reserved,
            )
        self.access.open(self.cipher)
        self.assertEqual(self.drafts.get_draft("a").text, exact)
        self.assertEqual(client.calls, [])

    async def test_navigation_guard_invalidates_pending_before_http(self):
        token = await self.enable()
        client = fx.FakeCompletionClient([])
        result = await self.send(
            self.sender(client), consent=token, dispatch_guard=lambda: False
        )
        self.assertEqual(result.error_type, ChatErrorType.INTERRUPTED)
        self.assertEqual(client.calls, [])

    async def test_opt_in_retry_uses_current_price_without_confirmation(self):
        token = await self.enable()
        client = fx.FakeCompletionClient(
            [
                fx._known_error(ChatErrorType.RATE_LIMIT_EXCEEDED),
                fx._success(cost="0.5"),
            ]
        )
        sender = self.sender(client)
        failed = await self.send(sender, consent=token)
        assert failed.turn_id is not None
        self.catalog.models = (replace(self.model, request_price=Decimal("0.5")),)
        preview = await sender.preview_failed_turn(
            failed.turn_id,
            api_key=fx.TEST_CREDENTIAL,
            key_validity=fx.KeyValidityState.VALID,
            key_limit=fx.KeyLimitInfo.from_validated_remaining(None),
            paid_consent=token,
        )
        self.assertTrue(preview.allowed)
        result = await sender.retry_failed_turn(
            failed.turn_id,
            api_key=fx.TEST_CREDENTIAL,
            key_validity=fx.KeyValidityState.VALID,
            key_limit=fx.KeyLimitInfo.from_validated_remaining(None),
            paid_consent=token,
        )
        self.assertTrue(result.successful)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(self.messages.list_turns("a")), 1)

    async def test_opt_out_after_final_saved_read_invalidates_queued_old_result(self):
        token = await self.enable()
        exact = "  synthetic unsent draft\n🙂  "
        self.drafts.save_draft(ChatDraft("a", 1, exact))
        original = self.service.get_chat
        entered, release = asyncio.Event(), asyncio.Event()
        reads = 0

        async def delayed(chat_id):
            nonlocal reads
            result = await original(chat_id)
            reads += 1
            if reads == 2:
                entered.set()
                await release.wait()
            return result

        client = fx.FakeCompletionClient([])
        with patch.object(self.service, "get_chat", delayed):
            sending = asyncio.create_task(
                self.send(self.sender(client), consent=token, draft_revision=1)
            )
            await entered.wait()
            await self.service.set_paid_without_confirmation("a", False)
            release.set()
            result = await sending
        self.assertEqual(result.error_type, ChatErrorType.PAID_CONFIRMATION_REQUIRED)
        self.assertEqual(client.calls, [])
        self.assertEqual(self.drafts.get_draft("a").text, exact)

    async def test_old_consent_is_not_reusable_after_lock_and_reopen(self):
        old = await self.enable()
        self.access.lock()
        self.access.open(self.cipher)
        client = fx.FakeCompletionClient([])
        result = await self.send(self.sender(client), consent=old)
        self.assertEqual(result.error_type, ChatErrorType.PAID_CONFIRMATION_REQUIRED)
        self.assertEqual(client.calls, [])

    async def test_unsent_restore_does_not_collide_with_unflushed_next_revision(self):
        token = await self.enable()
        drafts = ChatDraftService(self.drafts)
        await drafts.load("a")
        snapshot = drafts.record_edit("a", "  synthetic unsent draft\n🙂  ")
        await drafts.flush("a")

        async def reserved(_turn):
            drafts.acknowledge_reserved(snapshot)
            drafts.record_edit("a", "synthetic latest edit awaiting flush")
            await self.service.set_paid_without_confirmation("a", False)

        client = fx.FakeCompletionClient([])
        result = await self.send(
            self.sender(client),
            consent=token,
            draft_revision=snapshot.revision,
            on_reserved=reserved,
        )
        self.assertEqual(result.error_type, ChatErrorType.PAID_CONFIRMATION_REQUIRED)
        await drafts.flush("a")
        self.assertEqual(
            self.drafts.get_draft("a"),
            ChatDraft(
                "a", snapshot.revision + 1, "synthetic latest edit awaiting flush"
            ),
        )
        self.assertEqual(client.calls, [])
