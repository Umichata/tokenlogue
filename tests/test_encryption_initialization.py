"""Повторный запуск первичной защиты проверяется только на синтетических данных."""

from __future__ import annotations

# ruff: noqa: E402
import asyncio
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.pin import PinHasher
from platform_security.device_recovery import DeviceRecovery, RecoveryStatus
from storage.data_access import DataAccess
from storage.data_protection import (
    DATA_BINDING_ALIAS,
    DATA_KEY_ALIAS,
    DataProtection,
    DataProtectionError,
)
from storage.database import AuthDatabase
from storage.field_cipher import FieldCipher
from storage.secure_credentials import (
    API_KEY_STORAGE_NAME,
    REGISTRATION_ID_STORAGE_NAME,
    SECURE_STORAGE_NAMESPACE,
)
from tests.test_data_protection import Provider
from tests.test_secure_credentials import FakeSecureStorage

TABLES = ("auth_state", "chats", "chat_budgets", "turns", "messages", "chat_drafts")
INITIALIZATION_ALIAS = f"{SECURE_STORAGE_NAMESPACE}.chat_data_initialization.v1"


class TrackedStorage(FakeSecureStorage):
    """Двойник хранит отдельный журнал мутаций без обращения к Secret Service."""

    def __init__(self) -> None:
        super().__init__()
        self.mutations: list[tuple[str, str]] = []

    async def set(self, key, value):
        self.mutations.append(("set", key))
        await super().set(key, value)

    async def remove(self, key):
        self.mutations.append(("remove", key))
        await super().remove(key)


def snapshot(path: Path, cipher: FieldCipher | None = None) -> dict:
    """Сравнивает все прежние столбцы и rowid, а не только количество строк."""
    result = {}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        for table in TABLES:
            records = []
            for raw in connection.execute(
                f'SELECT rowid AS saved_rowid,* FROM "{table}" ORDER BY rowid'
            ):
                row = dict(raw)
                row.pop("title_origin", None)
                if cipher is not None:
                    fields = {
                        "chats": ("title",),
                        "messages": ("content",),
                        "chat_drafts": ("content",),
                        "turns": ("generation_id", "finish_reason"),
                    }.get(table, ())
                    for field in fields:
                        if row[field] is None:
                            continue
                        coordinates: dict[str, Any] = {"table": table, "field": field}
                        if table == "chats":
                            coordinates["record_id"] = row["id"]
                        elif table == "chat_drafts":
                            coordinates.update(
                                record_id=row["chat_id"],
                                chat_id=row["chat_id"],
                                revision=row["revision"],
                            )
                        else:
                            coordinates.update(
                                record_id=row["id"], chat_id=row["chat_id"]
                            )
                            if table == "messages":
                                coordinates["role"] = row["role"]
                        row[field] = cipher.decrypt(row[field], **coordinates)
                records.append(row)
            result[table] = records
    return result


class EncryptionInitializationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = AuthDatabase(self.temporary.name)
        self.hasher = PinHasher(iterations=100)
        self.database.save_auth_state(
            "initialization-fixture", self.hasher.create_record("0123")
        )
        self.database.register_failed_attempt(100, 5, 30)
        self.storage = TrackedStorage()
        self.storage.values[REGISTRATION_ID_STORAGE_NAME] = "initialization-fixture"
        self.storage.values[API_KEY_STORAGE_NAME] = "synthetic-api-token-no-network"
        timestamp = "2026-10-25T02:00:00+00:00"
        with sqlite3.connect(self.database.path) as connection:
            for number, title in enumerate(("Новый чат", "New chat"), 1):
                chat_id = f"chat-{number}"
                connection.execute(
                    "INSERT INTO chats (rowid,id,title,mode,requested_model_id,requested_model_name,prompt_price_per_token,completion_price_per_token,created_at,updated_at,title_is_manual) VALUES (?,?,?,?,?,?,?,?,?,?,1)",
                    (
                        10 * number,
                        chat_id,
                        title,
                        "paid",
                        "fixture/model",
                        "Fixture model",
                        "0.00000120",
                        "0.00000340",
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    "INSERT INTO chat_budgets (chat_id,limits_configured,token_limit,max_completion_tokens,prompt_tokens_used,completion_tokens_used,total_tokens_used,reserved_tokens,cost_limit_usd,cost_used_usd,cost_reserved_usd,state,updated_at) VALUES (?,1,16384,8192,17,23,40,8192,'1.0000','0.0001','0.012300','accounting_unknown',?)",
                    (chat_id, timestamp),
                )
                connection.execute(
                    "INSERT INTO turns (rowid,id,chat_id,status,requested_model_id,actual_model_id,generation_id,finish_reason,prompt_tokens,completion_tokens,total_tokens,cost_usd,reserved_tokens,reserved_cost_usd,accounting_status,error_type,request_sent,created_at,updated_at) VALUES (?,?,?,'failed','fixture/model','fixture/actual',?,'stop',17,23,40,'0.0001',8192,'0.012300','unknown','network_error',1,?,?)",
                    (
                        20 * number,
                        f"turn-{number}",
                        chat_id,
                        f"generation-initialization-{number}",
                        timestamp,
                        timestamp,
                    ),
                )
                for index, role in enumerate(("user", "assistant"), 1):
                    connection.execute(
                        "INSERT INTO messages (rowid,id,chat_id,turn_id,role,content,status,requested_model_id,actual_model_id,prompt_tokens,completion_tokens,total_tokens,created_at,updated_at) VALUES (?,?,?,?,?,?,'sent','fixture/model','fixture/actual',17,23,40,?,?)",
                        (
                            number * 100 + index,
                            f"message-{number}-{role}",
                            chat_id,
                            f"turn-{number}",
                            role,
                            f"INITIALIZATION_MESSAGE_{number}_{role} Привет",
                            timestamp,
                            timestamp,
                        ),
                    )
                connection.execute(
                    "INSERT INTO chat_drafts (chat_id,revision,content) VALUES (?,?,?)",
                    (
                        chat_id,
                        30 + number,
                        f"INITIALIZATION_DRAFT_{number}\nUnsaved text",
                    ),
                )
        self.original_auth = self.stored()
        self.original = snapshot(self.database.path)
        self.original_api_key = self.storage.values[API_KEY_STORAGE_NAME]
        self.access = DataAccess()

    def stored(self):
        value = self.database.get_auth_state()
        assert value is not None
        return value

    def protection(self, **kwargs):
        return DataProtection(
            self.database.path,
            self.database,
            self.storage,
            self.access,
            pin_hasher=self.hasher,
            **kwargs,
        )

    def restart(self, **kwargs):
        self.access = DataAccess()
        return self.protection(**kwargs)

    def assert_preserved(self):
        self.assertTrue(self.access.unlocked)
        with self.access.authorize("read") as cipher:
            self.assertEqual(snapshot(self.database.path, cipher), self.original)
        self.assertEqual(self.stored(), self.original_auth)
        self.assertTrue(self.hasher.verify("0123", self.stored().pin_record))
        self.assertFalse(self.hasher.verify("9999", self.stored().pin_record))
        self.assertEqual(
            self.storage.values[API_KEY_STORAGE_NAME], self.original_api_key
        )
        with sqlite3.connect(self.database.path) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 7)
            self.assertEqual(
                connection.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )
            self.assertEqual(
                connection.execute(
                    "SELECT title_origin FROM chats ORDER BY rowid"
                ).fetchall(),
                [("manual",), ("manual",)],
            )
        for file in Path(self.temporary.name).rglob("*"):
            if file.is_file():
                self.assertNotIn(b"INITIALIZATION_", file.read_bytes(), file.name)

    async def interrupted_initialization(self, *, ack=False):
        original_database = self.database.path.read_bytes()
        if not ack:
            self.storage.fail_set_key = DATA_KEY_ALIAS

        async def failed_first_ack():
            if (
                DATA_BINDING_ALIAS in self.storage.values
                and DATA_KEY_ALIAS not in self.storage.values
            ):
                raise OSError("synthetic first binding durable acknowledgement")

        protection = self.protection(durable_write=failed_first_ack if ack else None)
        with self.assertRaises(DataProtectionError):
            await protection.unlock("0123", self.stored())
        self.assertFalse(self.access.unlocked)
        self.assertIn(DATA_BINDING_ALIAS, self.storage.values)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.values)
        self.assertEqual(self.database.path.read_bytes(), original_database)
        self.storage.fail_set_key = None
        return protection

    async def resume_and_check(self, *, ack=False):
        await self.interrupted_initialization(ack=ack)
        replacement = self.restart()
        self.storage.read_keys.clear()
        await replacement.reconcile()
        await replacement.has_protection()
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await replacement.unlock("0123", self.stored())
        self.assert_preserved()
        persisted_key = self.storage.values[DATA_KEY_ALIAS]
        replacement.lock()
        reopened = self.restart()
        await reopened.unlock("0123", self.stored())
        self.assert_preserved()
        self.assertEqual(self.storage.values[DATA_KEY_ALIAS], persisted_key)

    async def test_key_set_failure_restart_valid_pin_resumes_without_losing_data(self):
        await self.resume_and_check()

    async def test_first_binding_ack_failure_restart_valid_pin_resumes_without_losing_data(
        self,
    ):
        await self.resume_and_check(ack=True)

    async def test_previous_binding_only_initial_state_resumes_with_original_pin(self):
        await self.interrupted_initialization()
        self.storage.values.pop(INITIALIZATION_ALIAS)
        original_binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        await self.restart().unlock("0123", self.stored())
        self.assert_preserved()
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        self.assertEqual(binding["database_id"], original_binding["database_id"])
        self.assertEqual(binding["key_id"], original_binding["key_id"])

    async def test_initial_intent_only_is_detected_without_reading_key_before_pin(self):
        self.storage.fail_set_key = DATA_BINDING_ALIAS
        with self.assertRaises(DataProtectionError):
            await self.protection().unlock("0123", self.stored())
        self.assertIn(INITIALIZATION_ALIAS, self.storage.values)
        self.assertNotIn(DATA_BINDING_ALIAS, self.storage.values)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.values)
        self.storage.fail_set_key = None
        self.storage.read_keys.clear()
        protection = self.restart()
        self.assertTrue(await protection.has_protection())
        await protection.reconcile()
        await self.assert_rejected_without_mutation(protection, pin="9999")
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await protection.unlock("0123", self.stored())
        self.assert_preserved()

    async def test_previous_binding_only_state_with_protected_flag_stays_closed(self):
        await self.interrupted_initialization()
        self.storage.values.pop(INITIALIZATION_ALIAS)
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        binding["protected"] = True
        self.storage.values[DATA_BINDING_ALIAS] = json.dumps(binding)
        await self.assert_rejected_without_mutation(self.restart())

    async def test_previous_binding_only_state_with_encrypted_field_stays_closed(self):
        await self.interrupted_initialization()
        self.storage.values.pop(INITIALIZATION_ALIAS)
        ciphertext = FieldCipher(
            bytes(range(32)), "synthetic-database", "synthetic-key"
        ).encrypt(
            "synthetic protected title",
            table="chats",
            field="title",
            record_id="chat-1",
        )
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE chats SET title=? WHERE id='chat-1'", (ciphertext,)
            )
        await self.assert_rejected_without_mutation(self.restart())

    async def test_previous_binding_only_state_with_cipher_temporary_stays_closed(self):
        await self.interrupted_initialization()
        self.storage.values.pop(INITIALIZATION_ALIAS)
        temporary = self.database.path.with_name(
            "." + self.database.path.name + ".protected-ambiguous"
        )
        temporary.write_bytes(b"synthetic evidence must remain")
        await self.assert_rejected_without_mutation(self.restart())
        self.assertEqual(temporary.read_bytes(), b"synthetic evidence must remain")

    async def test_previous_binding_only_state_with_schema5_stays_closed(self):
        await self.interrupted_initialization()
        self.storage.values.pop(INITIALIZATION_ALIAS)
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("PRAGMA user_version=5")
        await self.assert_rejected_without_mutation(self.restart())

    async def test_successful_system_fixture_can_finish_initialization_after_restart(
        self,
    ):
        await self.interrupted_initialization()
        protection = self.restart()
        token = await protection.recover(cast(DeviceRecovery, Provider()))
        self.assertFalse(self.access.unlocked)
        self.assertEqual(self.stored(), self.original_auth)
        await protection.replace_pin(token, "0123")
        # Выбор PIN закономерно создаёт новый verifier с новым salt.
        self.assertEqual(
            self.stored().registration_id, self.original_auth.registration_id
        )
        self.original_auth = self.stored()
        self.original["auth_state"] = snapshot(self.database.path)["auth_state"]
        self.assert_preserved()

    async def test_durable_ack_boundaries_resume_on_fresh_instances(self):
        calls = 0

        async def count_ack():
            nonlocal calls
            calls += 1

        protection = self.protection(durable_write=count_ack)
        await protection.unlock("0123", self.stored())
        self.assert_preserved()
        boundary_count = calls
        self.assertGreaterEqual(boundary_count, 4)
        for interrupted_ack in range(1, boundary_count + 1):
            with self.subTest(interrupted_ack=interrupted_ack):
                self.setUp()
                calls = 0

                async def interrupt_ack():
                    nonlocal calls
                    calls += 1
                    if calls == interrupted_ack:
                        raise OSError("synthetic interrupted durable acknowledgement")

                interrupted = self.protection(durable_write=interrupt_ack)
                with self.assertRaises(DataProtectionError):
                    await interrupted.unlock("0123", self.stored())
                self.assertFalse(self.access.unlocked)
                prior_key = self.storage.values.get(DATA_KEY_ALIAS)
                resumed = self.restart(durable_write=count_ack)
                await resumed.reconcile()
                await resumed.unlock("0123", self.stored())
                self.assert_preserved()
                if prior_key is not None:
                    self.assertEqual(self.storage.values[DATA_KEY_ALIAS], prior_key)

    async def test_storage_mutation_boundaries_resume_on_fresh_instances(self):
        original_set = self.storage.set
        mutations = []

        async def record_set(key, value):
            mutations.append(key)
            await original_set(key, value)

        with patch.object(self.storage, "set", side_effect=record_set):
            await self.protection().unlock("0123", self.stored())
        self.assertGreaterEqual(len(mutations), 4)
        for interrupt_after in (False, True):
            for operation in range(1, len(mutations) + 1):
                with self.subTest(operation=operation, interrupt_after=interrupt_after):
                    self.setUp()
                    calls = 0
                    original_set = self.storage.set

                    async def interrupt_set(key, value):
                        nonlocal calls
                        calls += 1
                        if calls == operation and not interrupt_after:
                            raise OSError("synthetic interruption before storage set")
                        await original_set(key, value)
                        if calls == operation and interrupt_after:
                            raise OSError("synthetic interruption after storage set")

                    with patch.object(self.storage, "set", side_effect=interrupt_set):
                        with self.assertRaises(DataProtectionError):
                            await self.protection().unlock("0123", self.stored())
                    self.assertFalse(self.access.unlocked)
                    prior_key = self.storage.values.get(DATA_KEY_ALIAS)
                    resumed = self.restart()
                    await resumed.reconcile()
                    await resumed.unlock("0123", self.stored())
                    self.assert_preserved()
                    if prior_key is not None:
                        self.assertEqual(self.storage.values[DATA_KEY_ALIAS], prior_key)

    async def test_lost_ack_and_lost_uncommitted_storage_resume_after_restart(self):
        calls = 0

        async def count_ack():
            nonlocal calls
            calls += 1

        await self.protection(durable_write=count_ack).unlock("0123", self.stored())
        boundary_count = calls
        for committed_before_failure in (False, True):
            for interrupted_ack in range(1, boundary_count + 1):
                with self.subTest(
                    ack=interrupted_ack, committed=committed_before_failure
                ):
                    self.setUp()
                    calls = 0
                    durable = dict(self.storage.values)

                    async def interrupt_ack():
                        nonlocal calls, durable
                        calls += 1
                        if calls == interrupted_ack and not committed_before_failure:
                            raise OSError("synthetic failure before backend commit")
                        durable = dict(self.storage.values)
                        if calls == interrupted_ack:
                            raise OSError(
                                "synthetic lost acknowledgement after backend commit"
                            )

                    with self.assertRaises(DataProtectionError):
                        await self.protection(durable_write=interrupt_ack).unlock(
                            "0123", self.stored()
                        )
                    self.assertFalse(self.access.unlocked)
                    self.storage.values = dict(durable)
                    durable_key = self.storage.values.get(DATA_KEY_ALIAS)
                    await self.restart(durable_write=count_ack).unlock(
                        "0123", self.stored()
                    )
                    self.assert_preserved()
                    if durable_key is not None:
                        self.assertEqual(
                            self.storage.values[DATA_KEY_ALIAS], durable_key
                        )

    async def test_storage_read_failures_restart_without_replacing_persisted_key(self):
        reads = 0
        original_get = self.storage.get
        original_contains = self.storage.contains_key

        async def count_get(key):
            nonlocal reads
            reads += 1
            return await original_get(key)

        async def count_contains(key):
            nonlocal reads
            reads += 1
            return await original_contains(key)

        with (
            patch.object(self.storage, "get", side_effect=count_get),
            patch.object(self.storage, "contains_key", side_effect=count_contains),
        ):
            await self.protection().unlock("0123", self.stored())
        boundary_count = reads
        for interrupted_read in range(1, boundary_count + 1):
            with self.subTest(interrupted_read=interrupted_read):
                self.setUp()
                reads = 0
                original_get = self.storage.get
                original_contains = self.storage.contains_key

                async def fail_get(key):
                    nonlocal reads
                    reads += 1
                    if reads == interrupted_read:
                        raise OSError("synthetic secure read failure")
                    return await original_get(key)

                async def fail_contains(key):
                    nonlocal reads
                    reads += 1
                    if reads == interrupted_read:
                        raise OSError("synthetic secure contains failure")
                    return await original_contains(key)

                with (
                    patch.object(self.storage, "get", side_effect=fail_get),
                    patch.object(
                        self.storage, "contains_key", side_effect=fail_contains
                    ),
                ):
                    with self.assertRaises(DataProtectionError):
                        await self.protection().unlock("0123", self.stored())
                self.assertFalse(self.access.unlocked)
                saved_key = self.storage.values.get(DATA_KEY_ALIAS)
                await self.restart().unlock("0123", self.stored())
                self.assert_preserved()
                if saved_key is not None:
                    self.assertEqual(self.storage.values[DATA_KEY_ALIAS], saved_key)

    async def assert_rejected_without_mutation(self, protection, *, pin="0123"):
        before_database = self.database.path.read_bytes()
        before_aliases = dict(self.storage.values)
        self.storage.mutations.clear()
        with self.assertRaises(DataProtectionError):
            await protection.unlock(pin, self.stored())
        self.assertFalse(self.access.unlocked)
        self.assertEqual(self.database.path.read_bytes(), before_database)
        self.assertEqual(self.storage.values, before_aliases)
        self.assertEqual(self.storage.mutations, [])

    async def test_wrong_pin_after_initial_fault_cannot_clean_or_resume_aliases(self):
        await self.interrupted_initialization()
        protection = self.restart()
        self.storage.read_keys.clear()
        await self.assert_rejected_without_mutation(protection, pin="9999")
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        await protection.unlock("0123", self.stored())
        self.assert_preserved()

    async def test_protected_database_missing_key_remains_closed_after_restart(self):
        protection = self.protection()
        await protection.unlock("0123", self.stored())
        protection.lock()
        self.storage.values.pop(DATA_KEY_ALIAS)
        await self.assert_rejected_without_mutation(self.restart())

    async def test_protected_database_corrupt_key_remains_closed_after_restart(self):
        protection = self.protection()
        await protection.unlock("0123", self.stored())
        protection.lock()
        self.storage.values[DATA_KEY_ALIAS] = "synthetic-corrupt-key"
        await self.assert_rejected_without_mutation(self.restart())

    async def test_initial_tampered_binding_cannot_create_key(self):
        await self.interrupted_initialization()
        original = self.storage.values[DATA_BINDING_ALIAS]
        for name in ("fingerprint", "database_id", "key_id"):
            with self.subTest(field=name):
                altered = json.loads(original)
                altered[name] = "synthetic-tampered-value"
                self.storage.values[DATA_BINDING_ALIAS] = json.dumps(altered)
                self.storage.read_keys.clear()
                await self.assert_rejected_without_mutation(self.restart())
                self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_system_challenge_cannot_override_tampered_initial_binding(self):
        await self.interrupted_initialization()
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        binding["fingerprint"] = "synthetic-tampered-fingerprint"
        self.storage.values[DATA_BINDING_ALIAS] = json.dumps(binding)
        before_database = self.database.path.read_bytes()
        before_aliases = dict(self.storage.values)
        self.storage.mutations.clear()
        self.storage.read_keys.clear()
        protection = self.restart()
        with self.assertRaises(DataProtectionError):
            await protection.recover(cast(DeviceRecovery, Provider()))
        self.assertEqual(self.storage.values, before_aliases)
        self.assertEqual(self.database.path.read_bytes(), before_database)
        self.assertEqual(self.storage.mutations, [])
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertFalse(self.access.unlocked)

    async def test_cancelled_system_fixture_cannot_resume_initialization(self):
        await self.interrupted_initialization()
        before_database = self.database.path.read_bytes()
        before_aliases = dict(self.storage.values)
        self.storage.mutations.clear()
        self.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.restart().recover(
                cast(DeviceRecovery, Provider(RecoveryStatus.CANCELLED))
            )
        self.assertFalse(self.access.unlocked)
        self.assertEqual(self.database.path.read_bytes(), before_database)
        self.assertEqual(self.storage.values, before_aliases)
        self.assertEqual(self.storage.mutations, [])
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_initial_missing_key_with_cipher_journal_preserves_evidence(self):
        await self.interrupted_initialization()
        journal = self.database.path.with_name(
            self.database.path.name + ".protection-migration.json"
        )
        journal.write_text('{"synthetic":"ambiguous-preserve-evidence"}')
        before = journal.read_bytes()
        await self.assert_rejected_without_mutation(self.restart())
        self.assertEqual(journal.read_bytes(), before)

    async def test_schema6_with_protection_marker_cannot_initialize_key(self):
        await self.interrupted_initialization()
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("CREATE TABLE content_protection (marker TEXT)")
            connection.execute(
                "INSERT INTO content_protection VALUES ('synthetic-protected-marker')"
            )
        await self.assert_rejected_without_mutation(self.restart())

    async def test_initial_database_substitution_preserves_file_and_aliases(self):
        await self.interrupted_initialization()
        with sqlite3.connect(self.database.path) as connection:
            connection.execute(
                "UPDATE chat_drafts SET content='synthetic-substitution' WHERE chat_id='chat-1'"
            )
        await self.assert_rejected_without_mutation(self.restart())

    async def test_initial_auth_substitution_with_its_valid_pin_cannot_resume(self):
        await self.interrupted_initialization()
        self.database.save_auth_state(
            "initialization-fixture", self.hasher.create_record("9999")
        )
        self.storage.read_keys.clear()
        await self.assert_rejected_without_mutation(self.restart(), pin="9999")
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_failed_attempt_counter_change_does_not_invalidate_initial_intent(
        self,
    ):
        await self.interrupted_initialization()
        self.database.register_failed_attempt(100, 5, 30)
        self.original_auth = self.stored()
        self.original["auth_state"] = snapshot(self.database.path)["auth_state"]
        await self.restart().unlock("0123", self.stored())
        self.assert_preserved()

    async def test_stale_binding_read_after_lock_cannot_create_or_clean_key(self):
        await self.interrupted_initialization()
        protection = self.restart()
        before_database = self.database.path.read_bytes()
        before_aliases = dict(self.storage.values)
        self.storage.mutations.clear()
        reached, release = asyncio.Event(), asyncio.Event()
        original_get = self.storage.get

        async def delayed_get(key):
            value = await original_get(key)
            if key == DATA_BINDING_ALIAS:
                reached.set()
                await release.wait()
            return value

        with patch.object(self.storage, "get", side_effect=delayed_get):
            task = asyncio.create_task(protection.unlock("0123", self.stored()))
            await asyncio.wait_for(reached.wait(), 2)
            protection.lock()
            release.set()
            with self.assertRaises(DataProtectionError):
                await asyncio.wait_for(task, 2)
        self.assertEqual(self.storage.values, before_aliases)
        self.assertEqual(self.database.path.read_bytes(), before_database)
        self.assertEqual(self.storage.mutations, [])
        self.assertFalse(self.access.unlocked)

    async def test_malformed_initialization_metadata_cannot_clean_or_create_key(self):
        await self.interrupted_initialization()
        original = self.storage.values[INITIALIZATION_ALIAS]
        for raw in (
            "not-json",
            "[]",
            '{"version":99}',
            json.dumps({**json.loads(original), "phase": "unknown"}),
        ):
            with self.subTest(value=raw[:32]):
                self.storage.values[INITIALIZATION_ALIAS] = raw
                await self.assert_rejected_without_mutation(self.restart())

    async def test_initialization_identity_mismatch_cannot_clean_or_create_key(self):
        await self.interrupted_initialization()
        original = json.loads(self.storage.values[INITIALIZATION_ALIAS])
        for name in ("database_id", "key_id", "fingerprint", "plaintext_digest"):
            with self.subTest(field=name):
                self.storage.values[INITIALIZATION_ALIAS] = json.dumps(
                    {**original, name: "0" * 64}
                )
                await self.assert_rejected_without_mutation(self.restart())

    async def test_key_ready_phase_missing_key_cannot_regenerate_even_schema6(self):
        await self.interrupted_initialization()
        state = json.loads(self.storage.values[INITIALIZATION_ALIAS])
        state["phase"] = "key_ready"
        self.storage.values[INITIALIZATION_ALIAS] = json.dumps(state)
        await self.assert_rejected_without_mutation(self.restart())


if __name__ == "__main__":
    unittest.main()
