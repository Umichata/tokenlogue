"""Legacy mode исправляется только в подтверждённом синтетическом профиле."""

from __future__ import annotations

import asyncio
import grp
import os
import pwd
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import storage.profile_deletion as deletion_module
from auth.pin import PinHasher
from storage.data_access import DataAccess
from storage.data_protection import DataProtection
from storage.database import AuthDatabase
from storage.secure_credentials import (
    API_KEY_STORAGE_NAME,
    REGISTRATION_ID_STORAGE_NAME,
)
from tests.test_secure_credentials import FakeSecureStorage


class LegacyProfileDeletionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "fixture-home"
        self.directory = self.home / ".local/share/io.github.umichata.tokenlogue/data"
        self.directory.mkdir(parents=True, mode=0o700)
        self.directory.parent.chmod(0o775)
        self.database = AuthDatabase(self.directory)
        self.hasher = PinHasher(iterations=100)
        self.database.save_auth_state(
            "synthetic-registration", self.hasher.create_record("0123")
        )
        self.storage = FakeSecureStorage()
        self.storage.values[REGISTRATION_ID_STORAGE_NAME] = "synthetic-registration"
        self.storage.values[API_KEY_STORAGE_NAME] = "synthetic-not-a-real-api-key"
        self.access = DataAccess()
        self.protection = DataProtection(
            self.database.path,
            self.database,
            self.storage,
            self.access,
            pin_hasher=self.hasher,
        )
        account = pwd.getpwuid(os.getuid())
        fields = list(account)
        fields[5] = str(self.home)
        self.addCleanup(patch.stopall)
        patch.object(
            deletion_module,
            "_local_profile_account",
            return_value=pwd.struct_passwd(fields),
            create=True,
        ).start()

    def diagnostic(
        self, deletion: deletion_module.ProfileDeletion
    ) -> deletion_module.DeletionDiagnostic:
        value = deletion.diagnostic
        assert value is not None
        return value

    async def check_legacy_capture(self, *, encrypted):
        if encrypted:
            stored = self.database.get_auth_state()
            assert stored is not None
            await self.protection.unlock("0123", stored)
            self.protection.lock()
        self.directory.chmod(0o775)
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        before = (
            self.database.path.read_bytes(),
            dict(self.storage.values),
            self.directory.stat().st_mode,
        )
        scope = await deletion.capture()
        self.assertTrue(scope.preparation_required)
        self.assertEqual(
            before,
            (
                self.database.path.read_bytes(),
                self.storage.values,
                self.directory.stat().st_mode,
            ),
        )
        deletion.cancel()
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)
        self.assertFalse(deletion.pending())

    async def test_schema_6_legacy_capture_offers_confirmation_without_mutation(self):
        await self.check_legacy_capture(encrypted=False)

    async def test_schema_7_legacy_capture_offers_confirmation_without_mutation(self):
        await self.check_legacy_capture(encrypted=True)

    async def encrypted(self):
        stored = self.database.get_auth_state()
        assert stored is not None
        await self.protection.unlock("0123", stored)
        self.protection.lock()
        self.storage.read_keys.clear()

    async def legacy(self):
        self.directory.chmod(0o775)
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        return deletion, await deletion.capture()

    async def complete(self, *, encrypted):
        if encrypted:
            await self.encrypted()
        backup = self.directory / "user-managed-backup.json"
        backup.write_text("preserve this export", encoding="utf-8")
        self.storage.values["other.application.alias"] = "preserve"
        owner = self.directory / ("." + self.database.path.name + ".owner.lock")
        inode = owner.stat().st_ino
        deletion, scope = await self.legacy()
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)
        await deletion.accept(scope)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.directory.parent.stat().st_mode & 0o777, 0o775)
        await deletion.finish()
        self.assertFalse(self.database.path.exists())
        self.assertFalse(deletion.pending())
        self.assertEqual(owner.stat().st_ino, inode)
        self.assertEqual(backup.read_text(encoding="utf-8"), "preserve this export")
        self.assertEqual(self.storage.values, {"other.application.alias": "preserve"})
        self.assertNotIn(deletion_module.DATA_KEY_ALIAS, self.storage.read_keys)
        self.assertNotIn(API_KEY_STORAGE_NAME, self.storage.read_keys)

    async def test_schema_6_confirmed_preparation_and_delete(self):
        await self.complete(encrypted=False)

    async def test_schema_7_confirmed_preparation_and_delete(self):
        await self.complete(encrypted=True)

    async def test_arbitrary_noncanonical_legacy_directory_is_rejected(self):
        arbitrary = self.home / "other-shared-directory"
        arbitrary.mkdir(mode=0o775)
        arbitrary.chmod(0o775)
        database = AuthDatabase(arbitrary)
        deletion = deletion_module.ProfileDeletion(database.path, self.storage)
        with self.assertRaises(deletion_module.ProfileDeletionError):
            await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_not_dedicated")
        self.assertEqual(arbitrary.stat().st_mode & 0o777, 0o775)
        self.assertEqual(self.storage.read_keys, [])

    async def test_world_writable_canonical_directory_is_rejected(self):
        self.directory.chmod(0o777)
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with self.assertRaises(deletion_module.ProfileDeletionError):
            await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_shared")
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o777)
        self.assertEqual(self.storage.read_keys, [])

    async def test_named_private_group_member_is_rejected(self):
        self.directory.chmod(0o775)
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with patch.object(
            grp, "getgrgid", return_value=SimpleNamespace(gr_mem=["other-person"])
        ):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_shared")
        self.assertEqual(self.storage.read_keys, [])

    async def test_supplementary_group_member_is_rejected(self):
        self.directory.chmod(0o775)
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        peer = next(
            user for user in pwd.getpwall() if user.pw_uid not in {0, os.getuid()}
        )
        original = os.getgrouplist

        def groups(name, gid):
            return [gid, os.getgid()] if name == peer.pw_name else original(name, gid)

        with patch.object(os, "getgrouplist", side_effect=groups):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_shared")

    async def test_foreign_live_process_supplementary_group_is_rejected(self):
        self.directory.chmod(0o775)
        fake = Path(self.temporary.name) / "424242"
        fake.mkdir()
        (fake / "status").write_text(
            f"Uid:\t2001 2001 2001 2001\nGid:\t2001 2001 2001 2001\nGroups:\t{os.getgid()}\n",
            encoding="utf-8",
        )
        original = Path.iterdir

        def processes(path):
            return iter([fake]) if path == Path("/proc") else original(path)

        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with patch.object(Path, "iterdir", autospec=True, side_effect=processes):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_shared")

    async def test_hidepid_prevents_private_group_claim(self):
        self.directory.chmod(0o775)
        original = Path.read_text

        def read(path, *args, **kwargs):
            return (
                "1 0 0:1 / /proc rw,hidepid=2 - proc proc rw,hidepid=2\n"
                if path == Path("/proc/self/mountinfo")
                else original(path, *args, **kwargs)
            )

        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with patch.object(Path, "read_text", autospec=True, side_effect=read):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_shared")

    async def test_acl_and_unknown_or_readonly_fs_refuse_before_storage_reads(self):
        self.directory.chmod(0o775)
        for helper, code in (
            ("_no_acl", "acl_unsupported"),
            ("_local_filesystem", "filesystem_unsupported"),
            ("_local_filesystem", "filesystem_readonly"),
        ):
            deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
            with patch.object(
                deletion_module,
                helper,
                side_effect=deletion_module.ProfileDeletionError(code),
            ):
                with self.assertRaises(deletion_module.ProfileDeletionError):
                    await deletion.capture()
            self.assertEqual(self.diagnostic(deletion).code, code)
            self.assertEqual(self.storage.read_keys, [])

    async def test_android_never_attempts_linux_account_preparation(self):
        self.directory.chmod(0o775)
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with (
            patch.object(
                deletion_module, "_android_application_runtime", return_value=True
            ),
            patch.object(
                deletion_module,
                "_local_profile_account",
                side_effect=AssertionError("Linux account lookup forbidden"),
            ),
        ):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "directory_not_dedicated")
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)

    async def test_cancelled_scope_cannot_prepare_directory(self):
        deletion, scope = await self.legacy()
        deletion.cancel()
        with self.assertRaises(deletion_module.ProfileDeletionError):
            await deletion.accept(scope)
        self.assertFalse(self.diagnostic(deletion).prepared)
        self.assertFalse(deletion.pending())
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)

    async def test_changed_db_before_confirmation_is_not_opened_or_prepared(self):
        deletion, scope = await self.legacy()
        replacement = self.directory / "replacement.sqlite3"
        replacement.write_bytes(self.database.path.read_bytes())
        os.replace(replacement, self.database.path)
        self.storage.read_keys.clear()
        with self.assertRaises(deletion_module.ProfileDeletionError):
            await deletion.accept(scope)
        self.assertEqual(self.storage.read_keys, [])
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)
        self.assertFalse(deletion.pending())

    async def test_fchmod_failure_keeps_original_mode_and_data(self):
        deletion, scope = await self.legacy()
        before = self.database.path.read_bytes(), dict(self.storage.values)
        with patch.object(
            os, "fchmod", side_effect=PermissionError("synthetic denied")
        ):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.accept(scope)
        self.assertEqual(self.diagnostic(deletion).stage, "prepare")
        self.assertFalse(self.diagnostic(deletion).prepared)
        self.assertFalse(deletion.pending())
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)
        self.assertEqual(before, (self.database.path.read_bytes(), self.storage.values))

    async def test_fsync_failure_after_fchmod_reports_prepared_but_not_deleted(self):
        deletion, scope = await self.legacy()
        before = self.database.path.read_bytes(), dict(self.storage.values)
        with patch.object(
            os, "fsync", side_effect=OSError("synthetic lost directory ACK")
        ):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.accept(scope)
        self.assertTrue(self.diagnostic(deletion).prepared)
        self.assertFalse(self.diagnostic(deletion).intent_pending)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual(before, (self.database.path.read_bytes(), self.storage.values))

    async def test_path_rebound_inside_fchmod_never_changes_replacement(self):
        deletion, scope = await self.legacy()
        before = self.database.path.read_bytes(), dict(self.storage.values)
        moved = self.directory.with_name("prepared-old-inode")
        original = os.fchmod

        def change(descriptor, mode):
            original(descriptor, mode)
            self.directory.rename(moved)
            self.directory.mkdir(mode=0o775)
            self.directory.chmod(0o775)
            (self.directory / "foreign-neighbor").write_text(
                "preserve", encoding="utf-8"
            )

        with patch.object(os, "fchmod", side_effect=change):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.accept(scope)
        self.assertEqual(moved.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)
        self.assertEqual(
            (self.directory / "foreign-neighbor").read_text(encoding="utf-8"),
            "preserve",
        )
        self.assertEqual(
            before,
            ((moved / self.database.path.name).read_bytes(), self.storage.values),
        )
        self.assertTrue(self.diagnostic(deletion).prepared)
        self.assertFalse(deletion.pending())

    async def test_backend_fails_after_preparation_without_starting_deletion(self):
        deletion, scope = await self.legacy()
        before = self.database.path.read_bytes(), dict(self.storage.values)
        original = self.storage.get

        async def get(key):
            if self.directory.stat().st_mode & 0o777 == 0o700:
                raise OSError("synthetic unavailable backend")
            return await original(key)

        with patch.object(self.storage, "get", side_effect=get):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.accept(scope)
        self.assertEqual(self.diagnostic(deletion).code, "backend_unavailable")
        self.assertTrue(self.diagnostic(deletion).prepared)
        self.assertFalse(self.diagnostic(deletion).intent_pending)
        self.assertEqual(before, (self.database.path.read_bytes(), self.storage.values))

    async def test_cancel_after_preparation_preserves_0700_without_intent(self):
        deletion, scope = await self.legacy()
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.storage.get

        async def get(key):
            if self.directory.stat().st_mode & 0o777 == 0o700:
                entered.set()
                await release.wait()
            return await original(key)

        with patch.object(self.storage, "get", side_effect=get):
            task = asyncio.create_task(deletion.accept(scope))
            await entered.wait()
            deletion.cancel()
            release.set()
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await task
        self.assertTrue(self.diagnostic(deletion).prepared)
        self.assertFalse(deletion.pending())
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)

    async def test_missing_owner_lock_is_not_recreated_during_confirmation(self):
        deletion, scope = await self.legacy()
        owner = self.directory / ("." + self.database.path.name + ".owner.lock")
        owner.unlink()
        with self.assertRaises(deletion_module.ProfileDeletionError):
            await deletion.accept(scope)
        self.assertFalse(owner.exists())
        self.assertFalse(deletion.pending())
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)

    async def test_post_intent_lost_alias_ack_resumes_without_repreparing(self):
        deletion, scope = await self.legacy()
        await deletion.accept(scope)
        with patch.object(
            self.storage, "remove", side_effect=OSError("synthetic lost remove ACK")
        ):
            with self.assertRaises(deletion_module.ProfileDeletionError):
                await deletion.finish()
        self.assertTrue(self.diagnostic(deletion).prepared)
        self.assertTrue(self.diagnostic(deletion).intent_pending)
        self.assertEqual(self.diagnostic(deletion).stage, "finish")
        restarted = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with patch.object(
            os, "fchmod", side_effect=AssertionError("restart cannot prepare again")
        ):
            await restarted.finish()
        self.assertFalse(restarted.pending())
        self.assertFalse(self.database.path.exists())

    async def test_invalid_schema_has_metadata_code_without_preparation(self):
        import sqlite3

        self.directory.chmod(0o775)
        with sqlite3.connect(self.database.path) as database:
            database.execute("PRAGMA user_version=99")
        deletion = deletion_module.ProfileDeletion(self.database.path, self.storage)
        with self.assertRaises(deletion_module.ProfileDeletionError):
            await deletion.capture()
        self.assertEqual(self.diagnostic(deletion).code, "metadata_invalid")
        self.assertEqual(self.diagnostic(deletion).stage, "inspect")
        self.assertFalse(self.diagnostic(deletion).prepared)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o775)
