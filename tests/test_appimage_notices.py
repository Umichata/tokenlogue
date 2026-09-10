"""Поведенческие проверки происхождения бинарников и полноты notices."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "packaging/linux/appimage"
sys.path.insert(0, str(SCRIPTS))

import notice_inputs  # noqa: E402  # pyright: ignore[reportMissingImports]
import notices  # noqa: E402  # pyright: ignore[reportMissingImports]


def minimal_elf(code: bytes = b"CODE", rodata: bytes = b"DATA") -> bytes:
    names = b"\0.text\0.rodata\0.shstrtab\0"
    header = bytearray(64)
    header[:6] = b"\x7fELF\x02\x01"
    body = code + rodata + names
    struct.pack_into("<Q", header, 40, len(header) + len(body))
    struct.pack_into("<HHH", header, 58, 64, 4, 3)
    sections = bytes(64)
    for name, start, size in [
        (1, 64, len(code)),
        (7, 64 + len(code), len(rodata)),
        (15, 64 + len(code) + len(rodata), len(names)),
    ]:
        sections += struct.pack("<IIQQQQIIQQ", name, 1, 0, 0, start, size, 0, 0, 0, 0)
    return bytes(header) + body + sections


class NoticeInputsTests(unittest.TestCase):
    def test_elf_header_edit_preserves_identity_but_changed_code_does_not(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            a.write_bytes(minimal_elf())
            changed = bytearray(a.read_bytes())
            changed[24] = 1
            b.write_bytes(changed)
            notice_inputs.same_binary(a, b)
            b.write_bytes(minimal_elf(code=b"EVIL"))
            with self.assertRaisesRegex(
                notice_inputs.NoticeError, "provenance mismatch"
            ):
                notice_inputs.same_binary(a, b)

    def test_provenance_mismatch_reports_sections_and_hashes_without_paths(self):
        with tempfile.TemporaryDirectory() as td:
            actual, reference = Path(td) / "actual.so", Path(td) / "reference.so"
            actual.write_bytes(minimal_elf(code=b"NEW!"))
            reference.write_bytes(minimal_elf())
            with self.assertRaises(notice_inputs.NoticeError) as caught:
                notice_inputs.same_binary(actual, reference)
            message = str(caught.exception)
            self.assertIn("binary provenance mismatch: actual.so;", message)
            self.assertIn("differing_sections=.text;", message)
            self.assertIn(f"actual_sha256={notice_inputs.sha256(actual)}", message)
            self.assertIn(
                f"reference_sha256={notice_inputs.sha256(reference)}", message
            )
            self.assertNotIn(td, message)

    def test_changed_constants_are_rejected_even_when_code_matches(self):
        with tempfile.TemporaryDirectory() as td:
            actual, reference = Path(td) / "actual.so", Path(td) / "reference.so"
            actual.write_bytes(minimal_elf(rodata=b"NEW!"))
            reference.write_bytes(minimal_elf())
            with self.assertRaisesRegex(
                notice_inputs.NoticeError, "differing_sections=.rodata;"
            ):
                notice_inputs.same_binary(actual, reference)

    def test_truncated_elf_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "file"
            path.write_bytes(minimal_elf()[:-20])
            with self.assertRaises(notice_inputs.NoticeError):
                notice_inputs.elf_fingerprint(path)

    def test_notice_paths_reject_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "license").write_text("text")
            (root / "alias").symlink_to("license")
            for name in ("../license", "/license", "alias", "a\\license"):
                with (
                    self.subTest(name=name),
                    self.assertRaises(notice_inputs.NoticeError),
                ):
                    notice_inputs.relative_file(root, name)

    def test_corrupt_cache_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            digest = hashlib.sha256(b"correct").hexdigest()
            (root / digest).write_bytes(b"wrong")
            with patch.object(notice_inputs, "urlopen") as request:
                with self.assertRaisesRegex(notice_inputs.NoticeError, "corrupt"):
                    notice_inputs.fetch_asset(
                        {
                            "url": "https://example.com/source",
                            "sha256": digest,
                            "bytes": 7,
                        },
                        root,
                    )
                request.assert_not_called()

    def test_vendor_text_checksum_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "license").write_text("wrong")
            (root / "notices.lock.json").write_text(
                json.dumps(
                    {"schema": 1, "texts": [{"path": "license", "sha256": "0" * 64}]}
                )
            )
            with self.assertRaisesRegex(notice_inputs.NoticeError, "checksum"):
                notice_inputs.load_lock(root)

    @unittest.skipUnless(shutil.which("zstd"), "zstd required")
    def test_python_tar_does_not_follow_selected_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode="w") as archive:
                entry = tarfile.TarInfo("python/licenses/LICENSE.bad.txt")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "/etc/passwd"
                archive.addfile(entry)
            compressed = subprocess.run(
                ["zstd", "-q", "-c"],
                input=data.getvalue(),
                capture_output=True,
                check=True,
            ).stdout
            (root / "archive").write_bytes(compressed)
            with self.assertRaisesRegex(
                notice_inputs.NoticeError, "unexpected Python archive member"
            ):
                notice_inputs.extract_python(root / "archive", root / "out")
            self.assertFalse((root / "out/python/licenses/LICENSE.bad.txt").exists())

    def test_font_unicode_and_reserved_name_are_preserved(self):
        fields = [(0, "Автор © 2026"), (13, "Reserved Font Name Пример")]
        strings = b""
        records = b""
        for name, text in fields:
            raw = text.encode("utf-16-be")
            records += struct.pack(">HHHHHH", 3, 1, 0x409, name, len(raw), len(strings))
            strings += raw
        table = (
            struct.pack(">HHH", 0, len(fields), 6 + len(records)) + records + strings
        )
        font = (
            struct.pack(">IHHHH", 0x10000, 1, 0, 0, 0)
            + struct.pack(">4sIII", b"name", 0, 28, len(table))
            + table
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "font.ttf"
            path.write_bytes(font)
            result = notice_inputs.font_names(path)
            self.assertEqual(result["0"], [fields[0][1]])
            self.assertEqual(result["13"], [fields[1][1]])

    def test_native_lookup_rejects_different_host_binary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app, host = root / "libtest.so", root / "host.so"
            app.write_bytes(minimal_elf())
            host.write_bytes(minimal_elf(code=b"NEW!"))
            with patch.object(
                notices, "run", return_value=f"libtest.so (libc6) => {host}\n"
            ):
                with self.assertRaisesRegex(
                    notice_inputs.NoticeError, "no matching installed Debian"
                ):
                    notices.native_origin(app)


class NoticeManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "app").write_bytes(minimal_elf())
        (self.root / "LICENSE").write_text("Copyright fixture, preserved in notice.\n")
        self.manifest = {
            "schema": 1,
            "result": "PASS",
            "source_materials": "REVIEW_REQUIRED",
            "subjects": ["app"],
            "components": [{"id": "fixture", "files": ["app"], "notices": ["LICENSE"]}],
            "files": {
                name: notice_inputs.sha256(self.root / name)
                for name in ["app", "LICENSE"]
            },
        }
        self.save()

    def save(self):
        notices.write_json(self.root / notices.MANIFEST, self.manifest)

    def test_valid_manifest_preserves_separate_source_review(self):
        result = notices.verify(self.root)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["source_materials"], "REVIEW_REQUIRED")

    def test_removed_license_fails(self):
        (self.root / "LICENSE").unlink()
        with self.assertRaisesRegex(notice_inputs.NoticeError, "missing regular file"):
            notices.verify(self.root)

    def test_modified_license_fails(self):
        (self.root / "LICENSE").write_text("changed")
        with self.assertRaisesRegex(notice_inputs.NoticeError, "checksum changed"):
            notices.verify(self.root)

    def test_new_elf_without_notice_fails(self):
        (self.root / "unknown.so").write_bytes(minimal_elf())
        with self.assertRaisesRegex(notice_inputs.NoticeError, "component set differs"):
            notices.verify(self.root)

    def test_removed_notice_association_fails(self):
        self.manifest["components"][0]["notices"] = []
        self.save()
        with self.assertRaisesRegex(notice_inputs.NoticeError, "no license references"):
            notices.verify(self.root)

    def test_unhashed_notice_reference_fails(self):
        del self.manifest["files"]["LICENSE"]
        self.save()
        with self.assertRaisesRegex(notice_inputs.NoticeError, "unhashed"):
            notices.verify(self.root)

    def test_new_python_distribution_fails(self):
        info = self.root / "unknown.dist-info"
        info.mkdir()
        (info / "METADATA").write_text("Name: unknown\nVersion: 1\n")
        with self.assertRaisesRegex(notice_inputs.NoticeError, "component set differs"):
            notices.verify(self.root)

    def test_python_package_without_license_fails_collection(self):
        info = self.root / notices.BUNDLE / "site-packages/missing-1.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text("Name: missing\nVersion: 1\n")
        collector = notices.Collector(self.root, {})
        with self.assertRaisesRegex(
            notice_inputs.NoticeError, "distribution notice missing"
        ):
            collector.collect_packages("LICENSE")

    def test_appdir_and_extracted_image_have_required_workflow_gates(self):
        text = (ROOT / ".github/workflows/build-linux.yml").read_text()
        self.assertIn('--appdir "$appdir"', text)
        self.assertIn('--appdir "$extracted"', text)
        self.assertIn("notices-appdir.json", text)
        self.assertIn("notices-appimage.json", text)
        script = (SCRIPTS / "build_appimage.sh").read_text()
        final_scan = script.index('"$script_dir/sanitize_paths.py" --check-only')
        self.assertLess(script.index('"$script_dir/notices.py" collect'), final_scan)
        self.assertLess(
            final_scan, script.index('"$appimagetool" --appimage-extract-and-run')
        )
        self.assertNotIn("rg -", script)
        self.assertLess(
            script.index('"$script_dir/notices.py" collect'),
            script.index('"$appimagetool" --appimage-extract-and-run'),
        )


class PubspecNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="notice workspace Пример ")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.path = str(self.workspace / "build/flutter-packages/flet_secure_storage")

    def lock(self, path: str | None = None, relative: str = "false") -> bytes:
        return (
            "# Generated by pub; copyright fixture ©\npackages:\n"
            "  flet_secure_storage:\n"
            '    dependency: "direct main"\n'
            "    description:\n"
            f"      path: {json.dumps(self.path if path is None else path)}\n"
            f"      relative: {relative}\n"
            "    source: path\n"
            '    version: "0.1.0"\n'
            "  serious_python_linux:\n"
            "    dependency: transitive\n"
            "    description:\n"
            "      name: serious_python_linux\n"
            f'      sha256: "{"a" * 64}"\n'
            '      url: "https://pub.dev"\n'
            "    source: hosted\n"
            '    version: "4.7.0"\n'
            "sdks:\n"
            '  dart: ">=3.11.0 <4.0.0"\n'
        ).encode()

    def test_audit_copy_preserves_all_but_known_local_path_and_flag(self):
        data = self.lock()
        result, origin = notice_inputs.pubspec_audit_copy(data, self.workspace)
        expected = (
            data.decode()
            .replace(json.dumps(self.path), '"../flutter-packages/flet_secure_storage"')
            .replace("relative: false", "relative: true")
        )
        self.assertEqual(result.split("\n", 2)[2], expected)
        self.assertIn("# Audit copy:", result)
        self.assertNotIn(str(self.workspace), result)
        self.assertNotIn("build/flutter", result)
        self.assertEqual(
            origin["resolved_packages_source_sha256"], hashlib.sha256(data).hexdigest()
        )
        self.assertEqual(
            notice_inputs.pubspec_audit_copy(data, self.workspace), (result, origin)
        )

    def test_already_relative_path_is_preserved(self):
        data = self.lock("../flutter-packages/flet_secure_storage", "true")
        result, _ = notice_inputs.pubspec_audit_copy(data, self.workspace)
        self.assertEqual(result.split("\n", 2)[2].encode(), data)

    def test_unknown_paths_and_inconsistent_flags_are_rejected(self):
        for path, relative in (
            (self.path + "/different", "false"),
            (str(self.workspace / "other/flet_secure_storage"), "false"),
            (self.path, "true"),
            ("../flutter-packages/flet_secure_storage", "false"),
            ("../../outside", "true"),
        ):
            with self.subTest(path=path, relative=relative):
                with self.assertRaisesRegex(
                    notice_inputs.NoticeError, "unexpected flet_secure_storage path"
                ):
                    notice_inputs.pubspec_audit_copy(
                        self.lock(path, relative), self.workspace
                    )

    def test_unexpected_lock_layouts_and_extra_local_dependencies_fail(self):
        raw = self.lock()
        for data in (
            raw.replace(b"      relative: false\n", b""),
            raw.replace(b"  serious_python_linux:", b"  unknown:"),
            raw.replace(b"    source: hosted", b"    source: path"),
            raw.replace(b"  flet_secure_storage:", b"  another_local_package:"),
            raw + raw,
        ):
            with self.subTest(data=data), self.assertRaises(notice_inputs.NoticeError):
                notice_inputs.pubspec_audit_copy(data, self.workspace)

    def test_collector_hashes_transformed_copy_without_modifying_source(self):
        source = self.workspace / "build/flutter/pubspec.lock"
        source.parent.mkdir(parents=True)
        original = self.lock()
        source.write_bytes(original)
        appdir = self.workspace / "Tokenlogue.AppDir"
        appdir.mkdir()
        (appdir / "LICENSE").write_text("Copyright fixture preserved without edits.\n")
        for name in [
            "tokenlogue",
            *["lib/" + n for n in notices.FLUTTER_LIBS],
            "lib/libdart_bridge.so",
        ]:
            path = appdir / notices.BUNDLE / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(minimal_elf())
        flutter = appdir / notices.BUNDLE / "data/flutter_assets/NOTICES.Z"
        flutter.parent.mkdir(parents=True)
        flutter.write_bytes(gzip.compress(b"serious_python flutter license fixture"))
        runtime = self.workspace / "runtime"
        runtime.write_bytes(b"fixture runtime")
        lock = notice_inputs.load_lock(SCRIPTS)
        lock["runtime"]["sha256"] = notice_inputs.sha256(runtime)
        cache = self.workspace / "cache"
        cache.mkdir()
        lock["bridge"]["sha256"] = hashlib.sha256(minimal_elf()).hexdigest()
        (cache / lock["bridge"]["sha256"]).write_bytes(minimal_elf())
        collector = notices.Collector(appdir, lock)
        # External package inventories are separate tested collectors. Here the
        # real final manifest covers every ELF in this small staging fixture.
        with (
            patch.object(collector, "collect_native"),
            patch.object(collector, "collect_python"),
            patch.object(collector, "collect_packages"),
            patch.object(collector, "collect_fonts"),
        ):
            collector.collect(cache, runtime, source)
        self.assertEqual(source.read_bytes(), original)
        manifest = json.loads((appdir / notices.MANIFEST).read_text())
        origin = next(
            c["origin"]
            for c in manifest["components"]
            if c["id"] == "flutter-and-plugins"
        )
        embedded = appdir / origin["resolved_packages"]
        self.assertIn("relative: true", embedded.read_text())
        self.assertEqual(
            manifest["files"][origin["resolved_packages"]],
            notice_inputs.sha256(embedded),
        )
        self.assertEqual(
            origin["resolved_packages_source_sha256"],
            hashlib.sha256(original).hexdigest(),
        )
        self.assertEqual(notices.verify(appdir)["result"], "PASS")
        embedded.write_bytes(original)
        with self.assertRaisesRegex(notice_inputs.NoticeError, "checksum changed"):
            notices.verify(appdir)


if __name__ == "__main__":
    unittest.main()
