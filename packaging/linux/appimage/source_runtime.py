"""Build the selected runtime from the current checkout and pinned upstream inputs."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import fetch_runtime

DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = DIRECTORY.parents[2]
sys.path.insert(0, str(DIRECTORY / "runtime"))
try:
    producer = importlib.import_module("build_runtime")
finally:
    sys.path.pop(0)


def check_contract(contract: dict[str, Any]) -> None:
    require = fetch_runtime.require
    require(
        contract.get("schema") == 2
        and contract.get("mode") == "current-source"
        and contract.get("repository") == "Umichata/tokenlogue"
        and contract.get("producer")
        == "packaging/linux/appimage/runtime/build_runtime.py"
        and contract.get("workflow") == ".github/workflows/build-appimage-runtime.yml",
        "Invalid current-source runtime contract",
    )
    locked = DIRECTORY / "runtime/runtime.lock.json"
    require(
        fetch_runtime.digest(locked) == contract.get("runtime_lock_sha256"),
        "Current runtime input lock differs from the source contract",
    )
    inputs = json.loads(locked.read_text())
    require(
        inputs["upstream"]["commit"] == contract.get("upstream_commit"),
        "Current runtime upstream commit differs from the source contract",
    )
    producer.load_acquisition_plan(DIRECTORY / "runtime/acquisition.lock.json", inputs)
    # The producer may fetch exact upstream inputs, never old application releases.
    for item in inputs["files"]:
        url = item["url"].lower()
        require(
            "/umichata/tokenlogue/" not in url,
            "Runtime inputs must not depend on Tokenlogue releases or Actions",
        )
    components = {}
    for component in inputs["components"]:
        components[component["name"]] = {
            "version": component.get(
                "package_version", component.get("version", component.get("commit"))
            ),
            "licenses": sorted(Path(name).name for name in component["licenses"]),
        }
    require(
        components
        == {
            name: {"version": item["version"], "licenses": sorted(item["licenses"])}
            for name, item in contract["components"].items()
        },
        "Runtime source component/license mapping differs from the contract",
    )


def input_acquisition(root: Path) -> dict[str, Any]:
    lock = fetch_runtime.read_json(root, "runtime.lock.json")
    audit = fetch_runtime.read_json(root, "reports/reports/input-network-audit.json")
    manifest = fetch_runtime.read_json(root, "manifest.json")
    acquisition_pins = [
        entry["sha256"]
        for entry in manifest.get("tokenlogue_recipe", {}).get("files", [])
        if entry["path"] == "packaging/linux/appimage/runtime/acquisition.lock.json"
    ]
    if acquisition_pins:
        fetch_runtime.require(
            len(acquisition_pins) == 1
            and audit.get("acquisition_plan_sha256") == acquisition_pins[0],
            "Runtime input audit differs from the committed acquisition plan",
        )
    records = audit.get("inputs", [])
    expected = {entry["path"]: entry for entry in lock["files"]}
    actual = {entry.get("path"): entry for entry in records}
    fetch_runtime.require(
        audit.get("result") == "PASS"
        and audit.get("old_tokenlogue_endpoints") == "DENIED"
        and len(actual) == len(records)
        and set(actual) == set(expected),
        "Missing or incomplete guarded runtime input acquisition receipt",
    )
    for name, record in expected.items():
        entry = actual[name]
        fetch_runtime.require(
            all(entry.get(key) == record[key] for key in ("size", "sha256"))
            and entry.get("mode") in {"verified-cache", "downloaded-and-verified"},
            "Runtime acquisition receipt does not match pinned input",
        )
    fetch_runtime.require(
        all(entry.get("allowed") is True for entry in audit.get("network", [])),
        "Rejected runtime request in acquisition receipt",
    )
    return {
        "guard": "official-source-only",
        "old_tokenlogue_endpoints": "DENIED",
        "downloaded_inputs": sum(
            entry["mode"] == "downloaded-and-verified" for entry in records
        ),
        "verified_cached_inputs": sum(
            entry["mode"] == "verified-cache" for entry in records
        ),
        "input_count": len(expected),
        "source_kinds": {
            kind: sum(
                entry.get("source_kind", "unspecified") == kind for entry in records
            )
            for kind in sorted(
                {entry.get("source_kind", "unspecified") for entry in records}
            )
        },
        "existing_container_cache_inputs": sum(
            entry.get("container_cache") == "reverified-existing-container-cache"
            for entry in records
        ),
        "audit_sha256": fetch_runtime.digest(
            root / "reports/reports/input-network-audit.json"
        ),
    }


def selected_lock(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    """Bind bytes and receipts to this clean recipe, not a historical artifact ID."""
    check_contract(contract)
    state = producer.recipe_state(REPOSITORY)
    fetch_runtime.require(state["dirty"] is False, "Runtime producer recipe is dirty")
    manifest = fetch_runtime.read_json(root, "manifest.json")
    saved = manifest.get("tokenlogue_recipe", {})
    fetch_runtime.require(
        all(
            saved.get(key) == state[key]
            for key in ("commit", "sha256", "files", "dirty")
        ),
        "Runtime producer does not match this checkout and recipe fingerprint",
    )
    runtime = manifest.get("runtime", {})
    fetch_runtime.require(
        runtime.get("path") == contract["runtime_path"]
        and type(runtime.get("size")) is int
        and runtime["size"] > 0
        and re.fullmatch(r"[a-f0-9]{64}", runtime.get("sha256", "")) is not None,
        "Invalid runtime identity in producer manifest",
    )
    return {
        **contract,
        "producer_commit": state["commit"],
        "recipe_fingerprint": state["sha256"],
        "runtime_sha256": runtime["sha256"],
        "runtime_size": runtime["size"],
        "manifest_sha256": fetch_runtime.digest(root / "manifest.json"),
        "input_acquisition": input_acquisition(root),
    }


def export_receipts(
    root: Path, destination: Path, lock: dict[str, Any]
) -> dict[str, Any]:
    """Export an explicit small proof set, without source/toolchain payloads."""
    fetch_runtime.require(
        lock.get("mode") == "current-source", "Current producer receipts required"
    )
    fetch_runtime.verify_bundle(root, lock)
    input_acquisition(root)
    sources = {
        "manifest.json": "manifest.json",
        "runtime.lock.json": "runtime.lock.json",
        "input-network-audit.json": "reports/reports/input-network-audit.json",
        **{
            stage + ".json": "reports/reports/" + stage + ".json"
            for stage in fetch_runtime.STAGES
        },
    }
    payload = {}
    total = 0
    for name, source in sources.items():
        path = fetch_runtime.checked_file(root, source)
        total += path.stat().st_size
        fetch_runtime.require(
            total <= 8 * 1024**2, "Runtime proof metadata exceeds small receipt limit"
        )
        payload[name] = path.read_bytes()
    identity = {
        "source": "manifest.json#tokenlogue_recipe",
        "scope": "Extracted identity from the verified producer manifest",
        "identity": json.loads(payload["manifest.json"])["tokenlogue_recipe"],
    }
    payload["recipe-identity.json"] = (
        json.dumps(identity, indent=2, sort_keys=True) + "\n"
    ).encode()
    payload["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(payload.items())
    ).encode()
    fetch_runtime.require(
        not destination.resolve().is_relative_to(root.resolve()),
        "Receipt export must stay outside the verified producer bundle",
    )
    if destination.exists() or destination.is_symlink():
        fetch_runtime.require(
            destination.is_dir() and not destination.is_symlink(),
            "Invalid receipt destination",
        )
        fetch_runtime.require(
            {path.name for path in destination.iterdir()} == set(payload),
            "Existing receipt inventory differs",
        )
        for name, data in payload.items():
            fetch_runtime.require(
                fetch_runtime.checked_file(destination, name).read_bytes() == data,
                "Existing runtime receipts differ",
            )
        state = "REVERIFIED"
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="runtime-proof-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / "receipts"
            staged.mkdir()
            for name, data in payload.items():
                (staged / name).write_bytes(data)
            staged.rename(destination)
        state = "EXPORTED"
    return {
        "result": "PASS",
        "directory": destination.name,
        "state": state,
        "files": len(payload),
        "bytes": sum(map(len, payload.values())),
        "checksums_sha256": hashlib.sha256(payload["SHA256SUMS"]).hexdigest(),
        "runtime_binary_or_build_inputs_copied": False,
    }


def prepare(
    output: Path,
    contract: dict[str, Any],
    *,
    run_name: str | None = None,
    engine: str = "docker",
) -> dict[str, Any]:
    check_contract(contract)
    state = producer.recipe_state(REPOSITORY)
    fetch_runtime.require(
        state["dirty"] is False, "Commit the reviewed runtime recipe before building"
    )
    if output.exists() or output.is_symlink():
        lock = selected_lock(output, contract)
        result = fetch_runtime.verify_bundle(output, lock)
        return {
            **result,
            "mode": "current-source",
            "cache": "REVERIFIED",
            "producer_commit": state["commit"],
            "recipe_fingerprint": state["sha256"],
            "input_acquisition": lock["input_acquisition"],
        }
    fetch_runtime.require(
        shutil.which(engine) is not None,
        "Current runtime producer requires Docker or Podman",
    )
    name = run_name or "current-" + uuid.uuid4().hex
    fetch_runtime.require(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name) is not None,
        "Invalid producer attempt name",
    )
    builder = DIRECTORY / "runtime/build_runtime.py"
    for stage in ("init", *fetch_runtime.STAGES, "bundle"):
        subprocess.run(
            [sys.executable, str(builder), stage, "--run", name, "--engine", engine],
            cwd=REPOSITORY,
            check=True,
        )
    artifact = REPOSITORY / "build/appimage/runtime/runs" / name / "artifact"
    lock = selected_lock(artifact, contract)
    result = fetch_runtime.verify_bundle(artifact, lock)
    output.parent.mkdir(parents=True, exist_ok=True)
    # The complete receipts/materials remain available without another large copy.
    with tempfile.TemporaryDirectory(
        prefix="current-runtime-", dir=output.parent
    ) as temporary:
        selected = Path(temporary) / "selected"
        shutil.copytree(artifact, selected, copy_function=os.link)
        fetch_runtime.verify_bundle(selected, lock)
        selected.rename(output)
    return {
        **result,
        "mode": "current-source",
        "cache": "BUILT",
        "producer": contract["producer"],
        "producer_commit": state["commit"],
        "recipe_fingerprint": state["sha256"],
        "producer_attempt": name,
        "old_tokenlogue_artifacts_used": False,
        "input_acquisition": lock["input_acquisition"],
    }
