"""Unknown package semantics and disabled account restrictions fail closed."""

from __future__ import annotations

import ast
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import platform_security.linux_session as session  # noqa: E402


class CinnamonPackageContractTests(unittest.TestCase):
    def test_verified_function_semantics_ignore_format_but_reject_changed_predicate(
        self,
    ):
        function = ast.parse("def capable():\n    return True\n").body[0]
        digest = hashlib.sha256(
            ast.dump(function, include_attributes=False).encode()
        ).hexdigest()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "locker.py"
            path.write_text(
                'def capable():\n    """Public package documentation."""\n    return True\n'
            )
            self.assertTrue(
                session._source_methods_match(
                    path, session._source_stamp(path), (("capable", digest),)
                )
            )
            path.write_text("def capable():\n    return False\n")
            self.assertFalse(
                session._source_methods_match(
                    path, session._source_stamp(path), (("capable", digest),)
                )
            )

    def test_untrusted_installed_source_never_gets_lock_contract(self):
        with (
            patch.object(session.os, "getuid", return_value=1000),
            patch.object(session, "_root_file", return_value=False),
        ):
            self.assertFalse(session.cinnamon_lock_contract(456))


class CinnamonAccountContractTests(unittest.TestCase):
    def setUp(self):
        self.members = []
        self.command = "BOOT_IMAGE=/vmlinuz root=/dev/test ro"
        self.environment = b"HOME=/home/qa\0PRIVATE_UNRELATED_VALUE=never_logged\0"
        self.patches = [
            patch.object(session.os, "getuid", return_value=1000),
            patch.object(
                session.pwd,
                "getpwuid",
                return_value=SimpleNamespace(pw_name="qa", pw_dir="/home/qa"),
            ),
            patch.object(
                session.grp,
                "getgrnam",
                side_effect=lambda _: SimpleNamespace(gr_mem=self.members),
            ),
            patch.object(Path, "read_text", side_effect=lambda: self.command),
            patch.object(Path, "read_bytes", side_effect=lambda: self.environment),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_normal_account_is_eligible_without_any_setting_write(self):
        self.assertTrue(session._cinnamon_account_can_lock(456))

    def test_nopasswdlogin_member_is_not_eligible(self):
        self.members = ["qa"]
        self.assertFalse(session._cinnamon_account_can_lock(456))

    def test_guest_process_home_is_checked_even_if_passwd_home_is_normal(self):
        self.environment = b"HOME=/tmp/guest-qa\0"
        self.assertFalse(session._cinnamon_account_can_lock(456))

    def test_live_boot_is_not_eligible(self):
        for keyword in ("boot=casper", "boot=live"):
            self.command = keyword
            self.assertFalse(session._cinnamon_account_can_lock(456))

    def test_root_or_unknown_process_is_not_eligible(self):
        with patch.object(session.os, "getuid", return_value=0):
            self.assertFalse(session._cinnamon_account_can_lock(456))
        with patch.object(Path, "read_bytes", side_effect=PermissionError):
            self.assertFalse(session._cinnamon_account_can_lock(456))


if __name__ == "__main__":
    unittest.main()
