"""Tests for the manual Ubuntu 22.04 Linux build pipeline."""

from __future__ import annotations

import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

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
            "xwininfo -root -tree",
            "xprop -id",
            "LC_ALL=C",
            "Map State: IsViewable",
            "20s",
            "AF_INET",
            "no fallback is allowed",
            "ulimit -c 0",
        ):
            self.assertIn(expected, text)
        self.assertNotIn("wmctrl", text)
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
            "requires a new build and matrix run",
        ):
            self.assertIn(phrase, documentation)


class PackagedMetadataValidationTests(unittest.TestCase):
    DESKTOP_PATH = "usr/share/applications/io.github.umichata.tokenlogue.desktop"

    def test_workflow_validates_only_appdir_and_extracted_desktop_files(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        targets = re.findall(
            r"desktop-file-validate\s+([^\n]+)", workflow.replace("\\\n", "")
        )
        self.assertEqual(
            [target.strip() for target in targets],
            [f'"$appdir/{self.DESKTOP_PATH}"', f'"$extracted/{self.DESKTOP_PATH}"'],
        )
        block = self._metadata_block()
        self.assertIn("set -Eeuo pipefail", block)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("|| true", block)
        self.assertIn(
            "extract_root=$PWD/build/linux-release/extracted-appimage", workflow
        )
        self.assertIn(
            "extracted=$PWD/build/linux-release/extracted-appimage/squashfs-root", block
        )

    def test_both_existing_desktops_are_validated_and_results_are_reported(
        self,
    ) -> None:
        status, calls, report, targets = self._run_metadata_fixture()
        self.assertEqual(status, 0)
        self.assertEqual(calls[:2], [f"desktop:{target}" for target in targets])
        self.assertEqual(calls[2:], ["appstream"] * 3)
        self.assertIn("Validating AppDir desktop entry", report)
        self.assertIn("Validating extracted AppImage desktop entry", report)
        self.assertEqual(report.count("fixture validator success"), 2)

    def test_missing_packaged_desktop_fails_even_if_validator_would_accept_it(
        self,
    ) -> None:
        for missing in (0, 1):
            with self.subTest(missing=missing):
                status, calls, report, targets = self._run_metadata_fixture(
                    missing=missing
                )
                self.assertNotEqual(status, 0)
                self.assertNotIn(f"desktop:{targets[missing]}", calls)
                self.assertEqual(
                    calls, [f"desktop:{target}" for target in targets[:missing]]
                )
                self.assertIn("Validating", report)

    def test_validator_failure_for_either_desktop_stops_metadata_validation(
        self,
    ) -> None:
        for rejected in (0, 1):
            with self.subTest(rejected=rejected):
                status, calls, report, targets = self._run_metadata_fixture(
                    rejected=rejected
                )
                self.assertEqual(status, 23)
                self.assertEqual(
                    calls, [f"desktop:{target}" for target in targets[: rejected + 1]]
                )
                self.assertIn("fixture validator rejection", report)
                self.assertNotIn("appstream", calls)

    def _metadata_block(self) -> str:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split(
            "      - name: Validate packaged metadata paths and ABI\n", 1
        )[1].split("\n      - name:", 1)[0]
        commands = textwrap.dedent(step.split("        run: |\n", 1)[1])
        # Exercise only metadata validation, never a build or workflow run.
        block, separator, _ = commands.partition("UV_MANAGED_PYTHON=")
        self.assertTrue(separator)
        self.assertIn("desktop-appstream-validation.txt 2>&1", block)
        return block

    def _run_metadata_fixture(
        self,
        *,
        missing: int | None = None,
        rejected: int | None = None,
    ) -> tuple[int, list[str], str, list[str]]:
        with tempfile.TemporaryDirectory(
            prefix="tokenlogue metadata validation "
        ) as temp:
            root = Path(temp)
            targets = [
                root / "build/appimage/Tokenlogue.AppDir" / self.DESKTOP_PATH,
                root
                / "build/linux-release/extracted-appimage/squashfs-root"
                / self.DESKTOP_PATH,
            ]
            for index, target in enumerate(targets):
                if index != missing:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(
                        "[Desktop Entry]\nType=Application\nName=Tokenlogue\n"
                        "Exec=tokenlogue\nIcon=tokenlogue\n",
                        encoding="utf-8",
                    )
            report = (
                root / "build/linux-release/reports/desktop-appstream-validation.txt"
            )
            report.parent.mkdir(parents=True)
            call_log = root / "calls.txt"
            # Deterministic validators let the tests prove fail-fast behavior
            # without depending on system package versions or using real artifacts.
            stubs = textwrap.dedent("""\
                calls_file=$1
                rejected_file=$2
                desktop-file-validate() {
                    printf 'desktop:%s\\n' "$1" >> "$calls_file"
                    if [[ "$1" == "$rejected_file" ]]; then
                        printf 'fixture validator rejection\\n' >&2
                        return 23
                    fi
                    printf 'fixture validator success\\n'
                }
                appstreamcli() {
                    printf 'appstream\\n' >> "$calls_file"
                }
            """)
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    stubs + self._metadata_block(),
                    "metadata-fixture",
                    str(call_log),
                    str(targets[rejected]) if rejected is not None else "",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = (
                call_log.read_text(encoding="utf-8").splitlines()
                if call_log.exists()
                else []
            )
            return (
                result.returncode,
                calls,
                report.read_text(encoding="utf-8"),
                [str(target) for target in targets],
            )


class SmokeAppImageBehaviorTests(unittest.TestCase):
    REPORT_NAMES = {
        "smoke-application.stderr.txt",
        "smoke-sandbox.stderr.txt",
        "smoke-xvfb.stderr.txt",
        "smoke-window-search.txt",
        "smoke-window-properties.txt",
        "smoke-window-state.txt",
        "smoke-test-summary.txt",
    }

    def test_viewable_window_is_found_without_ewmh_client_list(self) -> None:
        status, summary, reports, calls = self._run_fixture()
        self.assertEqual(status, 0)
        self.assertEqual(summary["result"], "PASS")
        self.assertEqual(summary["exit_code"], "124")
        self.assertEqual(summary["window_id"], "0xabc")
        self.assertEqual(summary["window_map_state"], "IsViewable")
        self.assertIn(
            'WM_CLASS(STRING) = "tokenlogue", "Tokenlogue"',
            reports["smoke-window-properties.txt"],
        )
        self.assertIn("Map State: IsViewable", reports["smoke-window-state.txt"])
        probes = [call for call in calls if call["tool"] in ("xprop", "xwininfo")]
        self.assertTrue(probes)
        for call in probes:
            self.assertEqual(call["display"], ":97")
            self.assertEqual(call["locale"], "C")
            arguments = call["args"]
            assert isinstance(arguments, list)
            self.assertNotIn("_NET_CLIENT_LIST", arguments)
        self.assertIn("xwininfo -root -tree exit=0", reports["smoke-window-search.txt"])

    def test_legacy_wm_name_is_accepted_when_net_wm_name_is_absent(self) -> None:
        status, summary, _, _ = self._run_fixture(window={"net_name": False})
        self.assertEqual(status, 0)
        self.assertEqual(summary["window_check"], "PASS")

    def test_foreign_or_hidden_window_is_rejected(self) -> None:
        for window in (
            {"instance": "other"},
            {"class_name": "tokenlogue"},
            {"title": "Tokenlogue extra"},
            {"title": "Other", "legacy_title": "Tokenlogue"},
            {"map_state": "IsUnMapped"},
            {"map_state": "IsUnviewable"},
        ):
            with self.subTest(window=window):
                status, summary, reports, _ = self._run_fixture(window=window)
                self.assertNotEqual(status, 0)
                self.assertEqual(summary["result"], "FAIL")
                self.assertEqual(summary["window_id"], "NOT_FOUND")
                self.assertIn("window was not observed", summary["reason"])
                self.assertIn("Candidate 0xabc", reports["smoke-window-search.txt"])

    def test_absent_window_keeps_reports_and_failure_status(self) -> None:
        status, summary, reports, _ = self._run_fixture(no_window=True)
        self.assertNotEqual(status, 0)
        self.assertEqual(summary["result"], "FAIL")
        self.assertEqual(summary["window_check"], "NOT_FOUND")
        self.assertEqual(summary["af_inet_socket_calls"], "0")
        self.assertEqual(summary["owned_process_cleanup"], "PASS")
        self.assertIn(
            "fixture application stderr", reports["smoke-application.stderr.txt"]
        )
        self.assertIn("fixture sandbox stderr", reports["smoke-sandbox.stderr.txt"])
        self.assertIn("fixture Xvfb stderr", reports["smoke-xvfb.stderr.txt"])
        self.assertIn("Root window", reports["smoke-window-search.txt"])

    def test_xvfb_startup_failure_saves_available_logs_and_cleans(self) -> None:
        status, summary, reports, _ = self._run_fixture(xvfb_failure=True)
        self.assertNotEqual(status, 0)
        self.assertEqual(summary["result"], "FAIL")
        self.assertIn("Xvfb exited before initialization", summary["reason"])
        for key in (
            "exit_code",
            "window_check",
            "af_inet_socket_calls",
            "fatal_diagnostics",
        ):
            self.assertEqual(summary[key], "NOT_RUN")
        self.assertEqual(summary["owned_process_cleanup"], "PASS")
        self.assertIn("fixture Xvfb stderr", reports["smoke-xvfb.stderr.txt"])
        self.assertIn("NOT_CAPTURED", reports["smoke-application.stderr.txt"])

    def test_namespace_failure_is_reported_before_launch(self) -> None:
        status, summary, reports, calls = self._run_fixture(namespace_failure=True)
        self.assertNotEqual(status, 0)
        self.assertIn("namespace is unavailable", summary["reason"])
        self.assertEqual(summary["network_namespace"], "NOT_RUN")
        self.assertEqual(summary["remaining_processes"], "NOT_RUN")
        self.assertIn("fixture namespace denied", reports["smoke-sandbox.stderr.txt"])
        self.assertFalse(any(call["tool"] == "Xvfb" for call in calls))

    def test_launcher_failure_does_not_invent_missing_measurements(self) -> None:
        status, summary, reports, _ = self._run_fixture(launch_failure=True)
        self.assertNotEqual(status, 0)
        self.assertEqual(summary["exit_code"], "72")
        self.assertEqual(summary["af_inet_socket_calls"], "UNAVAILABLE")
        self.assertEqual(summary["fatal_diagnostics"], "UNAVAILABLE")
        self.assertIn("application exited before timeout: 72", summary["reason"])
        self.assertIn("fixture launch failure", reports["smoke-sandbox.stderr.txt"])

    def test_report_copy_failure_cannot_prevent_cleanup_or_mask_failure(self) -> None:
        for no_window in (False, True):
            with self.subTest(no_window=no_window):
                status, summary, _, _ = self._run_fixture(
                    report_copy_failure=True, no_window=no_window
                )
                self.assertNotEqual(status, 0)
                self.assertEqual(summary["result"], "FAIL")
                self.assertEqual(summary["report_logs"], "FAIL")
                self.assertEqual(summary["owned_process_cleanup"], "PASS")
                if no_window:
                    self.assertIn("window was not observed", summary["reason"])

    def test_network_crash_and_leftover_process_gates_still_fail(self) -> None:
        for scenario, reason in (
            ({"network_activity": True}, "AF_INET or AF_INET6"),
            ({"crash": True}, "fatal runtime diagnostics"),
            ({"leftover_process": True}, "processes remain"),
            ({"missing_trace": True}, "network trace is unavailable"),
        ):
            with self.subTest(scenario=scenario):
                status, summary, _, _ = self._run_fixture(**scenario)
                self.assertNotEqual(status, 0)
                self.assertEqual(summary["result"], "FAIL")
                self.assertIn(reason, summary["reason"])

    def _run_fixture(
        self, **scenario: object
    ) -> tuple[int, dict[str, str], dict[str, str], list[dict[str, object]]]:
        with tempfile.TemporaryDirectory(prefix="tokenlogue smoke behavior ") as temp:
            root = Path(temp)
            fake_bin = root / "bin"
            scratch = root / "scratch"
            reports_dir = root / "reports"
            fake_bin.mkdir()
            scratch.mkdir()
            appimage = root / "fixture.AppImage"
            appimage.write_text("never executed\n", encoding="utf-8")
            appimage.chmod(0o755)
            fake = fake_bin / "fake_tool.py"
            fake.write_text(
                "#!" + sys.executable + "\n" + SMOKE_FAKE_TOOL, encoding="utf-8"
            )
            fake.chmod(0o755)
            for name in (
                "git",
                "bwrap",
                "dbus-run-session",
                "gdbus",
                "gnome-keyring-daemon",
                "pgrep",
                "strace",
                "timeout",
                "xwininfo",
                "xprop",
                "Xvfb",
                "sleep",
                "cp",
            ):
                (fake_bin / name).symlink_to(fake.name)
            environment = os.environ.copy()
            for name in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                environment.pop(name, None)
            environment.update(
                {
                    "PATH": str(fake_bin) + os.pathsep + "/usr/bin:/bin",
                    "TMPDIR": str(scratch),
                    "SMOKE_FIXTURE_ROOT": str(root),
                    "SMOKE_FIXTURE_SCENARIO": json.dumps(scenario),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            alive = []
            try:
                result = subprocess.run(
                    [
                        "bash",
                        str(APPIMAGE_DIR / "smoke_appimage.sh"),
                        str(appimage),
                        str(reports_dir),
                    ],
                    env=environment,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
            finally:
                pid_file = root / "xvfb.pid"
                if pid_file.exists():
                    pid = int(pid_file.read_text(encoding="utf-8"))
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        pass
                    else:
                        alive.append(pid)
                        os.kill(pid, signal.SIGKILL)
            self.assertEqual(alive, [], "smoke test leaked its fake Xvfb process")
            self.assertEqual(list(scratch.iterdir()), [], result.stderr)
            reports = {
                path.name: path.read_text(encoding="utf-8")
                for path in reports_dir.iterdir()
            }
            if scenario.get("report_copy_failure"):
                self.assertTrue(set(reports).issubset(self.REPORT_NAMES))
            else:
                self.assertEqual(set(reports), self.REPORT_NAMES)
            summary = dict(
                line.split("=", 1)
                for line in reports["smoke-test-summary.txt"].splitlines()
            )
            self.assertEqual(int(summary["script_exit_code"]), result.returncode)
            calls = [
                json.loads(line)
                for line in (root / "tools.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            return result.returncode, summary, reports, calls


# Executables below exist only in a test's temporary PATH. They simulate X11
# and sandbox lifecycles without starting an application, server or network.
SMOKE_FAKE_TOOL = r"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(os.environ["SMOKE_FIXTURE_ROOT"])
scenario = json.loads(os.environ["SMOKE_FIXTURE_SCENARIO"])
tool = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "tools.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"tool": tool, "args": args,
                            "display": os.environ.get("DISPLAY"),
                            "locale": os.environ.get("LC_ALL")}) + "\n")

if tool == "git":
    print(args[args.index("-C") + 1])
elif tool == "Xvfb":
    (root / "xvfb.pid").write_text(str(os.getpid()), encoding="utf-8")
    print("fixture Xvfb stderr", file=sys.stderr, flush=True)
    if scenario.get("xvfb_failure"):
        sys.exit(17)
    def stopped(*_):
        sys.exit(0)
    signal.signal(signal.SIGTERM, stopped)
    os.write(3, b"97\n")
    while True:
        signal.pause()
elif tool == "timeout":
    if args[0] == "2s":
        os.execvp(args[1], args[1:])
    assert "20s" in args
    command = args[args.index("20s") + 1:]
    status = subprocess.run(command, check=False).returncode
    if status:
        sys.exit(status)
    time.sleep(0.3)
    sys.exit(124)
elif tool == "bwrap":
    if "/usr/bin/true" in args:
        if scenario.get("namespace_failure"):
            print("fixture namespace denied", file=sys.stderr)
            sys.exit(1)
    else:
        if scenario.get("launch_failure"):
            print("fixture launch failure", file=sys.stderr)
            sys.exit(72)
        scratch = Path(args[args.index("--bind") + 1])
        logs = scratch / "logs"
        (logs / "isolation-ready").write_text("ready\n", encoding="utf-8")
        (root / "launched").touch()
        (logs / "application.stderr").write_text(
            "Traceback: fixture crash\n" if scenario.get("crash") else "fixture application stderr\n",
            encoding="utf-8",
        )
        if not scenario.get("missing_trace"):
            trace = "socket(AF_INET6, SOCK_STREAM, 0) = 1\n" if scenario.get("network_activity") else "socket(AF_UNIX, SOCK_STREAM, 0) = 1\n"
            (logs / "trace.42").write_text(trace, encoding="utf-8")
        (scratch / "storage" / "private.sqlite3").write_bytes(b"fixture private data")
        (scratch / "home" / "private-keyring").write_bytes(b"fixture private data")
        print("fixture sandbox stderr", file=sys.stderr)
elif tool == "xwininfo":
    window = scenario.get("window", {})
    if "-root" in args:
        print("Root window id: 0x001 (has no name)")
        if (root / "launched").exists() and not scenario.get("no_window"):
            print('     0xabc "Tokenlogue": ("tokenlogue" "Tokenlogue")  1280x720+0+0')
    else:
        print("  Map State: " + window.get("map_state", "IsViewable"))
elif tool == "xprop":
    assert "_NET_CLIENT_LIST" not in args
    window = scenario.get("window", {})
    print('WM_CLASS(STRING) = "{}", "{}"'.format(window.get("instance", "tokenlogue"), window.get("class_name", "Tokenlogue")))
    if window.get("net_name", True):
        print('_NET_WM_NAME(UTF8_STRING) = "{}"'.format(window.get("title", "Tokenlogue")))
    print('WM_NAME(STRING) = "{}"'.format(window.get("legacy_title", window.get("title", "Tokenlogue"))))
elif tool == "pgrep":
    sys.exit(0 if scenario.get("leftover_process") else 1)
elif tool == "sleep":
    time.sleep(0.002)
elif tool == "cp":
    if scenario.get("report_copy_failure") and Path(args[-1]).name.startswith("smoke-"):
        print("fixture report copy failure", file=sys.stderr)
        sys.exit(91)
    os.execv("/bin/cp", ["cp", *args])
else:
    raise AssertionError("unexpected tool execution: " + tool)
"""


class OptionalJniAbiTests(unittest.TestCase):
    JDK_RUNPATH = "/usr/lib/jvm/temurin-11-jdk-amd64/lib/server"
    JNI_PATH = "lib/libdartjni.so"
    SAFE_SYMBOLS = (
        "0 DF *UND* 0 (GLIBC_2.34) symbol_a\n"
        "0 DF *UND* 0 (GLIBCXX_3.4.29) symbol_b\n"
        "0 DF *UND* 0 (CXXABI_1.3) symbol_c\n"
    )

    def test_exact_source_jni_runpath_passes_and_preserves_all_reports(self) -> None:
        reports = self._verify_fixture(
            "bundle",
            self.JNI_PATH,
            runpath=self.JDK_RUNPATH,
            needed=("libjvm.so",),
            ldd_output=f"libjvm.so => {self.JDK_RUNPATH}/libjvm.so (0x01)\n",
        )
        self.assertIn("bundle:lib/libdartjni.so", reports["elf-abi.txt"])
        self.assertIn("GLIBC_2.34,GLIBCXX_3.4.29,CXXABI_1.3", reports["elf-abi.txt"])
        self.assertIn(self.JDK_RUNPATH, reports["rpaths.txt"])
        self.assertIn("removed from AppImage staging", reports["rpaths.txt"])
        self.assertIn("libjvm.so =>", reports["ldd.txt"])

    def test_source_jni_allowance_does_not_apply_to_other_elf_paths(self) -> None:
        for relative in (
            "lib/libdart_bridge.so",
            "lib/other/libdartjni.so",
            "libdartjni.so",
            "lib/libdartjni.so.extra",
        ):
            with self.subTest(relative=relative):
                self._verify_fixture(
                    "bundle",
                    relative,
                    runpath=self.JDK_RUNPATH,
                    expected_errors=("has absolute RUNPATH",),
                )

    def test_source_jni_allowance_does_not_allow_other_absolute_runpaths(self) -> None:
        for runpath in ("/opt/jdk-21/lib/server", f"{self.JDK_RUNPATH}:/opt/extra"):
            with self.subTest(runpath=runpath):
                self._verify_fixture(
                    "bundle",
                    self.JNI_PATH,
                    runpath=runpath,
                    expected_errors=("has absolute RUNPATH",),
                )

    def test_source_jni_still_enforces_abi_limits(self) -> None:
        for requirement in ("GLIBC_2.36", "GLIBCXX_3.4.30", "CXXABI_1.3.14"):
            with self.subTest(requirement=requirement):
                self._verify_fixture(
                    "bundle",
                    self.JNI_PATH,
                    runpath=self.JDK_RUNPATH,
                    symbols=f"0 DF *UND* 0 ({requirement}) symbol\n",
                    expected_errors=(f"requires {requirement}",),
                )

    def test_source_jni_still_enforces_ldd_checks(self) -> None:
        for output, returncode, message in (
            ("libjvm.so => not found\n", 0, "has unresolved libraries: libjvm.so"),
            ("loader failed\n", 1, "ldd failed"),
        ):
            with self.subTest(message=message):
                self._verify_fixture(
                    "bundle",
                    self.JNI_PATH,
                    runpath=self.JDK_RUNPATH,
                    needed=("libjvm.so",),
                    ldd_output=output,
                    ldd_returncode=returncode,
                    expected_errors=(message,),
                )

    def test_packaged_jni_is_rejected_at_source_and_staged_relative_paths(self) -> None:
        for label in ("appdir", "appimage"):
            for relative in (self.JNI_PATH, f"usr/lib/tokenlogue/{self.JNI_PATH}"):
                with self.subTest(label=label, relative=relative):
                    self._verify_fixture(
                        label,
                        relative,
                        runpath=self.JDK_RUNPATH,
                        expected_errors=(
                            "has absolute RUNPATH",
                            "is a forbidden Java library",
                        ),
                    )

    def test_packaged_java_libraries_are_rejected_without_jdk_runpath(self) -> None:
        for label in ("appdir", "appimage"):
            for name in ("libdartjni.so", "libjvm.so"):
                with self.subTest(label=label, name=name):
                    self._verify_fixture(
                        label,
                        "usr/lib/tokenlogue/lib/libdart_bridge.so",
                        extra_files={f"usr/lib/{name}": b"not even an ELF"},
                        expected_errors=(
                            f"usr/lib/{name} is a forbidden Java library",
                        ),
                    )

    def test_packaged_java_dependencies_are_rejected_even_if_library_is_absent(
        self,
    ) -> None:
        for label in ("appdir", "appimage"):
            for dependency in ("libdartjni.so", "libjvm.so", "$ORIGIN/libjvm.so"):
                with self.subTest(label=label, dependency=dependency):
                    self._verify_fixture(
                        label,
                        "usr/lib/tokenlogue/lib/libdart_bridge.so",
                        needed=(dependency,),
                        expected_errors=("retains Java dependency",),
                    )

    def test_packaged_jdk_jre_paths_are_rejected_in_file_contents(self) -> None:
        for label in ("appdir", "appimage"):
            for runtime_path in (
                self.JDK_RUNPATH,
                "/opt/java/openjdk/lib/server",
                "/opt/jdk-21/lib/server",
                "/usr/java/jre1.8.0/lib/amd64/server",
            ):
                with self.subTest(label=label, runtime_path=runtime_path):
                    self._verify_fixture(
                        label,
                        "usr/lib/tokenlogue/lib/libdart_bridge.so",
                        extra_files={"runtime-path.txt": runtime_path.encode()},
                        expected_errors=("runtime-path.txt contains JDK/JRE path",),
                    )

    def test_packaged_java_symlinks_are_rejected_without_following_them(self) -> None:
        for label in ("appdir", "appimage"):
            for name, target, message in (
                ("lib/libdartjni.so", "missing", "is a forbidden Java library"),
                ("lib/libjvm.so", "missing", "is a forbidden Java library"),
                ("lib/alias.so", "libjvm.so", "links to a Java runtime"),
                (
                    "lib/alias.so",
                    f"{self.JDK_RUNPATH}/libjvm.so",
                    "links to a Java runtime",
                ),
            ):
                with self.subTest(label=label, name=name, target=target):
                    self._verify_fixture(
                        label,
                        "usr/lib/tokenlogue/lib/libdart_bridge.so",
                        symlink=(name, target),
                        expected_errors=(message,),
                    )

    def test_packaged_transitive_java_resolution_is_rejected(self) -> None:
        for label in ("appdir", "appimage"):
            with self.subTest(label=label):
                self._verify_fixture(
                    label,
                    "usr/lib/tokenlogue/lib/libdart_bridge.so",
                    ldd_output=f"libjvm.so => {self.JDK_RUNPATH}/libjvm.so (0x01)\n",
                    expected_errors=(
                        "ldd resolves to JDK/JRE path",
                        "ldd retains Java dependency",
                    ),
                )

    def test_flet_plugin_runpath_allowance_stays_source_only(self) -> None:
        for name in (
            "libflutter_secure_storage_linux_plugin.so",
            "libpasteboard_plugin.so",
            "libscreen_retriever_linux_plugin.so",
            "libserious_python_linux_plugin.so",
            "liburl_launcher_linux_plugin.so",
            "libwindow_manager_plugin.so",
        ):
            runpath = "/build-agent/build/flutter/linux/flutter/ephemeral"
            with self.subTest(name=name):
                self._verify_fixture("bundle", f"lib/{name}", runpath=runpath)
                self._verify_fixture(
                    "bundle",
                    f"lib/{name}",
                    runpath=self.JDK_RUNPATH,
                    expected_errors=("has absolute RUNPATH",),
                )
                for label in ("appdir", "appimage"):
                    self._verify_fixture(
                        label,
                        f"usr/lib/tokenlogue/lib/{name}",
                        runpath=runpath,
                        expected_errors=(
                            "has absolute RUNPATH",
                            "retains Flutter build RUNPATH",
                        ),
                    )

    def test_tkinter_diagnostic_allowance_stays_source_only(self) -> None:
        relative = "python3.12/lib-dynload/_tkinter.cpython-312-x86_64-linux-gnu.so"
        dependencies = ("libtcl9tk9.0.so", "libtcl9.0.so")
        output = "".join(f"{name} => not found\n" for name in dependencies)
        self._verify_fixture("bundle", relative, needed=dependencies, ldd_output=output)
        for label in ("appdir", "appimage"):
            with self.subTest(label=label):
                self._verify_fixture(
                    label,
                    f"usr/lib/tokenlogue/{relative}",
                    needed=dependencies,
                    ldd_output=output,
                    expected_errors=(
                        "_tkinter remains",
                        "retains Tcl/Tk dependency",
                        "has unresolved libraries",
                    ),
                )

    def test_java_free_packaged_bridge_still_passes(self) -> None:
        for label in ("appdir", "appimage"):
            with self.subTest(label=label):
                self._verify_fixture(
                    label,
                    "usr/lib/tokenlogue/lib/libdart_bridge.so",
                    runpath="$ORIGIN:$ORIGIN/../..",
                )

    def test_host_desktop_libraries_are_rejected_only_in_packaged_roots(self) -> None:
        for label in ("bundle", "appdir", "appimage"):
            with self.subTest(label=label):
                self._verify_fixture(
                    label,
                    "usr/lib/libgio-2.0.so.0",
                    expected_errors=("bundles a host desktop library",)
                    if label != "bundle"
                    else (),
                )

    def test_renamed_desktop_library_is_rejected_by_soname(self) -> None:
        for label in ("bundle", "appdir", "appimage"):
            with self.subTest(label=label):
                self._verify_fixture(
                    label,
                    "usr/lib/renamed-library.so",
                    soname="libgtk-3.so.0",
                    expected_errors=("bundles a host desktop SONAME",)
                    if label != "bundle"
                    else (),
                )

    def _verify_fixture(
        self,
        label: str,
        relative: str,
        *,
        runpath: str = "$ORIGIN",
        soname: str | None = None,
        needed: tuple[str, ...] = ("libc.so.6",),
        symbols: str = SAFE_SYMBOLS,
        ldd_output: str = "libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x01)\n",
        ldd_returncode: int = 0,
        extra_files: dict[str, bytes] | None = None,
        symlink: tuple[str, str] | None = None,
        expected_errors: tuple[str, ...] = (),
    ) -> dict[str, str]:
        # No ELF is executed or built: only readelf/objdump/ldd output is mocked.
        # File discovery, packaged-file checks, ABI gates and reports are real.
        with tempfile.TemporaryDirectory(prefix="tokenlogue jni test ") as temp:
            root = Path(temp) / "artifact"
            reports = Path(temp) / "reports"
            workspace = Path(temp) / "workspace"
            files = dict(extra_files or {})
            files[relative] = b"\x7fELFfixture"
            if label != "bundle":
                files.update(
                    {
                        "LICENSE": b"MIT License\n",
                        "THIRD_PARTY_NOTICES.md": b"Fixture notices\n",
                        "usr/share/doc/tokenlogue/LICENSE": b"MIT License\n",
                        "usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md": b"Fixture notices\n",
                        "usr/share/applications/io.github.umichata.tokenlogue.desktop": b"[Desktop Entry]\nType=Application\nExec=tokenlogue\n",
                        "usr/share/metainfo/io.github.umichata.tokenlogue.metainfo.xml": b"<component/>\n",
                    }
                )
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            if symlink is not None:
                link = root / symlink[0]
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(symlink[1])
            dynamic = (
                "".join(f"0x (NEEDED) Shared library: [{name}]\n" for name in needed)
                + f"0x (RUNPATH) Library runpath: [{runpath}]\n"
            )
            if soname is not None:
                dynamic += f"0x (SONAME) Library soname: [{soname}]\n"
            with (
                patch.object(
                    verify_bundle, "_run_checked", side_effect=[dynamic, symbols]
                ) as elf_tools,
                patch.object(
                    verify_bundle,
                    "_run_ldd",
                    return_value=subprocess.CompletedProcess(
                        ["ldd"], ldd_returncode, ldd_output, ""
                    ),
                ) as ldd,
            ):
                if expected_errors:
                    with self.assertRaises(verify_bundle.VerificationError):
                        verify_bundle.verify_abi([(label, root)], reports, workspace)
                else:
                    verify_bundle.verify_abi([(label, root)], reports, workspace)
                self.assertEqual(
                    elf_tools.call_args_list[0].args[0],
                    ["readelf", "-d", str(root / relative)],
                )
                self.assertEqual(
                    elf_tools.call_args_list[1].args[0],
                    ["objdump", "-T", str(root / relative)],
                )
                ldd.assert_called_once()
                self.assertEqual(ldd.call_args.args[0], root / relative)
            result = {
                name: (reports / name).read_text(encoding="utf-8")
                for name in ("elf-abi.txt", "rpaths.txt", "ldd.txt")
            }
            for message in expected_errors:
                self.assertIn(message, result["elf-abi.txt"])
            if not expected_errors:
                self.assertIn("result: PASS", result["elf-abi.txt"])
            return result


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
