"""ELF, reproducibility, link evidence and minimal AppImage checks."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from runtime_inputs import Failure, Record, digest, tar_members, write_json


def elf_report(path: Path, forbidden_paths: list[str] | None = None) -> Record:
    data = path.read_bytes()
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise Failure("Runtime is not ELF64 little-endian")
    if data[8:11] != b"AI\x02":
        raise Failure("AppImage type-2 magic is missing at offset 8")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    (
        _,
        kind,
        machine,
        version,
        entry,
        phoff,
        shoff,
        _,
        ehsize,
        phsize,
        phnum,
        shsize,
        shnum,
        shstr,
    ) = header
    if (kind, machine, version, ehsize, phsize, shsize) != (3, 62, 1, 64, 56, 64):
        raise Failure("Runtime is not x86-64 ET_DYN/static PIE")
    if not phnum or phoff + phnum * phsize > len(data):
        raise Failure("Truncated ELF program headers")
    if not shnum or shoff + shnum * shsize > len(data) or shstr >= shnum:
        raise Failure("Truncated ELF section headers")
    dynamic = []
    executable_entry = False
    for index in range(phnum):
        ptype, flags, offset, address, _, size, memory_size, _ = struct.unpack_from(
            "<IIQQQQQQ", data, phoff + index * phsize
        )
        if offset + size > len(data) or (ptype == 1 and memory_size < size):
            raise Failure("Truncated/invalid ELF segment")
        if ptype == 3:
            raise Failure("Runtime has PT_INTERP")
        if ptype == 1 and flags & 1 and address <= entry < address + memory_size:
            executable_entry = True
        if ptype == 2:
            if size % 16:
                raise Failure("Invalid ELF dynamic segment")
            for position in range(offset, offset + size, 16):
                tag, value = struct.unpack_from("<qQ", data, position)
                if tag == 0:
                    break
                dynamic.append((tag, value))
    if not executable_entry:
        raise Failure("ELF entry is outside executable load segments")
    if any(tag == 1 for tag, _ in dynamic):
        raise Failure("Runtime has DT_NEEDED")
    if not any(tag == 0x6FFFFFFB and value & 0x08000000 for tag, value in dynamic):
        raise Failure("ELF has no DF_1_PIE flag")
    sections = [
        struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shsize)
        for i in range(shnum)
    ]
    strings = sections[shstr]
    if strings[4] + strings[5] > len(data):
        raise Failure("Invalid ELF section name table")
    names = data[strings[4] : strings[4] + strings[5]]
    named_sections = {}
    for section in sections:
        name_offset, stype, _, _, offset, size, _, _, _, _ = section
        if name_offset >= len(names) or (stype != 8 and offset + size > len(data)):
            raise Failure("Truncated ELF section")
        name = names[name_offset:].split(b"\0", 1)[0].decode("ascii")
        named_sections[name] = {"offset": offset, "size": size}
        if name == ".interp" or (stype == 0x6FFFFFFE and size):
            raise Failure("ELF contains interpreter/version requirements")
    if b"GLIBC_" in data:
        raise Failure("Runtime contains GLIBC requirements")
    forbidden = [
        "/home/",
        "/Users/",
        "/__w/",
        "/build-one/",
        "/build-two/",
        "/tmp/cc",
        "/tmp/runtime-build-",
    ]
    for text in forbidden + (forbidden_paths or []):
        if text.encode() in data:
            raise Failure(f"Build/user path remains in runtime: {text}")
    return {
        "result": "PASS",
        "format": "ELF64 little-endian x86-64 static PIE",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sections": named_sections,
        "PT_INTERP": False,
        "DT_NEEDED": False,
        "GLIBC": False,
    }


def compare_runtimes(first: Path, second: Path) -> Record:
    records = [{"size": p.stat().st_size, "sha256": digest(p)} for p in (first, second)]
    if first.resolve() == second.resolve() or os.path.samefile(first, second):
        raise Failure("Two independent runtime files are required")
    if first.read_bytes() != second.read_bytes():
        raise Failure(
            f"Runtime mismatch: first={records[0]['sha256']}; second={records[1]['sha256']}"
        )
    return {"result": "PASS", "byte_identical": True, "builds": records}


def check_appimage_prefix(runtime: Path, appimage: Path) -> None:
    report = elf_report(runtime)
    expected = bytearray(runtime.read_bytes())
    with appimage.open("rb") as stream:
        actual = bytearray(stream.read(len(expected)))
    section = report["sections"].get(".digest_md5")
    if section is None or section["size"] != 16:
        raise Failure("Runtime lacks the expected AppImage digest section")
    start = section["offset"]
    expected[start : start + 16] = b"\0" * 16
    actual[start : start + 16] = b"\0" * 16
    if actual != expected:
        raise Failure("Test AppImage does not embed the newly built runtime")


def run_logged(
    command: list[str],
    log: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as output:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise Failure(f"Command timed out; see {log.name}") from None
    if result.returncode:
        raise Failure(f"Command failed (exit {result.returncode}); see {log.name}")


STUB = """#!/bin/sh
set -eu
test "$#" -eq 4
test "$1" = '--flag'
test "$2" = 'space argument'
test "$3" = ''
test "$4" = 'кириллица'
printf 'runtime-arguments-ok\\n' > "${RUNTIME_TEST_MARKER:?}"
"""
SMOKE_ARGUMENTS = ["--flag", "space argument", "", "кириллица"]


def required_run(
    command: list[str], root: Path, marker: Path, env: dict[str, str]
) -> None:
    marker.unlink(missing_ok=True)
    run_logged(command, root / "extract-and-run.log", cwd=root, env=env)
    if not marker.is_file() or marker.read_bytes() != b"runtime-arguments-ok\n":
        raise Failure(
            "Mandatory AppImage run did not write the expected argument marker"
        )


def smoke_test(runtime: Path, tool: Path, root: Path) -> Record:
    root.mkdir(parents=True, exist_ok=True)
    elf_report(runtime)
    appdir = root / "Fixture.AppDir"
    appdir.mkdir()
    (appdir / "AppRun").write_text(STUB)
    (appdir / "AppRun").chmod(0o755)
    (appdir / "fixture.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Runtime fixture\nExec=fixture\nIcon=fixture\nCategories=Utility;\n"
    )
    (appdir / "fixture.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="16" height="16"/></svg>\n'
    )
    temporary = root / "temporary"
    temporary.mkdir()
    marker = root / "marker"
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "TZ": "UTC",
        "TMPDIR": str(temporary),
        "ARCH": "x86_64",
        "SOURCE_DATE_EPOCH": os.environ["SOURCE_DATE_EPOCH"],
        "RUNTIME_TEST_MARKER": str(marker),
    }
    image = root / "fixture.AppImage"
    run_logged(
        [str(tool), "--appimage-extract-and-run", "--version"],
        root / "appimagetool-version.log",
        cwd=root,
        env=env,
    )
    # The pinned packaging tool's own launcher is only used to run appimagetool.
    # All tests below execute the fixture, whose runtime prefix is compared.
    run_logged(
        [
            str(tool),
            "--appimage-extract-and-run",
            "--no-appstream",
            "--runtime-file",
            str(runtime),
            "--comp",
            "zstd",
            "--mksquashfs-opt",
            "-processors",
            "--mksquashfs-opt",
            "1",
            str(appdir),
            str(image),
        ],
        root / "package.log",
        cwd=root,
        env=env,
    )
    image.chmod(0o755)
    check_appimage_prefix(runtime, image)
    extracted = root / "extracted"
    extracted.mkdir()
    run_logged(
        [str(image), "--appimage-extract"], root / "extract.log", cwd=extracted, env=env
    )
    for name in ("AppRun", "fixture.desktop", "fixture.svg"):
        if (extracted / "squashfs-root" / name).read_bytes() != (
            appdir / name
        ).read_bytes():
            raise Failure(f"Extracted fixture differs: {name}")
    required_run(
        [str(image), "--appimage-extract-and-run", *SMOKE_ARGUMENTS], root, marker, env
    )
    return {
        "result": "PASS",
        "runtime_sha256": digest(runtime),
        "appimage_sha256": digest(image),
        "new_runtime_prefix": "PASS",
        "extract": "PASS",
        "extract_and_run": "PASS",
        "argument_marker": "PASS",
        "fuse": "NOT_RUN",
        "fuse_reason": "The unprivileged test container has no FUSE device/mount setup; extract-and-run does not test FUSE.",
    }


def link_report(work: Path, runtime_dir: Path, lock: Record, inputs: Path) -> Record:
    """Account for every linker LOAD, including empty archives, libc and CRT."""
    text = (work / "reports/runtime.map").read_text()
    loads = re.findall(r"^LOAD (.+)$", text, re.M)
    if not loads:
        raise Failure("Link map has no LOAD records")
    components = {c["name"]: c for c in lock["components"]}
    packages = {p["name"] + "-" + p["version"]: p for p in lock["packages"]}
    records = []
    unresolved = []
    evidence = work / "linked-inputs"
    evidence.mkdir()
    for index, name in enumerate(dict.fromkeys(loads)):
        path = Path(name)
        if not path.is_absolute():
            path = runtime_dir / path
        path = path.resolve(strict=True)
        record: Record = {
            "linker_path": name,
            "resolved_path": str(path),
            "sha256": digest(path),
            "size": path.stat().st_size,
        }
        if path.is_relative_to(runtime_dir) and path.name in {
            "runtime.o",
            "data_sections.ld",
        }:
            record["component"] = "type2-runtime"
        elif path.parent == work / "prefix/lib" and path.name in {
            "libfuse3.a",
            "libsquashfuse.a",
            "libsquashfuse_ll.a",
        }:
            record["component"] = (
                "libfuse" if path.name == "libfuse3.a" else "squashfuse"
            )
        else:
            owner = subprocess.run(
                ["apk", "info", "--who-owns", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            identity = owner.stdout.strip().rsplit(" is owned by ", 1)[-1]
            package = packages.get(identity)
            if owner.returncode or package is None:
                unresolved.append(f"No locked APK owner for {name}")
            else:
                contents = tar_members(
                    inputs / package["path"], [str(path).lstrip("/")]
                )
                original = next(iter(contents.values()))
                if hashlib.sha256(original).hexdigest() != record["sha256"]:
                    raise Failure(f"Linked file differs from signed APK: {path.name}")
                record["package"] = package
                record["component"] = package["origin"]
                if package["origin"] not in components:
                    unresolved.append(
                        f"Missing corresponding source for {name}: {package['origin']}"
                    )
        target = evidence / f"{index:02d}-{path.name}"
        shutil.copyfile(path, target)
        record["saved_as"] = target.relative_to(work).as_posix()
        records.append(record)
    present = {r.get("component") for r in records}
    if (
        not {
            "type2-runtime",
            "libfuse",
            "squashfuse",
            "musl",
            "gcc",
            "zstd",
            "zlib",
            "mimalloc2",
        }
        <= present
    ):
        raise Failure(
            "Link map is missing an expected runtime component, libc or compiler runtime"
        )
    result = {
        "result": "PASS" if not unresolved else "REVIEW_REQUIRED",
        "method": "GNU ld LOAD records; APK ownership and byte comparison with locked signed APK payloads",
        "files": records,
        "unresolved": unresolved,
    }
    write_json(work / "reports/linked-inputs.json", result)
    return result
