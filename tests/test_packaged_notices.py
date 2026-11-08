"""Regression checks for platform-specific delivery of original notice bytes."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging/notices"))

import notice_bundle  # noqa: E402  # pyright: ignore[reportMissingImports]


class PackagedNoticesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.inputs = self.root / "packaging/notices"
        (self.inputs / "inputs").mkdir(parents=True)
        shutil.copyfile(
            ROOT / "packaging/notices/notice_bundle.py",
            self.inputs / "notice_bundle.py",
        )
        self.texts = {
            "runtime.txt": b"Original runtime notice\r\nCopyright 2026\r\n",
            "font.txt": "Original font notice\nCopyright © 2019\n".encode(),
            "bridge.txt": b"Original bridge notice\n",
            "katex.txt": b"Original KaTeX notice\n",
        }
        self.registry = {
            "schema": 1,
            "platform_notes": {
                platform: {
                    "en": "Supplemental notices.",
                    "ru": "Дополнительные уведомления.",
                }
                for platform in ("android", "linux")
            },
            "components": [],
        }
        for identity, name, platforms in (
            ("libffi-runtime", "runtime.txt", ["android"]),
            ("material-icons", "font.txt", ["android", "linux"]),
            ("dart-bridge", "bridge.txt", ["android"]),
            ("katex-fonts", "katex.txt", ["android"]),
        ):
            data = self.texts[name]
            (self.inputs / "inputs" / name).write_bytes(data)
            self.registry["components"].append(
                {
                    "id": identity,
                    "version": "1.0",
                    "platforms": platforms,
                    "source": {"url": "https://example.invalid/exact-1.0.tar.gz"},
                    "files": [
                        {
                            "input": "inputs/" + name,
                            "output": "licenses/" + name,
                            "size": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    ],
                    "notes": {
                        platform: {"en": "Original text.", "ru": "Оригинальный текст."}
                        for platform in platforms
                    },
                }
            )
        self.save_registry()
        self.destination = Path(self.temporary.name) / "stage"

    def save_registry(self):
        (self.inputs / "sources.json").write_text(
            json.dumps(self.registry, ensure_ascii=False), encoding="utf-8"
        )

    def test_checked_in_registry_binds_original_notices_to_correct_platforms(self):
        android = notice_bundle.bundle_files(ROOT, "android")
        linux = notice_bundle.bundle_files(ROOT, "linux")
        android_manifest = json.loads(android["manifest.json"])
        linux_manifest = json.loads(linux["manifest.json"])
        components = {
            component["id"]: component for component in android_manifest["components"]
        }
        self.assertEqual(
            set(components),
            {"libffi-runtime", "dart-bridge", "katex-fonts", "material-icons"},
        )
        self.assertEqual(
            [component["id"] for component in linux_manifest["components"]],
            ["material-icons"],
        )
        expected = {
            "libffi-runtime": (
                "3.4.4",
                "2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388",
            ),
            "dart-bridge": (
                "1.10.0",
                "b7150f41f2912b5289ad687eb160b3f3b3e4f55cad82e98069b4d97c895aae83",
            ),
            "material-icons": (
                "3012db47f3130e62f7cc0beabff968a33cbec8d8",
                "be698262aecd042c0de6f886cc0af622f8def446462026992cc530275d8a9e74",
            ),
        }
        for identity, (version, digest) in expected.items():
            with self.subTest(component=identity):
                self.assertEqual(components[identity]["version"], version)
                self.assertIn(
                    digest,
                    {
                        hashlib.sha256(android[path]).hexdigest()
                        for path in components[identity]["notice_paths"]
                    },
                )
        for identity, digest in {
            "libffi-runtime": "d66c56ad259a82cf2a9dfc408b32bf5da52371500b84745f7fb8b645712df676",
            "dart-bridge": "a261849049b8710511a0bf264c4aad17acd2a94782c9563d59a636b520b5d7eb",
            "katex-fonts": "6d5f2f1aa57ae539ffb0a04bb39d2da67af74601d685a161aff7ce5bda5fa407",
            "material-icons": "e56fa8e9bb4589fde964be3de451f3e5b251e4a1eafb1dc98d94add034dd5a86",
        }.items():
            with self.subTest(source=identity):
                self.assertIn(digest, json.dumps(components[identity]["source"]))
        self.assertIn(
            "f6cf0d43333470fb4e91aa7b887e5b0bec4f4486",
            json.dumps(components["dart-bridge"]["source"]),
        )
        katex_texts = b"\n".join(
            android[path] for path in components["katex-fonts"]["notice_paths"]
        )
        self.assertIn(b"SIL OPEN FONT LICENSE Version 1.1", katex_texts)
        self.assertIn(b'THE FONT SOFTWARE IS PROVIDED "AS IS"', katex_texts)
        self.assertIn(b"Copyright (c) 2009-2010", katex_texts)
        self.assertIn(b"Copyright (c) 2014-2018 Khan Academy", katex_texts)
        for platform, files, manifest in (
            ("android", android, android_manifest),
            ("linux", linux, linux_manifest),
        ):
            material = next(
                component
                for component in manifest["components"]
                if component["id"] == "material-icons"
            )
            with self.subTest(platform=platform):
                self.assertIn(
                    b"Copyright 2019 Google LLC. All Rights Reserved.",
                    b"\n".join(files[path] for path in material["notice_paths"]),
                )

    def test_platform_bundle_preserves_complete_original_bytes_and_source_mapping(self):
        manifest = notice_bundle.stage_notices(self.root, "android", self.destination)
        for name, original in self.texts.items():
            self.assertEqual(
                (self.destination / "licenses" / name).read_bytes(), original
            )
        self.assertEqual(
            [component["id"] for component in manifest["components"]],
            ["libffi-runtime", "material-icons", "dart-bridge", "katex-fonts"],
        )
        self.assertEqual(
            manifest["components"][0]["source"],
            self.registry["components"][0]["source"],
        )
        self.assertEqual(
            notice_bundle.verify_notices(self.root, "android", self.destination),
            manifest,
        )
        readme = (self.destination / "README.md").read_text()
        for title, anchor in (("English", "english"), ("Русский", "russian")):
            self.assertEqual(readme.count(f"[{title}](#{anchor})"), 1)
            self.assertIn(f'<a id="{anchor}"></a>', readme)
            self.assertIn(f"## {title}", readme)
        self.assertNotIn("manifest.json", [row["path"] for row in manifest["files"]])

    def test_linux_uses_only_its_platform_inputs(self):
        (self.inputs / "inputs/runtime.txt").unlink()
        paths = notice_bundle.required_inputs(self.root, "linux")
        self.assertIn("packaging/notices/notice_bundle.py", paths)
        self.assertIn("packaging/notices/sources.json", paths)
        self.assertNotIn("packaging/notices/inputs/runtime.txt", paths)
        files = notice_bundle.bundle_files(self.root, "linux")
        self.assertEqual(files["licenses/font.txt"], self.texts["font.txt"])
        self.assertNotIn("licenses/runtime.txt", files)

    def test_missing_or_changed_required_input_fails_before_creating_output(self):
        path = self.inputs / "inputs/runtime.txt"
        for replacement in (None, b"Changed notice\r\n"):
            with self.subTest(replacement=replacement):
                if replacement is None:
                    path.unlink()
                else:
                    path.write_bytes(replacement)
                with self.assertRaises(notice_bundle.NoticeError):
                    notice_bundle.stage_notices(self.root, "android", self.destination)
                self.assertFalse(self.destination.exists())

    def test_missing_or_wrong_platform_mandatory_component_fails_before_output(self):
        mandatory = self.registry["components"].pop()
        self.save_registry()
        with self.assertRaisesRegex(
            notice_bundle.NoticeError, "required notice components.*missing katex-fonts"
        ):
            notice_bundle.stage_notices(self.root, "android", self.destination)
        self.assertFalse(self.destination.exists())
        mandatory["platforms"] = ["linux"]
        self.registry["components"].append(mandatory)
        self.save_registry()
        with self.assertRaisesRegex(
            notice_bundle.NoticeError, "required notice components.*missing katex-fonts"
        ):
            notice_bundle.stage_notices(self.root, "android", self.destination)
        self.assertFalse(self.destination.exists())

    def test_repeated_stage_keeps_bytes_and_mtimes_without_duplicate_notices(self):
        first = notice_bundle.stage_notices(self.root, "android", self.destination)
        before = {
            path.relative_to(self.destination).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in self.destination.rglob("*")
            if path.is_file()
        }
        second = notice_bundle.stage_notices(self.root, "android", self.destination)
        after = {
            path.relative_to(self.destination).as_posix(): (
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in self.destination.rglob("*")
            if path.is_file()
        }
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_changed_missing_or_unexpected_output_cannot_verify(self):
        notice_bundle.stage_notices(self.root, "android", self.destination)
        path = self.destination / "licenses/runtime.txt"
        for change in ("changed", "missing", "unexpected"):
            with self.subTest(change=change):
                path.write_bytes(self.texts["runtime.txt"])
                if change == "changed":
                    path.write_bytes(b"Truncated")
                elif change == "missing":
                    path.unlink()
                else:
                    (self.destination / "unexpected.txt").write_bytes(b"unknown")
                with self.assertRaises(notice_bundle.NoticeError):
                    notice_bundle.verify_notices(self.root, "android", self.destination)
        with self.assertRaises(notice_bundle.NoticeError):
            notice_bundle.stage_notices(self.root, "android", self.destination)

    def test_unsafe_repeated_or_symlink_inputs_fail_before_writing(self):
        record = self.registry["components"][0]["files"][0]
        for name in (
            "../runtime.txt",
            "/runtime.txt",
            "inputs/../runtime.txt",
            "inputs\\runtime.txt",
        ):
            with self.subTest(name=name):
                record["input"] = name
                self.save_registry()
                with self.assertRaises(notice_bundle.NoticeError):
                    notice_bundle.stage_notices(self.root, "android", self.destination)
                self.assertFalse(self.destination.exists())
        record["input"] = "inputs/runtime.txt"
        for name in ("../runtime.txt", "/runtime.txt", "licenses/../runtime.txt"):
            with self.subTest(output=name):
                record["output"] = name
                self.save_registry()
                with self.assertRaises(notice_bundle.NoticeError):
                    notice_bundle.stage_notices(self.root, "android", self.destination)
                self.assertFalse(self.destination.exists())
        record["output"] = "licenses/runtime.txt"
        self.registry["components"][0]["files"].append(dict(record))
        self.save_registry()
        with self.assertRaises(notice_bundle.NoticeError):
            notice_bundle.stage_notices(self.root, "android", self.destination)
        self.registry["components"][0]["files"].pop()
        font_record = self.registry["components"][1]["files"][0]
        font_record["output"] = "licenses/runtime.txt/nested.txt"
        self.save_registry()
        with self.assertRaisesRegex(notice_bundle.NoticeError, "conflicting"):
            notice_bundle.stage_notices(self.root, "android", self.destination)
        self.assertFalse(self.destination.exists())
        font_record["output"] = "licenses/font.txt"
        self.save_registry()
        original = self.inputs / "inputs/runtime.txt"
        original.unlink()
        original.symlink_to(self.inputs / "inputs/font.txt")
        with self.assertRaisesRegex(notice_bundle.NoticeError, "symlink"):
            notice_bundle.stage_notices(self.root, "android", self.destination)
        self.assertFalse(self.destination.exists())

    def test_symlink_or_changed_destination_is_rejected_without_overwriting(self):
        notice_bundle.stage_notices(self.root, "android", self.destination)
        path = self.destination / "licenses/runtime.txt"
        path.write_bytes(b"Do not replace me")
        with self.assertRaises(notice_bundle.NoticeError):
            notice_bundle.stage_notices(self.root, "android", self.destination)
        self.assertEqual(path.read_bytes(), b"Do not replace me")
        path.unlink()
        path.symlink_to(self.inputs / "inputs/runtime.txt")
        with self.assertRaisesRegex(notice_bundle.NoticeError, "symlink"):
            notice_bundle.verify_notices(self.root, "android", self.destination)


if __name__ == "__main__":
    unittest.main()
