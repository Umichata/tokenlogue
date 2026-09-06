"""No network, containers or application: test selection and failure orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "packaging/linux/appimage"
sys.path.insert(0, str(SCRIPTS))

import container_matrix as matrix  # noqa: E402 # pyright: ignore[reportMissingImports]
import source_artifact as source  # noqa: E402 # pyright: ignore[reportMissingImports]

from tests.test_linux_build_pipeline import SMOKE_FAKE_TOOL  # noqa: E402

COMMIT = "a" * 40
INFRASTRUCTURE = "b" * 40
RUN_ID = "123456"
PAYLOAD = b"fixture AppImage bytes, never executable in tests\n"
SHA256 = hashlib.sha256(PAYLOAD).hexdigest()
NAME = "Tokenlogue-0.1.0-x86_64.AppImage"
RUN = {
    "id": int(RUN_ID),
    "repository": {"full_name": "Umichata/tokenlogue"},
    "status": "completed",
    "conclusion": "success",
    "head_sha": COMMIT,
    "workflow_id": 100,
    "path": ".github/workflows/build-linux.yml",
}
WORKFLOW = {"id": 100, "path": ".github/workflows/build-linux.yml"}
ARTIFACT = {
    "id": 321,
    "name": "tokenlogue-linux-diagnostic-aaaaaaa",
    "expired": False,
    "workflow_run": {"id": int(RUN_ID), "head_sha": COMMIT},
}


def make_archive(
    path: Path, checksum: str = SHA256, extra: str | zipfile.ZipInfo | None = None
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("appimage/" + NAME, PAYLOAD)
        archive.writestr("linux-release/SHA256SUMS", f"{checksum}  {NAME}\n")
        if extra is not None:
            archive.writestr(extra, b"unexpected")


class ArtifactVerificationTests(unittest.TestCase):
    def test_selects_exact_source_and_never_the_new_infrastructure_commit(self) -> None:
        selected = source.select_artifact(RUN, WORKFLOW, [ARTIFACT], RUN_ID, COMMIT)
        self.assertEqual(selected["id"], 321)
        with self.assertRaisesRegex(source.VerificationError, "commit mismatch"):
            source.select_artifact(RUN, WORKFLOW, [ARTIFACT], RUN_ID, INFRASTRUCTURE)

    def test_rejects_repository_workflow_failed_or_incomplete_run(self) -> None:
        for change in (
            {"repository": {"full_name": "different/repository"}},
            {"status": "in_progress"},
            {"conclusion": "failure"},
            {"path": ".github/workflows/other.yml"},
            {"workflow_id": 101},
        ):
            with (
                self.subTest(change=change),
                self.assertRaises(source.VerificationError),
            ):
                source.select_artifact(
                    RUN | change, WORKFLOW, [ARTIFACT], RUN_ID, COMMIT
                )

    def test_rejects_absent_wrong_ambiguous_expired_or_unrelated_artifact(self) -> None:
        for artifacts in (
            [],
            [ARTIFACT | {"name": "wrong"}],
            [ARTIFACT, ARTIFACT],
            [ARTIFACT | {"expired": True}],
            [ARTIFACT | {"workflow_run": {"id": 7, "head_sha": COMMIT}}],
        ):
            with (
                self.subTest(artifacts=artifacts),
                self.assertRaises(source.VerificationError),
            ):
                source.select_artifact(RUN, WORKFLOW, artifacts, RUN_ID, COMMIT)

    def test_validates_inputs_before_api_calls(self) -> None:
        for run, sha in (
            ("1; echo unsafe", COMMIT),
            (RUN_ID, "aaaaaaa"),
            ("0", COMMIT),
        ):
            with self.subTest(run=run), self.assertRaises(source.VerificationError):
                source.validate_inputs(run, sha, INFRASTRUCTURE)

    def test_renaming_keeps_exact_bytes_and_manifest_uses_new_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_archive(root / "source.zip")
            info = source.unpack_verified(root / "source.zip", root / "output", COMMIT)
            self.assertEqual(
                info["filename"], "Tokenlogue-0.1.0-aaaaaaa-x86_64.AppImage"
            )
            self.assertEqual((root / "output" / info["filename"]).read_bytes(), PAYLOAD)
            self.assertEqual(info["sha256"], SHA256)
            self.assertEqual(
                (root / "output/SHA256SUMS").read_text(),
                f"{SHA256}  {info['filename']}\n",
            )
            self.assertEqual(len(list((root / "output").iterdir())), 2)

    def test_wrong_hash_is_rejected_and_partial_image_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_archive(root / "source.zip", "0" * 64)
            with self.assertRaisesRegex(source.VerificationError, "SHA-256 mismatch"):
                source.unpack_verified(root / "source.zip", root / "output", COMMIT)
            self.assertEqual(list((root / "output").iterdir()), [])

    def test_unsafe_zip_members_and_multiple_images_are_rejected(self) -> None:
        link = zipfile.ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra in (
            "../escape",
            "/absolute",
            "a/../escape",
            "a\\escape",
            "C:/escape",
            "second.AppImage",
            "another/SHA256SUMS",
            link,
        ):
            with self.subTest(extra=str(extra)), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                make_archive(root / "source.zip", extra=extra)
                with self.assertRaises(source.VerificationError):
                    source.unpack_verified(root / "source.zip", root / "output", COMMIT)
                self.assertFalse((root / "output").exists())

    def test_signed_blob_redirect_drops_authorization(self) -> None:
        handler = source.SafeRedirect()
        request = urllib.request.Request(
            "https://api.github.com/artifact",
            headers={"Authorization": "fixture-token-not-a-secret"},
        )
        redirected = handler.redirect_request(
            request, None, 302, "", {}, "https://example.invalid/blob"
        )
        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(source.VerificationError):
            handler.redirect_request(
                request, None, 302, "", {}, "http://example.invalid/blob"
            )

    def test_obtain_downloads_verified_id_and_cleans_archive_on_failure(self) -> None:
        class FakeGitHub:
            downloaded = []

            def json(self, path):
                return WORKFLOW if "workflows/" in path else RUN

            def artifacts(self, run):
                self.last_run = run
                return [ARTIFACT]

            def download(self, artifact_id, destination):
                self.downloaded.append(artifact_id)
                make_archive(destination, "0" * 64)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            client = FakeGitHub()
            with self.assertRaises(source.VerificationError):
                source.obtain(client, RUN_ID, COMMIT, INFRASTRUCTURE, root)
            self.assertEqual(client.downloaded, [321])
            self.assertEqual(list(root.glob("source-archive-*")), [])


def success_evidence() -> dict:
    return {
        "result": "PASS",
        "reason": "completed",
        "window_check": "PASS",
        "window_map_state": "IsViewable",
        "af_inet_socket_calls": "0",
        "af_inet_connect_calls": "0",
        "fatal_diagnostics": "0",
        "cleanup": "PASS",
        "remaining_processes": 0,
        "exit_code": "124",
        "elapsed_seconds": 20,
        "hash_check": "PASS",
    }


class MatrixFailureTests(unittest.TestCase):
    def test_unavailable_or_unsuccessful_evidence_never_passes(self) -> None:
        self.assertEqual(matrix.evaluate(success_evidence(), 0)[0], "PASS")
        for evidence, exit_code in (
            ({}, 0),
            ({"result": "BLOCKED"}, 0),
            (success_evidence(), 1),
            (success_evidence() | {"elapsed_seconds": 1}, 0),
        ):
            self.assertNotEqual(matrix.evaluate(evidence, exit_code)[0], "PASS")
        for field in success_evidence():
            if field == "reason":
                continue
            evidence = success_evidence()
            evidence[field] = "UNAVAILABLE"
            self.assertNotEqual(matrix.evaluate(evidence, 0)[0], "PASS", field)

    def _run(self, scenario: str) -> tuple[int, dict, list[list[str]], dict[str, str]]:
        with tempfile.TemporaryDirectory(prefix="matrix fixture ") as temp:
            root = Path(temp)
            source_dir = root / "source"
            source_dir.mkdir()
            reports = root / "reports"
            filename = "Tokenlogue-0.1.0-aaaaaaa-x86_64.AppImage"
            image = source_dir / filename
            image.write_bytes(PAYLOAD)
            provenance = {
                "source_commit": COMMIT,
                "source_run_id": RUN_ID,
                "infrastructure_commit": INFRASTRUCTURE,
                "artifact_id": 321,
                "filename": filename,
                "sha256": SHA256,
            }
            (source_dir / "provenance.json").write_text(json.dumps(provenance))
            calls = []

            def fake_command(args, log, timeout=120):
                calls.append(args)
                log.write_text("fixture diagnostic\n")
                if args[1] == "build":
                    context = Path(args[-1])
                    self.assertEqual(
                        {p.name for p in context.iterdir()},
                        {
                            "Containerfile.matrix",
                            "source_artifact.py",
                            "container_matrix.py",
                            "container_smoke.sh",
                            "smoke_appimage.sh",
                        },
                    )
                    if scenario == "environment_failure":
                        raise source.VerificationError(
                            "fixture environment unavailable"
                        )
                if args[1] == "start" and scenario == "early_launch_failure":
                    raise source.VerificationError("fixture launch failed")
                if args[1] == "wait":
                    if scenario == "timeout_diagnostic_failure":
                        raise subprocess.TimeoutExpired(args, timeout)
                    return "1\n" if scenario == "no_window" else "0\n"
                if args[1] == "inspect":
                    if scenario == "state_unavailable":
                        raise source.VerificationError("fixture state unavailable")
                    return json.dumps({"Running": False, "OOMKilled": False})
                if args[1] == "cp":
                    destination = Path(args[-1])
                    if destination.name == "container-summary.json":
                        evidence = success_evidence()
                        if scenario == "no_window":
                            evidence.update(result="FAIL", window_check="NOT_FOUND")
                        destination.write_text(json.dumps(evidence))
                    else:
                        destination.write_text("fixture available stderr\n")
                if args[1] == "rm":
                    if scenario == "cleanup_failure":
                        raise source.VerificationError("fixture cleanup failed")
                    if scenario == "bytes_changed":
                        image.write_bytes(b"changed")
                return ""

            with (
                patch.object(matrix, "run_command", fake_command),
                patch.object(matrix.shutil, "which", return_value="fixture-docker"),
                patch.dict(os.environ, {}, clear=True),
            ):
                code = matrix.run_matrix(
                    "ubuntu-22.04",
                    source_dir,
                    reports,
                    SHA256,
                    COMMIT,
                    RUN_ID,
                    INFRASTRUCTURE,
                )
            summary = json.loads((reports / "matrix-summary.json").read_text())
            saved = {p.name: p.read_text() for p in reports.iterdir()}
            return code, summary, calls, saved

    def test_success_verifies_bytes_and_isolation_arguments(self) -> None:
        code, report, calls, _ = self._run("success")
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["sha256_before"], report["sha256_after"])
        create = next(call for call in calls if call[1] == "create")
        for option, value in (
            ("--network", "none"),
            ("--user", "10001:10001"),
            ("--cap-drop", "ALL"),
            ("--cap-add", "SYS_PTRACE"),
        ):
            self.assertEqual(create[create.index(option) + 1], value)
        self.assertNotIn("--privileged", create)
        self.assertNotIn("--env", create)
        self.assertTrue(any(call[1] == "rm" for call in calls))

    def test_environment_failure_reports_blocked_and_not_run(self) -> None:
        code, report, calls, saved = self._run("environment_failure")
        self.assertNotEqual(code, 0)
        self.assertEqual(report["result"], "BLOCKED")
        self.assertEqual(report["network_check"], "NOT_RUN")
        self.assertFalse(any(call[1] == "create" for call in calls))
        self.assertEqual(saved["smoke-application.stderr.txt"], "NOT_CAPTURED\n")

    def test_failure_copies_diagnostics_and_always_removes_container(self) -> None:
        for scenario in (
            "early_launch_failure",
            "no_window",
            "timeout_diagnostic_failure",
        ):
            with self.subTest(scenario=scenario):
                code, report, calls, saved = self._run(scenario)
                self.assertNotEqual(code, 0)
                self.assertNotEqual(report["result"], "PASS")
                self.assertEqual(report["container_cleanup"], "PASS")
                self.assertIn(
                    "fixture available stderr", saved["smoke-application.stderr.txt"]
                )
                self.assertTrue(any(call[1] == "rm" for call in calls))
                for call in calls:
                    if call[1] == "cp":
                        self.assertIn(Path(call[-1]).name, matrix.REPORT_FILES)

    def test_cleanup_failure_and_changed_bytes_override_success(self) -> None:
        for scenario in ("cleanup_failure", "bytes_changed", "state_unavailable"):
            with self.subTest(scenario=scenario):
                code, report, _, _ = self._run(scenario)
                self.assertNotEqual(code, 0)
                self.assertEqual(report["result"], "FAIL")


class MatrixInfrastructureTests(unittest.TestCase):
    def test_exported_window_probe_accepts_only_exact_viewable_window(self) -> None:
        for window, expected_status in (
            ({}, 0),
            ({"map_state": "IsUnMapped"}, 1),
            ({"instance": "other"}, 1),
            ({"title": "Other"}, 1),
        ):
            with self.subTest(window=window), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "logs").mkdir()
                (root / "launched").touch()
                fake_bin = root / "bin"
                fake_bin.mkdir()
                fake = fake_bin / "fake_tool.py"
                fake.write_text("#!" + sys.executable + "\n" + SMOKE_FAKE_TOOL)
                fake.chmod(0o755)
                for name in ("xwininfo", "xprop"):
                    (fake_bin / name).symlink_to(fake.name)
                library = root / "library.sh"
                matrix.smoke_library(SCRIPTS / "smoke_appimage.sh", library)
                environment = os.environ | {
                    "PATH": str(fake_bin) + ":/usr/bin:/bin",
                    "SMOKE_FIXTURE_ROOT": str(root),
                    "SMOKE_FIXTURE_SCENARIO": json.dumps({"window": window}),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        'source "$1"; smoke_root=$2; display=:97; window_attempts=NOT_RUN; find_tokenlogue_window',
                        "fixture",
                        str(library),
                        str(root),
                    ],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, expected_status, result.stderr)
                calls = [
                    json.loads(line)
                    for line in (root / "tools.jsonl").read_text().splitlines()
                ]
                for call in calls:
                    self.assertEqual(call["display"], ":97")
                    self.assertEqual(call["locale"], "C")
                    self.assertNotIn("_NET_CLIENT_LIST", call["args"])

    def test_real_container_exit_handler_preserves_errors_reports_and_cleanup(
        self,
    ) -> None:
        # Exercise the actual EXIT handler with fake observations, without Docker,
        # Xvfb, the AppImage, or the container-only process reaper.
        for scenario in ("early", "no_window", "report_failure"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                reports = root / "reports"
                scratch = root / "scratch"
                scratch.mkdir()
                matrix.smoke_library(
                    SCRIPTS / "smoke_appimage.sh", root / "smoke-functions.sh"
                )
                prefix = (
                    (SCRIPTS / "container_smoke.sh")
                    .read_text()
                    .split("[[ -f /run/tokenlogue-matrix-container", 1)[0]
                )
                prefix = prefix.replace("reports_dir=/reports", 'reports_dir="$1"')
                script = root / "fixture.sh"
                body = r"""
