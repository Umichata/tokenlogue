from __future__ import annotations

import copy
import hashlib
import io
import json
import runpy
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = runpy.run_path(str(ROOT / "packaging/native_wheels/verify.py"))


class NativeWheelVerificationTests(unittest.TestCase):
    def test_both_platform_inputs_have_authenticated_component_and_license_inventory(
        self,
    ):
        for platform in ("android", "linux"):
            with self.subTest(platform=platform):
                receipt = NATIVE["verify_inputs"](ROOT, platform)
                self.assertEqual(receipt["status"], "PASS")
                self.assertIn("cffi", {row["package"] for row in receipt["wheels"]})
                lock = NATIVE["load_lock"](ROOT)
                cffi = next(
                    row
                    for row in lock["wheels"]
                    if row["platform"] == platform and row["package"] == "cffi"
                )
                notice = next(
                    member
                    for member in cffi["metadata_members"]
                    if member["path"].endswith("/licenses/libffi/LICENSE")
                )
                self.assertEqual(notice["sha256"], lock["libffi"]["license_sha256"])

    def test_missing_or_modified_input_fails_before_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in NATIVE["required_inputs"](ROOT, "android"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            lock = NATIVE["load_lock"](root)
            wheel = next(row for row in lock["wheels"] if row["platform"] == "android")
            target = root / wheel["path"]
            original = target.read_bytes()
            target.write_bytes(original + b"changed")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                NATIVE["verify_inputs"](root, "android")
            target.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                NATIVE["verify_inputs"](root, "android")

    def test_record_rejects_modified_member_even_with_a_new_outer_container_hash(self):
        lock = NATIVE["load_lock"](ROOT)
        row = next(row for row in lock["wheels"] if row["package"] == "msgpack")
        with zipfile.ZipFile(ROOT / row["path"]) as archive:
            files = NATIVE["zip_files"](archive)
        native = row["native_members"][0]["path"]
        files[native] += b"changed"
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, contents in files.items():
                archive.writestr(name, contents)
        altered = copy.deepcopy(row)
        altered["bytes"] = len(data.getvalue())
        altered["sha256"] = hashlib.sha256(data.getvalue()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "changed.whl"
            wheel.write_bytes(data.getvalue())
            with self.assertRaisesRegex(ValueError, "RECORD content checksum"):
                NATIVE["check_wheel"](wheel, altered)

    def _carrier(self, path: Path, *, corrupt_notice: bool = False) -> None:
        lock = NATIVE["load_lock"](ROOT)
        metadata = {}
        native = {}
        for row in lock["wheels"]:
            if row["platform"] != "android":
                continue
            with zipfile.ZipFile(ROOT / row["path"]) as wheel:
                for item in row["native_members"]:
                    target = NATIVE["apk_native_name"](item["path"], "arm64-v8a")
                    native[target] = wheel.read(item["path"])
                for item in row["metadata_members"]:
                    metadata[item["path"]] = wheel.read(item["path"])
        if corrupt_notice:
            notice = next(name for name in metadata if name.endswith("/libffi/LICENSE"))
            metadata[notice] += b"changed"
        nested = io.BytesIO()
        with zipfile.ZipFile(nested, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in metadata.items():
                archive.writestr(name, data)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("assets/sitepackages.zip", nested.getvalue())
            for name, data in native.items():
                archive.writestr(name, data)

    def test_final_carrier_reads_real_nested_metadata_and_native_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "synthetic-carrier.apk"
            self._carrier(apk)
            first = NATIVE["verify_apk"](apk, ROOT)
            second = NATIVE["verify_apk"](apk, ROOT)
            self.assertEqual(first, second)
            self.assertEqual(first["status"], "PASS")
            self.assertEqual(
                first["artifact_sha256"], hashlib.sha256(apk.read_bytes()).hexdigest()
            )
            self.assertGreater(first["metadata_members_verified"], 0)
            self.assertGreater(len(first["native_members"]), 0)
            self._carrier(apk, corrupt_notice=True)
            with self.assertRaisesRegex(ValueError, "metadata or notice differs"):
                NATIVE["verify_apk"](apk, ROOT)

    def test_unsafe_or_duplicate_nested_names_are_not_treated_as_absent_findings(self):
        for member in ("/absolute", "../escape"):
            with self.subTest(member=member):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr(member, b"fixture")
                with zipfile.ZipFile(stream) as archive:
                    with self.assertRaisesRegex(ValueError, "Unsafe"):
                        NATIVE["zip_files"](archive)

    def test_lock_rejects_a_missing_platform_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = json.loads((ROOT / NATIVE["LOCK"]).read_text())
            lock["wheels"] = lock["wheels"][:-1]
            path = root / NATIVE["LOCK"]
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                NATIVE["load_lock"](root)


if __name__ == "__main__":
    unittest.main()
