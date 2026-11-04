"""Автономные проверки точной политики подготовки Android staging."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import io
import json
import marshal
import os
import runpy
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT / "packaging/android"
sys.path.insert(0, str(SCRIPTS))
try:
    policy_module = importlib.import_module("package_stage")
finally:
    sys.path.pop(0)

ABI = "arm64-v8a"
POLICY_RELATIVE = "packaging/android/crypto-selftest-policy.json"
OWN_INPUTS = (
    "packaging/android/package_stage.py",
    POLICY_RELATIVE,
    "packaging/android/package_stage.gradle.kts",
    policy_module.NOTICES_MODULE,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def pyc_bytes(source: bytes, filename: Path) -> bytes:
    code = compile(source, str(filename), "exec", dont_inherit=True, optimize=0)
    return (
        importlib.util.MAGIC_NUMBER
        + struct.pack("<III", 0, 123456789, len(source))
        + marshal.dumps(code)
    )


def tree_bytes(root: Path) -> dict[str, tuple[str, bytes | str, int]]:
    result: dict[str, tuple[str, bytes | str, int]] = {}
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            kind, content = "symlink", os.readlink(path)
        elif stat.S_ISREG(mode):
            kind, content = "file", path.read_bytes()
        else:
            kind, content = "directory", ""
        result[path.relative_to(root).as_posix()] = (
            kind,
            content,
            stat.S_IMODE(mode),
        )
    return result


@dataclass
class StageFixture:
    run: Path
    stage: Path
    policy: dict[str, Any]
    excluded: dict[str, bytes]

    @property
    def source(self) -> Path:
        return self.run / "source"

    @property
    def policy_path(self) -> Path:
        return self.source / POLICY_RELATIVE

    @property
    def receipt(self) -> Path:
        return self.run / "package-preparation" / f"{ABI}.json"

    @property
    def success_proof(self) -> Path:
        return self.run / "package-preparation" / f"{ABI}.success.json"

    def expected_excluded(self) -> list[dict[str, Any]]:
        by_name = {row["path"]: row for row in self.policy["files"]}
        return [
            {
                "path": name,
                "size": len(data),
                "sha256": digest(data),
                "mode": stat.S_IMODE((self.stage / name).lstat().st_mode),
                "source_sha256": by_name[name]["source_sha256"],
                "code_sha256": by_name[name]["code_sha256"],
            }
            for name, data in sorted(self.excluded.items())
        ]


class AndroidPackagePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="tokenlogue-package-policy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def stage_fixture(self, label: str = "run") -> StageFixture:
        run = self.root / label
        stage = run / "source/build/site-packages" / ABI
        stage.mkdir(parents=True)
        metadata_path = "pycryptodomex-3.23.0.dist-info/METADATA"
        wheel_metadata_path = "pycryptodomex-3.23.0.dist-info/WHEEL"
        metadata = b"Metadata-Version: 2.1\nName: pycryptodomex\nVersion: 3.23.0\n"
        wheel_metadata = (
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: false\n"
            b"Tag: cp312-cp312-android_24_arm64_v8a\n"
        )
        retained = {
            "Cryptodome/Cipher/AES.pyc": b"synthetic runtime module\x00\xff",
            metadata_path: metadata,
            wheel_metadata_path: wheel_metadata,
            "pycryptodomex-3.23.0.dist-info/LICENSE.rst": b"upstream license",
            "pycryptodomex-3.23.0.dist-info/NOTICE": b"upstream notice",
            "neighbor/runtime.pyc": b"neighbor package bytes",
            "neighbor/SelfTest/keep.pyc": b"neighbor tests stay present",
        }
        for name, data in retained.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o640)
        excluded = {}
        records = []
        for index, name in enumerate(
            ("__init__", "Cipher/test_sample", "Hash/test_sample")
        ):
            source_path = f"Cryptodome/SelfTest/{name}.py"
            source = f"def sample():\n    return {111 + index}\n".encode()
            path = stage / (source_path + "c")
            path.parent.mkdir(parents=True, exist_ok=True)
            data = pyc_bytes(source, stage / source_path)
            path.write_bytes(data)
            relative = path.relative_to(stage).as_posix()
            excluded[relative] = data
            records.append(
                {
                    "path": relative,
                    "type": "regular",
                    "source_path": source_path,
                    "source_size": len(source),
                    "source_sha256": digest(source),
                    "code_sha256": policy_module._code_fingerprint(
                        marshal.loads(data[16:])
                    ),
                    "reference_pyc": {"size": len(data), "sha256": digest(data)},
                }
            )
        policy = {
            "schema": 1,
            "id": "pycryptodomex-selftest",
            "version": 1,
            "stage": "compiled-site-packages-before-native-packaging",
            "distribution": {
                "name": "pycryptodomex",
                "version": "3.23.0",
                "metadata_path": metadata_path,
                "metadata_sha256": digest(metadata),
            },
            "bytecode": {
                "python": [3, 12],
                "magic": importlib.util.MAGIC_NUMBER.hex(),
                "flags": 0,
                "optimize": 0,
                "fingerprint": "code-fields-v1",
                "timestamp": "staging-generated",
                "filename": "absolute-stage-source-path",
            },
            "sources": {
                ABI: {
                    "wheel_filename": (
                        "pycryptodomex-3.23.0-cp312-cp312-android_24_arm64_v8a.whl"
                    ),
                    "wheel_sha256": "a" * 64,
                    "wheel_metadata_path": wheel_metadata_path,
                    "wheel_metadata_sha256": digest(wheel_metadata),
                }
            },
            "files": records,
            "reference": {"kind": "synthetic offline fixture"},
        }
        fixture = StageFixture(run, stage, policy, excluded)
        for name in OWN_INPUTS:
            path = fixture.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if name != POLICY_RELATIVE:
                shutil.copy2(PROJECT / name, path)
        notices = runpy.run_path(str(PROJECT / policy_module.NOTICES_MODULE))
        for name in notices["required_inputs"](PROJECT, "android"):
            path = fixture.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT / name, path)
        notices["stage_notices"](
            fixture.source, "android", fixture.source / policy_module.NOTICES_ASSETS
        )
        notices["stage_notices"](
            fixture.source, "android", fixture.source / policy_module.NOTICES_APP_STAGE
        )
        self.authenticate(fixture)
        return fixture

    def authenticate(self, fixture: StageFixture) -> None:
        write_json(fixture.policy_path, fixture.policy)
        files = []
        notices = runpy.run_path(str(fixture.source / policy_module.NOTICES_MODULE))
        names = set(OWN_INPUTS)
        names.update(notices["required_inputs"](fixture.source, "android"))
        names.update(
            path.relative_to(fixture.source).as_posix()
            for path in (fixture.source / policy_module.NOTICES_ASSETS).rglob("*")
            if path.is_file()
        )
        for name in sorted(names):
            path = fixture.source / name
            files.append(
                {
                    "path": name,
                    "size": path.stat().st_size,
                    "sha256": digest(path.read_bytes()),
                    "mode": stat.S_IMODE(path.stat().st_mode),
                }
            )
        write_json(
            fixture.run / "preparation.json",
            {
                "recipe_version": "6",
                "arch": ABI,
                "source": str(fixture.source),
                "package_policy": {
                    "schema": fixture.policy["schema"],
                    "id": fixture.policy["id"],
                    "version": fixture.policy["version"],
                    "sha256": digest(fixture.policy_path.read_bytes()),
                    "stage": fixture.policy["stage"],
                },
                "packaged_notices": notices["verify_notices"](
                    fixture.source,
                    "android",
                    fixture.source / policy_module.NOTICES_ASSETS,
                ),
                "files": files,
            },
        )

    def assert_preflight_rejected(self, fixture: StageFixture) -> None:
        before = tree_bytes(fixture.stage)
        with self.assertRaises((ValueError, OSError)):
            policy_module.prepare_stage(fixture.run, ABI)
        self.assertEqual(tree_bytes(fixture.stage), before)
        self.assertFalse(fixture.receipt.exists())
        self.assertFalse(fixture.success_proof.exists())

    def run_stage_cli(self, fixture: StageFixture) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(fixture.source / OWN_INPUTS[0]),
                "--run-dir",
                str(fixture.run),
                "--abi",
                ABI,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=3,
        )

    def test_exact_composition_manifest_preservation_and_confirmed_repeat(self) -> None:
        fixture = self.stage_fixture()
        before = tree_bytes(fixture.stage)
        expected_excluded = fixture.expected_excluded()
        receipt = policy_module.prepare_stage(fixture.run, ABI)
        self.assertEqual(receipt["status"], "PREPARED")
        self.assertEqual(receipt["excluded"], expected_excluded)
        after = tree_bytes(fixture.stage)
        self.assertEqual(
            after,
            {
                name: entry
                for name, entry in before.items()
                if name not in fixture.excluded
            },
        )
        retained = [
            {
                "path": name,
                "size": len(entry[1]),
                "sha256": digest(entry[1]),
                "mode": entry[2],
            }
            for name, entry in sorted(after.items())
            if entry[0] == "file" and isinstance(entry[1], bytes)
        ]
        self.assertEqual(receipt["retained"], retained)
        self.assertEqual(
            receipt["policy"]["sha256"], digest(fixture.policy_path.read_bytes())
        )
        self.assertEqual(receipt["abi"], ABI)
        self.assertEqual(receipt["stage"], fixture.policy["stage"])
        self.assertEqual(json.loads(fixture.receipt.read_text()), receipt)
        encoded = fixture.receipt.read_bytes()
        modified = fixture.receipt.stat().st_mtime_ns
        proof_bytes = fixture.success_proof.read_bytes()
        proof_modified = fixture.success_proof.stat().st_mtime_ns
        self.assertNotIn(str(self.root).encode(), encoded)
        repeated = policy_module.prepare_stage(fixture.run, ABI)
        self.assertEqual(repeated, receipt)
        self.assertEqual(fixture.receipt.read_bytes(), encoded)
        self.assertEqual(fixture.receipt.stat().st_mtime_ns, modified)
        self.assertEqual(fixture.success_proof.read_bytes(), proof_bytes)
        self.assertEqual(fixture.success_proof.stat().st_mtime_ns, proof_modified)
        self.assertEqual(tree_bytes(fixture.stage), after)

    def test_notice_input_or_shipped_text_tamper_blocks_crypto_preparation(
        self,
    ) -> None:
        for variant in (
            "missing-input",
            "changed-input",
            "missing-asset",
            "changed-asset",
            "extra-asset",
            "missing-app-stage",
            "changed-app-stage",
        ):
            with self.subTest(case=variant):
                fixture = self.stage_fixture(variant)
                notices = runpy.run_path(
                    str(fixture.source / policy_module.NOTICES_MODULE)
                )
                if variant.endswith("input"):
                    paths = [
                        fixture.source / name
                        for name in notices["required_inputs"](
                            fixture.source, "android"
                        )
                    ]
                else:
                    paths = list(
                        (
                            fixture.source
                            / (
                                policy_module.NOTICES_APP_STAGE
                                if variant.endswith("app-stage")
                                else policy_module.NOTICES_ASSETS
                            )
                        ).rglob("*")
                    )
                original = next(
                    path
                    for path in paths
                    if path.is_file()
                    and digest(path.read_bytes())
                    == "2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388"
                )
                if variant.startswith("missing"):
                    original.unlink()
                elif variant.startswith("changed"):
                    original.write_bytes(original.read_bytes() + b"edited")
                else:
                    original.with_name("unexpected.txt").write_bytes(b"unexpected")
                self.assert_preflight_rejected(fixture)

    def test_preflight_checks_all_files_paths_sizes_versions_and_bytecode(self) -> None:
        variants = (
            "extra",
            "missing",
            "renamed",
            "changed-code",
            "changed-size",
            "changed-source-size",
            "wrong-magic",
            "wrong-flags",
            "wrong-filename",
            "wrong-version",
        )
        for variant in variants:
            with self.subTest(case=variant):
                fixture = self.stage_fixture(variant)
                name = sorted(fixture.excluded)[-1]
                path = fixture.stage / name
                data = path.read_bytes()
                if variant == "extra":
                    (path.parent / "unexpected.pyc").write_bytes(data)
                elif variant == "missing":
                    path.unlink()
                elif variant == "renamed":
                    path.rename(path.with_name("renamed.pyc"))
                elif variant == "changed-code":
                    path.write_bytes(
                        pyc_bytes(
                            b"def sample():\n    return 999\n", path.with_suffix(".py")
                        )
                    )
                elif variant == "changed-size":
                    path.write_bytes(data + b"unexpected trailer")
                elif variant == "changed-source-size":
                    path.write_bytes(data[:12] + struct.pack("<I", 1) + data[16:])
                elif variant == "wrong-magic":
                    path.write_bytes(b"BAD!" + data[4:])
                elif variant == "wrong-flags":
                    path.write_bytes(data[:4] + struct.pack("<I", 3) + data[8:])
                elif variant == "wrong-filename":
                    source = b"def sample():\n    return 113\n"
                    path.write_bytes(pyc_bytes(source, Path("/unexpected/source.py")))
                else:
                    metadata = (
                        fixture.stage / fixture.policy["distribution"]["metadata_path"]
                    )
                    metadata.write_bytes(
                        metadata.read_bytes().replace(b"3.23.0", b"3.24.0")
                    )
                self.assert_preflight_rejected(fixture)

    def test_documented_timestamp_variation_retains_exact_observed_manifest(
        self,
    ) -> None:
        fixture = self.stage_fixture()
        for name, original in fixture.excluded.items():
            varied = original[:8] + struct.pack("<I", 987654321) + original[12:]
            (fixture.stage / name).write_bytes(varied)
            fixture.excluded[name] = varied
        expected = fixture.expected_excluded()
        receipt = policy_module.prepare_stage(fixture.run, ABI)
        self.assertEqual(receipt["excluded"], expected)

    def test_missing_stage_without_successful_proof_is_rejected(self) -> None:
        for mode in ("partial", "empty"):
            with self.subTest(mode=mode):
                fixture = self.stage_fixture(mode)
                names = sorted(fixture.excluded)
                for name in names[:1] if mode == "partial" else names:
                    (fixture.stage / name).unlink()
                self.assert_preflight_rejected(fixture)

    def test_stage_authentication_rejects_missing_changed_and_escaped_inputs(
        self,
    ) -> None:
        for variant in (
            "unscoped",
            "source-escape",
            "module-changed",
            "policy-changed",
            "wrong-abi",
            "extra-abi",
        ):
            with self.subTest(case=variant):
                fixture = self.stage_fixture(variant)
                proof_path = fixture.run / "preparation.json"
                if variant == "unscoped":
                    proof_path.unlink()
                elif variant == "source-escape":
                    proof = json.loads(proof_path.read_text())
                    proof["source"] = str(self.root / "outside")
                    write_json(proof_path, proof)
                elif variant == "module-changed":
                    module = fixture.source / OWN_INPUTS[0]
                    module.write_bytes(
                        module.read_bytes() + "\n# Изменённая фикстура\n".encode()
                    )
                elif variant == "policy-changed":
                    fixture.policy["version"] += 1
                    write_json(fixture.policy_path, fixture.policy)
                elif variant == "extra-abi":
                    (fixture.stage.parent / "x86_64").mkdir()
                else:
                    before = tree_bytes(fixture.stage)
                    with self.assertRaises(ValueError):
                        policy_module.prepare_stage(fixture.run, "../../outside")
                    self.assertEqual(tree_bytes(fixture.stage), before)
                    self.assertFalse(fixture.receipt.exists())
                    continue
                self.assert_preflight_rejected(fixture)

    def test_symlink_components_and_internal_links_are_rejected(self) -> None:
        for variant in ("run", "build", "package", "selftest", "file", "neighbor"):
            with self.subTest(component=variant):
                fixture = self.stage_fixture(variant)
                if variant == "run":
                    alias = self.root / "run-alias"
                    alias.symlink_to(fixture.run, target_is_directory=True)
                    before = tree_bytes(fixture.stage)
                    with self.assertRaises(ValueError):
                        policy_module.prepare_stage(alias, ABI)
                    self.assertEqual(tree_bytes(fixture.stage), before)
                    self.assertFalse(fixture.receipt.exists())
                    continue
                relative = {
                    "build": fixture.source / "build",
                    "package": fixture.stage / "Cryptodome",
                    "selftest": fixture.stage / "Cryptodome/SelfTest",
                    "file": fixture.stage / sorted(fixture.excluded)[-1],
                    "neighbor": fixture.stage / "neighbor/runtime.pyc",
                }[variant]
                moved = self.root / f"outside-{variant}"
                relative.rename(moved)
                relative.symlink_to(moved, target_is_directory=moved.is_dir())
                outside_before = (
                    tree_bytes(moved) if moved.is_dir() else moved.read_bytes()
                )
                with self.assertRaises(ValueError):
                    policy_module.prepare_stage(fixture.run, ABI)
                outside_after = (
                    tree_bytes(moved) if moved.is_dir() else moved.read_bytes()
                )
                self.assertEqual(outside_after, outside_before)
                self.assertFalse(fixture.receipt.exists())

    def test_symlink_swap_during_unlink_cannot_follow_external_parent(self) -> None:
        fixture = self.stage_fixture()
        package = fixture.stage / "Cryptodome"
        outside = self.root / "external-crypto"
        original = tree_bytes(package)
        real_open = os.open
        real_unlink = policy_module._unlink_checked
        armed = False
        swapped = False

        def arm_unlink(*args: Any, **kwargs: Any) -> None:
            nonlocal armed
            armed = True
            real_unlink(*args, **kwargs)

        def swap_parent(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            nonlocal swapped
            if (
                armed
                and not swapped
                and path == "Cryptodome"
                and flags & os.O_DIRECTORY
            ):
                package.rename(outside)
                package.symlink_to(outside, target_is_directory=True)
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        with (
            patch.object(policy_module, "_unlink_checked", arm_unlink),
            patch.object(policy_module.os, "open", swap_parent),
            self.assertRaises(OSError),
        ):
            policy_module.prepare_stage(fixture.run, ABI)
        self.assertTrue(swapped)
        self.assertEqual(tree_bytes(outside), original)
        self.assertFalse(fixture.receipt.exists())
        self.assertFalse(fixture.success_proof.exists())

    def test_repeat_refuses_changed_retained_content_modes_and_forged_receipt(
        self,
    ) -> None:
        for variant in (
            "runtime",
            "mode",
            "extra",
            "receipt-status",
            "receipt-excluded",
            "receipt-retained",
            "receipt-sha",
            "receipt-size",
            "receipt-before",
            "missing-proof",
        ):
            with self.subTest(case=variant):
                fixture = self.stage_fixture(variant)
                policy_module.prepare_stage(fixture.run, ABI)
                runtime = fixture.stage / "Cryptodome/Cipher/AES.pyc"
                if variant == "runtime":
                    runtime.write_bytes(b"changed runtime bytes")
                elif variant == "mode":
                    runtime.chmod(0o600)
                elif variant == "extra":
                    (fixture.stage / "neighbor/extra.pyc").write_bytes(b"extra file")
                elif variant == "missing-proof":
                    fixture.success_proof.unlink()
                else:
                    receipt = json.loads(fixture.receipt.read_text())
                    if variant == "receipt-status":
                        receipt["status"] = "PENDING"
                    elif variant == "receipt-excluded":
                        receipt["excluded"].pop()
                    elif variant == "receipt-retained":
                        receipt["retained"][0]["sha256"] = "0" * 64
                    elif variant == "receipt-sha":
                        receipt["excluded"][0]["sha256"] = "z" * 64
                    elif variant == "receipt-size":
                        receipt["excluded"][0]["size"] = -1
                    else:
                        receipt["before_inventory_sha256"] = "0" * 64
                    if variant in {"receipt-sha", "receipt-size", "receipt-before"}:
                        receipt["proof_sha256"] = policy_module._receipt_digest(receipt)
                    write_json(fixture.receipt, receipt)
                before = tree_bytes(fixture.stage)
                receipt_before = fixture.receipt.read_bytes()
                with self.assertRaises(ValueError):
                    policy_module.prepare_stage(fixture.run, ABI)
                self.assertEqual(tree_bytes(fixture.stage), before)
                self.assertEqual(fixture.receipt.read_bytes(), receipt_before)

    def test_delete_error_stops_and_cannot_create_successful_repeat(self) -> None:
        fixture = self.stage_fixture()
        real_unlink = policy_module._unlink_checked
        calls: list[str] = []

        def fail_second(stage: Path, name: str, *args: Any, **kwargs: Any) -> None:
            calls.append(name)
            if len(calls) == 2:
                raise OSError("synthetic unlink failure")
            real_unlink(stage, name, *args, **kwargs)

        with patch.object(policy_module, "_unlink_checked", fail_second):
            with self.assertRaisesRegex(OSError, "synthetic unlink failure"):
                policy_module.prepare_stage(fixture.run, ABI)
        self.assertEqual(len(calls), 2)
        self.assertFalse((fixture.stage / calls[0]).exists())
        self.assertTrue((fixture.stage / calls[1]).exists())
        self.assertFalse(fixture.receipt.exists())
        self.assertFalse(fixture.success_proof.exists())
        self.assert_preflight_rejected(fixture)

    def test_success_record_io_error_cannot_confirm_previous_run(self) -> None:
        fixture = self.stage_fixture()
        with (
            patch.object(
                policy_module.os,
                "fsync",
                side_effect=[None, OSError("synthetic confirmation write failure")],
            ),
            self.assertRaisesRegex(OSError, "synthetic confirmation write failure"),
        ):
            policy_module.prepare_stage(fixture.run, ABI)
        self.assertFalse(fixture.success_proof.exists())
        before = tree_bytes(fixture.stage)
        with self.assertRaises(ValueError):
            policy_module.prepare_stage(fixture.run, ABI)
        self.assertEqual(tree_bytes(fixture.stage), before)
        self.assertFalse(fixture.success_proof.exists())

    def test_cli_uses_authenticated_stage_and_fails_closed(self) -> None:
        fixture = self.stage_fixture()
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            self.assertEqual(
                policy_module.main(["--run-dir", str(fixture.run), "--abi", ABI]), 0
            )
        self.assertTrue(fixture.receipt.is_file())
        refused = self.stage_fixture("unscoped-cli")
        (refused.run / "preparation.json").unlink()
        before = tree_bytes(refused.stage)
        result = self.run_stage_cli(refused)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(refused.receipt.exists())
        self.assertEqual(tree_bytes(refused.stage), before)

    def test_cli_rejects_special_proof_and_malformed_json_without_hanging(self) -> None:
        for variant in ("fifo-proof", "json-list"):
            with self.subTest(case=variant):
                fixture = self.stage_fixture(variant)
                preparation = fixture.run / "preparation.json"
                if variant == "fifo-proof":
                    preparation.unlink()
                    os.mkfifo(preparation, 0o600)
                else:
                    write_json(preparation, [])
                before = tree_bytes(fixture.stage)
                result = self.run_stage_cli(fixture)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Подготовка SelfTest остановлена", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(fixture.receipt.exists())
                self.assertFalse(fixture.success_proof.exists())
                self.assertEqual(tree_bytes(fixture.stage), before)


if __name__ == "__main__":
    unittest.main()
