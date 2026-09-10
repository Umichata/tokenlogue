"""Проверенные исходные материалы для notices. Не запускает проверяемые ELF."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen


class NoticeError(ValueError):
    pass


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pubspec_audit_copy(data: bytes, workspace: Path) -> tuple[str, dict[str, str]]:
    """Normalize only Flet's known local plugin reference, before manifest hashing."""
    text = data.decode("utf-8")
    if not re.search(r"(?m)^  serious_python_linux:$", text):
        raise NoticeError("resolved Flutter lock is missing serious_python_linux")
    # Dart emits this block in a fixed form. Unknown layouts or local packages
    # require review instead of a global replacement in audit/license texts.
    block = re.compile(
        r"(?m)(^  flet_secure_storage:\n    dependency: [^\n]+\n"
        r'    description:\n)      path: ("(?:[^"\\\n]|\\.)*")\n'
        r"      relative: (true|false)\n"
        r"(    source: path\n    version: [^\n]+\n)"
    )
    matches = list(block.finditer(text))
    if len(matches) != 1 or len(re.findall(r"(?m)^    source: path$", text)) != 1:
        raise NoticeError("unexpected local dependencies in Flutter lock")
    match = matches[0]
    path = json.loads(match[2])
    expected = str(workspace / "build/flutter-packages/flet_secure_storage")
    portable = "../flutter-packages/flet_secure_storage"
    if (path, match[3]) not in ((expected, "false"), (portable, "true")):
        raise NoticeError("unexpected flet_secure_storage path in Flutter lock")
    replacement = (
        match[1] + f'      path: "{portable}"\n      relative: true\n' + match[4]
    )
    output = text[: match.start()] + replacement + text[match.end() :]
    header = (
        "# Audit copy: local plugin path is relative to the generated Flutter project.\n"
        "# This is not a standalone build input; the original lock is in CI reports.\n"
    )
    return header + output, {
        "resolved_packages_source_sha256": hashlib.sha256(data).hexdigest(),
        "resolved_packages_transform": "flet_secure_storage path made project-relative; audit copy",
    }


