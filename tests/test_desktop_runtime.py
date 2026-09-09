"""Regression checks for mixing bundled GTK with newer desktop modules."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "packaging/linux/appimage"
sys.path.insert(0, str(SCRIPTS))

import desktop_runtime as desktop  # noqa: E402 # pyright: ignore[reportMissingImports]


class DesktopRuntimeTests(unittest.TestCase):
    def test_policy_catches_nested_files_and_broken_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / "usr/lib/tokenlogue/lib"
            nested.mkdir(parents=True)
            (nested / "libgio-2.0.so.0").write_bytes(b"fixture")
            (nested / "libgtk-3.so.0").symlink_to("absent-library")
            (nested / "libflutter_linux_gtk.so").write_bytes(b"preserved")
            self.assertEqual(
                desktop.bundled_desktop_libraries(root),
                [
                    "usr/lib/tokenlogue/lib/libgio-2.0.so.0",
                    "usr/lib/tokenlogue/lib/libgtk-3.so.0",
                ],
            )

    def test_deployment_exclusions_use_the_shared_policy(self) -> None:
        text = (SCRIPTS / "build_appimage.sh").read_text()
        block = re.search(
            r"(?ms)^linuxdeploy_args=\(.*?^done <<< \"\$desktop_exclusions\"", text
        )
        assert block is not None
        result = subprocess.run(
            [
                "bash",
                "-eu",
                "-c",
                "python_bin=$1; script_dir=$2; appdir=/fixture\n"
                + block.group()
                + '\nprintf "%s\\n" "${linuxdeploy_args[@]}"',
                "fixture",
                sys.executable,
                str(SCRIPTS),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        args = result.stdout.splitlines()
        for pattern in desktop.HOST_DESKTOP_PATTERNS:
            self.assertIn("--exclude-library=" + pattern, args)
        self.assertIn("--exclude-library=libflutter_linux_gtk.so", args)
        self.assertIn("--exclude-library=libpython3.12.so.1.0", args)

    def _probe(self, *, missing: str = "", failure: str = "", private: bool = False):
        modules = {
            "gio": [Path("/usr/lib/gio/modules/libgvfsdbus.so")],
            "ibus": [Path("/usr/lib/gtk-3.0/3.0.0/immodules/im-ibus.so")],
            "xapp": [],
        }
        if missing:
            modules[missing] = []

        def load(name, **kwargs):
            self.assertEqual(kwargs["mode"], os.RTLD_NOW | os.RTLD_GLOBAL)
            if failure and name.endswith(failure):
                raise OSError("undefined symbol: g_task_set_static_name")
            return object()

        mapped = (
            Path("/fixture/usr/lib/libgio-2.0.so.0")
            if private
            else Path("/usr/lib/libgio-2.0.so.0")
        )
        with (
            patch.object(desktop, "discover_modules", return_value=modules),
            patch.object(desktop.ctypes, "CDLL", side_effect=load),
            patch.object(desktop, "loaded_desktop_libraries", return_value=[mapped]),
        ):
            return desktop.probe_modules(Path("/fixture"))

    def test_required_modules_resolve_with_eager_symbol_binding(self) -> None:
        report = self._probe()
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(len(report["modules"]), 4)

    def test_missing_gvfs_or_ibus_never_passes(self) -> None:
        for group in ("gio", "ibus"):
            with self.subTest(group=group):
                self.assertEqual(self._probe(missing=group)["result"], "FAIL")

    def test_symbol_error_and_private_runtime_never_pass(self) -> None:
        for target in ("libgvfsdbus.so", "im-ibus.so"):
            with self.subTest(target=target):
                report = self._probe(failure=target)
                self.assertEqual(report["result"], "FAIL")
                self.assertIn("g_task_set_static_name", json.dumps(report))
        self.assertEqual(self._probe(private=True)["result"], "FAIL")

    def test_subprocess_uses_apprun_paths_without_disabling_desktop_features(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="desktop probe ") as temp:
            root = Path(temp)
            env = {
                "GTK_IM_MODULE": "ibus",
                "GIO_USE_VFS": "gvfs",
                "LD_LIBRARY_PATH": "/old",
            }
            with (
                patch.dict(os.environ, env),
                patch.object(
                    desktop.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        [], 0, '{"result":"PASS"}', ""
                    ),
                ) as run,
            ):
                self.assertEqual(desktop.run_probe(root, root / "report.json"), 0)
            actual = run.call_args.kwargs["env"]
            self.assertEqual(
                actual["LD_LIBRARY_PATH"],
                f"{root}/usr/lib:{root}/usr/lib/tokenlogue/lib",
            )
            self.assertEqual(actual["GTK_IM_MODULE"], "ibus")
            self.assertEqual(actual["GIO_USE_VFS"], "gvfs")
            self.assertEqual(run.call_args.args[0][-1], str(root))

    def test_child_failure_timeout_and_invalid_output_leave_failure_report(
        self,
    ) -> None:
        for outcome in (
            subprocess.CompletedProcess([], 1, "", "loader error"),
            subprocess.CompletedProcess([], 0, "invalid JSON", ""),
            subprocess.CompletedProcess([], 0, "null", ""),
            subprocess.CompletedProcess([], 0, "{}", ""),
            subprocess.TimeoutExpired("fixture", 20),
        ):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                with patch.object(desktop.subprocess, "run") as run:
                    if isinstance(outcome, Exception):
                        run.side_effect = outcome
                    else:
                        run.return_value = outcome
                    self.assertEqual(desktop.run_probe(root, root / "report.json"), 1)
                self.assertEqual(
                    json.loads((root / "report.json").read_text())["result"], "FAIL"
                )


if __name__ == "__main__":
    unittest.main()
