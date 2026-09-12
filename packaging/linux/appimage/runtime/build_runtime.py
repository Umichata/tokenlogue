#!/usr/bin/env python3
"""Standalone, manually invoked runtime pipeline; never builds Tokenlogue."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from runtime_checks import (
    compare_runtimes,
    elf_report,
    link_report,
    run_logged,
    smoke_test,
)
from runtime_inputs import (
    Failure,
    Record,
    check_inputs,
    check_inventory,
    digest,
    extract_source,
    fetch_inputs,
    load_lock,
    parse_inventory,
    verify_file,
    write_json,
)

MODULE = Path(__file__).resolve().parent
STAGES = ("fetch", "prepare", "build-one", "build-two", "compare", "verify", "smoke")
RECIPE_NAMES = (
    "Containerfile",
    "README.md",
    "build_runtime.py",
    "runtime_inputs.py",
    "runtime_checks.py",
    "runtime.lock.json",
    "compile.sh",
    "install.sh",
    "patches/runtime-makefile.patch",
)


def recipe_state(repo: Path) -> Record:
    paths = [MODULE / name for name in RECIPE_NAMES]
    paths.append(repo / ".github/workflows/build-appimage-runtime.yml")
    files = []
    dirty = False
    for path in paths:
        name = path.relative_to(repo).as_posix()
        files.append(
            {
                "path": name,
                "sha256": digest(path),
                "size": path.stat().st_size,
                "mode": 0o755 if path.stat().st_mode & 0o111 else 0o644,
            }
        )
        committed = subprocess.run(
            ["git", "show", "HEAD:" + name], cwd=repo, capture_output=True, check=False
        )
        dirty |= (
            committed.returncode != 0
            or hashlib.sha256(committed.stdout).hexdigest() != files[-1]["sha256"]
        )
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    dirty |= bool(
        subprocess.check_output(
            [
                "git",
                "diff",
                "HEAD",
                "--name-only",
                "--",
                *(item["path"] for item in files),
            ],
            cwd=repo,
            text=True,
        ).strip()
    )
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=repo,
        text=True,
    )
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {
        "commit": commit,
        "dirty": dirty,
        "worktree_dirty": bool(status),
        "sha256": fingerprint,
        "files": files,
    }


def record_stage(run: Path, stage: str, value: Record, recipe: Record | None) -> None:
    if recipe is not None:
        value["recipe_sha256"] = recipe["sha256"]
    write_json(run / "reports" / (stage + ".json"), value)


def required_stages(
    run: Path, names: tuple[str, ...], recipe_hash: str
) -> dict[str, Record]:
    result = {}
    for name in names:
        path = run / "reports" / (name + ".json")
        if not path.is_file():
            raise Failure(f"Mandatory stage NOT_RUN: {name}")
        value = json.loads(path.read_text())
        if value.get("result") != "PASS" or value.get("recipe_sha256") != recipe_hash:
            raise Failure(f"Mandatory stage not PASS for this recipe: {name}")
        result[name] = value
    return result


def engine_command(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise Failure(
            f"{name} is unavailable; container builds and runtime execution NOT_RUN"
        )
    return executable


def image_id(engine: str, reference: str) -> str:
    result = subprocess.run(
        [engine, "image", "inspect", "--format", "{{.Id}}", reference],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or not re.fullmatch(
        r"sha256:[a-f0-9]{64}", result.stdout.strip()
    ):
        raise Failure("Required container image is not available locally")
    return result.stdout.strip()


def container_run(
    engine: str,
    image: str,
    recipe: Path,
    inputs: Path,
    work: Path,
    mount_at: str,
    command: list[str],
    log: Path,
    environment: dict[str, str],
    extra_mounts: list[tuple[Path, str]] | None = None,
) -> None:
    if os.getuid() == 0:
        raise Failure(
            "Run the pipeline from a normal host UID; compilation cannot run as root"
        )
    name = "tokenlogue-runtime-" + uuid.uuid4().hex
    args = [
        engine,
        "run",
        "--rm",
        "--name",
        name,
        "--pull=never",
        "--platform",
        "linux/amd64",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--pids-limit",
        "256",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "--workdir",
        mount_at,
    ]
    for path, target, readonly in [
        (recipe, "/recipe", True),
        (inputs, "/inputs", True),
        (work, mount_at, False),
        *((p, t, True) for p, t in (extra_mounts or [])),
    ]:
        if "," in str(path):
            raise Failure("Container mount paths cannot contain commas")
        args += [
            "--mount",
            f"type=bind,src={path},dst={target}" + (",readonly" if readonly else ""),
        ]
    for key, value in environment.items():
        args += ["--env", key + "=" + value]
    args += [image, *command]
    try:
        run_logged(args, log, timeout=1800)
    finally:
        # This unique container belongs to this invocation. Cleanup must run even
        # on timeout/report errors, without replacing the primary failure.
        try:
            subprocess.run(
                [engine, "rm", "--force", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            print(f"Cleanup could not confirm removal of {name}", file=sys.stderr)


def prepare_builder(
    engine: str, lock: Record, inputs: Path, run: Path, recipe: Record
) -> Record:
    fetched = required_stages(run, ("fetch",), recipe["sha256"])["fetch"]
    base = fetched.get("local_base")
    if base is None:
        raise Failure(
            "Image pull NOT_RUN (fetch --inputs-only cannot prepare a builder)"
        )
    config_pin = next(
        item["sha256"]
        for item in lock["files"]
        if item["path"] == lock["builder"]["config"]
    )
    if image_id(engine, base) != "sha256:" + config_pin:
        raise Failure("Locally cached base image config mismatch")
    tag = (
        "tokenlogue-runtime-builder:"
        + hashlib.sha256(str(run).encode()).hexdigest()[:24]
    )
    # A minimal context includes no repository, .git, user files or host caches.
    with tempfile.TemporaryDirectory(prefix="context-", dir=run) as temporary:
        context = Path(temporary)
        locked = context / "locked"
        (locked / "apks").mkdir(parents=True)
        checksums = []
        by_path = {item["path"]: item for item in lock["files"]}
        for package in lock["packages"]:
            path = package["path"]
            shutil.copyfile(inputs / path, locked / path)
            checksums.append(by_path[path]["sha256"] + "  " + path)
        (locked / "SHA256SUMS").write_text("\n".join(checksums) + "\n")
        write_json(locked / "base.json", lock["builder"]["inherited_packages"])
        write_json(locked / "installed.json", lock["installed_inventory"])
        for name in ("install.sh", "runtime_inputs.py"):
            shutil.copyfile(MODULE / name, locked / name)
        shutil.copyfile(MODULE / "Containerfile", context / "Containerfile")
        environment = os.environ.copy()
        if Path(engine).name == "docker":
            # Legacy Docker resolves this inspected local tag without BuildKit's
            # registry metadata resolution. No remote frontend is requested.
            environment["DOCKER_BUILDKIT"] = "0"
            pull = "--pull=false"
        else:
            pull = "--pull=never"
        run_logged(
            [
                engine,
                "build",
                "--network=none",
                pull,
                "--no-cache",
                "--build-arg",
                "BUILDER=" + base,
                "--tag",
                tag,
                "--file",
                str(context / "Containerfile"),
                str(context),
            ],
            run / "reports/prepare.log",
            env=environment,
            timeout=1200,
        )
    identifier = image_id(engine, tag)
    evidence = run / "builder-evidence"
    evidence.mkdir()
    container_run(
        engine,
        identifier,
        MODULE,
        inputs,
        evidence,
        "/evidence",
        ["/bin/sh", "-c", "cp /opt/runtime-evidence/* /evidence/"],
        run / "reports/builder-evidence.log",
        {},
    )
    check_inventory(
        parse_inventory((evidence / "installed").read_text()),
        lock["installed_inventory"],
    )
    inventory = json.loads((evidence / "inventory.json").read_text())
    if inventory["result"] != "PASS" or inventory["apk_signatures"] != "PASS":
        raise Failure("APK signature verification or installed inventory failed")
    return {
        "result": "PASS",
        "image_id": identifier,
        "base_config": "sha256:" + config_pin,
        "apk_signatures": "PASS",
        "inventory": "PASS",
    }


def build_one(
    engine: str,
    lock: Record,
    inputs: Path,
    run: Path,
    recipe: Record,
    name: str,
    environment: dict[str, str],
) -> Record:
    prepared = required_stages(run, ("prepare",), recipe["sha256"])["prepare"]
    work = run / name
    work.mkdir()
    container_run(
        engine,
        prepared["image_id"],
        MODULE,
        inputs,
        work,
        "/" + name,
        ["python3", "/recipe/build_runtime.py", "inside-build", "/" + name],
        work / "reports/build.log",
        environment,
    )
    runtime = work / "runtime-x86_64"
    return {
        "result": "PASS",
        "sha256": digest(runtime),
        "size": runtime.stat().st_size,
        "work_directory": name,
        "independent_container": True,
    }


def make_bundle(
    repo: Path, inputs: Path, run: Path, lock: Record, recipe: Record
) -> Record:
    stages = required_stages(run, STAGES, recipe["sha256"])
    runtime = run / "build-one/runtime-x86_64"
    actual = digest(runtime)
    if (
        actual != stages["build-one"]["sha256"]
        or actual != stages["smoke"]["runtime_sha256"]
    ):
        raise Failure("Runtime changed after build/test")
    if digest(run / "build-two/runtime-x86_64") != actual:
        raise Failure("Second runtime changed after comparison")
    output = run / "artifact"
    output.mkdir()
    materials = output / "materials"
    check_inputs(lock, inputs, materials)
    for item in lock["files"]:
        target = materials / "inputs" / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(inputs / item["path"], target)
    for item in recipe["files"]:
        target = materials / "recipe" / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / item["path"], target)
        target.chmod(item["mode"])
    shutil.copyfile(runtime, output / "runtime-x86_64")
    (output / "runtime-x86_64").chmod(0o755)
    shutil.copyfile(MODULE / "runtime.lock.json", output / "runtime.lock.json")
    for name in ("reports", "builder-evidence"):
        shutil.copytree(run / name, output / "reports" / name)
    for name in ("build-one", "build-two"):
        shutil.copytree(run / name / "reports", output / "reports" / name)
        shutil.copytree(
            run / name / "linked-inputs", materials / "linked-inputs" / name
        )
        shutil.copyfile(
            run / name / "runtime-x86_64.debug",
            output / "reports" / name / "runtime-x86_64.debug",
        )
    for path in (run / "smoke").glob("*.log"):
        target = output / "reports/smoke" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    coverage = json.loads((run / "build-one/reports/linked-inputs.json").read_text())
    manifest: Record = {
        "schema": 1,
        "result": "PASS",
        "runtime": {
            "path": "runtime-x86_64",
            "sha256": actual,
            "size": runtime.stat().st_size,
        },
        "upstream_source_commit": lock["upstream"]["commit"],
        "tokenlogue_recipe": recipe,
        "builder": lock["builder"],
        "prepared_image_id": stages["prepare"]["image_id"],
        "source_date_epoch": lock["source_date_epoch"],
        "runtime_source_materials": coverage,
        "source_materials": lock["source_materials"],
        "checks": stages,
        "files": [
            {
                "path": p.relative_to(output).as_posix(),
                "size": p.stat().st_size,
                "sha256": digest(p),
            }
            for p in sorted(output.rglob("*"))
            if p.is_file()
        ],
    }
    write_json(output / "manifest.json", manifest)
    (output / "SHA256SUMS").write_text(
        "".join(
            f"{digest(p)}  {p.relative_to(output).as_posix()}\n"
            for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "SHA256SUMS"
        )
    )
    return {
        "result": "PASS",
        "artifact": "artifact",
        "runtime_sha256": actual,
        "runtime_source_materials": coverage["result"],
    }


def inside(command: str, work: Path) -> None:
    if command not in {"inside-build", "inside-link", "inside-verify", "inside-smoke"}:
        raise Failure("Unknown internal stage")
    lock = load_lock(MODULE / "runtime.lock.json")
    inputs = Path("/inputs")
    if command == "inside-build":
        if os.getuid() == 0:
            raise Failure("Compilation must use a normal UID")
        check_inputs(lock, inputs)
        (work / "sources").mkdir()
        for component in lock["components"]:
            if component["name"] not in {"type2-runtime", "libfuse", "squashfuse"}:
                continue
            unpack = work / ("unpack-" + component["name"])
            extract_source(
                inputs / component["source"], unpack, lock["source_date_epoch"]
            )
            shutil.move(
                str(unpack / component["root"]), work / "sources" / component["root"]
            )
            unpack.rmdir()
        subprocess.run(["bash", "/recipe/compile.sh"], cwd=work, check=True)
    elif command == "inside-link":
        link_report(
            work,
            work / "sources" / lock["upstream"]["root"] / "src/runtime",
            lock,
            inputs,
        )
    elif command == "inside-verify":
        runtime = work / "runtime-x86_64"
        report = elf_report(runtime, [str(work)])
        run_logged(
            [str(runtime), "--appimage-version"], work / "reports/version.txt", cwd=work
        )
        if (
            os.environ["RUNTIME_VERSION"]
            not in (work / "reports/version.txt").read_text()
        ):
            raise Failure(
                "Runtime version does not identify this upstream commit/recipe"
            )
        write_json(work / "reports/elf.json", report)
    elif command == "inside-smoke":
        item = next(
            i for i in lock["files"] if i["path"] == lock["appimagetool"]["path"]
        )
        tool = inputs / item["path"]
        verify_file(tool, item)
        # Keep cached inputs read-only, including their file modes.
        local_tool = work / "appimagetool"
        shutil.copyfile(tool, local_tool)
        local_tool.chmod(0o755)
        write_json(
            work / "smoke.json",
            smoke_test(Path("/runtime/runtime-x86_64"), local_tool, work),
        )


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1].startswith("inside-"):
        inside(sys.argv[1], Path(sys.argv[2]))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "verify-inputs", *STAGES, "bundle"))
    parser.add_argument(
        "--run",
        required=True,
        help="New attempt name; existing results are never overwritten",
    )
    parser.add_argument("--engine", choices=("docker", "podman"), default="docker")
    parser.add_argument(
        "--inputs-only",
        action="store_true",
        help="fetch/check files without claiming native APK verification",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run):
        parser.error("Invalid run name")
    repo = MODULE.parents[3]
    root = repo / "build/appimage/runtime"
    inputs = root / "inputs"
    run = root / "runs" / args.run
    stage = args.command
    recipe: Record | None = None
    try:
        lock = load_lock(MODULE / "runtime.lock.json")
        recipe = recipe_state(repo)
        if stage == "init":
            run.mkdir(parents=True)
            write_json(run / "recipe.json", recipe)
            write_json(
                run / "reports/initial-status.json",
                {name: "NOT_RUN" for name in STAGES},
            )
            result: Record = {
                "result": "PASS",
                "recipe": recipe,
                "source_materials": lock["source_materials"],
            }
        else:
            saved = json.loads((run / "recipe.json").read_text())
            if recipe != saved:
                raise Failure("Recipe/Git state changed; initialize a new run")
            if (run / "reports" / (stage + ".json")).exists():
                raise Failure(
                    "Stage already attempted; initialize a new run to preserve evidence"
                )
            if stage == "fetch":
                fetch_inputs(lock, inputs)
            result = (
                check_inputs(lock, inputs, run / "input-materials")
                if stage in {"fetch", "verify-inputs"}
                else {"result": "PASS"}
            )
            environment = {
                "SOURCE_DATE_EPOCH": str(lock["source_date_epoch"]),
                "LC_ALL": "C",
                "TZ": "UTC",
                "RUNTIME_VERSION": "tokenlogue-unofficial-"
                + lock["upstream"]["commit"]
                + "-recipe-"
                + recipe["sha256"],
            }
            if stage == "fetch" and not args.inputs_only:
                engine = engine_command(args.engine)
                reference = lock["builder"]["reference"]
                run_logged(
                    [engine, "pull", "--platform", "linux/amd64", reference],
                    run / "reports/pull.log",
                    timeout=600,
                )
                actual = image_id(engine, reference)
                expected = next(
                    i["sha256"]
                    for i in lock["files"]
                    if i["path"] == lock["builder"]["config"]
                )
                if actual != "sha256:" + expected:
                    raise Failure("Pulled image config differs from locked manifest")
                local = (
                    "tokenlogue-runtime-base:"
                    + lock["builder"]["digest"].split(":")[1][:32]
                )
                subprocess.run([engine, "tag", reference, local], check=True)
                result["local_base"] = local
                run_logged([engine, "version"], run / "reports/engine-version.txt")
            elif stage == "prepare":
                check_inputs(lock, inputs)
                result = prepare_builder(
                    engine_command(args.engine), lock, inputs, run, recipe
                )
            elif stage in {"build-one", "build-two"}:
                result = build_one(
                    engine_command(args.engine),
                    lock,
                    inputs,
                    run,
                    recipe,
                    stage,
                    environment,
                )
            elif stage == "compare":
                required_stages(run, ("build-one", "build-two"), recipe["sha256"])
                try:
                    result = compare_runtimes(
                        run / "build-one/runtime-x86_64",
                        run / "build-two/runtime-x86_64",
                    )
                except Failure:
                    try:
                        first = (run / "build-one/reports/readelf.txt").read_text()
                        second = (run / "build-two/reports/readelf.txt").read_text()
                        (run / "reports/readelf-difference.txt").write_text(
                            "".join(
                                difflib.unified_diff(
                                    first.splitlines(True),
                                    second.splitlines(True),
                                    fromfile="build-one",
                                    tofile="build-two",
                                )
                            )
                        )
                    except OSError as diagnostic_error:
                        print(
                            f"Could not write comparison diagnostics: {diagnostic_error}",
                            file=sys.stderr,
                        )
                    raise
            elif stage in {"verify", "smoke"}:
                dependencies = (
                    ("prepare", "build-one", "build-two")
                    if stage == "verify"
                    else ("prepare", "compare", "verify")
                )
                prepared = required_stages(run, dependencies, recipe["sha256"])[
                    "prepare"
                ]
                engine = engine_command(args.engine)
                if stage == "verify":
                    for name in ("build-one", "build-two"):
                        container_run(
                            engine,
                            prepared["image_id"],
                            MODULE,
                            inputs,
                            run / name,
                            "/" + name,
                            [
                                "python3",
                                "/recipe/build_runtime.py",
                                "inside-verify",
                                "/" + name,
                            ],
                            run / name / "reports/verify.log",
                            environment,
                        )
                    result = {
                        "result": "PASS",
                        "builds": [
                            json.loads((run / name / "reports/elf.json").read_text())
                            for name in ("build-one", "build-two")
                        ],
                    }
                else:
                    work = run / "smoke"
                    work.mkdir()
                    container_run(
                        engine,
                        prepared["image_id"],
                        MODULE,
                        inputs,
                        work,
                        "/smoke",
                        [
                            "python3",
                            "/recipe/build_runtime.py",
                            "inside-smoke",
                            "/smoke",
                        ],
                        work / "smoke.log",
                        environment,
                        [(run / "build-one/runtime-x86_64", "/runtime/runtime-x86_64")],
                    )
                    result = json.loads((work / "smoke.json").read_text())
            elif stage == "bundle":
                result = make_bundle(repo, inputs, run, lock, recipe)
        record_stage(run, stage, result, recipe)
        print(f"{stage}: {result['result']}")
        return 0
    except (
        Failure,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
    ) as error:
        message = str(error)
        print(f"{stage}: FAIL: {message}", file=sys.stderr)
        try:
            if not (run / "reports" / (stage + ".json")).exists():
                record_stage(run, stage, {"result": "FAIL", "reason": message}, recipe)
        except OSError as report_error:
            print(f"Could not write failure report: {report_error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
