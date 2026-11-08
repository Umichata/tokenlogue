"""Final-carrier path inspection with synthetic APKs and Python 3.12 bytecode."""

from __future__ import annotations

import gzip
import hashlib
import importlib
import importlib.util
import io
import json
import marshal
import re
import struct
import sys
import tempfile
import unittest
import warnings
import zlib
from pathlib import Path
from types import CodeType, SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "packaging/android"
sys.path.insert(0, str(SCRIPTS))
try:
    gate = importlib.import_module("build_paths")
finally:
    sys.path.pop(0)

PERSONAL = "/home/Synthetic Builder"
NEUTRAL = "/tmp/tokenlogue-compile/source/build/site-packages/example.py"


def zipped(files: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(buffer, "w") as archive:
            for name, data in files:
                archive.writestr(name, data)
    return buffer.getvalue()


def pyc(code: CodeType) -> bytes:
    return (
        importlib.util.MAGIC_NUMBER
        + struct.pack("<III", 0, 123, 77)
        + marshal.dumps(code)
    )


class AndroidBuildPathTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="tokenlogue-path-gate-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.apk = self.root / "synthetic.apk"
        self.report = self.root / "result.json"

    def verify(self, files: list[tuple[str, bytes]], **kwargs: object) -> dict:
        self.apk.write_bytes(zipped(files))
        return gate.verify_apk(
            self.apk, prefixes=[PERSONAL], report=self.report, **kwargs
        )

    def test_neutral_and_frozen_code_is_read_without_execution(self) -> None:
        code = compile("raise RuntimeError('must never execute')\n", NEUTRAL, "exec")
        frozen = compile("pass", "<frozen importlib._bootstrap>", "exec")
        result = self.verify(
            [
                ("assets/app.zip", zipped([("main.pyc", pyc(code))])),
                ("assets/stdlib.zip", zipped([("frozen.pyc", pyc(frozen))])),
                ("lib/arm64-v8a/libapp.so", b"\x7fELF\0/build/worker/generated.dart\0"),
            ]
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["pyc_files_read"], 2)
        self.assertFalse(result["application_code_executed"])
        self.assertFalse(result["secret_scanner_changed"])

    def test_nested_code_filename_blocks_even_with_a_neutral_top_level(self) -> None:
        code = compile(
            "def outer():\n    return lambda: 42\n", PERSONAL + "/module.py", "exec"
        )
        code = code.replace(co_filename=NEUTRAL)
        with self.assertRaisesRegex(ValueError, "builder-home"):
            self.verify(
                [("assets/sitepackages.zip", zipped([("example.pyc", pyc(code))]))]
            )
        result = json.loads(self.report.read_text())
        code_findings = [f for f in result["findings"] if f["kind"] == "co_filename"]
        self.assertEqual(len(code_findings), 2)
        self.assertTrue(
            all("sitepackages.zip!example.pyc" in f["member"] for f in code_findings)
        )
        self.assertNotIn(PERSONAL, self.report.read_text())

    def test_nested_code_constant_paths_are_not_hidden_by_marshal_framing(self) -> None:
        for constant in (PERSONAL, PERSONAL.encode()):
            with self.subTest(kind=type(constant).__name__):
                code = compile(
                    f"def outer():\n    return {constant!r}\n", NEUTRAL, "exec"
                )
                with self.assertRaises(ValueError):
                    self.verify(
                        [
                            (
                                "assets/sitepackages.zip",
                                zipped([("example.pyc", pyc(code))]),
                            )
                        ]
                    )
                findings = json.loads(self.report.read_text())["findings"]
                self.assertTrue(any(f["kind"].startswith("code-") for f in findings))
                self.assertFalse(any(f["kind"] == "co_filename" for f in findings))

    def test_native_unicode_spaces_uri_and_encoded_representations_block(self) -> None:
        prefix = "/home/Другой пользователь"
        uri = "file://" + prefix + "/generated.dart"
        values = [
            prefix + "/source.dart",
            uri,
            "FILE://LOCALHOST" + prefix + "/source.dart",
            quote(uri, safe="/:"),
            json.dumps(uri, ensure_ascii=True)[1:-1],
            uri.replace("/", "\\/"),
        ]
        for value in values:
            for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
                with self.subTest(value_kind=values.index(value), encoding=encoding):
                    self.apk.write_bytes(
                        zipped(
                            [
                                (
                                    "lib/arm64-v8a/libapp.so",
                                    b"\0\0" + value.encode(encoding) + b"\0\0",
                                )
                            ]
                        )
                    )
                    with self.assertRaises(ValueError):
                        gate.verify_apk(self.apk, prefixes=[prefix], report=self.report)
                    self.assertEqual(
                        json.loads(self.report.read_text())["status"], "FAIL"
                    )
                    self.assertNotIn(prefix, self.report.read_text())

    def test_similar_user_and_contained_relative_path_do_not_match(self) -> None:
        self.apk.write_bytes(
            zipped(
                [
                    (
                        "assets/data",
                        b"/home/annex/a\0/tmp/home/ann/a\0file:///home/anna/b\0",
                    )
                ]
            )
        )
        self.assertEqual(
            gate.verify_apk(self.apk, prefixes=["/home/ann"])["status"], "PASS"
        )

    def test_windows_path_and_escaped_metadata_are_inspected(self) -> None:
        prefix = "C:\\Users\\Synthetic Person"
        for value in (
            prefix + "\\module.py",
            "c:\\users\\synthetic person\\module.py",
            json.dumps(prefix + "\\module.py")[1:-1],
            "file:///C:/Users/Synthetic%20Person/module.py",
        ):
            self.apk.write_bytes(
                zipped([("lib/example.so", b"\0" + value.encode() + b"\0")])
            )
            with self.assertRaises(ValueError):
                gate.verify_apk(self.apk, prefixes=[prefix])

    def test_mixed_escape_hex_case_and_encoded_slashes_are_detected(self) -> None:
        prefix = "/home/Юзер"
        uri = quote("file://" + prefix + "/entry.dart", safe="/:")
        mixed = re.sub(
            r"%([0-9A-F])([0-9A-F])",
            lambda match: "%" + match[1].upper() + match[2].lower(),
            uri,
        )
        escaped = json.dumps(prefix + "/entry.dart", ensure_ascii=True)[1:-1]
        escaped = re.sub(
            r"\\u([0-9a-f]{4})", lambda match: "\\u" + match[1].upper(), escaped
        )
        full_escaped = (
            "".join("\\u" + character.encode("utf-16-be").hex() for character in prefix)
            + "\\u002fentry.dart"
        )
        for value in (mixed, escaped, full_escaped):
            with self.subTest(
                representation=(mixed, escaped, full_escaped).index(value)
            ):
                self.apk.write_bytes(
                    zipped([("lib/example.so", b"\0" + value.encode() + b"\0")])
                )
                with self.assertRaises(ValueError):
                    gate.verify_apk(self.apk, prefixes=[prefix], report=self.report)
                self.assertNotIn(prefix, self.report.read_text())

    def test_encoded_nearby_home_and_posix_case_do_not_match(self) -> None:
        for value in (
            "/home/ann other/a",
            "\\u002fhome\\u002fann\\u0061/a",
            "/HOME/ANN/a",
        ):
            self.apk.write_bytes(
                zipped([("assets/data", b"\0" + value.encode() + b"\0")])
            )
            self.assertEqual(
                gate.verify_apk(self.apk, prefixes=["/home/ann"])["status"], "PASS"
            )

    def test_native_aot_uri_is_not_hidden_by_binary_string_metadata(self) -> None:
        uri = quote("file://" + PERSONAL + "/generated.dart", safe="/:").encode()
        for metadata in (b"%", b"/", b":", b"A"):
            with (
                self.subTest(metadata_kind=metadata.hex()),
                self.assertRaises(ValueError),
            ):
                self.verify(
                    [("lib/arm64-v8a/libapp.so", b"\x7fELF" + metadata + uri + b"\0")]
                )

    def test_unknown_magic_flags_malformed_marshal_and_trailing_data_fail_closed(
        self,
    ) -> None:
        valid = pyc(compile("pass", NEUTRAL, "exec"))
        invalid = [
            b"not a pyc",
            b"????" + valid[4:],
            valid[:4] + struct.pack("<I", 4) + valid[8:],
            valid[:16] + b"not marshal",
            valid + b"trailing",
            valid[:16] + marshal.dumps(42),
        ]
        for data in invalid:
            with self.subTest(kind=invalid.index(data)):
                with self.assertRaises(ValueError):
                    self.verify(
                        [("assets/sitepackages.zip", zipped([("module.pyc", data)]))]
                    )
                self.assertEqual(json.loads(self.report.read_text())["status"], "FAIL")

    def test_wrong_interpreter_does_not_claim_pyc_absence(self) -> None:
        self.apk.write_bytes(
            zipped([("main.pyc", pyc(compile("pass", NEUTRAL, "exec")))])
        )
        with (
            patch.object(gate.sys, "version_info", (3, 13)),
            self.assertRaisesRegex(ValueError, "Python 3.12"),
        ):
            gate.verify_apk(self.apk, prefixes=[PERSONAL])

    def test_broken_nested_archive_and_duplicate_members_fail_closed(self) -> None:
        for nested in (
            b"broken zip",
            zipped([("same", b"first"), ("same", b"second")]),
        ):
            with self.subTest(archive_size=len(nested)), self.assertRaises(ValueError):
                self.verify([("assets/app.zip", nested)])

    def test_flutter_notices_compression_is_read_and_invalid_stream_fails(self) -> None:
        for compress in (gzip.compress, zlib.compress):
            with self.subTest(compression=compress.__module__):
                with self.assertRaisesRegex(ValueError, "builder-home"):
                    self.verify(
                        [
                            (
                                "assets/flutter_assets/NOTICES.Z",
                                compress((PERSONAL + "/input").encode()),
                            )
                        ]
                    )
        with self.assertRaisesRegex(ValueError, "compressed"):
            self.verify([("assets/flutter_assets/NOTICES.Z", b"broken compression")])

    def test_public_fixture_origin_is_pinned_and_is_not_a_secret_classification(
        self,
    ) -> None:
        member = "APK!assets/upstream-example.txt"
        content = b"Synthetic public upstream example /Users/example/input\n"
        origin = {
            member: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "source_url": "https://example.invalid/public-fixture.txt?note="
                + quote(PERSONAL + "/input"),
            }
        }
        result = self.verify(
            [("assets/upstream-example.txt", content)], public_fixtures=origin
        )
        self.assertEqual(result["status"], "PASS")
        self.assertNotIn(PERSONAL, self.report.read_text())
        self.assertNotIn(quote(PERSONAL), self.report.read_text())
        self.assertEqual(
            result["pinned_public_fixtures"][0]["sha256"], origin[member]["sha256"]
        )
        with self.assertRaisesRegex(ValueError, "pinned origin"):
            self.verify(
                [("assets/upstream-example.txt", content + b"changed")],
                public_fixtures=origin,
            )

    def test_fixture_origin_does_not_waive_a_real_builder_prefix(self) -> None:
        member = "APK!assets/upstream-example.txt"
        content = (PERSONAL + "/example\n").encode()
        origin = {
            member: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "source_url": "https://example.invalid/public-fixture.txt",
            }
        }
        with self.assertRaises(ValueError):
            self.verify(
                [("assets/upstream-example.txt", content)], public_fixtures=origin
            )
        findings = json.loads(self.report.read_text())["findings"]
        self.assertEqual(findings[0]["origin"], "pinned-public-upstream-fixture")
        self.assertIn("not a claim of user secrets", findings[0]["classification"])

    def test_missing_prefix_and_resource_overflow_are_not_success(self) -> None:
        self.apk.write_bytes(zipped([("assets/data", b"neutral")]))
        with self.assertRaises(ValueError):
            gate.verify_apk(self.apk, prefixes=[])
        with (
            patch.object(gate, "MAX_FILE", 8),
            self.assertRaisesRegex(ValueError, "limit"),
        ):
            gate.verify_apk(self.apk, prefixes=[PERSONAL])

    def test_original_account_home_survives_a_neutral_session_home(self) -> None:
        with patch.object(
            gate.pwd, "getpwuid", return_value=SimpleNamespace(pw_dir=PERSONAL)
        ):
            prefixes = gate.personal_prefixes(
                {
                    "HOME": "/tmp/tokenlogue-build/home",
                    "USERPROFILE": "C:\\Users\\Другой пользователь",
                }
            )
        self.assertIn(PERSONAL, prefixes)
        self.assertIn("C:\\Users\\Другой пользователь", prefixes)
        self.assertNotIn("/tmp/tokenlogue-build/home", prefixes)


if __name__ == "__main__":
    unittest.main()
