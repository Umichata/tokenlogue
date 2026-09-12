from __future__ import annotations

import copy
import hashlib
import importlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
MODULE = PROJECT / "packaging/linux/appimage/runtime"
sys.path.insert(0, str(MODULE))
try:
    inputs = importlib.import_module("runtime_inputs")
    checks = importlib.import_module("runtime_checks")
    pipeline = importlib.import_module("build_runtime")
finally:
    sys.path.pop(0)


class InputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="runtime-input-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock = inputs.load_lock(MODULE / "runtime.lock.json")

    def write_lock(self, lock: dict) -> Path:
        path = self.root / "lock.json"
        path.write_text(json.dumps(lock))
        return path

    def test_valid_checked_in_lock_is_accepted(self) -> None:
        self.assertEqual(self.lock["builder"]["platform"], "linux/amd64")
        self.assertEqual(
            len(self.lock["installed_inventory"]), len(self.lock["packages"])
        )

    def test_corrupted_cached_input_is_rejected_without_replacement(self) -> None:
        path = self.root / "input.tar.gz"
        path.write_bytes(b"damaged")
        lock = {
            "files": [
                {
                    "path": path.name,
                    "size": 7,
                    "sha256": hashlib.sha256(b"correct").hexdigest(),
                    "url": "https://example.invalid/source",
                }
            ]
        }
        with patch.object(inputs.urllib.request, "build_opener") as opener:
            with self.assertRaisesRegex(inputs.Failure, "SHA-256 mismatch"):
                inputs.fetch_inputs(lock, self.root)
            opener.return_value.open.assert_not_called()
        self.assertEqual(path.read_bytes(), b"damaged")

    def test_verified_cache_is_rehashed_and_reused_without_network(self) -> None:
        path = self.root / "input"
        path.write_bytes(b"correct")
        lock = {
            "files": [{"path": path.name, "size": 7, "sha256": inputs.digest(path)}]
        }
        with patch.object(inputs.urllib.request, "build_opener") as opener:
            inputs.fetch_inputs(lock, self.root)
            opener.return_value.open.assert_not_called()

    def test_missing_package_in_lock_fails(self) -> None:
        self.lock["packages"].pop()
        with self.assertRaisesRegex(inputs.Failure, "locked package"):
            inputs.load_lock(self.write_lock(self.lock))

    def test_missing_required_source_in_lock_fails(self) -> None:
        source = self.lock["components"][0]["source"]
        self.lock["files"] = [f for f in self.lock["files"] if f["path"] != source]
        with self.assertRaisesRegex(inputs.Failure, "required source"):
            inputs.load_lock(self.write_lock(self.lock))

    def test_missing_package_or_source_on_disk_fails_before_processing(self) -> None:
        for kind in ("apk", "source"):
            with self.subTest(kind=kind):
                record = next(f for f in self.lock["files"] if f["kind"] == kind)
                with self.assertRaisesRegex(inputs.Failure, "Missing regular input"):
                    inputs.check_inputs({"files": [record]}, self.root)

    def test_wrong_aports_origin_is_rejected(self) -> None:
        package = next(p for p in self.lock["packages"] if p["name"] == "musl-dev")
        package["aports_commit"] = "a" * 40
        installed = next(
            p for p in self.lock["installed_inventory"] if p["name"] == "musl-dev"
        )
        installed["aports_commit"] = package["aports_commit"]
        with self.assertRaisesRegex(inputs.Failure, "origin mismatch"):
            inputs.load_lock(self.write_lock(self.lock))

    def test_mismatched_inventory_and_extra_packages_are_rejected(self) -> None:
        expected = self.lock["installed_inventory"]
        inputs.check_inventory(copy.deepcopy(expected), expected)
        cases = [expected[:-1], [*expected, {**expected[0], "name": "unrequested"}]]
        for key in ("version", "origin", "arch", "aports_commit"):
            changed = copy.deepcopy(expected)
            changed[0][key] = "unexpected"
            cases.append(changed)
        for actual in cases:
            with self.subTest(actual=actual[0]):
                with self.assertRaisesRegex(inputs.Failure, "Inventory mismatch"):
                    inputs.check_inventory(actual, expected)

    def test_input_symlinks_and_escaping_paths_fail(self) -> None:
        (self.root / "target").write_bytes(b"data")
        (self.root / "link").symlink_to("target")
        for name in ("../escape", "/absolute", "link", "bad\\path"):
            with self.subTest(name=name):
                with self.assertRaises(inputs.Failure):
                    inputs.input_path(self.root, name)

    def test_redirect_does_not_forward_registry_authorization(self) -> None:
        request = inputs.urllib.request.Request(
            "https://registry.example/file",
            headers={"Authorization": "Bearer private-test-value"},
        )
        redirect = inputs.PublicRedirect().redirect_request(
            request,
            None,
            302,
            "redirect",
            {},
            "https://cdn.example/file?signature=value",
        )
        self.assertNotIn("Authorization", redirect.headers)
        with self.assertRaisesRegex(inputs.Failure, "Non-HTTPS"):
            inputs.PublicRedirect().redirect_request(
                request, None, 302, "redirect", {}, "http://cdn.example/file"
            )


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="runtime-tar-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, members: list[tuple[str, bytes | str, bytes]]) -> Path:
        path = self.root / "archive.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            for name, value, kind in members:
                member = tarfile.TarInfo(name)
                member.type = kind
                if kind == tarfile.REGTYPE:
                    assert isinstance(value, bytes)
                    member.size = len(value)
                    archive.addfile(member, io.BytesIO(value))
                else:
                    assert isinstance(value, str)
                    member.linkname = value
                    archive.addfile(member)
        return path

    def test_valid_source_with_internal_links_extracts(self) -> None:
        path = self.archive(
            [
                ("src/file", b"source", tarfile.REGTYPE),
                ("src/link", "file", tarfile.SYMTYPE),
                ("src/hard", "src/file", tarfile.LNKTYPE),
            ]
        )
        destination = self.root / "source"
        inputs.extract_source(path, destination, 1234567890)
        self.assertEqual((destination / "src/link").read_bytes(), b"source")
        self.assertEqual((destination / "src/hard").read_bytes(), b"source")
        self.assertEqual((destination / "src/file").stat().st_mtime, 1234567890)

    def test_malicious_archive_is_rejected_before_any_extraction(self) -> None:
        cases = [
            [("../escape", b"bad", tarfile.REGTYPE)],
            [("/absolute", b"bad", tarfile.REGTYPE)],
            [("src/link", "../../outside", tarfile.SYMTYPE)],
            [("src/link", "/outside", tarfile.SYMTYPE)],
            [
                ("src/file", b"ok", tarfile.REGTYPE),
                ("src/file", b"overwrite", tarfile.REGTYPE),
            ],
            [
                ("src/link", "target", tarfile.SYMTYPE),
                ("src/link/child", b"write", tarfile.REGTYPE),
            ],
            [("fifo", "", tarfile.FIFOTYPE)],
        ]
        for members in cases:
            with self.subTest(members=members):
                destination = self.root / "unpacked"
                with self.assertRaises(inputs.Failure):
                    inputs.extract_source(self.archive(members), destination, 0)
                self.assertFalse(destination.exists())


class ELFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("cc")
        if compiler is None or os.uname().machine != "x86_64":
            raise unittest.SkipTest(
                "x86_64 C/assembler driver is needed for a real ELF fixture"
            )
        cls.temp = tempfile.TemporaryDirectory(prefix="runtime-elf-fixture-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.elf = cls.root / "fixture"
        assembly = '.global _start\n.text\n_start:\nmov $60, %rax\nxor %rdi, %rdi\nsyscall\n.section .digest_md5,"a",@progbits\n.zero 16\n'
        subprocess.run(
            [
                compiler,
                "-nostdlib",
                "-static-pie",
                "-Wl,--build-id=none",
                "-x",
                "assembler",
                "-o",
                str(cls.elf),
                "-",
            ],
            input=assembly,
            text=True,
            check=True,
            capture_output=True,
        )
        data = bytearray(cls.elf.read_bytes())
        data[8:11] = b"AI\x02"
        cls.elf.write_bytes(data)
        cls.original = bytes(data)

    def test_actual_static_pie_elf_is_parsed_and_executes(self) -> None:
        report = checks.elf_report(self.elf)
        self.assertEqual(report["sha256"], inputs.digest(self.elf))
        subprocess.run([str(self.elf)], check=True, timeout=10)

    def test_wrong_elf_header_magic_dynamic_interpreter_and_paths_fail(self) -> None:
        variants = []
        for offset, replacement in [
            (4, b"\x01"),
            (5, b"\x02"),
            (8, b"bad"),
            (16, struct.pack("<H", 2)),
            (18, struct.pack("<H", 183)),
        ]:
            data = bytearray(self.original)
            data[offset : offset + len(replacement)] = replacement
            variants.append(data)
        header = struct.unpack_from("<16sHHIQQQIHHHHHH", self.original)
        phoff, phsize, phnum = header[5], header[9], header[10]
        data = bytearray(self.original)
        struct.pack_into("<I", data, phoff, 3)
        variants.append(data)
        for index in range(phnum):
            position = phoff + index * phsize
            ptype, _, offset, _, _, _, _, _ = struct.unpack_from(
                "<IIQQQQQQ", self.original, position
            )
            if ptype == 2:
                data = bytearray(self.original)
                struct.pack_into("<qQ", data, offset, 1, 1)
                variants.append(data)
        variants.extend(
            [
                self.original[:60],
                self.original + b"GLIBC_2.34",
                self.original + b"/home/runner/build/source.c",
            ]
        )
        for index, data in enumerate(variants):
            with self.subTest(index=index):
                path = self.root / "invalid"
                path.write_bytes(data)
                with self.assertRaises(inputs.Failure):
                    checks.elf_report(path)

    def test_different_runtimes_fail_and_both_remain(self) -> None:
        second = self.root / "second"
        second.write_bytes(self.original)
        self.assertTrue(checks.compare_runtimes(self.elf, second)["byte_identical"])
        second.write_bytes(self.original + b"difference")
        with self.assertRaisesRegex(inputs.Failure, "Runtime mismatch"):
            checks.compare_runtimes(self.elf, second)
        self.assertEqual(self.elf.read_bytes(), self.original)
        self.assertTrue(second.read_bytes().endswith(b"difference"))
        with self.assertRaisesRegex(inputs.Failure, "independent"):
            checks.compare_runtimes(self.elf, self.elf)

    def test_packaged_prefix_allows_only_md5_field_update(self) -> None:
        image = self.root / "fixture.AppImage"
        data = bytearray(self.original)
        section = checks.elf_report(self.elf)["sections"][".digest_md5"]
        data[section["offset"] : section["offset"] + 16] = b"1" * 16
        image.write_bytes(data + b"squashfs-fixture")
        checks.check_appimage_prefix(self.elf, image)
        data[-1] ^= 1
        image.write_bytes(data + b"squashfs-fixture")
        with self.assertRaisesRegex(inputs.Failure, "newly built runtime"):
            checks.check_appimage_prefix(self.elf, image)


class MandatoryRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="runtime-launch-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.marker = self.root / "marker"
        self.env = {"PATH": "/usr/bin:/bin", "RUNTIME_TEST_MARKER": str(self.marker)}

    def test_real_stub_success_checks_all_arguments(self) -> None:
        app = self.root / "AppRun"
        app.write_text(checks.STUB)
        app.chmod(0o755)
        checks.required_run(
            [str(app), *checks.SMOKE_ARGUMENTS], self.root, self.marker, self.env
        )
        self.assertEqual(self.marker.read_bytes(), b"runtime-arguments-ok\n")
        with self.assertRaisesRegex(inputs.Failure, "Command failed"):
            checks.required_run([str(app), "wrong"], self.root, self.marker, self.env)

    def test_mandatory_launch_failure_cannot_be_pass(self) -> None:
        with self.assertRaisesRegex(inputs.Failure, "exit 7"):
            checks.required_run(
                ["/bin/sh", "-c", "exit 7"], self.root, self.marker, self.env
            )

    def test_successful_exit_without_marker_is_failure(self) -> None:
        self.marker.write_text("stale marker")
        with self.assertRaisesRegex(inputs.Failure, "expected argument marker"):
            checks.required_run(
                ["/bin/sh", "-c", "exit 0"], self.root, self.marker, self.env
            )

    def test_absent_failed_and_wrong_recipe_stages_block_bundle(self) -> None:
        recipe = "a" * 64
        for stage in pipeline.STAGES:
            pipeline.record_stage(
                self.root, stage, {"result": "PASS"}, {"sha256": recipe}
            )
        pipeline.required_stages(self.root, pipeline.STAGES, recipe)
        path = self.root / "reports/smoke.json"
        for content in (
            None,
            {"result": "NOT_RUN", "recipe_sha256": recipe},
            {"result": "FAIL", "recipe_sha256": recipe},
            {"result": "PASS", "recipe_sha256": "b" * 64},
        ):
            with self.subTest(content=content):
                if content is None:
                    path.unlink()
                else:
                    inputs.write_json(path, content)
                with self.assertRaisesRegex(inputs.Failure, "Mandatory stage"):
                    pipeline.required_stages(self.root, pipeline.STAGES, recipe)

    def test_cleanup_failure_does_not_hide_primary_build_failure(self) -> None:
        with (
            patch.object(pipeline.os, "getuid", return_value=1000),
            patch.object(
                pipeline,
                "run_logged",
                side_effect=inputs.Failure("original build failed"),
            ),
            patch.object(
                pipeline.subprocess, "run", side_effect=OSError("cleanup failed")
            ) as cleanup,
        ):
            with self.assertRaisesRegex(inputs.Failure, "original build failed"):
                pipeline.container_run(
                    "docker",
                    "fixture-image",
                    MODULE,
                    self.root,
                    self.root,
                    "/build-one",
                    ["compile"],
                    self.root / "build.log",
                    {},
                )
            cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
