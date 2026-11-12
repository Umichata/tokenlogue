"""Current-source runtime uses pinned upstream inputs and full producer receipts."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from tests.runtime_fixture import RuntimeFixture, encoded

SCRIPTS = Path(__file__).resolve().parents[1] / "packaging/linux/appimage"
sys.path.insert(0, str(SCRIPTS))
import fetch_runtime  # noqa: E402  # pyright: ignore[reportMissingImports]
import notices  # noqa: E402  # pyright: ignore[reportMissingImports]
import source_runtime  # noqa: E402  # pyright: ignore[reportMissingImports]


class CurrentContractTests(unittest.TestCase):
    def test_official_pinned_inputs_and_application_workflow_need_no_old_release(
        self,
    ) -> None:
        contract = json.loads((SCRIPTS / "runtime-artifact.lock.json").read_text())
        source_runtime.check_contract(contract)
        self.assertNotIn("archive_url", contract)
        self.assertNotIn("artifact_id", contract)
        workflow = yaml.safe_load(
            (SCRIPTS.parents[2] / ".github/workflows/build-linux.yml").read_text()
        )
        steps = workflow["jobs"]["build-linux"]["steps"]
        step = next(
            step
            for step in steps
            if step["name"] == "Build and verify current standalone runtime"
        )
        self.assertIn("packaging/linux/appimage/fetch_runtime.py", step["run"])
        self.assertNotIn("curl", step["run"])
        self.assertNotIn("archive", step["run"])
        self.assertIn(
            "--producer-reports build/linux-release/reports/runtime-producer",
            step["run"],
        )
        self.assertLess(
            steps.index(step),
            next(
                i
                for i, step in enumerate(steps)
                if step["name"] == "Build AppImage"
            ),
        )

    def test_notice_registry_matches_current_producer_inputs_and_components(
        self,
    ) -> None:
        contract = json.loads((SCRIPTS / "runtime-artifact.lock.json").read_text())
        registry = notices.load_lock(SCRIPTS)["runtime"]
        self.assertEqual(registry["mode"], contract["mode"])
        for field in ("workflow", "runtime_lock_sha256"):
            self.assertEqual(registry[field], contract[field], field)
        self.assertEqual(registry["commit"], contract["upstream_commit"])
        self.assertEqual(
            {
                name: {key: component[key] for key in ("version", "licenses")}
                for name, component in registry["components"].items()
            },
            contract["components"],
        )

    def test_input_lock_or_component_contract_change_is_rejected(self) -> None:
        original = json.loads((SCRIPTS / "runtime-artifact.lock.json").read_text())
        for field, value in (
            ("runtime_lock_sha256", "0" * 64),
            ("upstream_commit", "0" * 40),
            ("components", {}),
        ):
            with self.subTest(field=field):
                changed = {**original, field: value}
                with self.assertRaises(fetch_runtime.RuntimeArtifactError):
                    source_runtime.check_contract(changed)


class CurrentProducerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="current-runtime-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = RuntimeFixture(self.root)
        build_lock = json.loads(self.fixture.files["runtime.lock.json"])
        audit_path = "reports/reports/input-network-audit.json"
        audit = {
            "result": "PASS",
            "old_tokenlogue_endpoints": "DENIED",
            "network": [],
            "inputs": [
                {
                    **{key: record[key] for key in ("path", "size", "sha256")},
                    "mode": "verified-cache",
                }
                for record in build_lock["files"]
            ],
        }
        self.fixture.files[audit_path] = encoded(audit)
        self.fixture.manifest["files"].append(
            {
                "path": audit_path,
                "size": len(self.fixture.files[audit_path]),
                "sha256": hashlib.sha256(self.fixture.files[audit_path]).hexdigest(),
            }
        )
        self.fixture.files["manifest.json"] = encoded(self.fixture.manifest)
        self.fixture.files["SHA256SUMS"] = "".join(
            f"{hashlib.sha256(contents).hexdigest()}  {name}\n"
            for name, contents in sorted(self.fixture.files.items())
            if name != "SHA256SUMS"
        ).encode()
        self.contract = {
            **self.fixture.lock,
            "schema": 2,
            "mode": "current-source",
            "producer": "packaging/linux/appimage/runtime/build_runtime.py",
        }
        self.state = {
            **self.fixture.manifest["tokenlogue_recipe"],
            "worktree_dirty": False,
        }
        self.output = self.root / "runtime-selected"
        self.artifact = self.root / "build/appimage/runtime/runs/test-producer/artifact"
        self.calls: list[str] = []
        engine = patch.object(
            source_runtime.shutil, "which", return_value="/synthetic/docker"
        )
        engine.start()
        self.addCleanup(engine.stop)
        for target, name, value in (
            (source_runtime, "REPOSITORY", self.root),
            (source_runtime.producer, "recipe_state", None),
            (source_runtime, "check_contract", None),
        ):
            mocked = (
                patch.object(target, name, return_value=self.state)
                if name == "recipe_state"
                else patch.object(target, name, value)
                if name == "REPOSITORY"
                else patch.object(target, name)
            )
            mocked.start()
            self.addCleanup(mocked.stop)

    def run_producer(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        stage = command[2]
        self.calls.append(stage)
        if stage == "bundle":
            self.artifact.mkdir(parents=True)
            for name, contents in self.fixture.files.items():
                target = self.artifact / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(contents)
            (self.artifact / "runtime-x86_64").chmod(0o755)
        return subprocess.CompletedProcess(command, 0)

    def test_new_producer_all_stages_real_validator_and_reverified_cache(self) -> None:
        with patch.object(
            source_runtime.subprocess, "run", side_effect=self.run_producer
        ):
            result = source_runtime.prepare(
                self.output, self.contract, run_name="test-producer"
            )
        self.assertEqual(self.calls, ["init", *fetch_runtime.STAGES, "bundle"])
        self.assertEqual(result["result"], "PASS")
        self.assertFalse(result["old_tokenlogue_artifacts_used"])
        self.assertEqual(result["producer_commit"], self.state["commit"])
        with patch.object(
            source_runtime.subprocess,
            "run",
            side_effect=AssertionError("must not rebuild cache"),
        ):
            repeated = source_runtime.prepare(self.output, self.contract)
        self.assertEqual(repeated["cache"], "REVERIFIED")
        (self.output / "materials/licenses/libfuse/LICENSE").write_bytes(b"altered")
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            source_runtime.prepare(self.output, self.contract)

    def test_receipt_export_has_exact_raw_checks_and_no_source_or_binary_payloads(
        self,
    ) -> None:
        self.run_producer(["python", "producer", "bundle"])
        lock = source_runtime.selected_lock(self.artifact, self.contract)
        destination = self.root / "diagnostic/reports/runtime-producer"
        result = source_runtime.export_receipts(self.artifact, destination, lock)
        expected = {
            "manifest.json",
            "runtime.lock.json",
            "input-network-audit.json",
            "recipe-identity.json",
            "SHA256SUMS",
            *(stage + ".json" for stage in fetch_runtime.STAGES),
        }
        self.assertEqual({path.name for path in destination.iterdir()}, expected)
        self.assertEqual(result["state"], "EXPORTED")
        self.assertFalse(result["runtime_binary_or_build_inputs_copied"])
        for name in ("manifest.json", "runtime.lock.json"):
            self.assertEqual(
                (destination / name).read_bytes(), (self.artifact / name).read_bytes()
            )
        for name in ("input-network-audit", *fetch_runtime.STAGES):
            self.assertEqual(
                (destination / (name + ".json")).read_bytes(),
                (self.artifact / "reports/reports" / (name + ".json")).read_bytes(),
            )
        identity = json.loads((destination / "recipe-identity.json").read_text())
        self.assertEqual(
            identity["identity"], self.fixture.manifest["tokenlogue_recipe"]
        )
        self.assertEqual(identity["source"], "manifest.json#tokenlogue_recipe")
        records = fetch_runtime.checksum_records(
            (destination / "SHA256SUMS").read_text()
        )
        self.assertEqual(set(records), expected - {"SHA256SUMS"})
        for name, digest in records.items():
            self.assertEqual(fetch_runtime.digest(destination / name), digest)
        before = {
            path.name: (path.stat().st_mtime_ns, path.read_bytes())
            for path in destination.iterdir()
        }
        repeated = source_runtime.export_receipts(self.artifact, destination, lock)
        self.assertEqual(repeated["state"], "REVERIFIED")
        self.assertEqual(
            before,
            {
                path.name: (path.stat().st_mtime_ns, path.read_bytes())
                for path in destination.iterdir()
            },
        )
        (destination / "smoke.json").write_bytes(b"altered saved proof")
        with self.assertRaisesRegex(
            fetch_runtime.RuntimeArtifactError, "Existing runtime receipts differ"
        ):
            source_runtime.export_receipts(self.artifact, destination, lock)
        self.assertEqual(
            (destination / "smoke.json").read_bytes(), b"altered saved proof"
        )

    def test_corrupt_or_missing_raw_receipt_blocks_export_before_destination_creation(
        self,
    ) -> None:
        self.run_producer(["python", "producer", "bundle"])
        lock = source_runtime.selected_lock(self.artifact, self.contract)
        destination = self.root / "not-exported"
        audit = self.artifact / "reports/reports/input-network-audit.json"
        audit.unlink()
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            source_runtime.export_receipts(self.artifact, destination, lock)
        self.assertFalse(destination.exists())

    def test_real_cli_exports_proof_to_the_diagnostic_artifact_location(self) -> None:
        self.run_producer(["python", "producer", "bundle"])
        lock = source_runtime.selected_lock(self.artifact, self.contract)
        destination = self.root / "linux-release/reports/runtime-producer"
        report = self.root / "linux-release/reports/runtime-inputs.json"
        output = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                [
                    "fetch_runtime.py",
                    "--output",
                    str(self.artifact),
                    "--producer-reports",
                    str(destination),
                    "--report",
                    str(report),
                ],
            ),
            patch.object(
                source_runtime,
                "prepare",
                return_value={"result": "PASS", "mode": "current-source"},
            ),
            patch.object(fetch_runtime, "load_lock", return_value=lock),
            patch.object(
                fetch_runtime.subprocess,
                "check_output",
                return_value=self.state["commit"] + "\n",
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(fetch_runtime.main(), 0)
        result = json.loads(report.read_text())
        self.assertEqual(result["producer_receipts"]["result"], "PASS")
        self.assertEqual(
            (destination / "manifest.json").read_bytes(),
            (self.artifact / "manifest.json").read_bytes(),
        )

    def test_missing_container_engine_stops_before_download(self) -> None:
        with (
            patch.object(source_runtime.shutil, "which", return_value=None),
            patch.object(
                source_runtime.subprocess,
                "run",
                side_effect=AssertionError("no fetch without engine"),
            ),
        ):
            with self.assertRaisesRegex(
                fetch_runtime.RuntimeArtifactError, "Docker or Podman"
            ):
                source_runtime.prepare(self.output, self.contract)
        self.assertFalse(self.output.exists())

    def test_failed_stage_stops_before_selection(self) -> None:
        def failed(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            if command[2] == "prepare":
                raise subprocess.CalledProcessError(1, command)
            return self.run_producer(command, **kwargs)

        with patch.object(source_runtime.subprocess, "run", side_effect=failed):
            with self.assertRaises(subprocess.CalledProcessError):
                source_runtime.prepare(
                    self.output, self.contract, run_name="test-producer"
                )
        self.assertEqual(self.calls, ["init", "fetch"])
        self.assertFalse(self.output.exists())

    def test_old_producer_or_dirty_recipe_cannot_be_relabelled_current(self) -> None:
        self.run_producer(["python", "producer", "bundle"])
        changed = copy.deepcopy(self.fixture.manifest)
        changed["tokenlogue_recipe"]["commit"] = "b" * 40
        (self.artifact / "manifest.json").write_bytes(encoded(changed))
        with self.assertRaisesRegex(
            fetch_runtime.RuntimeArtifactError, "does not match"
        ):
            source_runtime.selected_lock(self.artifact, self.contract)
        self.state["dirty"] = True
        with patch.object(
            source_runtime.subprocess,
            "run",
            side_effect=AssertionError("must not build dirty recipe"),
        ):
            with self.assertRaisesRegex(fetch_runtime.RuntimeArtifactError, "Commit"):
                source_runtime.prepare(self.output, self.contract)

    def test_current_runtime_notices_bind_real_output_and_unchanged_component_licenses(
        self,
    ) -> None:
        self.run_producer(["python", "producer", "bundle"])
        lock = source_runtime.selected_lock(self.artifact, self.contract)
        registry = copy.deepcopy(self.fixture.notice_lock)
        previous = registry["runtime"]
        registry["runtime"] = {
            key: previous[key]
            for key in (
                "commit",
                "components",
                "source_materials",
                "fuse",
                "source",
                "workflow",
                "runtime_lock_sha256",
            )
        }
        registry["runtime"]["mode"] = "current-source"
        root = self.root / "appdir"
        root.mkdir()
        collector = notices.Collector(root, registry)
        with patch.object(fetch_runtime, "load_lock", return_value=lock):
            collector.collect_runtime(self.artifact / "runtime-x86_64")
        manifest = {
            "source_materials": registry["release_source_status"],
            "components": collector.components,
            "files": {
                name: notices.sha256(root / name) for name in collector.notice_paths
            },
        }
        notices.verify_runtime_notice(root, manifest, registry)
        component = next(
            component
            for component in collector.components
            if component["id"] == "appimage-runtime"
        )
        self.assertEqual(
            component["origin"]["selected_runtime"]["sha256"], lock["runtime_sha256"]
        )
        provenance = json.loads(
            (
                root / notices.DOC / "licenses/appimage-runtime/provenance.json"
            ).read_text()
        )
        self.assertEqual(provenance["mode"], "current-source")
        self.assertNotIn("artifact_id", provenance)
        self.assertNotIn("source_run_id", provenance)

    def test_missing_guard_audit_or_untrusted_cache_record_blocks_selection(
        self,
    ) -> None:
        self.run_producer(["python", "producer", "bundle"])
        audit = self.artifact / "reports/reports/input-network-audit.json"
        value = json.loads(audit.read_text())
        value["inputs"][0]["sha256"] = "0" * 64
        audit.write_bytes(encoded(value))
        with self.assertRaisesRegex(
            fetch_runtime.RuntimeArtifactError, "does not match pinned"
        ):
            source_runtime.selected_lock(self.artifact, self.contract)
        audit.unlink()
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            source_runtime.selected_lock(self.artifact, self.contract)

    def test_mandatory_smoke_cannot_be_replaced_with_skipped_stage(self) -> None:
        self.run_producer(["python", "producer", "bundle"])
        changed = copy.deepcopy(self.fixture.manifest)
        changed["checks"]["smoke"]["result"] = "NOT_RUN"
        (self.artifact / "manifest.json").write_bytes(encoded(changed))
        lock = source_runtime.selected_lock(self.artifact, self.contract)
        with self.assertRaises(fetch_runtime.RuntimeArtifactError):
            fetch_runtime.verify_bundle(self.artifact, lock)


if __name__ == "__main__":
    unittest.main()
