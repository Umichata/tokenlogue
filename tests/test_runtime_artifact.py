"""Проверки выбора готового runtime, публикации ZIP и привязки notices."""

from __future__ import annotations

import copy
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import warnings
import zipfile
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from tests.runtime_fixture import RuntimeFixture, encoded, sha

SCRIPTS = Path(__file__).resolve().parents[1] / "packaging/linux/appimage"
sys.path.insert(0, str(SCRIPTS))
import fetch_runtime  # noqa: E402  # pyright: ignore[reportMissingImports]
import notice_inputs  # noqa: E402  # pyright: ignore[reportMissingImports]
import notices  # noqa: E402  # pyright: ignore[reportMissingImports]


class FakeGitHub:
    def __init__(self, fixture: RuntimeFixture):
        self.fixture = fixture
        self.calls = []
        self.downloads = []

    def json(self, path: str) -> dict:
        self.calls.append(path)
        run, workflow, artifact = self.fixture.api()
        lock = self.fixture.lock
        return {
            f"/actions/runs/{lock['source_run_id']}/attempts/{lock['run_attempt']}": run,
            "/actions/workflows/build-appimage-runtime.yml": workflow,
            f"/actions/artifacts/{lock['artifact_id']}": artifact,
        }[path]

    def download(self, artifact_id: int, destination: Path) -> None:
        self.downloads.append(artifact_id)
        shutil.copyfile(self.fixture.archive, destination)


class RuntimeArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="runtime-artifact-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = RuntimeFixture(self.root)
        self.output = self.root / "verified"

    def test_complete_archive_publishes_without_network_or_execution(self) -> None:
        with (
            patch.object(
                fetch_runtime, "GitHub", side_effect=AssertionError("network")
            ),
            patch.object(
                fetch_runtime.subprocess, "run", side_effect=AssertionError("execution")
            ),
        ):
            result = fetch_runtime.obtain(
                self.fixture.lock, self.output, archive=self.fixture.archive
            )
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["api_metadata"], "NOT_CHECKED")
        self.assertEqual(result["crc"], "PASS")
        self.assertTrue((self.output / fetch_runtime.WORKFLOW_MEMBER).is_file())
        self.assertTrue((self.output / "runtime-x86_64").stat().st_mode & 0o111)
        self.assertEqual(
            fetch_runtime.verify_bundle(self.output, self.fixture.lock)["result"],
            "PASS",
        )

    def test_exact_api_selection_downloads_pinned_id_and_checks_cache_again(
        self,
    ) -> None:
        client = FakeGitHub(self.fixture)
        result = fetch_runtime.obtain(self.fixture.lock, self.output, client=client)
        self.assertEqual(result["api_metadata"], "PASS")
        self.assertEqual(client.downloads, [self.fixture.lock["artifact_id"]])
        result = fetch_runtime.obtain(self.fixture.lock, self.output, client=client)
        self.assertEqual(result["cache"], "REVERIFIED")
        self.assertEqual(client.downloads, [self.fixture.lock["artifact_id"]])
        (self.output / "runtime-x86_64").write_bytes(b"damaged")
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            fetch_runtime.obtain(self.fixture.lock, self.output, client=client)
        self.assertEqual(client.downloads, [self.fixture.lock["artifact_id"]])

    def test_every_api_identity_field_is_enforced(self) -> None:
        originals = self.fixture.api()
        changes = [
            (0, ("id",), 999),
            (0, ("run_attempt",), 2),
            (0, ("repository", "full_name"), "other/repo"),
            (0, ("head_sha",), "b" * 40),
            (0, ("conclusion",), "failure"),
            (0, ("status",), "in_progress"),
            (0, ("workflow_id",), 999),
            (0, ("path",), ".github/workflows/other.yml"),
            (1, ("path",), ".github/workflows/build-linux.yml"),
            (2, ("id",), 999),
            (2, ("name",), "latest"),
            (2, ("size_in_bytes",), 1),
            (2, ("digest",), "sha256:" + "0" * 64),
            (2, ("expired",), True),
            (2, ("expires_at",), "2000-01-01T00:00:00Z"),
            (2, ("workflow_run", "id"), 999),
            (2, ("workflow_run", "head_sha"), "b" * 40),
        ]
        for group, fields, value in changes:
            with self.subTest(fields=fields, value=value):
                metadata = copy.deepcopy(originals)
                target = metadata[group]
                for field in fields[:-1]:
                    target = target[field]
                target[fields[-1]] = value
                with self.assertRaises(fetch_runtime.RuntimeArtifactError):
                    fetch_runtime.select_artifact(*metadata, self.fixture.lock)

    def test_bad_archive_size_or_digest_fails_before_publication(self) -> None:
        for field, value in [("archive_size", 1), ("archive_sha256", "0" * 64)]:
            lock = {**self.fixture.lock, field: value}
            with (
                self.subTest(field=field),
                self.assertRaises(fetch_runtime.RuntimeArtifactError),
            ):
                fetch_runtime.obtain(lock, self.output, archive=self.fixture.archive)
            self.assertFalse(self.output.exists())

    def test_crc_failure_prevents_publication_even_with_matching_outer_hash(
        self,
    ) -> None:
        with zipfile.ZipFile(self.fixture.archive) as archive:
            member = archive.getinfo("runtime-x86_64")
            offset = (
                member.header_offset
                + 30
                + len(member.filename.encode())
                + len(member.extra)
            )
        data = bytearray(self.fixture.archive.read_bytes())
        data[offset] ^= 1
        self.fixture.archive.write_bytes(data)
        lock = {**self.fixture.lock, "archive_sha256": sha(bytes(data))}
        with self.assertRaises(zipfile.BadZipFile):
            fetch_runtime.obtain(lock, self.output, archive=self.fixture.archive)
        self.assertFalse(self.output.exists())

    def test_unreadable_cache_directory_is_not_treated_as_complete(self) -> None:
        fetch_runtime.obtain(
            self.fixture.lock, self.output, archive=self.fixture.archive
        )

        def failed_walk(_root, **kwargs):
            kwargs["onerror"](PermissionError("private path must not be logged"))

        with patch.object(fetch_runtime.os, "walk", side_effect=failed_walk):
            with self.assertRaisesRegex(
                fetch_runtime.RuntimeArtifactError, "прочитать каталог"
            ):
                fetch_runtime.verify_bundle(self.output, self.fixture.lock)

    def test_incomplete_or_changed_files_are_rejected(self) -> None:
        for name, value in [
            ("runtime-x86_64", b"corrupt runtime"),
            (fetch_runtime.WORKFLOW_MEMBER, None),
            ("materials/licenses/gcc/COPYING.RUNTIME", None),
            ("unexpected", b"extra"),
        ]:
            with self.subTest(name=name):
                files = dict(self.fixture.files)
                if value is None:
                    del files[name]
                else:
                    files[name] = value
                archive, lock = self.fixture.write_zip(files)
                with self.assertRaises(fetch_runtime.RuntimeArtifactError):
                    fetch_runtime.obtain(lock, self.output, archive=archive)
                self.assertFalse(self.output.exists())
                self.assertFalse(list(self.root.glob("runtime-input-*")))

    def test_manifest_and_checksum_entries_cannot_be_dropped(self) -> None:
        for part in ("manifest", "sums"):
            with self.subTest(part=part):
                files = dict(self.fixture.files)
                if part == "manifest":
                    manifest = copy.deepcopy(self.fixture.manifest)
                    manifest["files"] = [
                        r
                        for r in manifest["files"]
                        if r["path"] != fetch_runtime.WORKFLOW_MEMBER
                    ]
                    files["manifest.json"] = encoded(manifest)
                    files["SHA256SUMS"] = "".join(
                        f"{sha(data)}  {name}\n"
                        for name, data in sorted(files.items())
                        if name != "SHA256SUMS"
                    ).encode()
                else:
                    files["SHA256SUMS"] = (
                        b"\n".join(
                            line
                            for line in files["SHA256SUMS"].splitlines()
                            if fetch_runtime.WORKFLOW_MEMBER.encode() not in line
                        )
                        + b"\n"
                    )
                archive, lock = self.fixture.write_zip(files)
                with self.assertRaises(fetch_runtime.RuntimeArtifactError):
                    fetch_runtime.obtain(lock, self.output, archive=archive)

    def test_wrong_embedded_commit_fingerprint_and_failed_stage_are_rejected(
        self,
    ) -> None:
        for field, value in [
            ("commit", "a" * 40),
            ("sha256", "b" * 64),
            ("dirty", True),
        ]:
            manifest = copy.deepcopy(self.fixture.manifest)
            manifest["tokenlogue_recipe"][field] = value
            self.assert_bad_manifest(manifest)
        manifest = copy.deepcopy(self.fixture.manifest)
        manifest["checks"]["smoke"]["result"] = "NOT_RUN"
        self.assert_bad_manifest(manifest)

    def assert_bad_manifest(self, manifest: dict) -> None:
        files = dict(self.fixture.files)
        files["manifest.json"] = encoded(manifest)
        files["SHA256SUMS"] = "".join(
            f"{sha(data)}  {name}\n"
            for name, data in files.items()
            if name != "SHA256SUMS"
        ).encode()
        archive, lock = self.fixture.write_zip(files)
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            fetch_runtime.obtain(lock, self.output, archive=archive)

    def test_unsafe_duplicate_and_symlink_zip_members_are_rejected(self) -> None:
        for path in ("../outside", "/absolute", "bad\\path", "a/../b"):
            files = {**self.fixture.files, path: b"bad"}
            archive, lock = self.fixture.write_zip(files)
            with self.assertRaises(fetch_runtime.RuntimeArtifactError):
                fetch_runtime.obtain(lock, self.output, archive=archive)
            self.assertFalse(self.output.exists())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            archive, lock = self.fixture.write_zip(
                self.fixture.files, duplicate="runtime-x86_64"
            )
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            fetch_runtime.obtain(lock, self.output, archive=archive)
        archive, lock = self.fixture.write_zip(
            self.fixture.files, symlink="runtime-x86_64"
        )
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            fetch_runtime.obtain(lock, self.output, archive=archive)

    def test_prefix_allows_only_md5_and_rejects_truncation_and_other_runtime(
        self,
    ) -> None:
        runtime = self.root / "runtime"
        runtime.write_bytes(self.fixture.files["runtime-x86_64"])
        report = fetch_runtime.runtime_checks.elf_report(runtime)
        offset = report["sections"][".digest_md5"]["offset"]
        image = self.root / "fixture.AppImage"
        data = bytearray(runtime.read_bytes())
        data[offset : offset + 16] = b"x" * 16
        image.write_bytes(data + b"squashfs fixture")
        self.assertEqual(
            fetch_runtime.check_prefix(runtime, image, self.fixture.lock)["result"],
            "PASS",
        )
        for invalid in (data[:offset], data[:-1], data[:120] + b"wrong" + data[125:]):
            image.write_bytes(invalid)
            with self.assertRaises(fetch_runtime.RuntimeArtifactError):
                fetch_runtime.check_prefix(runtime, image, self.fixture.lock)

    def test_http_error_report_never_contains_token_or_signed_url(self) -> None:
        output = io.StringIO()
        report = self.root / "report.json"
        error = urllib.error.HTTPError(
            "https://blob.invalid/?signature=secret",
            403,
            "private detail",
            Message(),
            None,
        )
        with (
            patch.object(
                sys,
                "argv",
                [
                    "fetch_runtime.py",
                    "--output",
                    str(self.output),
                    "--report",
                    str(report),
                ],
            ),
            patch.object(fetch_runtime, "RuntimeGitHub", side_effect=error),
            redirect_stdout(output),
        ):
            self.assertEqual(fetch_runtime.main(), 1)
        self.assertIn("HTTP 403", output.getvalue())
        self.assertNotIn("secret", output.getvalue() + report.read_text())
        self.assertNotIn("blob.invalid", output.getvalue() + report.read_text())

    def test_application_commit_is_separate_from_runtime_producer(self) -> None:
        output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "fetch_runtime.py",
                    "--archive",
                    str(self.fixture.archive),
                    "--output",
                    str(self.output),
                ],
            ),
            patch.object(fetch_runtime, "load_lock", return_value=self.fixture.lock),
            patch.object(
                fetch_runtime.subprocess, "check_output", return_value="f" * 40 + "\n"
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(fetch_runtime.main(), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["application_commit"], "f" * 40)
        self.assertEqual(
            report["producer_commit"], self.fixture.lock["producer_commit"]
        )
        self.assertEqual(report["runtime_sha256"], self.fixture.lock["runtime_sha256"])

    def test_packaging_passes_same_runtime_and_blocks_publication_on_bad_prefix(
        self,
    ) -> None:
        source = (SCRIPTS / "build_appimage.sh").read_text()
        collect = re.search(
            r'^"\$python_bin" "\$script_dir/notices.py" collect \\\n(?:.*\\\n)*.*$',
            source,
            re.M,
        )
        assert collect is not None
        start = source.index("env \\\n    HOME=", collect.end())
        end = source.index("\nsource_hash_after=", start)
        program = collect[0] + "\n" + source[start:end]
        scripts = self.root / "scripts"
        scripts.mkdir()
        lock_file = scripts / "lock.json"
        lock_file.write_text(json.dumps(self.fixture.lock))
        (scripts / "notices.py").write_text(
            "import json,os,sys\n"
            'with open(os.environ["CAPTURE"],"a") as f:\n'
            ' f.write(json.dumps({"tool":"notices","runtime":sys.argv[sys.argv.index("--runtime")+1]})+"\\n")\n'
        )
        (scripts / "fetch_runtime.py").write_text(
            "import argparse,json,sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0,{str(SCRIPTS)!r})\nimport fetch_runtime\n"
            'p=argparse.ArgumentParser();p.add_argument("action");p.add_argument("--runtime");p.add_argument("--appimage");p.add_argument("--report");a=p.parse_args()\n'
            f"lock=json.loads(Path({str(lock_file)!r}).read_text())\n"
            "result=fetch_runtime.check_prefix(Path(a.runtime),Path(a.appimage),lock)\n"
            "Path(a.report).write_text(json.dumps(result))\n"
        )
        tool = scripts / "appimagetool"
        tool.write_text(
            f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0,{str(SCRIPTS)!r})\nimport fetch_runtime\n"
            'runtime=Path(sys.argv[sys.argv.index("--runtime-file")+1])\n'
            'with open(os.environ["CAPTURE"],"a") as f:\n'
            ' f.write(json.dumps({"tool":"packager","runtime":str(runtime)})+"\\n")\n'
            "data=bytearray(runtime.read_bytes())\n"
            'offset=fetch_runtime.runtime_checks.elf_report(runtime)["sections"][".digest_md5"]["offset"]\n'
            'data[offset:offset+16]=b"m"*16\n'
            'if os.environ.get("CORRUPT"):data[100]^=1\n'
            'Path(sys.argv[-1]).write_bytes(data+b"squashfs fixture")\n'
        )
        tool.chmod(0o755)
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt):
                run = self.root / ("bad" if corrupt else "good")
                run.mkdir()
                work = run / "appimage"
                work.mkdir()
                staging = work / ".stage"
                staging.mkdir()
                appdir = staging / "Tokenlogue.AppDir"
                appdir.mkdir()
                (appdir / "notice-marker").write_text("new notices")
                final = work / "Tokenlogue-0.1.0-x86_64.AppImage"
                final.write_bytes(b"previous artifact")
                selected = run / "selected-runtime"
                selected.write_bytes(self.fixture.files["runtime-x86_64"])
                old = run / "legacy-runtime"
                old.write_bytes(b"must never be selected")
                capture = run / "calls.jsonl"
                values = {
                    "python_bin": sys.executable,
                    "script_dir": scripts,
                    "appdir": appdir,
                    "work_root": work,
                    "repo_root": run,
                    "standalone_runtime": selected,
                    "appimagetool_runtime": old,
                    "appimagetool": tool,
                    "tool_home": run / "tool-home",
                    "SOURCE_DATE_EPOCH": "1",
                    "partial_image": staging / "partial.AppImage",
                    "version": "0.1.0",
                    "final_appdir": work / "Tokenlogue.AppDir",
                    "final_image": final,
                    "RUNTIME_PREFIX_REPORT": run / "prefix.json",
                }
                assignments = "\n".join(
                    f"{key}={shlex.quote(str(value))}" for key, value in values.items()
                )
                env = {"PATH": os.environ["PATH"], "CAPTURE": str(capture)}
                if corrupt:
                    env["CORRUPT"] = "1"
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        "set -Eeuo pipefail\ndie(){ exit 1; }\n"
                        + assignments
                        + "\n"
                        + program,
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                )
                records = [
                    json.loads(line) for line in capture.read_text().splitlines()
                ]
                self.assertEqual(
                    {r["tool"] for r in records}, {"notices", "packager"}, result.stderr
                )
                self.assertEqual({r["runtime"] for r in records}, {str(selected)})
                if corrupt:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(final.read_bytes(), b"previous artifact")
                    self.assertFalse((work / "Tokenlogue.AppDir").exists())
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        json.loads((run / "prefix.json").read_text())["result"], "PASS"
                    )
                    self.assertTrue(
                        (work / "Tokenlogue.AppDir/notice-marker").is_file()
                    )


class RuntimeNoticeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="runtime-notice-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = RuntimeFixture(self.root)
        self.materials = self.root / "verified"
        fetch_runtime.obtain(
            self.fixture.lock, self.materials, archive=self.fixture.archive
        )
        self.appdir = self.root / "AppDir"
        self.appdir.mkdir()
        collector = notices.Collector(self.appdir, self.fixture.notice_lock)
        with patch.object(fetch_runtime, "load_lock", return_value=self.fixture.lock):
            collector.collect_runtime(self.materials / "runtime-x86_64")
        self.manifest = {
            "schema": 1,
            "result": "PASS",
            "source_materials": self.fixture.notice_lock["release_source_status"],
            "subjects": [],
            "components": collector.components,
            "files": {
                p: notice_inputs.sha256(self.appdir / p) for p in collector.notice_paths
            },
        }
        notices.write_json(self.appdir / notices.MANIFEST, self.manifest)
        self.registry_patch = patch.object(
            notices, "load_lock", return_value=self.fixture.notice_lock
        )
        self.registry_patch.start()
        self.addCleanup(self.registry_patch.stop)

    def test_all_licenses_are_unchanged_hashed_and_provenance_is_compact(self) -> None:
        self.assertEqual(notices.verify(self.appdir)["result"], "PASS")
        self.assertTrue(
            notices.verify(self.appdir)["source_materials"].startswith(
                "REVIEW_REQUIRED"
            )
        )
        licenses = [p for p in self.manifest["files"] if not p.endswith(".json")]
        self.assertEqual(len(licenses), 15)
        for path in licenses:
            source = "materials/licenses/" + path.split("/appimage-runtime/", 1)[1]
            self.assertEqual(
                (self.appdir / path).read_bytes(), self.fixture.files[source]
            )
        for path in self.manifest["files"]:
            self.assertNotIn(b"/home/runner", (self.appdir / path).read_bytes())
            self.assertNotIn(b"/build-one", (self.appdir / path).read_bytes())

    def test_missing_changed_notice_or_missing_runtime_component_fails(self) -> None:
        path = (
            self.appdir / notices.DOC / "licenses/appimage-runtime/gcc/COPYING.RUNTIME"
        )
        data = path.read_bytes()
        for content in (None, b"modified"):
            if content is None:
                path.unlink()
            else:
                path.write_bytes(content)
            with self.assertRaises(notice_inputs.NoticeError):
                notices.verify(self.appdir)
        path.write_bytes(data)
        self.manifest["components"] = [
            c for c in self.manifest["components"] if c["id"] != "appimage-runtime"
        ]
        notices.write_json(self.appdir / notices.MANIFEST, self.manifest)
        with self.assertRaisesRegex(notice_inputs.NoticeError, "appimage-runtime"):
            notices.verify(self.appdir)

    def test_another_runtime_is_not_accepted_by_notice_registry(self) -> None:
        self.fixture.notice_lock["runtime"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(notice_inputs.NoticeError, "appimage-runtime"):
            notices.verify(self.appdir)
        collector = notices.Collector(self.appdir, self.fixture.notice_lock)
        with patch.object(fetch_runtime, "load_lock", return_value=self.fixture.lock):
            with self.assertRaisesRegex(notice_inputs.NoticeError, "registry"):
                collector.collect_runtime(self.materials / "runtime-x86_64")


if __name__ == "__main__":
    unittest.main()