python3() {
    if [[ "${2-}" == cleanup ]]; then
        printf '{"cleanup":"PASS","remaining_processes":0}\n'
        printf 'cleanup called\n' > "$reports_dir/cleanup-called.txt"
    else
        command python3 "$@"
    fi
}
smoke_root=$(mktemp -d "$2/smoke.XXXXXX")
mkdir "$smoke_root/logs" "$smoke_root/private"
printf 'private fixture\n' > "$smoke_root/private/database.sqlite3"
printf 'fixture Xvfb error\n' > "$smoke_root/logs/xvfb.stderr"
if [[ "$3" != early ]]; then
    phase=FAIL
    smoke_status=124
    elapsed_seconds=20
    window_check=NOT_FOUND
    printf 'fixture application stderr\n' > "$smoke_root/logs/application.stderr"
    printf 'fixture sandbox stderr\n' > "$smoke_root/logs/sandbox.stderr"
    printf 'socket(AF_UNIX, SOCK_STREAM, 0) = 1\n' > "$smoke_root/logs/trace.42"
fi
if [[ "$3" == report_failure ]]; then
    cp() { return 17; }
fi
die "fixture $3 failure"
"""
                script.write_text(prefix + body)
                result = subprocess.run(
                    ["bash", str(script), str(reports), str(scratch), scenario],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                report = json.loads((reports / "container-summary.json").read_text())
                self.assertNotEqual(report["result"], "PASS")
                self.assertEqual(list(scratch.iterdir()), [])
                self.assertTrue((reports / "cleanup-called.txt").exists())
                self.assertIn("fixture", report["reason"])
                if scenario == "early":
                    self.assertEqual(report["af_inet_socket_calls"], "NOT_RUN")
                    self.assertEqual(report["window_check"], "NOT_RUN")
                    self.assertIn(
                        "fixture Xvfb error",
                        (reports / "smoke-xvfb.stderr.txt").read_text(),
                    )

    def test_function_exports_are_exact_and_exclude_outer_runner(self) -> None:
        text = (SCRIPTS / "smoke_appimage.sh").read_text()
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "library.sh"
            matrix.smoke_library(SCRIPTS / "smoke_appimage.sh", output)
            generated = output.read_text()
            for name in matrix.SMOKE_FUNCTIONS:
                original = re.findall(rf"(?ms)^{name}\(\) \{{\n.*?^\}}\n", text)[0]
                self.assertIn(original, generated)
            self.assertNotIn("bwrap_args=", generated)
            self.assertNotIn("finish_outer", generated)
            self.assertIn("xwininfo -root -tree", generated)
            self.assertIn('"tokenlogue", "Tokenlogue"', generated)
            self.assertIn("Map State: IsViewable", generated)

    def test_image_pins_are_exact_official_amd64_manifests(self) -> None:
        data = json.loads((SCRIPTS / "container-images.lock.json").read_text())
        self.assertEqual(
            set(data["images"]), {"ubuntu-22.04", "ubuntu-24.04", "fedora-44"}
        )
        for image in data["images"].values():
            self.assertRegex(image["digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertTrue(image["manifest_url"].endswith(image["digest"]))
            self.assertTrue(image["tag"].startswith("docker.io/library/"))
            self.assertNotIn("latest", image["tag"])

    def test_workflow_is_manual_least_privilege_and_uses_verified_actions(self) -> None:
        workflow = (ROOT / ".github/workflows/test-linux-appimage.yml").read_text()
        expected = {
            "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
            "actions/upload-artifact": (
                "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
                "v7.0.1",
            ),
            "actions/download-artifact": (
                "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
                "v8.0.1",
            ),
        }
        actions = re.findall(r"uses: ([^@\s]+)@([0-9a-f]+) # (v\S+)", workflow)
        self.assertEqual(len(actions), workflow.count("uses:"))
        for action, sha, tag in actions:
            self.assertEqual((sha, tag), expected[action])
        for text in (
            "workflow_dispatch:",
            "contents: read",
            "actions: read",
            "fail-fast: false",
            "persist-credentials: false",
            "retention-days: 14",
            "always() && !cancelled()",
        ):
            self.assertIn(text, workflow)
        for text in (
            "pull_request:",
            "push:",
            "schedule:",
            "continue-on-error",
            "secrets.",
            "ref: ${{ inputs.source_commit",
        ):
            self.assertNotIn(text, workflow)
        self.assertEqual(workflow.count("GH_TOKEN:"), 1)
        for block in re.findall(
            r"(?ms)^        run: \|\n(.*?)(?=^      -|\Z)", workflow
        ):
            self.assertNotIn("${{ inputs.", block)

    def test_container_has_runtime_only_and_reports_exclude_private_data(self) -> None:
        text = (SCRIPTS / "Containerfile.matrix").read_text()
        for forbidden in (
            "-dev ",
            "-devel ",
            "build-essential",
            "clang",
            "pip install",
            "flutter build",
        ):
            self.assertNotIn(forbidden, text)
        script = (SCRIPTS / "container_smoke.sh").read_text()
        for required in (
            "-nolisten tcp",
            "LIBGL_ALWAYS_SOFTWARE=1",
            "20s dbus-run-session",
            "trap 'finish \"$?\"' EXIT",
            "save_diagnostic_logs",
            "mktemp -d",
        ):
            self.assertIn(required, script)
        for name in matrix.REPORT_FILES:
            self.assertNotRegex(name, r"trace\.|sqlite|keyring|home|cache")


if __name__ == "__main__":
    unittest.main()
