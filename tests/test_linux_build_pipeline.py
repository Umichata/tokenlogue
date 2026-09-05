"""Tests for the manual Ubuntu 22.04 Linux build pipeline."""

from __future__ import annotations

import json
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPIMAGE_DIR = PROJECT_ROOT / "packaging" / "linux" / "appimage"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "build-linux.yml"
sys.path.insert(0, str(APPIMAGE_DIR))

import verify_bundle  # noqa: E402  # pyright: ignore[reportMissingImports]

EXPECTED_ACTIONS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "astral-sh/setup-uv": ("20cfd1bf945f4377ade1205e4dbc17946fc9a30d", "v10.0.1"),
    "actions/upload-artifact": (
        "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "v7.0.1",
    ),
}
REQUIRED_APT_PACKAGES = {
    "appstream",
    "binutils",
    "bubblewrap",
    "clang",
    "cmake",
    "dbus-x11",
    "desktop-file-utils",
    "gnome-keyring",
    "libgl1-mesa-dri",
    "libgtk-3-dev",
    "libsecret-1-0",
    "libsecret-1-dev",
    "libunwind-dev",
    "lld",
    "llvm",
    "ninja-build",
    "shellcheck",
    "squashfs-tools",
    "strace",
    "wmctrl",
    "xauth",
    "xvfb",
}


