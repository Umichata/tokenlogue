"""Удаление работает только с временными синтетическими профилями."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import stat
import subprocess
import sys
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import storage.profile_deletion as deletion_module
from auth.models import AuthStatus
from auth.service import AuthService
from preferences import PreferencesStore
from storage.data_access import DataAccess, DataAccessError
from storage.data_protection import (
    DATA_BINDING_ALIAS,
    DATA_INITIALIZATION_ALIAS,
    DATA_KEY_ALIAS,
    DataProtection,
    DataProtectionError,
)
from storage.database import AuthDatabase
from storage.database_connections import DatabaseDeletionPendingError
from storage.profile_deletion import (
    PROFILE_ALIASES,
    ProfileDeletion,
    ProfileDeletionError,
    validate_profile_path,
)
from storage.secure_credentials import (
    API_KEY_STORAGE_NAME,
    REGISTRATION_ID_STORAGE_NAME,
    FletSecureCredentials,
)
from tests.test_data_protection import ProtectionFixture
from tests.test_message_sending import FakeKeyValidator


class ProfileDeletionTests(ProtectionFixture):
    async def asyncSetUp(self):
        self.storage.values[API_KEY_STORAGE_NAME] = "synthetic-credential"
        self.deletion = ProfileDeletion(self.database.path, self.storage)

    async def test_capture_and_cancel_never_read_secret_or_change_profile(self):
        await self.enroll()
        before = self.database.path.read_bytes(), dict(self.storage.values)
        scope = await self.deletion.capture()
        self.deletion.cancel()
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.accept(scope)
        self.assertEqual(before, (self.database.path.read_bytes(), self.storage.values))
        self.assertEqual(
            set(self.storage.read_keys),
            {
                REGISTRATION_ID_STORAGE_NAME,
                DATA_BINDING_ALIAS,
                DATA_INITIALIZATION_ALIAS,
            },
        )
        self.assertFalse(self.deletion.pending())

    async def test_schema_6_deletion_preserves_neighbors_preferences_and_owner_inode(
        self,
    ):
        self.storage.read_keys.clear()
        neighbor = self.database.path.with_name("user-export.json")
        neighbor.write_text("user export", encoding="utf-8")
        preferences = self.database.path.with_name("tokenlogue-preferences.json")
        preferences.write_text('{"language":"en"}', encoding="utf-8")
        self.storage.values["another.application.alias"] = "preserve"
        owner = self.database.path.with_name(
            "." + self.database.path.name + ".owner.lock"
        )
        inode = owner.stat().st_ino
        scope = await self.deletion.capture()
        await self.deletion.accept(scope)
        self.assertTrue(self.deletion.pending())
        await self.deletion.finish()
        self.assertFalse(self.database.path.exists())
        self.assertFalse(self.deletion.pending())
        self.assertEqual(owner.stat().st_ino, inode)
        self.assertTrue(neighbor.exists())
        self.assertTrue(preferences.exists())
        self.assertEqual(self.storage.values, {"another.application.alias": "preserve"})
        self.assertEqual(
            set(self.storage.read_keys),
            {
                REGISTRATION_ID_STORAGE_NAME,
                DATA_BINDING_ALIAS,
                DATA_INITIALIZATION_ALIAS,
            },
        )

    async def test_schema_7_missing_dek_and_pending_pin_journal_can_be_deleted(self):
        await self.enroll()
        self.storage.values.pop(DATA_KEY_ALIAS)
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        binding["pending"] = {"unreadable": "old pin journal is never parsed"}
        self.storage.values[DATA_BINDING_ALIAS] = json.dumps(binding)
        self.storage.read_keys.clear()
        await self.deletion.accept(await self.deletion.capture())
        await self.deletion.finish()
        self.assertFalse(self.database.path.exists())
        self.assertEqual(self.storage.values, {})
        self.assertEqual(
            set(self.storage.read_keys),
            {
                REGISTRATION_ID_STORAGE_NAME,
                DATA_BINDING_ALIAS,
                DATA_INITIALIZATION_ALIAS,
            },
        )

    async def test_remove_failure_and_restart_resume_only_same_profile(self):
        await self.enroll()
        await self.deletion.accept(await self.deletion.capture())
        original = self.storage.remove

        async def fail(key):
            if key == DATA_KEY_ALIAS:
                raise RuntimeError("synthetic unavailable backend")
            await original(key)

        with patch.object(self.storage, "remove", side_effect=fail):
            with self.assertRaises(ProfileDeletionError):
                await self.deletion.finish()
        self.assertTrue(self.deletion.pending())
        self.assertTrue(self.database.path.exists())
        self.assertNotIn(API_KEY_STORAGE_NAME, self.storage.values)
        restarted = ProfileDeletion(self.database.path, self.storage)
        await restarted.finish()
        self.assertFalse(self.database.path.exists())
        self.assertFalse(restarted.pending())
        self.assertEqual(self.storage.values, {})

    async def test_lost_android_ack_and_readback_failure_keep_durable_intent(self):
        await self.enroll()
        acks = 0

        async def ack():
            nonlocal acks
            acks += 1
            if acks == 1:
                raise RuntimeError("lost native ACK")

        self.deletion = ProfileDeletion(
            self.database.path, self.storage, durable_write=ack
        )
        await self.deletion.accept(await self.deletion.capture())
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.finish()
        self.assertTrue(self.deletion.pending())
        self.assertTrue(self.database.path.exists())
        await self.deletion.finish()
        self.assertGreaterEqual(acks, len(PROFILE_ALIASES))
        self.assertFalse(self.deletion.pending())

    async def test_failed_removal_readback_does_not_allow_new_registration(self):
        await self.deletion.accept(await self.deletion.capture())
        with patch.object(self.storage, "remove", return_value=None):
            with self.assertRaises(ProfileDeletionError):
                await self.deletion.finish()
        self.assertTrue(self.deletion.pending())
        self.assertTrue(self.database.path.exists())

    async def test_changed_registration_or_database_rejects_stale_confirmation(self):
        scope = await self.deletion.capture()
        self.storage.values[REGISTRATION_ID_STORAGE_NAME] = "another-registration"
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.accept(scope)
        self.assertFalse(self.deletion.pending())
        self.assertTrue(self.database.path.exists())

    async def test_symlink_hardlink_wrong_owner_and_corrupt_metadata_fail_closed(self):
        sidecar = self.database.path.with_name(self.database.path.name + "-journal")
        neighbor = self.database.path.with_name("outside-backup")
        neighbor.write_text("preserve", encoding="utf-8")
        sidecar.symlink_to(neighbor)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.capture()
        sidecar.unlink()
        os.link(neighbor, sidecar)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.capture()
        sidecar.unlink()
        with sqlite3.connect(self.database.path) as connection:
            connection.execute("UPDATE auth_state SET registration_id=''")
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.capture()
        self.assertEqual(neighbor.read_text(encoding="utf-8"), "preserve")
        self.assertFalse(self.deletion.pending())

    async def test_database_path_symlink_never_claims_foreign_profile(self):
        symlink = self.database.path.with_name("foreign.sqlite3")
        symlink.symlink_to(self.database.path)
        with self.assertRaises(ProfileDeletionError):
            await ProfileDeletion(symlink, self.storage).capture()
        self.assertTrue(self.database.path.exists())

    async def test_foreign_alias_registration_during_retry_is_never_deleted(self):
        await self.deletion.accept(await self.deletion.capture())
        self.storage.values[REGISTRATION_ID_STORAGE_NAME] = "foreign-registration"
        before = dict(self.storage.values)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.finish()
        self.assertEqual(self.storage.values, before)
        self.assertTrue(self.deletion.pending())

    async def test_missing_files_after_partial_unlink_are_idempotent(self):
        await self.enroll()
        await self.deletion.accept(await self.deletion.capture())
        original = self.deletion._unlink
        removed = False

        def unlink(name, identity):
            nonlocal removed
            original(name, identity)
            if not removed:
                removed = True
                raise OSError("process stopped after unlink")

        with patch.object(self.deletion, "_unlink", side_effect=unlink):
            with self.assertRaises(ProfileDeletionError):
                await self.deletion.finish()
        self.assertTrue(self.deletion.pending())
        await ProfileDeletion(self.database.path, self.storage).finish()
        self.assertFalse(self.deletion.pending())
        self.assertFalse(self.database.path.exists())

    async def test_terminal_deletion_revocation_rejects_old_completion_lease(self):
        await self.protection.unlock("0123", self.stored())
        lease = self.access.completion("draft", "chat", "chat")
        self.access.revoke_for_deletion()
        with lease.use(), self.assertRaises(DataAccessError):
            with self.access.authorize("draft", chat_id="chat", record_id="chat"):
                self.fail("deleted profile lease must never authorize")
        with self.assertRaises(DataAccessError):
            cipher = lease.cipher
            assert cipher is not None
            self.access.open(cipher)
        lease.close()

    async def test_lock_during_capture_invalidates_unaccepted_confirmation(self):
        original_get = self.storage.get
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked(key):
            entered.set()
            await release.wait()
            return await original_get(key)

        with patch.object(self.storage, "get", side_effect=blocked):
            task = asyncio.create_task(self.deletion.capture())
            await entered.wait()
            self.deletion.cancel()
            release.set()
            with self.assertRaises(ProfileDeletionError):
                await task
        self.assertFalse(self.deletion.pending())

    async def test_foreign_binding_coordinates_refuse_deletion_even_same_registration(
        self,
    ):
        await self.enroll()
        value = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        value["database_id"] = "different-database"
        self.storage.values[DATA_BINDING_ALIAS] = json.dumps(value)
        before = dict(self.storage.values)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.capture()
        self.assertEqual(before, self.storage.values)
        self.assertFalse(self.deletion.pending())

    async def test_pending_intent_blocks_ordinary_connections_and_constructor(self):
        await self.deletion.accept(await self.deletion.capture())
        before = self.database.path.read_bytes()
        with self.assertRaises(DatabaseDeletionPendingError):
            self.database.get_auth_state()
        with self.assertRaises(DatabaseDeletionPendingError):
            AuthDatabase(self.temporary.name)
        self.assertEqual(self.database.path.read_bytes(), before)

    async def test_sqlite_owned_sidecars_are_deleted_but_adjacent_backup_is_preserved(
        self,
    ):
        sidecars = [
            self.database.path.with_name(self.database.path.name + suffix)
            for suffix in ("-wal", "-shm", "-journal")
        ]
        for sidecar in sidecars:
            sidecar.touch()
        backup = self.database.path.with_name(self.database.path.name + ".backup")
        backup.write_bytes(b"user-managed external copy")
        scope = await self.deletion.capture()
        await self.deletion.accept(scope)
        await self.deletion.finish()
        for sidecar in sidecars:
            self.assertFalse(sidecar.exists())
        self.assertTrue(backup.exists())

    async def test_wrong_owner_and_unsafe_profile_directory_are_rejected(self):
        original = Path.stat

        def wrong_owner(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == self.database.path:
                fields = list(result)
                fields[4] = os.getuid() + 1
                return os.stat_result(fields)
            return result

        with patch.object(Path, "stat", autospec=True, side_effect=wrong_owner):
            with self.assertRaises(ProfileDeletionError):
                await self.deletion.capture()
        Path(self.temporary.name).chmod(0o777)
        try:
            with self.assertRaises(ProfileDeletionError):
                await self.deletion.capture()
        finally:
            Path(self.temporary.name).chmod(0o700)
        self.assertFalse(self.deletion.pending())

    async def test_unbound_foreign_dek_in_schema_6_namespace_is_not_deleted(self):
        self.storage.values[DATA_KEY_ALIAS] = "unrelated opaque value is not inspected"
        before = dict(self.storage.values)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.capture()
        self.assertEqual(self.storage.values, before)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_unexpected_profile_preferences_are_removed_and_language_layout_retained(
        self,
    ):
        preferences = self.database.path.parent / "tokenlogue-preferences.json"
        preferences.write_text(
            json.dumps(
                {
                    "language": "en",
                    "wide_sidebar_visible": False,
                    "selected_chat_id": "old-chat",
                    "title": "old synthetic title",
                    "draft": "old synthetic draft",
                }
            ),
            encoding="utf-8",
        )
        await self.deletion.accept(await self.deletion.capture())
        intent = self.deletion.intent_path.read_text(encoding="utf-8")
        self.assertNotIn("old-chat", intent)
        self.assertNotIn("old synthetic", intent)
        await self.deletion.finish()
        self.assertEqual(
            json.loads(preferences.read_text(encoding="utf-8")),
            {"language": "en", "wide_sidebar_visible": False},
        )

    async def test_restart_after_preference_replace_ack_loss_drops_no_foreign_file(
        self,
    ):
        preferences = self.database.path.parent / "tokenlogue-preferences.json"
        preferences.write_text(
            '{"language":"en","selected_chat":"old-chat"}', encoding="utf-8"
        )
        await self.deletion.accept(await self.deletion.capture())
        original = self.deletion._sanitize_preferences

        def interrupted(intent):
            original(intent)
            raise OSError("simulated stop after atomic preference replace")

        with patch.object(
            self.deletion, "_sanitize_preferences", side_effect=interrupted
        ):
            with self.assertRaises(ProfileDeletionError):
                await self.deletion.finish()
        self.assertTrue(self.deletion.pending())
        await ProfileDeletion(self.database.path, self.storage).finish()
        self.assertEqual(
            json.loads(preferences.read_text(encoding="utf-8")), {"language": "en"}
        )
        self.assertFalse(self.deletion.pending())

    async def test_user_owned_profile_directory_symlink_is_never_followed(self):
        linked = self.database.path.parent / "profile-link"
        linked.symlink_to(self.database.path.parent, target_is_directory=True)
        with self.assertRaises(ProfileDeletionError):
            await ProfileDeletion(
                linked / self.database.path.name, self.storage
            ).capture()
        self.assertTrue(self.database.path.exists())

    async def test_quiesced_wal_change_between_dialog_and_confirm_uses_current_allowlist(
        self,
    ):
        scope = await self.deletion.capture()
        wal = self.database.path.with_name(self.database.path.name + "-wal")
        wal.touch()
        preferences = self.database.path.parent / "tokenlogue-preferences.json"
        preferences.write_text(
            '{"language":"en","selected_chat":"synthetic-stale"}', encoding="utf-8"
        )
        await self.deletion.accept(scope)
        await self.deletion.finish()
        self.assertFalse(wal.exists())
        self.assertEqual(
            json.loads(preferences.read_text(encoding="utf-8")), {"language": "en"}
        )

    async def test_replaced_main_inode_between_dialog_and_confirm_is_never_accepted(
        self,
    ):
        scope = await self.deletion.capture()
        replacement = self.database.path.with_name("replacement.sqlite3")
        replacement.write_bytes(self.database.path.read_bytes())
        os.replace(replacement, self.database.path)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.accept(scope)
        self.assertFalse(self.deletion.pending())
        self.assertIn(API_KEY_STORAGE_NAME, self.storage.values)

    async def test_late_old_auth_worker_cannot_write_into_new_profile_after_intent_removed(
        self,
    ):
        await self.deletion.accept(await self.deletion.capture())
        await self.deletion.finish()
        replacement = AuthDatabase(self.temporary.name)
        replacement.save_auth_state(
            "new-registration", self.hasher.create_record("4567")
        )
        with self.assertRaises(DatabaseDeletionPendingError):
            self.database.save_auth_state(
                "fixture-registration", self.hasher.create_record("0123")
            )
        stored = replacement.get_auth_state()
        assert stored is not None
        self.assertEqual(stored.registration_id, "new-registration")

    async def test_running_thread_delayed_before_sql_cannot_mutate_replacement_registration(
        self,
    ):
        entered, release = threading.Event(), threading.Event()
        record = self.hasher.create_record("0123")

        def late_worker():
            entered.set()
            release.wait(10)
            try:
                self.database.save_auth_state("old-delayed-registration", record)
            except DatabaseDeletionPendingError:
                return "refused"
            return "wrote"

        worker = asyncio.create_task(asyncio.to_thread(late_worker))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            await self.deletion.accept(await self.deletion.capture())
            await self.deletion.finish()
            replacement = AuthDatabase(self.temporary.name)
            replacement.save_auth_state(
                "new-registration", self.hasher.create_record("4567")
            )
        finally:
            release.set()
        self.assertEqual(await worker, "refused")
        stored = replacement.get_auth_state()
        assert stored is not None
        self.assertEqual(stored.registration_id, "new-registration")

    async def test_migration_temporaries_require_matching_journal_and_no_symlink(self):
        await self.enroll()
        binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        temporary = self.database.path.with_name(
            "." + self.database.path.name + ".protected-synthetic"
        )
        temporary.write_bytes(b"synthetic encrypted migration fragment")
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.capture()
        journal = self.database.path.with_name(
            self.database.path.name + ".protection-migration.json"
        )
        journal.write_text(
            json.dumps(
                dict(
                    version=1,
                    stage="copying",
                    temporary=temporary.name,
                    database_id=binding["database_id"],
                    key_id=binding["key_id"],
                    proof="ignored encrypted marker",
                )
            ),
            encoding="utf-8",
        )
        await self.deletion.accept(await self.deletion.capture())
        await self.deletion.finish()
        self.assertFalse(temporary.exists())
        self.assertFalse(journal.exists())

    async def test_restart_resumes_complete_intent_write_left_before_rename(self):
        await self.deletion.accept(await self.deletion.capture())
        writing = self.deletion.intent_path.with_name(
            self.deletion.intent_path.name + ".write"
        )
        self.deletion.intent_path.replace(writing)
        restarted = ProfileDeletion(self.database.path, self.storage)
        self.assertTrue(restarted.pending())
        await restarted.finish()
        self.assertFalse(restarted.pending())
        self.assertFalse(self.database.path.exists())

    async def test_restart_discards_same_intent_progress_write_and_retries(self):
        await self.deletion.accept(await self.deletion.capture())
        value = json.loads(self.deletion.intent_path.read_text(encoding="utf-8"))
        value["removed"] = [API_KEY_STORAGE_NAME]
        self.storage.values.pop(API_KEY_STORAGE_NAME)
        writing = self.deletion.intent_path.with_name(
            self.deletion.intent_path.name + ".write"
        )
        writing.write_text(json.dumps(value), encoding="utf-8")
        await ProfileDeletion(self.database.path, self.storage).finish()
        self.assertFalse(self.deletion.pending())
        self.assertFalse(writing.exists())

    async def test_corrupt_intent_or_foreign_progress_write_never_deletes(self):
        await self.deletion.accept(await self.deletion.capture())
        value = json.loads(self.deletion.intent_path.read_text(encoding="utf-8"))
        value["nonce"] = "f" * 32
        writing = self.deletion.intent_path.with_name(
            self.deletion.intent_path.name + ".write"
        )
        writing.write_text(json.dumps(value), encoding="utf-8")
        before = dict(self.storage.values)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.finish()
        self.assertEqual(self.storage.values, before)
        self.assertTrue(self.database.path.exists())

    async def test_metadata_queries_cannot_read_pin_verifier_or_content_columns(self):
        await self.enroll()
        connect = sqlite3.connect
        denied = []

        def guarded(*args, **kwargs):
            connection = connect(*args, **kwargs)

            def authorize(action, table, column, _database, _trigger):
                if action == sqlite3.SQLITE_READ and (
                    (table == "auth_state" and column != "registration_id")
                    or table
                    in {"chats", "messages", "turns", "chat_budgets", "chat_drafts"}
                ):
                    denied.append((table, column))
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            connection.set_authorizer(authorize)
            return connection

        with patch("storage.profile_deletion.sqlite3.connect", side_effect=guarded):
            await self.deletion.accept(await self.deletion.capture())
            await self.deletion.finish()
        self.assertEqual(denied, [])
        self.assertNotIn(API_KEY_STORAGE_NAME, self.storage.read_keys)
        self.assertNotIn(DATA_KEY_ALIAS, self.storage.read_keys)

    async def test_owner_lock_blocks_second_process_after_deletion_before_setup(self):
        await self.deletion.accept(await self.deletion.capture())
        await self.deletion.finish()
        script = "import sys; from storage.database import AuthDatabase; AuthDatabase(sys.argv[1])"
        result = subprocess.run(
            [sys.executable, "-c", script, self.temporary.name],
            env=dict(
                os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")
            ),
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DatabaseOwnershipError", result.stderr)
        self.assertFalse(self.database.path.exists())

    async def test_real_language_preference_write_after_intent_does_not_block_deletion(
        self,
    ):
        preferences = self.database.path.parent / "tokenlogue-preferences.json"
        preferences.write_text(
            '{"language":"ru","wide_sidebar_visible":false,"selected_chat":"old-chat"}',
            encoding="utf-8",
        )
        store = PreferencesStore(preferences)
        await self.deletion.accept(await self.deletion.capture())
        store.set_language("en")
        await self.deletion.finish()
        self.assertFalse(self.deletion.pending())
        self.assertEqual(
            json.loads(preferences.read_text(encoding="utf-8")),
            {"language": "en", "wide_sidebar_visible": False},
        )

    async def test_new_inode_with_profile_preference_keys_after_intent_is_rejected(
        self,
    ):
        preferences = self.database.path.parent / "tokenlogue-preferences.json"
        preferences.write_text('{"language":"ru"}', encoding="utf-8")
        await self.deletion.accept(await self.deletion.capture())
        replacement = preferences.with_name("synthetic-new-preferences.json")
        replacement.write_text(
            '{"language":"en","selected_chat":"foreign-chat"}', encoding="utf-8"
        )
        os.replace(replacement, preferences)
        with self.assertRaises(ProfileDeletionError):
            await self.deletion.finish()
        self.assertTrue(self.deletion.pending())
        self.assertTrue(self.database.path.exists())

    async def test_new_preferences_created_after_intent_allow_only_public_whitelist(
        self,
    ):
        preferences = self.database.path.parent / "tokenlogue-preferences.json"
        await self.deletion.accept(await self.deletion.capture())
        PreferencesStore(preferences).set_language("en")
        await self.deletion.finish()
        self.assertFalse(self.deletion.pending())
        self.assertEqual(
            json.loads(preferences.read_text(encoding="utf-8")),
            {"language": "en", "wide_sidebar_visible": True},
        )

    def test_path_validator_creates_only_private_parent_without_database_or_flock(self):
        path = (
            self.database.path.parent / "new-profile" / "private" / "tokenlogue.sqlite3"
        )
        self.assertEqual(validate_profile_path(path), path)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        self.assertFalse(path.exists())
        self.assertFalse(path.with_name("." + path.name + ".owner.lock").exists())

    def test_path_validator_no_create_mode_and_symlink_ancestors_touch_no_foreign_paths(
        self,
    ):
        path = self.database.path.parent / "not-created" / "tokenlogue.sqlite3"
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)
        self.assertFalse(path.parent.exists())
        foreign = self.database.path.parent / "foreign"
        foreign.mkdir(mode=0o700)
        linked = self.database.path.parent / "linked-profile"
        linked.symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(linked / "not-created" / "tokenlogue.sqlite3")
        self.assertEqual(list(foreign.iterdir()), [])


class AndroidProfilePathTests(unittest.TestCase):
    def fixture(self, *, android=True, link_path="/data/user/0", target="/data/data"):
        self.metadata = {}
        for name, uid, gid, mode in (
            ("/", 0, 0, 0o755),
            ("/data", 1000, 1000, 0o771),
            ("/data/user", 0, 0, 0o751),
            ("/data/data", 0, 0, 0o751),
            ("/data/user/0", 0, 0, 0o777),
            ("/data/user/0/io.github.umichata.tokenlogue", 10216, 10216, 0o700),
            ("/data/user/0/io.github.umichata.tokenlogue/files", 10216, 10216, 0o771),
            (
                "/data/user/0/io.github.umichata.tokenlogue/files/data",
                10216,
                10216,
                0o700,
            ),
        ):
            self.metadata[name] = SimpleNamespace(
                st_uid=uid,
                st_gid=gid,
                st_mode=(stat.S_IFLNK if name == link_path else stat.S_IFDIR) | mode,
                st_nlink=1,
                st_dev=1,
                st_ino=len(self.metadata) + 1,
            )

        def stat_path(path, *, follow_symlinks=True):
            name = str(path)
            if name == link_path and follow_symlinks:
                name = target
            if name not in self.metadata:
                raise FileNotFoundError(name)
            return self.metadata[name]

        stack = ExitStack()
        self.addCleanup(stack.close)
        for context in (
            patch.object(Path, "stat", autospec=True, side_effect=stat_path),
            patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=lambda path, strict=False: (
                    Path(target) if str(path) == link_path else path
                ),
            ),
            patch.object(Path, "readlink", autospec=True, return_value=Path(target)),
            patch.object(
                deletion_module,
                "_android_application_runtime",
                return_value=android,
                create=True,
            ),
            patch.object(deletion_module.os, "getuid", return_value=10216),
        ):
            stack.enter_context(context)
        return Path(
            "/data/user/0/io.github.umichata.tokenlogue/files/data/tokenlogue.sqlite3"
        )

    def test_actual_android_system_authority_layout_is_supported(self):
        path = self.fixture()
        self.assertEqual(validate_profile_path(path, create_parent=False), path)

    def test_system_uid_is_not_trusted_on_ordinary_linux(self):
        path = self.fixture(android=False)
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)

    def test_android_link_rejects_wrong_owner_target_and_writable_authority(self):
        path = self.fixture()
        self.metadata["/data/user/0"].st_uid = 10216
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)
        self.metadata["/data/user/0"].st_uid = 0
        self.metadata["/data"].st_mode |= 0o002
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)
        self.metadata["/data"].st_mode &= ~0o002
        self.metadata["/data/data"].st_gid = 1001
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)
        self.metadata["/data/data"].st_uid = 1000
        self.metadata["/data/data"].st_gid = 1000
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)

    def test_android_link_requires_exact_os_path_and_target(self):
        path = self.fixture(target="/data/elsewhere")
        self.metadata["/data/elsewhere"] = self.metadata["/data/data"]
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(path, create_parent=False)

    def test_android_exception_cannot_authorize_another_root_owned_os_link(self):
        path = self.fixture()
        self.metadata = {
            name.replace("/data/user/0", "/data/user/1"): value
            for name, value in self.metadata.items()
        }
        with self.assertRaises(ProfileDeletionError):
            validate_profile_path(
                Path(str(path).replace("/data/user/0", "/data/user/1")),
                create_parent=False,
            )

    def test_ordinary_linux_function_or_environment_cannot_supply_android_marker(self):
        def getandroidapilevel():
            return 24

        getandroidapilevel.__module__ = "sys"
        with (
            patch.object(
                deletion_module.sys,
                "getandroidapilevel",
                getandroidapilevel,
                create=True,
            ),
            patch.dict(
                os.environ, {"ANDROID_ROOT": "/system", "ANDROID_DATA": "/data"}
            ),
            patch.object(deletion_module.os, "getuid", return_value=10216),
        ):
            self.assertFalse(deletion_module._android_application_runtime())

    def test_ordinary_group_writable_profile_can_open_but_cannot_be_deleted(self):
        with self.subTest("normal owned Linux directory"):
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                parent = Path(directory)
                parent.chmod(0o775)
                path = parent / "tokenlogue.sqlite3"
                self.assertEqual(
                    validate_profile_path(path, require_private=False), path
                )
                with self.assertRaises(ProfileDeletionError):
                    validate_profile_path(path)


class ProfileDeletionAuthTests(ProtectionFixture):
    async def asyncSetUp(self):
        self.credentials = FletSecureCredentials(self.storage)
        await self.credentials.save_credentials(
            "synthetic-old-api", "fixture-registration"
        )
        self.validator = FakeKeyValidator()
        self.deletion = ProfileDeletion(self.database.path, self.storage)
        self.auth = AuthService(
            self.validator,
            self.credentials,
            self.database,
            pin_hasher=self.hasher,
            protection=self.protection,
            profile_deletion=self.deletion,
        )

    async def test_pending_deletion_dominates_old_pin_and_code_reconcile(self):
        await self.enroll()
        await self.deletion.accept(await self.deletion.capture())
        self.storage.read_keys.clear()
        with patch.object(
            self.protection,
            "reconcile",
            side_effect=AssertionError("ordinary reconcile forbidden"),
        ) as reconcile:
            self.assertEqual(
                (await self.auth.initialize()).status, AuthStatus.STORAGE_ERROR
            )
            self.assertEqual(
                (await self.auth.login("0123")).status, AuthStatus.STORAGE_ERROR
            )
            self.assertEqual(
                (await self.auth.recover_with_code("A" * 32)).status,
                AuthStatus.STORAGE_ERROR,
            )
            self.assertEqual(
                (await self.auth.start_setup("synthetic-api")).status,
                AuthStatus.STORAGE_ERROR,
            )
        reconcile.assert_not_called()
        self.assertEqual(self.storage.read_keys, [])
        self.assertEqual(self.validator.calls, 0)

    async def test_direct_old_protection_reconcile_cannot_resurrect_deleted_profile(
        self,
    ):
        await self.enroll()
        await self.deletion.accept(await self.deletion.capture())
        self.storage.read_keys.clear()
        with self.assertRaises(DataProtectionError):
            await self.protection.reconcile()
        self.assertEqual(self.storage.read_keys, [])

    async def test_clean_registration_after_deletion_has_new_identities_and_rejects_old_code(
        self,
    ):
        await self.protection.unlock("0123", self.stored())
        issue = await self.protection.begin_recovery_code("0123")
        await self.protection.confirm_recovery_code(issue.attempt_id, issue.code)
        old_binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        old_key = self.storage.values[DATA_KEY_ALIAS]
        self.protection.lock()
        grant = await self.protection.recover_with_code(issue.code)
        scope = await self.auth.capture_profile_deletion()
        self.auth.prepare_profile_deletion()
        self.assertEqual(
            (await self.auth.confirm_profile_deletion(scope)).status,
            AuthStatus.PROFILE_DELETED,
        )
        self.assertEqual(self.validator.calls, 0)
        self.assertEqual(
            (await self.auth.login("0123")).status, AuthStatus.STORAGE_ERROR
        )
        with self.assertRaises(DataProtectionError):
            await self.protection.replace_pin(grant, "9999")
        database = AuthDatabase(self.temporary.name)
        access = DataAccess()
        protection = DataProtection(
            database.path, database, self.storage, access, pin_hasher=self.hasher
        )
        auth = AuthService(
            self.validator,
            self.credentials,
            database,
            pin_hasher=self.hasher,
            protection=protection,
            profile_deletion=ProfileDeletion(database.path, self.storage),
        )
        self.assertEqual((await auth.initialize()).status, AuthStatus.SETUP_REQUIRED)
        started = await auth.start_setup("synthetic-new-api")
        self.assertEqual(started.status, AuthStatus.PIN_CHOICE_REQUIRED)
        assert started.pending_setup_token is not None
        self.assertEqual(
            (await auth.complete_setup("4567", started.pending_setup_token)).status,
            AuthStatus.AUTHENTICATED,
        )
        new_binding = json.loads(self.storage.values[DATA_BINDING_ALIAS])
        self.assertNotEqual(new_binding["database_id"], old_binding["database_id"])
        self.assertNotEqual(new_binding["key_id"], old_binding["key_id"])
        self.assertNotEqual(self.storage.values[DATA_KEY_ALIAS], old_key)
        stored = database.get_auth_state()
        assert stored is not None
        self.assertNotEqual(stored.registration_id, "fixture-registration")
        with sqlite3.connect(database.path) as connection:
            for table in ("chats", "messages", "turns", "chat_budgets", "chat_drafts"):
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM " + table).fetchone()[0], 0
                )
        new_issue = await auth.begin_recovery_code("4567")
        self.assertEqual(new_issue.status, AuthStatus.RECOVERY_CODE_ISSUED)
        assert new_issue.recovery_code_issue is not None
        await auth.confirm_recovery_code(
            new_issue.recovery_code_issue.attempt_id, new_issue.recovery_code_issue.code
        )
        auth.lock_access()
        self.assertEqual(
            (await auth.recover_with_code(issue.code)).status, AuthStatus.STORAGE_ERROR
        )
        self.assertEqual((await auth.login("0123")).status, AuthStatus.INVALID_PIN)
        self.assertEqual((await auth.login("4567")).status, AuthStatus.AUTHENTICATED)
