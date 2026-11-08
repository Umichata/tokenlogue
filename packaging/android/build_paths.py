#!/usr/bin/env python3
"""Reject builder home paths in a final APK without executing its Python code."""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import importlib.util
import io
import json
import lzma
import marshal
import os
import pwd
import re
import sys
import tarfile
import zlib
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path, PurePosixPath
from types import CodeType
from typing import Any
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

MAX_BYTES = 512 * 1024 * 1024
MAX_FILE = 128 * 1024 * 1024
MAX_ENTRIES = 50000
MAX_DEPTH = 8


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def personal_prefixes(environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Capture original account homes before selecting a neutral build environment.

    Generic build/system directories and arbitrary upstream sample paths are not
    guessed to be personal. Explicit prefixes remain available to the caller.
    """
    env = os.environ if environment is None else environment
    values = [env.get("HOME", ""), env.get("USERPROFILE", "")]
    if env.get("HOMEDRIVE") and env.get("HOMEPATH"):
        values.append(env["HOMEDRIVE"] + env["HOMEPATH"])
    account = pwd.getpwuid(os.getuid()).pw_dir
    values.append(account)
    result = set()
    for value in values:
        if not value:
            continue
        normalized = value.replace("\\", "/").rstrip("/")
        recognized = bool(
            re.match(r"^(?:/home/|/Users/|[A-Za-z]:/Users/)[^/]+", normalized)
        )
        if recognized or (
            value == account
            and normalized not in {"", "/root", "/home", "/Users"}
            and not normalized.startswith(
                ("/tmp/", "/var/tmp/", "/build/", "/workspace/")
            )
        ):
            result.add(value.rstrip("/\\"))
            if value.startswith("/"):
                result.add(os.path.realpath(value).rstrip("/"))
    return tuple(sorted(result))


def _representations(prefix: str) -> set[str]:
    forward = prefix.replace("\\", "/").rstrip("/")
    if not forward or forward == "/" or re.fullmatch(r"[A-Za-z]:", forward):
        raise ValueError("A personal prefix must identify a home, not a system root")
    values = {forward, forward.replace("/", "\\")}
    for value in tuple(values):
        values.update(
            json.dumps(value, ensure_ascii=ascii_only)[1:-1]
            for ascii_only in (False, True)
        )
    values.add(forward.replace("/", "\\/"))
    uri_path = "/" + forward if re.match(r"^[A-Za-z]:/", forward) else forward
    values.update(
        ("file:" + uri_path, "file://" + uri_path, "file://localhost" + uri_path)
    )
    for value in (forward, "file://" + uri_path):
        for safe in ("/:", ""):
            encoded = quote(value, safe=safe)
            values.add(encoded)
            values.add(re.sub(r"%[0-9A-F]{2}", lambda match: match[0].lower(), encoded))
    for value in tuple(values):
        values.add(value.replace("/", "\\/"))
        values.update(
            json.dumps(value, ensure_ascii=ascii_only)[1:-1]
            for ascii_only in (False, True)
        )
    return values


def redaction_needles(prefixes: Sequence[str]) -> tuple[bytes, ...]:
    """Known home representations for log redaction, never for artifact rewriting."""
    return tuple(
        sorted(
            {
                value.encode("utf-8")
                for prefix in prefixes
                for value in _representations(prefix)
            },
            key=len,
            reverse=True,
        )
    )


def redact_text(value: str, prefixes: Sequence[str]) -> str:
    data = value.encode("utf-8", "surrogatepass")
    for prefix in prefixes:
        for pattern in _patterns(prefix, "utf-8"):
            data = pattern.sub(b"<builder-home>", data)
    return data.decode("utf-8", "surrogatepass")


@lru_cache(maxsize=128)
def _patterns(prefix: str, encoding: str) -> tuple[re.Pattern[bytes], ...]:
    """Match mixed literal, JSON and URI encodings without case-folding POSIX names."""
    _representations(prefix)  # Validate before compiling or recording diagnostics.
    forward = prefix.replace("\\", "/").rstrip("/")
    windows = bool(re.match(r"^[A-Za-z]:/", forward))
    uri = "/" + forward if windows else forward
    forms = {
        forward,
        forward.replace("/", "\\"),
        "file:" + uri,
        "file://" + uri,
        "file://localhost" + uri,
    }
    result = []
    for form in sorted(forms):
        pieces = []
        for index, character in enumerate(form):
            cases = {character}
            uri_case_end = (
                len("file://localhost") if form.startswith("file://localhost") else 4
            )
            if windows or form.startswith("file:") and index < uri_case_end:
                cases.update((character.lower(), character.upper()))
            alternatives = set()
            for value in cases:
                alternatives.add(re.escape(value.encode(encoding)))
                escaped = json.dumps(value, ensure_ascii=True)[1:-1]
                unicode_hex = value.encode("utf-16-be", "surrogatepass").hex()
                unicode_escape = "".join(
                    "\\u" + unicode_hex[n : n + 4]
                    for n in range(0, len(unicode_hex), 4)
                )
                percent = "".join(
                    f"%{byte:02X}" for byte in value.encode("utf-8", "surrogatepass")
                )
                for encoded in (escaped, unicode_escape, percent):
                    if encoded != value:
                        alternatives.add(
                            b"(?i:" + re.escape(encoded.encode(encoding)) + b")"
                        )
                if value == "/":
                    alternatives.add(re.escape("\\/".encode(encoding)))
            pieces.append(
                b"(?:" + b"|".join(sorted(alternatives, key=len, reverse=True)) + b")"
            )
        pattern = b"".join(pieces)
        if form.startswith("file:"):
            # AOT strings have binary length/type metadata, not a C delimiter.
            # The absolute URI identifies itself even beside a header byte.
            pattern = b"(?P<absolute_uri>" + pattern + b")"
        result.append(re.compile(pattern))
    return tuple(result)


def _path_boundary(before: str, after: str) -> bool:
    if before and (before.isalnum() or before in "_./\\~%:-"):
        return False
    if after.startswith("\\u") and re.match(r"\\u[0-9a-fA-F]{4}", after):
        return int(after[2:6], 16) in (0, 47, 92)
    if not after or after[0] in "/\\\0'\"<>?#":
        return True
    return after.lower().startswith(("%2f", "%5c", "\\u002f", "\\u005c"))


class PathScan:
    """Bounded container and CodeType reader, separate from the secret scanner."""

    def __init__(
        self,
        prefixes: Sequence[str],
        public_fixtures: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.prefixes = tuple(dict.fromkeys(prefixes))
        self.patterns = [
            (index, encoding, pattern)
            for index, prefix in enumerate(self.prefixes)
            for encoding in ("utf-8", "utf-16-le", "utf-16-be")
            for pattern in _patterns(prefix, encoding)
        ]
        self.fixtures = public_fixtures or {}
        self.findings: list[dict[str, Any]] = []
        self.origins: list[dict[str, str]] = []
        self.entries = 0
        self.bytes = 0
        self.pyc_files = 0
        self.code_objects = 0
        self.current_member = "APK"

    def _label(self, member: str) -> str:
        return redact_text(member, self.prefixes)

    def _matches(self, data: bytes) -> list[int]:
        matched = set()
        for index, encoding, pattern in self.patterns:
            if index in matched:
                continue
            for match in pattern.finditer(data):
                position, end = match.span()
                before = data[max(0, position - 8) : position].decode(
                    encoding, "ignore"
                )[-1:]
                if "absolute_uri" in pattern.groupindex:
                    before = ""
                after = data[end : end + 16].decode(encoding, "ignore")
                if _path_boundary(before, after):
                    matched.add(index)
                    break
        return sorted(matched)

    def _check(self, member: str, data: bytes, kind: str) -> None:
        matches = self._matches(data)
        if matches:
            self.findings.append(
                {
                    "member": self._label(member),
                    "kind": kind,
                    "prefix_ids": matches,
                    "sha256": _digest(data),
                    "origin": "pinned-public-upstream-fixture"
                    if member in self.fixtures
                    else "packaged-content",
                    "classification": "builder-path metadata or bytes, not a claim of user secrets",
                }
            )

    def _code(self, value: object, member: str, depth: int = 0) -> None:
        if depth > 256:
            raise ValueError("Code object nesting exceeds inspection limit")
        if isinstance(value, CodeType):
            self.code_objects += 1
            self._check(
                member,
                value.co_filename.encode("utf-8", "surrogatepass"),
                "co_filename",
            )
            self._code(value.co_consts, member, depth + 1)
        elif isinstance(value, str):
            self._check(
                member, value.encode("utf-8", "surrogatepass"), "code-string-constant"
            )
        elif isinstance(value, bytes):
            self._check(member, value, "code-bytes-constant")
        elif isinstance(value, (tuple, list, set, frozenset)):
            for child in value:
                self._code(child, member, depth + 1)
        elif isinstance(value, dict):
            for key, child in value.items():
                self._code(key, member, depth + 1)
                self._code(child, member, depth + 1)

    def _pyc(self, member: str, data: bytes) -> None:
        if sys.version_info[:2] != (3, 12):
            raise ValueError("APK PYC inspection requires Python 3.12")
        if len(data) < 16 or data[:4] != importlib.util.MAGIC_NUMBER:
            raise ValueError("Unknown or truncated Python 3.12 PYC")
        if int.from_bytes(data[4:8], "little") not in (0, 1, 3):
            raise ValueError("Unsupported PYC header flags")
        payload = io.BytesIO(data[16:])
        try:
            code = marshal.load(payload)
        except (ValueError, EOFError, TypeError) as error:
            raise ValueError("Unreadable Python 3.12 PYC") from error
        if not isinstance(code, CodeType) or payload.tell() != len(data) - 16:
            raise ValueError("PYC payload is not one complete code object")
        self.pyc_files += 1
        self._code(code, member)

    def _read(self, stream: Any) -> bytes:
        remaining = min(MAX_FILE, MAX_BYTES - self.bytes)
        data = stream.read(remaining + 1)
        if len(data) > remaining:
            raise ValueError("APK container exceeds inspection byte limit")
        return data

    def inspect(self, member: str, data: bytes, depth: int = 0) -> None:
        self.current_member = member
        if depth > MAX_DEPTH:
            raise ValueError("APK container nesting exceeds inspection limit")
        self.entries += 1
        self.bytes += len(data)
        if self.entries > MAX_ENTRIES or self.bytes > MAX_BYTES or len(data) > MAX_FILE:
            raise ValueError("APK contents exceed inspection limits")
        origin = self.fixtures.get(member)
        if origin is not None:
            if origin.get("sha256") != _digest(data) or not origin.get(
                "source_url", ""
            ).startswith("https://"):
                raise ValueError("Public fixture does not match its pinned origin")
            self.origins.append(
                {
                    "member": self._label(member),
                    "sha256": _digest(data),
                    "source_url": self._label(origin["source_url"]),
                }
            )
        self._check(
            member, member.encode("utf-8", "surrogatepass"), "container-member-name"
        )
        self._check(member, data, "packaged-bytes")
        leaf = member.rsplit("!", 1)[-1]
        if leaf.endswith(".pyc"):
            self._pyc(member, data)
        elif leaf.endswith((".zip", ".apk")) or data.startswith(
            (b"PK\x03\x04", b"PK\x05\x06")
        ):
            try:
                with ZipFile(io.BytesIO(data)) as archive:
                    names = set()
                    for entry in archive.infolist():
                        if entry.filename in names or entry.flag_bits & 1:
                            raise ValueError(
                                "Duplicate or encrypted APK container member"
                            )
                        names.add(entry.filename)
                        path = PurePosixPath(entry.filename)
                        if (
                            path.is_absolute()
                            or ".." in path.parts
                            or "\\" in entry.filename
                        ):
                            raise ValueError("Unsafe APK container member name")
                        if entry.is_dir():
                            continue
                        with archive.open(entry) as stream:
                            child = self._read(stream)
                        self.inspect(member + "!" + entry.filename, child, depth + 1)
            except (BadZipFile, RuntimeError, EOFError, NotImplementedError) as error:
                raise ValueError("Unreadable APK ZIP container") from error
        elif leaf.endswith(".tar"):
            try:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
                    for entry in archive:
                        if entry.isdir():
                            continue
                        if not entry.isfile():
                            raise ValueError(
                                "Unsupported special member in APK tar container"
                            )
                        stream = archive.extractfile(entry)
                        if stream is None:
                            raise ValueError("Unreadable APK tar member")
                        with stream:
                            child = self._read(stream)
                        self.inspect(member + "!" + entry.name, child, depth + 1)
            except tarfile.TarError as error:
                raise ValueError("Unreadable APK tar container") from error
        elif leaf.endswith((".gz", ".bz2", ".xz", ".Z")):
            try:
                if leaf.endswith(".Z") and not data.startswith(b"\x1f\x8b"):
                    decompressor = zlib.decompressobj()
                    child = decompressor.decompress(
                        data, min(MAX_FILE, MAX_BYTES - self.bytes) + 1
                    )
                    if not decompressor.eof or decompressor.unused_data:
                        raise ValueError("Incomplete or trailing compressed APK member")
                else:
                    if leaf.endswith((".gz", ".Z")):
                        stream = gzip.GzipFile(fileobj=io.BytesIO(data))
                    elif leaf.endswith(".bz2"):
                        stream = bz2.BZ2File(io.BytesIO(data))
                    else:
                        stream = lzma.LZMAFile(io.BytesIO(data))
                    with stream:
                        child = self._read(stream)
                self.inspect(member[: -len(Path(leaf).suffix)], child, depth + 1)
            except (OSError, EOFError, zlib.error, lzma.LZMAError) as error:
                raise ValueError("Unreadable compressed APK member") from error


def verify_apk(
    apk: Path,
    *,
    prefixes: Sequence[str] | None = None,
    report: Path | None = None,
    public_fixtures: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Fail closed on a path finding or an unsupported/unreadable final container.

    Prefix values and application constants are never included in diagnostics.
    Pinned fixture provenance annotates evidence and does not waive a real match.
    """
    scan = PathScan(
        personal_prefixes() if prefixes is None else prefixes, public_fixtures
    )
    result: dict[str, Any] = {
        "schema": 1,
        "gate": "final-apk-build-paths",
        "status": "FAIL",
    }
    error: str | None = None
    try:
        if not scan.prefixes:
            raise ValueError(
                "No original builder-home prefixes supplied for inspection"
            )
        if apk.is_symlink() or not apk.is_file():
            raise ValueError("Final APK must be one regular file")
        with apk.open("rb") as stream:
            data = scan._read(stream)
        result.update(apk_sha256=_digest(data), apk_size=len(data))
        if not data.startswith(b"PK\x03\x04"):
            raise ValueError("Final APK is not a ZIP container")
        scan.inspect("APK", data)
        if scan.findings:
            raise ValueError("Final APK contains builder-home path metadata or bytes")
        result["status"] = "PASS"
    except (OSError, ValueError, RecursionError) as failure:
        # Deliberately do not serialize exception text that may contain input paths.
        error = str(failure) if type(failure) is ValueError else "APK inspection failed"
        error = scan._label(error)
        result["error"] = error
        result["failure_member"] = scan._label(scan.current_member)
    result.update(
        prefix_count=len(scan.prefixes),
        entries_read=scan.entries,
        bytes_read=scan.bytes,
        pyc_files_read=scan.pyc_files,
        code_objects_read=scan.code_objects,
        findings=scan.findings,
        pinned_public_fixtures=scan.origins,
        secret_scanner_changed=False,
        application_code_executed=False,
    )
    if report is not None:
        report.write_text(
            json.dumps(result, ensure_ascii=True, indent=2) + "\n", "utf-8"
        )
    if error is not None:
        raise ValueError(error)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        verify_apk(args.apk, report=args.report)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