class LinuxBuildPipelineTests(unittest.TestCase):
    def test_pipeline_files_exist_and_scripts_are_executable(self) -> None:
        for name in (
            "build_linux_bundle.sh",
            "smoke_appimage.sh",
            "verify_bundle.py",
        ):
            path = APPIMAGE_DIR / name
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                _clean_utf8_text(path)
        for name in ("build_linux_bundle.sh", "smoke_appimage.sh"):
            self.assertTrue((APPIMAGE_DIR / name).stat().st_mode & stat.S_IXUSR)

    def test_bundle_script_uses_locked_export_reference_and_constraint(self) -> None:
        text = (APPIMAGE_DIR / "build_linux_bundle.sh").read_text(encoding="utf-8")
        for expected in (
            "set -Eeuo pipefail",
            "uv lock --check",
            "uv export",
            "--locked",
            "--no-default-groups",
            "--no-dev",
            "--no-emit-project",
            "--no-emit-local",
            "--format requirements.txt",
            "--no-hashes",
            "uv venv",
            "--no-install-project",
            'VIRTUAL_ENV="$reference_env" uv sync',
            'PIP_CONSTRAINT="$constraints"',
            "uv run --locked flet build linux -v --yes",
            "pyproject_hash_before",
            "lock_hash_before",
        ):
            self.assertIn(expected, text)
        self.assertIn('reference_env="$release_root/reference-venv"', text)
        self.assertNotRegex(text, re.compile(r"(^|\n)\s*(HOME|home)="))
        self.assertNotIn("sudo", text)

    def test_constraints_are_strict_and_exclude_development(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            constraints = Path(temp) / "constraints.txt"
            constraints.write_text(_constraints_text(), encoding="utf-8")
            pins = verify_bundle.verify_constraints(constraints)

            self.assertEqual(pins["anyio"], "4.14.2")
            self.assertEqual(pins["flet"], "0.86.5")
            self.assertNotIn("tokenlogue", pins)

            constraints.write_text(
                _constraints_text() + "ruff==0.16.5\n", encoding="utf-8"
            )
            with self.assertRaises(verify_bundle.VerificationError):
                verify_bundle.verify_constraints(constraints)

            constraints.write_text(_constraints_text() + "-e .\n", encoding="utf-8")
            with self.assertRaises(verify_bundle.VerificationError):
                verify_bundle.verify_constraints(constraints)

    def test_inventory_reads_metadata_and_writes_normalized_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            constraints = root / "constraints.txt"
            expected_raw = root / "expected.raw.json"
            bundle = root / "bundle"
            reports = root / "reports"
            constraints.write_text(_constraints_text(), encoding="utf-8")
            expected = [
                {"name": name, "version": version}
                for name, version in (
                    ("anyio", "4.14.2"),
                    ("flet", "0.86.5"),
                    ("flet-secure-storage", "0.86.5"),
                    ("httpx", "0.28.1"),
                )
            ]
            expected_raw.write_text(json.dumps(expected), encoding="utf-8")
            for item in expected:
                _write_dist_info(bundle, item["name"], item["version"])

            comparison = verify_bundle.verify_inventory(
                constraints, expected_raw, bundle, reports
            )

            self.assertTrue(comparison["ok"])
            self.assertTrue(comparison["anyio_ok"])
            self.assertEqual(comparison["constraints_missing_from_environment"], [])
            self.assertEqual(comparison["environment_missing_from_constraints"], [])
            expected_report = json.loads(
                (reports / "expected-packages.json").read_text(encoding="utf-8")
            )
            self.assertEqual(expected_report[0]["name"], "anyio")
            self.assertIn("uv.lock", expected_report[0]["source"])
            self.assertTrue((reports / "bundle-packages.json").is_file())
            self.assertTrue((reports / "package-comparison.json").is_file())

    def test_inventory_fails_for_wrong_anyio_and_unexpected_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            constraints = root / "constraints.txt"
            expected_raw = root / "expected.raw.json"
            bundle = root / "bundle"
            reports = root / "reports"
            constraints.write_text(_constraints_text(), encoding="utf-8")
            expected = [
                {"name": "anyio", "version": "4.14.2"},
                {"name": "flet", "version": "0.86.5"},
                {"name": "flet-secure-storage", "version": "0.86.5"},
                {"name": "httpx", "version": "0.28.1"},
            ]
            expected_raw.write_text(json.dumps(expected), encoding="utf-8")
            for item in expected:
                version = "4.15.0" if item["name"] == "anyio" else item["version"]
                _write_dist_info(bundle, item["name"], version)
            _write_dist_info(bundle, "flet-cli", "0.86.5")

            with self.assertRaises(verify_bundle.VerificationError):
                verify_bundle.verify_inventory(
                    constraints, expected_raw, bundle, reports
                )
            comparison = json.loads(
                (reports / "package-comparison.json").read_text(encoding="utf-8")
            )
            self.assertFalse(comparison["ok"])
            self.assertFalse(comparison["anyio_ok"])
            self.assertEqual(comparison["development_distributions"], ["flet-cli"])

    def test_abi_parsers_and_ubuntu_2204_gates(self) -> None:
        symbol_output = "\n".join(
            (
                "0 DF *UND* 0 (GLIBC_2.35) symbol_a",
                "0 DF *UND* 0 (GLIBCXX_3.4.29) symbol_b",
                "0 DF *UND* 0 (CXXABI_1.3.13) symbol_c",
                "0 DF .text 0 GLIBC_9.9 provided_not_undefined",
            )
        )
        versions = verify_bundle.parse_undefined_abi_versions(symbol_output)
        self.assertEqual(max(versions["GLIBC"]), (2, 35))
        self.assertEqual(max(versions["GLIBCXX"]), (3, 4, 29))
        self.assertEqual(max(versions["CXXABI"]), (1, 3, 13))
        self.assertEqual(
            verify_bundle.MAX_ABI_VERSIONS,
            {"GLIBC": (2, 35), "GLIBCXX": (3, 4, 29), "CXXABI": (1, 3, 13)},
        )

        needed, runpaths = verify_bundle.parse_dynamic_section(
            " 0x (NEEDED) Shared library: [libc.so.6]\n"
            " 0x (RUNPATH) Library runpath: [$ORIGIN:$ORIGIN/../lib]\n"
        )
        self.assertEqual(needed, ["libc.so.6"])
        self.assertEqual(runpaths, ["$ORIGIN", "$ORIGIN/../lib"])
        self.assertEqual(verify_bundle.ALLOWED_BUNDLE_EXTRAS, {})

    def test_workflow_has_manual_least_privilege_policy(self) -> None:
        text = _clean_utf8_text(WORKFLOW)
        self.assertRegex(text, re.compile(r"(?m)^on:\n  workflow_dispatch:\s*$"))
        for forbidden_trigger in (
            "push",
            "pull_request",
            "pull_request_target",
            "release",
            "schedule",
            "workflow_run",
        ):
            self.assertNotRegex(text, rf"(?m)^\s{{2}}{forbidden_trigger}:")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("runs-on: ubuntu-22.04", text)
        timeout = re.search(r"timeout-minutes:\s*(\d+)", text)
        assert timeout is not None
        self.assertLessEqual(int(timeout.group(1)), 60)
        self.assertIn("cancel-in-progress: true", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("secrets.", text)
        self.assertNotRegex(text, r"(?m)^\s+environment:")
        self.assertNotIn("signing", text.lower())

    def test_workflow_actions_are_full_verified_commits(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        action_lines = re.findall(
            r"uses:\s*([^@\s]+)@([0-9a-f]{40})\s+#\s+(v[^\s]+)", text
        )
        self.assertEqual(len(action_lines), len(EXPECTED_ACTIONS))
        self.assertEqual(
            {name: (commit, tag) for name, commit, tag in action_lines},
            EXPECTED_ACTIONS,
        )
        self.assertNotRegex(text, r"uses:\s*[^\n]+@(main|master|v\d+)\s*$")
        self.assertIn('version: "0.12.8"', text)
        self.assertIn("enable-cache: false", text)
        self.assertIn('github-token: ""', text)

    def test_workflow_packages_steps_and_artifact_are_scoped(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for package in REQUIRED_APT_PACKAGES:
            self.assertRegex(text, rf"(?m)^\s+{re.escape(package)}$")
        for forbidden in ("gstreamer", "mpv", "docker", "podman"):
            self.assertNotIn(forbidden, text.lower())

        step_names = re.findall(r"(?m)^\s+- name: (.+)$", text)
        required_order = (
            "Export locked production constraints",
            "Create isolated production reference environment",
            "Build Flet Linux bundle with production constraints",
            "Compare bundle package inventory",
            "Verify source bundle ABI",
            "Fetch and verify pinned AppImage tools",
            "Build first diagnostic AppImage",
            "Rebuild AppImage and verify reproducibility",
            "Extract diagnostic AppImage",
            "Validate packaged metadata paths and ABI",
            "Run isolated headless AppImage smoke test",
            "Create artifact checksums",
            "Upload diagnostic AppImage and reports",
        )
        indices = [step_names.index(name) for name in required_order]
        self.assertEqual(indices, sorted(indices))

        upload = text[text.index("- name: Upload diagnostic AppImage and reports") :]
        for required in (
            "Tokenlogue-0.1.0-x86_64.AppImage",
            "SHA256SUMS",
            "production-constraints.txt",
            "build/linux-release/reports/",
            "retention-days: 14",
        ):
            self.assertIn(required, upload)
        self.assertNotIn("Tokenlogue.AppDir", upload)
        self.assertNotRegex(upload, r"(?m)^\s+build/linux/$")
        self.assertNotIn("build/appimage/tools/", upload)

    def test_smoke_script_is_headless_isolated_and_does_not_reassign_home(self) -> None:
        text = (APPIMAGE_DIR / "smoke_appimage.sh").read_text(encoding="utf-8")
        for expected in (
            "Xvfb",
            "--appimage-extract-and-run",
            "--unshare-net",
            "dbus-run-session",
            "gnome-keyring-daemon",
            "LIBGL_ALWAYS_SOFTWARE",
            "wmctrl",
            "20s",
            "AF_INET",
            "no fallback is allowed",
            "ulimit -c 0",
        ):
            self.assertIn(expected, text)
        self.assertNotRegex(
            text,
            re.compile(r"(^|\n)\s*(export\s+)?(HOME|home)=", re.MULTILINE),
        )
        self.assertIn('--bind "$smoke_root/home" "$HOME"', text)

    def test_gitignore_and_documentation_cover_only_generated_pipeline_files(
        self,
    ) -> None:
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for name in (
            "build_linux_bundle.sh",
            "smoke_appimage.sh",
            "verify_bundle.py",
        ):
            self.assertIn(f"!packaging/linux/appimage/{name}", ignore)
        self.assertNotIn("!packaging/linux/appimage/**", ignore)

        root_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        packaging_readme = (APPIMAGE_DIR / "README.md").read_text(encoding="utf-8")
        documentation = " ".join((root_readme + packaging_readme).split())
        for phrase in (
            "Ubuntu 22.04",
            "GLIBC_2.35",
            "uv.lock",
            "manual-only",
            "has not yet been run",
        ):
            self.assertIn(phrase, documentation)


def _constraints_text() -> str:
    return """\
anyio==4.14.2
flet==0.86.5
flet-secure-storage==0.86.5
httpx==0.28.1
"""


def _write_dist_info(bundle: Path, name: str, version: str) -> None:
    dist_info = bundle / "site-packages" / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n",
        encoding="utf-8",
    )


def _clean_utf8_text(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("utf-8")
    if not text.endswith("\n"):
        raise AssertionError(f"Missing final newline: {path}")
    if any(line != line.rstrip(" \t") for line in text.splitlines()):
        raise AssertionError(f"Trailing whitespace: {path}")
    return text


if __name__ == "__main__":
    unittest.main()
