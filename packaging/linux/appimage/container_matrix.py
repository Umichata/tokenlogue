"""Container userspace diagnostics for an already verified AppImage (stdlib only)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from source_artifact import (  # pyright: ignore[reportMissingImports]
    VerificationError,
    digest,
    require,
    validate_inputs,
)

HERE = Path(__file__).resolve().parent
SMOKE_FUNCTIONS = (
    "die",
    "run_inner",
    "find_tokenlogue_window",
    "count_log_matches",
    "collect_diagnostics",
    "stop_owned_process",
    "save_diagnostic_logs",
)
REPORT_FILES = (
    "desktop-modules.json",
    "smoke-application.stderr.txt",
    "smoke-sandbox.stderr.txt",
    "smoke-xvfb.stderr.txt",
    "smoke-window-search.txt",
    "smoke-window-properties.txt",
    "smoke-window-state.txt",
    "container-summary.json",
    "system-packages.txt",
    "os-release.txt",
)


def smoke_library(source: Path, destination: Path) -> None:
    """Reuse exact function bodies without evaluating the original entry point.

    The original script's top-level functions use unindented closing braces.
    Fail closed if this export contract changes; never source its outer runner.
    """
    text = source.read_text(encoding="utf-8")
    chunks = []
    for name in SMOKE_FUNCTIONS:
        matches = re.findall(rf"(?ms)^{name}\(\) \{{\n.*?^\}}\n", text)
        require(len(matches) == 1, f"smoke function export changed: {name}")
        chunks.append(matches[0])
    destination.write_text(
        "# Generated from the unchanged build smoke script.\n" + "\n".join(chunks),
        encoding="utf-8",
    )
    subprocess.run(["bash", "-n", str(destination)], check=True)


def cleanup_container_processes() -> dict[str, Any]:
    """Only inside our disposable container: reap its non-root test processes."""
    require(
        Path("/run/tokenlogue-matrix-container").is_file(), "not a matrix container"
    )
    require(os.getuid() == 10001, "unexpected container user")
    protected = {1}
    pid = os.getpid()
    while pid > 1 and pid not in protected:
        protected.add(pid)
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        pid = int(fields[1])

    def live() -> list[int]:
        result = []
        for path in Path("/proc").iterdir():
            if not path.name.isdigit() or int(path.name) in protected:
                continue
            try:
                if path.stat().st_uid == os.getuid():
                    state = (path / "stat").read_text().rsplit(")", 1)[1].split()[0]
                    if state != "Z":
                        result.append(int(path.name))
            except FileNotFoundError:
                continue
        return result

    before = live()
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in live():
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 2
        while live() and time.monotonic() < deadline:
            time.sleep(0.05)
    remaining = live()
    return {
        "cleanup": "PASS" if not remaining else "FAIL",
        "remaining_processes": len(remaining),
        "processes_stopped": len(before),
    }


def evaluate(evidence: dict[str, Any], exit_code: int) -> tuple[str, str]:
    if not evidence:
        return "BLOCKED", "container diagnostics unavailable"
    if evidence.get("result") == "BLOCKED":
        return "BLOCKED", str(evidence.get("reason", "environment unavailable"))
    required = {
        "desktop_modules": "PASS",
        "window_check": "PASS",
        "window_map_state": "IsViewable",
        "af_inet_socket_calls": "0",
        "af_inet_connect_calls": "0",
        "fatal_diagnostics": "0",
        "cleanup": "PASS",
        "remaining_processes": 0,
        "exit_code": "124",
        "result": "PASS",
        "hash_check": "PASS",
    }
    if exit_code != 0:
        return "FAIL", "container command failed"
    for key, value in required.items():
        if evidence.get(key) != value:
            return "FAIL", f"missing or unsuccessful evidence: {key}"
    elapsed = evidence.get("elapsed_seconds")
    if not isinstance(elapsed, int) or isinstance(elapsed, bool) or elapsed < 20:
        return "FAIL", "expected timeout lifetime was not observed"
    return "PASS", "container userspace launch checks passed"


def run_command(args: list[str], log: Path, timeout: int = 120) -> str:
    with log.open("ab") as output:
        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=output, timeout=timeout, check=False
        )
        output.write(result.stdout)
    if result.returncode:
        raise VerificationError(
            f"{args[0]} {args[1]} failed (exit {result.returncode})"
        )
    return result.stdout.decode("utf-8")


def run_matrix(
    distribution: str,
    source: Path,
    reports: Path,
    expected_hash: str,
    commit: str,
    run_id: str,
    infrastructure: str,
) -> int:
    reports.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "result": "BLOCKED",
        "reason": "environment not prepared",
        "distribution": distribution,
        "source_commit": commit,
        "source_run_id": run_id,
        "infrastructure_commit": infrastructure,
        "mode": "container / extract-and-run / Xvfb / software GL",
        "window_check": "NOT_RUN",
        "process_check": "NOT_RUN",
        "network_check": "NOT_RUN",
        "container_cleanup": "NOT_RUN",
    }
    container = "tokenlogue-matrix-" + uuid.uuid4().hex
    created = False
    target: Path | None = None
    code = 1
    try:
        validate_inputs(run_id, commit, infrastructure)
        require(
            bool(re.fullmatch(r"[0-9a-f]{64}", expected_hash)),
            "invalid expected SHA-256",
        )
        require(shutil.which("docker") is not None, "Docker unavailable; no fallback")
        images = json.loads((HERE / "container-images.lock.json").read_text())["images"]
        require(distribution in images, "unknown distribution")
        image = images[distribution]
        base = image["tag"].split(":")[0] + "@" + image["digest"]
        require(
            bool(
                re.fullmatch(
                    r"docker.io/library/(ubuntu|fedora)@sha256:[0-9a-f]{64}", base
                )
            ),
            "invalid pinned base image",
        )
        report.update(image_digest=image["digest"], base_image=image["tag"])
        provenance = json.loads((source / "provenance.json").read_text())
        require(
            provenance["source_commit"] == commit
            and provenance["source_run_id"] == run_id,
            "source provenance mismatch",
        )
        require(
            provenance["infrastructure_commit"] == infrastructure,
            "infrastructure provenance mismatch",
        )
        filename = provenance["filename"]
        require(
            bool(
                re.fullmatch(
                    r"Tokenlogue-\d+\.\d+\.\d+-" + commit[:7] + r"-x86_64\.AppImage",
                    filename,
                )
            ),
            "invalid verified filename",
        )
        target = source / filename
        assert isinstance(target, Path)
        require(
            not target.is_symlink() and len(list(source.glob("*.AppImage"))) == 1,
            "one regular verified AppImage required",
        )
        require(
            digest(target) == expected_hash == provenance["sha256"],
            "pre-test SHA-256 mismatch",
        )
        report.update(
            artifact_id=provenance["artifact_id"],
            sha256_before=expected_hash,
            size=target.stat().st_size,
            filename=filename,
        )
        # Restrict the build context; never send the repository, caches or data to Docker.
        with tempfile.TemporaryDirectory(prefix="matrix-context-") as temp:
            context = Path(temp)
            for name in (
                "Containerfile.matrix",
                "source_artifact.py",
                "container_matrix.py",
                "container_smoke.sh",
                "smoke_appimage.sh",
                "desktop_runtime.py",
            ):
                shutil.copyfile(HERE / name, context / name)
            run_command(
                [
                    "docker",
                    "build",
                    "--platform",
                    "linux/amd64",
                    "--no-cache",
                    "--build-arg",
                    f"BASE_IMAGE={base}",
                    "-t",
                    container,
                    "-f",
                    str(context / "Containerfile.matrix"),
                    str(context),
                ],
                reports / "environment-build.txt",
                1500,
            )
        # No host HOME, socket, credentials or runner libraries are mounted.
        # SYS_PTRACE enables strace of descendants under Docker's default seccomp policy.
        # A daemon may create the container even if the client subsequently times out.
        created = True
        run_command(
            [
                "docker",
                "create",
                "--name",
                container,
                "--platform",
                "linux/amd64",
                "--init",
                "--network",
                "none",
                "--user",
                "10001:10001",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "SYS_PTRACE",
                "--security-opt",
                "no-new-privileges=true",
                "--pids-limit",
                "256",
                "--memory",
                "2g",
                "--cpus",
                "2",
                "--ulimit",
                "core=0:0",
                "--mount",
                f"type=bind,source={target.resolve()},target=/input/Tokenlogue.AppImage,readonly",
                container,
                expected_hash,
                image["os_id"],
                image["version_id"],
            ],
            reports / "container-control.txt",
        )
        run_command(["docker", "start", container], reports / "container-control.txt")
        exit_text = run_command(
            ["docker", "wait", container], reports / "container-control.txt", 100
        )
        exit_code = int(exit_text.strip())
        report["container_exit_code"] = exit_code
        # Copy only fixed diagnostic paths. Raw traces and application data stay inside.
        for name in REPORT_FILES:
            run_command(
                ["docker", "cp", f"{container}:/reports/{name}", str(reports / name)],
                reports / "container-control.txt",
            )
        evidence = json.loads((reports / "container-summary.json").read_text())
        result, reason = evaluate(evidence, exit_code)
        report.update(
            result=result,
            reason=reason,
            window_check=evidence.get("window_check", "NOT_RUN"),
            process_check=evidence.get("exit_code", "NOT_RUN"),
            network_check=evidence.get("af_inet_socket_calls", "NOT_RUN"),
            evidence=evidence,
        )
        code = 0 if result == "PASS" else 1
    except VerificationError as error:
        report["reason"] = str(error)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        report["reason"] = "environment or diagnostic operation unavailable"
    finally:
        # Also recover available diagnostics after early launch/observation failure.
        if created:
            try:
                run_command(
                    ["docker", "logs", container], reports / "container-launch.txt"
                )
                state = run_command(
                    ["docker", "inspect", "--format", "{{json .State}}", container],
                    reports / "container-control.txt",
                )
                (reports / "container-state.json").write_text(state, encoding="utf-8")
                state_data = json.loads(state)
                require(
                    state_data.get("Running") is False, "container is still running"
                )
                require(
                    state_data.get("OOMKilled") is False, "container was OOM killed"
                )
            except (OSError, ValueError, subprocess.SubprocessError):
                report["container_launch_diagnostics"] = "UNAVAILABLE"
                if code == 0:
                    code = 1
                    report.update(
                        result="FAIL", reason="container state/logs not confirmed"
                    )
            for name in REPORT_FILES:
                if not (reports / name).exists():
                    try:
                        run_command(
                            [
                                "docker",
                                "cp",
                                f"{container}:/reports/{name}",
                                str(reports / name),
                            ],
                            reports / "container-control.txt",
                        )
                    except (OSError, ValueError, subprocess.SubprocessError):
                        (reports / name).write_text("NOT_CAPTURED\n")
            try:
                run_command(
                    ["docker", "rm", "--force", container],
                    reports / "container-control.txt",
                )
                remaining = run_command(
                    ["docker", "ps", "-aq", "--filter", f"name=^/{container}$"],
                    reports / "container-control.txt",
                )
                require(not remaining.strip(), "test container still exists")
                report["container_cleanup"] = "PASS"
            except (OSError, ValueError, subprocess.SubprocessError):
                report.update(
                    result="FAIL",
                    reason="container cleanup not confirmed",
                    container_cleanup="FAIL",
                )
                code = 1
        if target is not None and target.is_file():
            after = digest(target)
            report["sha256_after"] = after
            if after != expected_hash:
                report.update(result="FAIL", reason="post-test SHA-256 mismatch")
                code = 1
        for name in REPORT_FILES:
            if not (reports / name).exists():
                (reports / name).write_text("NOT_CAPTURED\n")
        package_report = reports / "system-packages.txt"
        packages = package_report.read_text(encoding="utf-8")
        report["package_inventory"] = (
            "NOT_CAPTURED"
            if packages == "NOT_CAPTURED\n"
            else {
                "file": package_report.name,
                "sha256": digest(package_report),
                "entries": len(packages.splitlines()),
            }
        )
        report["os_release"] = (reports / "os-release.txt").read_text(encoding="utf-8")
        (reports / "matrix-summary.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(summary, "a", encoding="utf-8") as output:
                output.write(
                    f"### {distribution}\n\n```json\n"
                    + json.dumps(report, indent=2)
                    + "\n```\n"
                )
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    library = commands.add_parser("library")
    library.add_argument("source", type=Path)
    library.add_argument("output", type=Path)
    commands.add_parser("cleanup")
    test = commands.add_parser("test")
    test.add_argument("--distribution", required=True)
    test.add_argument("--source", type=Path, required=True)
    test.add_argument("--reports", type=Path, required=True)
    test.add_argument("--sha256", required=True)
    test.add_argument("--source-commit", required=True)
    test.add_argument("--source-run-id", required=True)
    test.add_argument("--infrastructure-commit", required=True)
    args = parser.parse_args()
    if args.command == "library":
        smoke_library(args.source, args.output)
        return 0
    if args.command == "cleanup":
        print(json.dumps(cleanup_container_processes()))
        return 0
    return run_matrix(
        args.distribution,
        args.source,
        args.reports,
        args.sha256,
        args.source_commit,
        args.source_run_id,
        args.infrastructure_commit,
    )


if __name__ == "__main__":
    raise SystemExit(main())
