#!/usr/bin/env python3
"""Verify locked Python inventory and Linux ELF compatibility reports."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from email.parser import BytesParser
from pathlib import Path
from typing import Sequence

EXPECTED_ANYIO_VERSION = "4.14.2"
MAX_ABI_VERSIONS = {
    "GLIBC": (2, 35),
    "GLIBCXX": (3, 4, 29),
    "CXXABI": (1, 3, 13),
}
REQUIRED_PRODUCTION_PINS = {
    "anyio": "4.14.2",
    "flet": "0.86.5",
    "flet-secure-storage": "0.86.5",
    "httpx": "0.28.1",
}
DEV_ONLY_DISTRIBUTIONS = {
    "flet-cli",
    "flet-desktop",
    "nodeenv",
    "pyright",
    "ruff",
}

# Deliberately empty. Any build-only distribution must be justified here and
# covered by a regression test before it may enter a release bundle.
ALLOWED_BUNDLE_EXTRAS: dict[str, str] = {}

_NORMALIZE_NAME = re.compile(r"[-_.]+")
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)(?:\s*;.*)?$")
_VERSION_REFERENCE = re.compile(r"\((GLIBCXX|GLIBC|CXXABI)_([0-9]+(?:\.[0-9]+)*)\)")
_DYNAMIC_PATH = re.compile(r"\((RPATH|RUNPATH)\).*\[([^]]*)\]")
_NEEDED = re.compile(r"\(NEEDED\).*Shared library: \[([^]]+)\]")
_LABEL = re.compile(r"^[a-z][a-z0-9_-]*$")
_SOURCE_FLUTTER_RUNPATH = "/build/flutter/linux/flutter/ephemeral"
_TCL_LIBRARIES = {"libtcl9tk9.0.so", "libtcl9.0.so"}
# Source-only diagnostic allowance: build_appimage.sh removes this exact JNI
# library from staging before linuxdeploy. Its ABI and ldd checks still apply.
_SOURCE_JNI_LIBRARY = "lib/libdartjni.so"
_SOURCE_JNI_RUNPATH = "/usr/lib/jvm/temurin-11-jdk-amd64/lib/server"
_JAVA_LIBRARIES = {"libdartjni.so", "libjvm.so"}
_JAVA_RUNTIME_PATH = re.compile(
    rb"/(?:[^\x00\s/\"'<>]+/)*(?:jvm|(?:openjdk|jdk|jre)[^\x00\s/\"'<>]*)"
    rb"(?=[/\x00\s\"'<>]|$)"
)


class VerificationError(RuntimeError):
    """A safe, expected verification failure."""


def normalize_distribution_name(name: str) -> str:
    return _NORMALIZE_NAME.sub("-", name).lower()


def read_constraints(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("-", ".", "/", "file:", "git+", "http:", "https:")):
            raise VerificationError(
                f"local, editable, URL, or option requirement at line {line_number}"
            )
        match = _PIN.fullmatch(stripped)
        if match is None:
            raise VerificationError(f"unrecognized constraint at line {line_number}")
        name = normalize_distribution_name(match.group(1))
        version = match.group(2)
        if name in pins:
            raise VerificationError(f"duplicate constraint: {name}")
        pins[name] = version
    return pins


def verify_constraints(path: Path) -> dict[str, str]:
    pins = read_constraints(path)
    for name, expected in REQUIRED_PRODUCTION_PINS.items():
        if pins.get(name) != expected:
            raise VerificationError(f"required production pin mismatch: {name}")
    forbidden = sorted(DEV_ONLY_DISTRIBUTIONS.intersection(pins))
    if forbidden:
        raise VerificationError(
            "development distributions in production constraints: "
            + ", ".join(forbidden)
        )
    if "tokenlogue" in pins:
        raise VerificationError("local project entered production constraints")
    return pins


def read_uv_inventory(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise VerificationError("uv inventory must be a JSON list")
    inventory: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            raise VerificationError("invalid uv inventory entry")
        name_value = item.get("name")
        version_value = item.get("version")
        if not isinstance(name_value, str) or not isinstance(version_value, str):
            raise VerificationError("uv inventory entry lacks name or version")
        name = normalize_distribution_name(name_value)
        if name in inventory:
            raise VerificationError(f"duplicate expected distribution: {name}")
        inventory[name] = version_value
    return inventory


def read_bundle_inventory(bundle: Path) -> dict[str, str]:
    site_packages = bundle / "site-packages"
    if not site_packages.is_dir():
        raise VerificationError("bundle site-packages directory is missing")
    inventory: dict[str, str] = {}
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        metadata_path = dist_info / "METADATA"
        if not metadata_path.is_file():
            raise VerificationError(f"METADATA is missing: {dist_info.name}")
        metadata = BytesParser().parsebytes(metadata_path.read_bytes())
        raw_name = metadata.get("Name")
        version = metadata.get("Version")
        if not raw_name or not version:
            raise VerificationError(f"invalid METADATA: {dist_info.name}")
        name = normalize_distribution_name(raw_name)
        if name in inventory:
            raise VerificationError(f"duplicate bundled distribution: {name}")
        inventory[name] = version
    return inventory


def verify_inventory(
    constraints_path: Path,
    expected_json: Path,
    bundle: Path,
    reports_dir: Path,
) -> dict[str, object]:
    constraints = verify_constraints(constraints_path)
    expected = read_uv_inventory(expected_json)
    bundled = read_bundle_inventory(bundle)
    reports_dir.mkdir(parents=True, exist_ok=True)

    constraint_mismatches = _version_mismatches(constraints, expected)
    constraints_missing_from_environment = sorted(set(constraints).difference(expected))
    environment_missing_from_constraints = sorted(set(expected).difference(constraints))
    missing = sorted(set(expected).difference(bundled))
    unexpected = sorted(
        set(bundled).difference(expected).difference(ALLOWED_BUNDLE_EXTRAS)
    )
    version_mismatches = _version_mismatches(expected, bundled)
    dev_only = sorted(DEV_ONLY_DISTRIBUTIONS.intersection(bundled))
    allowlist_mismatches = sorted(
        name
        for name, version in ALLOWED_BUNDLE_EXTRAS.items()
        if name in bundled and bundled[name] != version
    )
    anyio_ok = (
        expected.get("anyio") == EXPECTED_ANYIO_VERSION
        and bundled.get("anyio") == EXPECTED_ANYIO_VERSION
    )

    ok = (
        not any(
            (
                constraint_mismatches,
                constraints_missing_from_environment,
                environment_missing_from_constraints,
                missing,
                unexpected,
                version_mismatches,
                dev_only,
                allowlist_mismatches,
            )
        )
        and anyio_ok
    )
    comparison: dict[str, object] = {
        "allowlisted_extras": ALLOWED_BUNDLE_EXTRAS,
        "anyio_expected": EXPECTED_ANYIO_VERSION,
        "anyio_ok": anyio_ok,
        "constraint_environment_mismatches": constraint_mismatches,
        "constraints_missing_from_environment": constraints_missing_from_environment,
        "development_distributions": dev_only,
        "environment_missing_from_constraints": environment_missing_from_constraints,
        "missing": missing,
        "ok": ok,
        "unexpected": unexpected,
        "version_mismatches": version_mismatches,
    }

    _write_inventory(
        reports_dir / "expected-packages.json",
        expected,
        "isolated uv production environment synchronized from uv.lock",
    )
    _write_inventory(
        reports_dir / "bundle-packages.json",
        bundled,
        "build/linux/site-packages dist-info METADATA",
    )
    _write_json(reports_dir / "package-comparison.json", comparison)
    if not ok:
        raise VerificationError("bundle package inventory differs from uv.lock")
    return comparison


def _version_mismatches(
    expected: dict[str, str], actual: dict[str, str]
) -> list[dict[str, str]]:
    return [
        {"actual": actual[name], "expected": version, "name": name}
        for name, version in sorted(expected.items())
        if name in actual and actual[name] != version
    ]


def _write_inventory(path: Path, inventory: dict[str, str], source: str) -> None:
    records = [
        {"name": name, "source": source, "version": version}
        for name, version in sorted(inventory.items())
    ]
    _write_json(path, records)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_undefined_abi_versions(output: str) -> dict[str, set[tuple[int, ...]]]:
    versions = {family: set() for family in MAX_ABI_VERSIONS}
    for line in output.splitlines():
        if "*UND*" not in line:
            continue
        for family, version in _VERSION_REFERENCE.findall(line):
            versions[family].add(_version_tuple(version))
    return versions


def parse_dynamic_section(output: str) -> tuple[list[str], list[str]]:
    needed: list[str] = []
    runpaths: list[str] = []
    for line in output.splitlines():
        needed_match = _NEEDED.search(line)
        if needed_match is not None:
            needed.append(needed_match.group(1))
        path_match = _DYNAMIC_PATH.search(line)
        if path_match is not None:
            runpaths.extend(path_match.group(2).split(":"))
    return needed, runpaths


def verify_abi(
    roots: Sequence[tuple[str, Path]], reports_dir: Path, workspace: Path
) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    abi_lines = [
        "Tokenlogue ELF ABI report",
        "gates: GLIBC<=2.35 GLIBCXX<=3.4.29 CXXABI<=1.3.13",
    ]
    rpath_lines = ["Tokenlogue ELF RPATH/RUNPATH report"]
    ldd_lines = ["Tokenlogue ELF ldd report"]

    for label, root in roots:
        resolved_root = root.resolve(strict=True)
        elf_files = _find_elf_files(resolved_root)
        if not elf_files:
            errors.append(f"{label}: no ELF files found")
            continue
        maxima: dict[str, tuple[int, ...]] = {family: () for family in MAX_ABI_VERSIONS}
        abi_lines.append(f"\n[root {label}] ELF files: {len(elf_files)}")
        rpath_lines.append(f"\n[root {label}]")
        ldd_lines.append(f"\n[root {label}]")

        for elf in elf_files:
            relative = elf.relative_to(resolved_root).as_posix()
            dynamic_output = _run_checked(["readelf", "-d", str(elf)])
            needed, runpaths = parse_dynamic_section(dynamic_output)
            symbol_output = _run_checked(["objdump", "-T", str(elf)])
            versions = parse_undefined_abi_versions(symbol_output)
            file_versions: list[str] = []
            for family, found_versions in versions.items():
                if found_versions:
                    file_max = max(found_versions)
                    maxima[family] = max(maxima[family], file_max)
                    file_versions.append(f"{family}_{_version_text(file_max)}")
                    if file_max > MAX_ABI_VERSIONS[family]:
                        errors.append(
                            f"{label}:{relative} requires "
                            f"{family}_{_version_text(file_max)}"
                        )
            abi_lines.append(
                f"{label}:{relative}\t{','.join(file_versions) or 'no-versioned-UND'}"
            )

            rendered_runpaths = ":".join(runpaths) if runpaths else "<none>"
            safe_runpaths = _sanitize_report_text(
                rendered_runpaths,
                workspace=workspace,
                root=resolved_root,
                label=label,
            )
            rpath_lines.append(f"{label}:{relative}\t{safe_runpaths}")
            for entry in runpaths:
                if not entry or not entry.startswith("/"):
                    continue
                if label == "bundle" and entry.endswith(_SOURCE_FLUTTER_RUNPATH):
                    continue
                if (
                    label == "bundle"
                    and relative == _SOURCE_JNI_LIBRARY
                    and entry == _SOURCE_JNI_RUNPATH
                ):
                    rpath_lines.append(
                        f"{label}:{relative}\tsource-only JNI allowance; "
                        "removed from AppImage staging before linuxdeploy"
                    )
                    continue
                errors.append(f"{label}:{relative} has absolute RUNPATH")
            if label != "bundle" and any("build/flutter" in item for item in runpaths):
                errors.append(f"{label}:{relative} retains Flutter build RUNPATH")
            if label != "bundle" and _TCL_LIBRARIES.intersection(needed):
                errors.append(f"{label}:{relative} retains Tcl/Tk dependency")
            if label != "bundle":
                if _JAVA_LIBRARIES.intersection(Path(item).name for item in needed):
                    errors.append(f"{label}:{relative} retains Java dependency")
                if _JAVA_RUNTIME_PATH.search(dynamic_output.encode("utf-8")):
                    errors.append(f"{label}:{relative} retains JDK/JRE path")

            ldd_result = _run_ldd(elf, _library_path(label, resolved_root))
            safe_ldd = _sanitize_report_text(
                ldd_result.stdout + ldd_result.stderr,
                workspace=workspace,
                root=resolved_root,
                label=label,
            )
            ldd_lines.append(f"\n[{label}:{relative}]\n{safe_ldd.rstrip()}")
            if label != "bundle":
                if _JAVA_RUNTIME_PATH.search(safe_ldd.encode("utf-8")):
                    errors.append(f"{label}:{relative} ldd resolves to JDK/JRE path")
                if any(name in safe_ldd for name in _JAVA_LIBRARIES):
                    errors.append(f"{label}:{relative} ldd retains Java dependency")
            missing_libraries = set(
                re.findall(r"^\s*(\S+)\s+=>\s+not found", safe_ldd, re.MULTILINE)
            )
            allowed_source_tcl = (
                label == "bundle"
                and elf.name.startswith("_tkinter.cpython-312-")
                and missing_libraries.issubset(_TCL_LIBRARIES)
            )
            if missing_libraries and not allowed_source_tcl:
                errors.append(
                    f"{label}:{relative} has unresolved libraries: "
                    + ",".join(sorted(missing_libraries))
                )
            if (
                ldd_result.returncode != 0
                and "statically linked" not in safe_ldd
                and "not a dynamic executable" not in safe_ldd
                and not allowed_source_tcl
            ):
                errors.append(f"{label}:{relative} ldd failed")

        for family, maximum in maxima.items():
            rendered = f"{family}_{_version_text(maximum)}" if maximum else "none"
            abi_lines.append(f"{label} maximum {family}: {rendered}")

        if label != "bundle":
            _verify_packaged_root(label, resolved_root, workspace, errors)

    if errors:
        abi_lines.append("\nFAILURES")
        abi_lines.extend(sorted(set(errors)))
    else:
        abi_lines.append("\nresult: PASS")

    _write_lines(reports_dir / "elf-abi.txt", abi_lines)
    _write_lines(reports_dir / "rpaths.txt", rpath_lines)
    _write_lines(reports_dir / "ldd.txt", ldd_lines)
    if errors:
        raise VerificationError("ELF/ABI verification failed")


def _find_elf_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) == b"\x7fELF":
                files.append(path)
    return files


def _run_checked(command: list[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise VerificationError(f"tool failed: {Path(command[0]).name}")
    return result.stdout


def _run_ldd(elf: Path, library_path: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = library_path
    environment.pop("LD_PRELOAD", None)
    return subprocess.run(
        ["ldd", str(elf)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _library_path(label: str, root: Path) -> str:
    if label == "bundle":
        return str(root / "lib")
    return os.pathsep.join(
        (str(root / "usr" / "lib"), str(root / "usr" / "lib" / "tokenlogue" / "lib"))
    )


def _verify_packaged_root(
    label: str, root: Path, workspace: Path, errors: list[str]
) -> None:
    required = (
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "usr/share/doc/tokenlogue/LICENSE",
        "usr/share/doc/tokenlogue/THIRD_PARTY_NOTICES.md",
        "usr/share/applications/io.github.umichata.tokenlogue.desktop",
        "usr/share/metainfo/io.github.umichata.tokenlogue.metainfo.xml",
    )
    for relative in required:
        if not (root / relative).is_file():
            errors.append(f"{label}: required packaged file missing: {relative}")

    if list(root.rglob("_tkinter.cpython-312-*.so")):
        errors.append(f"{label}: _tkinter remains in packaged output")
    if list(root.rglob("*.appdata.xml")):
        errors.append(f"{label}: duplicated AppStream appdata metadata")

    desktop = root / "usr/share/applications/io.github.umichata.tokenlogue.desktop"
    if desktop.is_file():
        desktop_lines = desktop.read_text(encoding="utf-8").splitlines()
        exec_lines = [line for line in desktop_lines if line.startswith("Exec=")]
        if exec_lines != ["Exec=tokenlogue"]:
            errors.append(f"{label}: invalid AppImage desktop Exec")
        if any(line.startswith("TryExec=") for line in desktop_lines):
            errors.append(f"{label}: TryExec remains in AppImage desktop entry")
        if "/usr/bin/tokenlogue" in "\n".join(desktop_lines):
            errors.append(f"{label}: system launcher path remains in desktop entry")

    forbidden_patterns = {
        b"/home/runner": "runner home path",
        b"/tmp/serious_python_temp": "temporary Python build path",
        b"build/flutter": "Flutter build path",
    }
    workspace_bytes = str(workspace).encode("utf-8")
    if workspace_bytes:
        forbidden_patterns[workspace_bytes] = "runner workspace path"
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.name in _JAVA_LIBRARIES:
            errors.append(f"{label}:{relative} is a forbidden Java library")
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).name in _JAVA_LIBRARIES or _JAVA_RUNTIME_PATH.search(
                os.fsencode(target)
            ):
                errors.append(f"{label}:{relative} links to a Java runtime")
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        if _JAVA_RUNTIME_PATH.search(data):
            errors.append(f"{label}:{relative} contains JDK/JRE path")
        for pattern, description in forbidden_patterns.items():
            if pattern in data:
                errors.append(
                    f"{label}:{path.relative_to(root).as_posix()} contains {description}"
                )


def _sanitize_report_text(text: str, workspace: Path, root: Path, label: str) -> str:
    replacements = (
        (str(root), f"<{label.upper()}_ROOT>"),
        (str(workspace), "<WORKSPACE>"),
        ("/home/runner", "<RUNNER_HOME>"),
    )
    for original, replacement in replacements:
        if original:
            text = text.replace(original, replacement)
    return text


def _write_lines(path: Path, lines: Sequence[str]) -> None:
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _version_text(value: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in value)


def _labeled_root(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator or _LABEL.fullmatch(label) is None or not raw_path:
        raise argparse.ArgumentTypeError("root must use label=/absolute/path")
    path = Path(raw_path)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("ELF root path must be absolute")
    return label, path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    constraints_parser = subparsers.add_parser("constraints")
    constraints_parser.add_argument("--constraints", type=Path, required=True)

    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument("--constraints", type=Path, required=True)
    inventory_parser.add_argument("--expected-json", type=Path, required=True)
    inventory_parser.add_argument("--bundle", type=Path, required=True)
    inventory_parser.add_argument("--reports-dir", type=Path, required=True)

    abi_parser = subparsers.add_parser("abi")
    abi_parser.add_argument(
        "--root", type=_labeled_root, action="append", required=True
    )
    abi_parser.add_argument("--reports-dir", type=Path, required=True)
    abi_parser.add_argument("--workspace", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "constraints":
            pins = verify_constraints(args.constraints)
            print(f"verified production constraints: {len(pins)} distributions")
        elif args.command == "inventory":
            verify_inventory(
                args.constraints,
                args.expected_json,
                args.bundle,
                args.reports_dir,
            )
            print("bundle package inventory: PASS")
        else:
            verify_abi(args.root, args.reports_dir, args.workspace.resolve())
            print("ELF/ABI verification: PASS")
    except (OSError, ValueError, json.JSONDecodeError, VerificationError) as error:
        print(f"verify_bundle: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
