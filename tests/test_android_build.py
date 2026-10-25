"""Offline tests for isolation, integrity, and failure reporting of the APK recipe."""

from __future__ import annotations

import importlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
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

    def test_snapshot_imports_production_initialization_without_checkout_fallback(
        self,
    ) -> None:
        """Новый модуль должен попадать в изолированную копию до git add."""
        destination = self.root / "production-snapshot"
        helper.snapshot(PROJECT, destination)
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from storage.data_protection import DataProtection
import storage.encryption_initialization as initialization
assert DataProtection.__module__ == 'storage.data_protection'
assert Path(initialization.__file__).resolve() == Path(sys.argv[1]) / 'storage/encryption_initialization.py'
"""
        result = subprocess.run(
            [sys.executable, "-I", "-c", code, str(destination / "src")],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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

    def test_crypto_dependency_versions_and_namespace_are_strict(self) -> None:
        repo = self.root / "crypto-config"
        repo.mkdir()
        current = (PROJECT / "pyproject.toml").read_text()
        for before, after in (
            ("pycryptodomex==3.23.0", "pycryptodome==3.23.0"),
            ("pycryptodomex==3.23.0", "pycryptodomex>=3.23.0"),
            ("cffi==2.0.0", "cffi==2.1.1"),
            ("pycparser==3.11", "pycparser==3.10"),
        ):
            with self.subTest(requirement=before):
                (repo / "pyproject.toml").write_text(current.replace(before, after))
                with self.assertRaisesRegex(ValueError, "pinned Android configuration"):
                    helper.check_configuration(repo, {})

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

    def test_selected_abi_reaches_runner_and_preparation_metadata(self) -> None:
        archive = self.archive()
        repo = self.root / "repo"
        for name in ("src/main.py", *helper.OWN_FILES):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("current source bytes", "utf-8")
        (repo / "pyproject.toml").write_bytes((PROJECT / "pyproject.toml").read_bytes())
        for index, (options, arch, prepare_only) in enumerate(
            (
                ([], "x86_64", False),
                (["--arch", "x86_64"], "x86_64", False),
                (["--arch", "arm64-v8a"], "arm64-v8a", False),
                (["--arch", "arm64-v8a", "--prepare-only"], "arm64-v8a", True),
            )
        ):
            with self.subTest(arch=arch, options=options):
                run = self.root / f"run-{index}"
                argv = [
                    "build_apk.py",
                    "--no-device-recovery",
                    "--run-dir",
                    str(run),
                    "--jdk-home",
                    str(self.root / "jdk"),
                    "--sdk-root",
                    str(self.root / "sdk"),
                    "--template-zip",
                    str(archive),
                    *options,
                ]
                with (
                    patch.object(sys, "argv", argv),
                    patch.object(helper, "PROJECT_ROOT", repo),
                    patch.object(helper.Path, "home", return_value=self.root),
                    patch.dict(os.environ, {"HOME": "/unchanged-home"}, clear=True),
                    patch.object(
                        helper.subprocess,
                        "check_output",
                        side_effect=[b"src/main.py\0pyproject.toml\0", "test-head\n"],
                    ),
                    patch.object(helper, "check_tools") as check_tools,
                    patch.object(helper, "run_logged", return_value=7) as runner,
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(helper.main(), 0 if prepare_only else 7)
                metadata = json.loads((run / "preparation.json").read_text())
                command = [
                    str(repo / ".venv/bin/flet"),
                    "build",
                    "apk",
                    "--arch",
                    arch,
                    "--template",
                    metadata["template"],
                    "-vv",
                ]
                self.assertEqual(metadata["arch"], arch)
                self.assertEqual(metadata["command"], command)
                self.assertEqual(
                    metadata["build"], "NOT_RUN" if prepare_only else "PENDING"
                )
                self.assertEqual(
                    (run / "source/src/main.py").read_text(), "current source bytes"
                )
                if prepare_only:
                    check_tools.assert_not_called()
                    runner.assert_not_called()
                else:
                    check_tools.assert_called_once_with(
                        repo, self.root / "jdk", self.root / "sdk"
                    )
                    runner.assert_called_once()
                    actual_command, cwd, environment, actual_run = runner.call_args.args
                    self.assertEqual(actual_command, command)
                    self.assertEqual(cwd, run / "source")
                    self.assertEqual(actual_run, run)
                    self.assertEqual(environment["HOME"], "/unchanged-home")
                    self.assertEqual(
                        environment["XDG_CONFIG_HOME"], str(run / "flutter-config")
                    )

    def test_unsupported_abi_is_rejected_before_preparation_or_flet(self) -> None:
        run = self.root / "unsupported-run"
        for arch in ("armeabi-v7a", "aarch64", "universal", "x86_64,arm64-v8a"):
            with self.subTest(arch=arch):
                argv = [
                    "build_apk.py",
                    "--no-device-recovery",
                    "--run-dir",
                    str(run),
                    "--jdk-home",
                    str(self.root / "jdk"),
                    "--sdk-root",
                    str(self.root / "sdk"),
                    "--arch",
                    arch,
                ]
                with (
                    patch.object(sys, "argv", argv),
                    patch.object(helper, "build_environment") as environment,
                    patch.object(helper, "prepare_template") as template,
                    patch.object(helper, "check_tools") as check_tools,
                    patch.object(helper, "run_logged") as runner,
                    redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as caught,
                ):
                    helper.main()
                self.assertEqual(caught.exception.code, 2)
                environment.assert_not_called()
                template.assert_not_called()
                check_tools.assert_not_called()
                runner.assert_not_called()
                self.assertFalse(run.exists())

    def test_untracked_branding_is_explicit_but_foreign_ui_is_excluded(self) -> None:
        repo = self.root / "repo"
        for name in (
            *helper.OWN_FILES,
            "src/main.py",
            "src/ui/branding.py",
            "src/ui/foreign.py",
        ):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("current allowed source", "utf-8")
        with patch.object(
            helper.subprocess, "check_output", return_value=b"src/main.py\0"
        ):
            inventory = helper.snapshot(repo, self.root / "snapshot")
        entries = {entry["path"]: entry for entry in inventory}
        self.assertIn("src/ui/branding.py", entries)
        target = self.root / "snapshot/src/ui/branding.py"
        self.assertEqual(
            target.read_bytes(), (repo / "src/ui/branding.py").read_bytes()
        )
        self.assertEqual(entries["src/ui/branding.py"]["sha256"], helper.sha256(target))
        self.assertFalse((self.root / "snapshot/src/ui/foreign.py").exists())

    def test_untracked_branding_assets_keep_binary_bytes_and_exclude_alternatives(
        self,
    ) -> None:
        repo = self.root / "repo"
        assets = (
            "src/assets/branding/tokenlogue-logo-transparent.png",
            "src/assets/branding/tokenlogue-loading.webp",
            "src/assets/branding/tokenlogue-loading-static.png",
        )
        excluded = (
            "src/assets/branding/foreign.png",
            "src/assets/branding/tokenlogue-loading.apng",
            "src/assets/branding/source/private.json",
            "docs/assets/tokenlogue-logo-transparent.png",
        )
        for name in (*helper.OWN_FILES, "src/main.py", *assets, *excluded):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\x00\xff\x89\x00" + name.encode())
            path.chmod(0o640)
        destination = self.root / "snapshot"
        with patch.object(
            helper.subprocess, "check_output", return_value=b"src/main.py\0"
        ):
            inventory = helper.snapshot(repo, destination)
        entries = {entry["path"]: entry for entry in inventory}
        for name in assets:
            with self.subTest(asset=name):
                self.assertIn(name, entries)
                copied = destination / name
                self.assertEqual(copied.read_bytes(), (repo / name).read_bytes())
                self.assertEqual(entries[name]["sha256"], helper.sha256(copied))
                self.assertEqual(entries[name]["size"], copied.stat().st_size)
                self.assertEqual(entries[name]["mode"], 0o640)
        for name in excluded:
            self.assertNotIn(name, entries)
            self.assertFalse((destination / name).exists())

    def test_explicit_build_number_reaches_flet_and_metadata(self) -> None:
        archive = self.archive()
        repo = self.root / "repo"
        for name in ("src/main.py", *helper.OWN_FILES):
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("current source", "utf-8")
        (repo / "pyproject.toml").write_bytes((PROJECT / "pyproject.toml").read_bytes())
        run = self.root / "build-number"
        argv = [
            "build_apk.py",
            "--no-device-recovery",
            "--run-dir",
            str(run),
            "--jdk-home",
            str(self.root / "jdk"),
            "--sdk-root",
            str(self.root / "sdk"),
            "--template-zip",
            str(archive),
            "--arch",
            "arm64-v8a",
            "--build-number",
            "2",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(helper, "PROJECT_ROOT", repo),
            patch.object(helper.Path, "home", return_value=self.root),
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                helper.subprocess,
                "check_output",
                side_effect=[b"src/main.py\0pyproject.toml\0", "test-head\n"],
            ),
            patch.object(helper, "check_tools"),
            patch.object(helper, "run_logged", return_value=0) as runner,
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(helper.main(), 0)
        metadata = json.loads((run / "preparation.json").read_text())
        self.assertEqual(metadata["build_number_override"], 2)
        command = metadata["command"]
        self.assertEqual(command[command.index("--build-number") + 1], "2")
        self.assertEqual(command[command.index("--arch") + 1], "arm64-v8a")
        self.assertEqual(runner.call_args.args[0], command)
        self.assertEqual(
            (repo / "pyproject.toml").read_bytes(),
            (PROJECT / "pyproject.toml").read_bytes(),
        )

    def test_main_enables_recovery_recipe_by_default(self) -> None:
        repo = self.root / "default-recovery"
        repo.mkdir()
        (repo / "pyproject.toml").write_bytes((PROJECT / "pyproject.toml").read_bytes())
        run = self.root / "default-recovery-run"
        argv = [
            "build_apk.py",
            "--run-dir",
            str(run),
            "--jdk-home",
            "jdk",
            "--sdk-root",
            "sdk",
            "--prepare-only",
        ]
        with (
            patch.object(sys, "argv", argv),
            patch.object(helper, "PROJECT_ROOT", repo),
            patch.object(helper, "check_tools"),
            patch.object(
                helper,
                "build_environment",
                return_value={
                    name: "scoped"
                    for name in (
                        "JAVA_HOME",
                        "ANDROID_HOME",
                        "ANDROID_SDK_ROOT",
                        "ANDROID_USER_HOME",
                        "XDG_CONFIG_HOME",
                        "GRADLE_USER_HOME",
                        "PATH",
                    )
                },
            ),
            patch.object(
                helper,
                "prepare_template",
                return_value=(self.root / "template", "identity"),
            ) as prepare,
            patch.object(helper, "snapshot", return_value=[]),
            patch.object(helper.subprocess, "check_output", return_value="test-head\n"),
            patch.dict(os.environ, {}, clear=True),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(helper.main(), 0)
        self.assertTrue(prepare.call_args.kwargs["with_device_recovery"])
        self.assertTrue(
            json.loads((run / "preparation.json").read_text())["device_recovery"]
        )

    def test_nonpositive_build_number_is_rejected_without_preparation(self) -> None:
        for number in ("0", "-1", "text"):
            run = self.root / ("bad-build-" + number)
            argv = [
                "build_apk.py",
                "--no-device-recovery",
                "--run-dir",
                str(run),
                "--jdk-home",
                "jdk",
                "--sdk-root",
                "sdk",
                "--build-number",
                number,
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(helper, "run_logged") as runner,
                patch.object(helper, "build_environment") as environment,
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as caught,
            ):
                helper.main()
            self.assertEqual(caught.exception.code, 2)
            environment.assert_not_called()
            runner.assert_not_called()
            self.assertFalse(run.exists())


if __name__ == "__main__":
    unittest.main()