def relative_file(root: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    if not name or parts.is_absolute() or ".." in parts.parts or "\\" in name:
        raise NoticeError(f"unsafe relative file: {name}")
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise NoticeError(f"missing regular file: {name}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise NoticeError(f"escaping file: {name}")
    return path


def elf_fingerprint(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01" or len(data) < 64:
        raise NoticeError(f"expected ELF64 little endian: {path.name}")
    offset = struct.unpack_from("<Q", data, 40)[0]
    size, count, names_index = struct.unpack_from("<HHH", data, 58)
    if (
        size != 64
        or not 0 < names_index < count < 4096
        or offset + count * size > len(data)
    ):
        raise NoticeError(f"invalid ELF section table: {path.name}")
    sections = [
        struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size) for i in range(count)
    ]
    names_section = sections[names_index]
    names = data[names_section[4] : names_section[4] + names_section[5]]
    result = {}
    for section in sections:
        end = names.find(b"\0", section[0])
        if end < 0:
            raise NoticeError("invalid ELF section name")
        name = names[section[0] : end].decode("ascii")
        if name in {".text", ".rodata", ".note.gnu.build-id"}:
            start, length = section[4:6]
            if start + length > len(data):
                raise NoticeError("truncated ELF section")
            result[name] = hashlib.sha256(data[start : start + length]).hexdigest()
    if ".text" not in result:
        raise NoticeError(f"missing ELF code: {path.name}")
    return result


def same_binary(actual: Path, reference: Path) -> None:
    actual_sections = elf_fingerprint(actual)
    reference_sections = elf_fingerprint(reference)
    if actual_sections != reference_sections:
        changed = sorted(
            name
            for name in actual_sections.keys() | reference_sections.keys()
            if actual_sections.get(name) != reference_sections.get(name)
        )
        raise NoticeError(
            f"binary provenance mismatch: {actual.name}; "
            f"differing_sections={','.join(changed)}; "
            f"actual_sha256={sha256(actual)}; "
            f"reference_sha256={sha256(reference)}"
        )


def fetch_asset(spec: dict, cache: Path) -> Path:
    expected = spec["sha256"]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise NoticeError("invalid locked SHA-256")
    if not spec["url"].startswith("https://"):
        raise NoticeError("HTTPS source required")
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / expected
    if dest.is_symlink():
        raise NoticeError("symlink in input cache")
    if dest.is_file():
        if sha256(dest) != expected:
            raise NoticeError("corrupt cached notice input")
        return dest
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as stream:
            temporary = Path(stream.name)
            request = Request(spec["url"], headers={"User-Agent": "Tokenlogue-notices"})
            with urlopen(request, timeout=60) as response:
                if not response.url.startswith("https://"):
                    raise NoticeError("non-HTTPS redirect")
                count = 0
                while block := response.read(1024 * 1024):
                    count += len(block)
                    if count > spec["bytes"]:
                        raise NoticeError("notice input exceeds locked size")
                    stream.write(block)
        if temporary.stat().st_size != spec["bytes"] or sha256(temporary) != expected:
            raise NoticeError("notice input SHA-256/size mismatch")
        temporary.replace(dest)
        return dest
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def extract_python(archive: Path, output: Path) -> None:
    """Извлекает только metadata, тексты лицензий и эталонные ELF."""
    output.mkdir(parents=True, exist_ok=True)
    seen = set()
    with subprocess.Popen(
        ["zstd", "-dc", str(archive)], stdout=subprocess.PIPE
    ) as proc:
        assert proc.stdout is not None
        with tarfile.open(fileobj=proc.stdout, mode="r|") as entries:
            for entry in entries:
                name = PurePosixPath(entry.name)
                if name.is_absolute() or ".." in name.parts:
                    raise NoticeError("unsafe path in Python archive")
                selected = (
                    entry.name == "python/PYTHON.json"
                    or entry.name.startswith("python/licenses/")
                    or entry.name
                    in {
                        "python/install/lib/libpython3.12.so.1.0",
                        "python/install/lib/libpython3.so",
                    }
                    or entry.name.startswith(
                        "python/install/lib/python3.12/lib-dynload/"
                    )
                    and entry.name.endswith(".so")
                )
                if not selected or entry.isdir():
                    continue
                if (
                    not entry.isfile()
                    or entry.name in seen
                    or entry.size > 512 * 1024 * 1024
                ):
                    raise NoticeError("unexpected Python archive member")
                seen.add(entry.name)
                stream = entries.extractfile(entry)
                assert stream is not None
                dest = output / entry.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(stream.read())
        if proc.wait() != 0:
            raise NoticeError("cannot decompress Python reference")
    relative_file(output, "python/PYTHON.json")


def font_names(path: Path) -> dict[str, list[str]]:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] not in {b"\x00\x01\x00\x00", b"OTTO"}:
        raise NoticeError("unsupported font")
    count = struct.unpack_from(">H", data, 4)[0]
    for i in range(count):
        tag, _, offset, length = struct.unpack_from(">4sIII", data, 12 + i * 16)
        if tag != b"name":
            continue
        table = data[offset : offset + length]
        _, records, strings = struct.unpack_from(">HHH", table)
        result: dict[str, set[str]] = {}
        for n in range(records):
            platform, _, _, name, size, start = struct.unpack_from(
                ">HHHHHH", table, 6 + n * 12
            )
            if name not in {0, 1, 4, 6, 13, 14}:
                continue
            end = strings + start + size
            if end > len(table):
                raise NoticeError("truncated font name")
            value = table[strings + start : end].decode(
                "utf-16-be" if platform in {0, 3} else "mac_roman"
            )
            result.setdefault(str(name), set()).add(value)
        return {k: sorted(v) for k, v in result.items()}
    raise NoticeError("missing font name table")


def load_lock(directory: Path) -> dict:
    lock = json.loads((directory / "notices.lock.json").read_text())
    if lock["schema"] != 1:
        raise NoticeError("unsupported notices lock")
    for record in lock["texts"]:
        path = relative_file(directory, record["path"])
        if sha256(path) != record["sha256"]:
            raise NoticeError(f"vendored notice checksum mismatch: {record['path']}")
    return lock


def reject_proxies() -> None:
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        if os.environ.get(name):
            raise NoticeError(f"proxy variable {name} must be unset")
