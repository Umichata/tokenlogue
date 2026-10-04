"""Offline tests for isolation, integrity, and failure reporting of the APK recipe."""

from __future__ import annotations

import importlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "packaging/android"))
try:
    helper = importlib.import_module("build_apk")
finally:
    sys.path.pop(0)


class AndroidBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="tokenlogue-apk-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def archive(self, *, settings: str | None = None, extra: str | None = None) -> Path:
        path = self.root / "template.zip"
        with ZipFile(path, "w") as zipped:
            zipped.writestr("build/cookiecutter.json", '{"out_dir": "flutter"}')
            zipped.writestr(
                helper.SETTINGS,
                settings
                if settings is not None
                else (
                    helper.OLD_AGP
                    + '\nid("org.jetbrains.kotlin.android") version "2.2.20"'
                ),
            )
            zipped.writestr(helper.WRAPPER, "distributionUrl=gradle-8.14-all.zip\n")
            zipped.writestr(
                helper.APP_GRADLE, 'signingConfig = signingConfigs.getByName("debug")'
            )
            wrapper = ZipInfo("build/{{cookiecutter.out_dir}}/android/gradlew")
            wrapper.external_attr = (stat.S_IFREG | 0o755) << 16
            zipped.writestr(wrapper, "#!/bin/sh\n")
            if extra:
                zipped.writestr(extra, "extra")
        self.addCleanup(patch.stopall)
        patch.object(helper, "TEMPLATE_SIZE", path.stat().st_size).start()
        patch.object(helper, "TEMPLATE_SHA256", helper.sha256(path)).start()
        return path

    def test_wrong_checksum_is_rejected_before_extraction(self) -> None:
        archive = self.archive()
        archive.write_bytes(archive.read_bytes().replace(b"flutter", b"fluttar", 1))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            helper.prepare_template(archive, self.root / "derived")
        self.assertFalse((self.root / "derived").exists())

    def test_derivation_preserves_structure_wrapper_and_modes(self) -> None:
        archive = self.archive()
        original = archive.read_bytes()
        template, identity = helper.prepare_template(archive, self.root / "derived")
        self.assertTrue((template / "cookiecutter.json").is_file())
        settings = (
            template / "{{cookiecutter.out_dir}}/android/settings.gradle.kts"
        ).read_text()
        self.assertIn(helper.NEW_AGP, settings)
        self.assertNotIn(helper.OLD_AGP, settings)
        self.assertIn('version "2.2.20"', settings)
        self.assertEqual(
            (template / "{{cookiecutter.out_dir}}/android/gradlew").stat().st_mode
            & 0o777,
            0o755,
        )
        self.assertEqual(archive.read_bytes(), original)
        self.assertIn(identity, str(template))
        with patch.object(helper, "RECIPE_VERSION", helper.RECIPE_VERSION + "-changed"):
            _, changed = helper.prepare_template(archive, self.root / "changed")
        self.assertNotEqual(identity, changed)
        second, unchanged = helper.prepare_template(archive, self.root / "repeat")
        self.assertEqual(identity, unchanged)
        self.assertEqual(
            (
                second / "{{cookiecutter.out_dir}}/android/settings.gradle.kts"
            ).read_bytes(),
            settings.encode(),
        )

    def test_duplicate_or_changed_agp_declaration_is_rejected(self) -> None:
        for settings in (
            helper.OLD_AGP + "\n" + helper.OLD_AGP,
            helper.NEW_AGP,
            helper.OLD_AGP.replace("8.11.1", "8.12.0"),
        ):
            archive = self.archive(settings=settings)
            with self.assertRaisesRegex(ValueError, "AGP declaration"):
                helper.prepare_template(archive, self.root / "derived")

    def test_path_traversal_is_rejected(self) -> None:
        for member in ("build/../outside", "/outside", "build/..\\outside"):
            archive = self.archive(extra=member)
            with self.assertRaisesRegex(ValueError, "Unsafe template"):
                helper.prepare_template(archive, self.root / "derived")
            self.assertFalse((self.root / "outside").exists())

    def test_snapshot_copies_current_bytes_but_excludes_unknown_and_secrets(
        self,
    ) -> None:
        repo = self.root / "repo"
        names = [
            "src/main.py",
            "pyproject.toml",
            "uv.lock",
            "LICENSE",
            "src/.env",
            "src/tokenlogue.sqlite3",
        ]
        for name in (
            names
            + list(helper.OWN_FILES)
            + ["src/unknown.py", ".env", "foreign/private"]
        ):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("current uncommitted bytes", "utf-8")
        (repo / helper.OWN_FILES[0]).chmod(0o755)
        destination = self.root / "snapshot"
        with patch.object(
            helper.subprocess,
            "check_output",
            return_value="\0".join(names).encode() + b"\0",
        ):
            inventory = helper.snapshot(repo, destination)
        copied = {entry["path"] for entry in inventory}
        self.assertEqual(copied, set(names[:4]) | set(helper.OWN_FILES))
        self.assertEqual(
            (destination / "src/main.py").read_text(), "current uncommitted bytes"
        )
        self.assertEqual(
            (destination / helper.OWN_FILES[0]).stat().st_mode & 0o777, 0o755
        )
        for name in (
            "src/unknown.py",
            "src/.env",
            "src/tokenlogue.sqlite3",
            ".env",
            "foreign/private",
            ".git",
            ".venv",
            "build",
        ):
            self.assertFalse((destination / name).exists())

    def test_snapshot_refuses_symlink_into_external_private_material(self) -> None:
        repo = self.root / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src/main.py").symlink_to(self.root / "private")
        with (
            patch.object(helper, "OWN_FILES", ()),
            patch.object(
                helper.subprocess, "check_output", return_value=b"src/main.py\0"
            ),
        ):
            with self.assertRaisesRegex(ValueError, "symlink"):
                helper.snapshot(repo, self.root / "snapshot")

    def test_log_preserves_both_streams_and_failure_exit_code(self) -> None:
        run = self.root / "run"
        run.mkdir()
        command = [
            sys.executable,
            "-c",
            "import os; os.write(1, b'output\\n'); os.write(2, b'error\\n'); raise SystemExit(7)",
        ]
        code = helper.run_logged(
            command, self.root, os.environ.copy(), run, mirror=False
        )
        self.assertEqual(code, 7)
        self.assertEqual((run / "build.log").read_bytes(), b"output\nerror\n")
        self.assertEqual(
            json.loads((run / "exit-code.json").read_text()), {"exit_code": 7}
        )
        self.assertEqual(
            json.loads((run / "command.json").read_text())["argv"], command
        )

    def test_production_signing_environment_is_blocked_without_exposure(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text((PROJECT / "pyproject.toml").read_text())
        for variable in (
            "FLET_ANDROID_SIGNING_KEY_STORE",
            "FLET_ANDROID_SIGNING_KEY_PASSWORD",
        ):
            with self.assertRaisesRegex(ValueError, "Production signing") as caught:
                helper.check_configuration(repo, {variable: "private-value"})
            self.assertNotIn("private-value", str(caught.exception))

    def test_environment_is_scoped_and_only_socks_all_proxy_is_removed(self) -> None:
        run = self.root / "run"
        with (
            patch.object(helper.Path, "home", return_value=self.root),
            patch.dict(
                os.environ,
                {
                    "ALL_PROXY": "socks5://private-proxy.invalid:1",
                    "all_proxy": "http://retained-proxy.invalid:2",
                    "XDG_CONFIG_HOME": "/existing-config",
                },
            ),
        ):
            environment = helper.build_environment(
                self.root / "jdk", self.root / "sdk", run
            )
            self.assertNotIn("ALL_PROXY", environment)
            self.assertEqual(environment["all_proxy"], os.environ["all_proxy"])
            self.assertEqual(
                helper.removed_socks_proxy_names(os.environ), ["ALL_PROXY"]
            )
            self.assertIn("ALL_PROXY", os.environ)
            self.assertEqual(os.environ["XDG_CONFIG_HOME"], "/existing-config")
        self.assertEqual(environment["XDG_CONFIG_HOME"], str(run / "flutter-config"))
        self.assertEqual(environment["ANDROID_USER_HOME"], str(run / "android-user"))
        self.assertIn(
            str(self.root / "flutter/3.44.8/bin"), environment["PATH"].split(os.pathsep)
        )

    def test_legacy_flutter_settings_block_unisolated_global_writes(self) -> None:
        legacy = self.root / ".flutter_settings"
        legacy.write_text("untouched legacy settings")
        with patch.object(helper.Path, "home", return_value=self.root):
            with self.assertRaisesRegex(ValueError, "Legacy Flutter settings"):
                helper.build_environment(
                    self.root / "jdk", self.root / "sdk", self.root / "run"
                )
        self.assertEqual(legacy.read_text(), "untouched legacy settings")


if __name__ == "__main__":
    unittest.main()
