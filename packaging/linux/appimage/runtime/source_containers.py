"""Exact retained runtime inputs from official ISO ranges and one pinned small kit."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from runtime_inputs import (
    CURRENT_DEPENDENCY_URL,
    Failure,
    Record,
    digest,
    input_path,
    relative_path,
    verify_file,
)

MAX_MEMBER = 64 * 1024**2
MAX_CONTAINER = 64 * 1024**2
MAX_EXPANDED = 128 * 1024**2
MAX_ENTRIES = 2048


class ShortReadFailure(Failure):
    """Unexpected EOF before the pinned transfer size, never an integrity waiver."""

    def __init__(
        self,
        expected_size: int,
        received_size: int,
        *,
        item_path: str | None = None,
        source_kind: str | None = None,
        download_attempts: int = 1,
        prior_short_read_counts: list[Record] | None = None,
    ) -> None:
        self.expected_size = expected_size
        self.received_size = received_size
        self.download_attempts = download_attempts
        self.prior_short_read_counts = prior_short_read_counts or []
        context = (
            f" for {item_path} ({source_kind}, attempts {download_attempts})"
            if item_path is not None
            else ""
        )
        super().__init__(
            f"Truncated container response{context}: "
            f"expected {expected_size} bytes, received {received_size}"
        )


def valid_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def load_acquisition_plan(path: Path, lock: Record) -> Record:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024**2:
        raise Failure("Missing regular runtime acquisition lock")
    plan = json.loads(path.read_text())
    if plan.get("schema") != 1 or plan.get("runtime_lock_sha256") != digest(
        path.parent / "runtime.lock.json"
    ):
        raise Failure("Runtime acquisition plan does not match the pinned input lock")
    inputs = {item["path"]: item for item in lock["files"]}
    selectors = plan["selectors"]
    if not isinstance(selectors, dict):
        raise Failure("Invalid runtime source selectors")
    bundle = plan["dependency_bundle"]
    if (
        not isinstance(bundle, dict)
        or bundle.get("url") != CURRENT_DEPENDENCY_URL
        or type(bundle.get("size")) is not int
        or not 0 < bundle["size"] <= MAX_CONTAINER
        or not valid_sha(bundle.get("sha256"))
    ):
        raise Failure("Invalid exact dependency-only container pin")
    members = bundle["members"]
    if not isinstance(members, dict):
        raise Failure("Invalid dependency container member inventory")
    chosen_bundle = set()
    for name, selector in selectors.items():
        if name not in inputs or not name.startswith("apks/"):
            raise Failure("Unpinned runtime source selector")
        if not isinstance(selector, dict):
            raise Failure("Invalid runtime container selector")
        item = inputs[name]
        if (
            selector.get("size") != item["size"]
            or selector.get("sha256") != item["sha256"]
        ):
            raise Failure("Container selector differs from exact input size/SHA-256")
        member = str(relative_path(selector["member"]))
        if selector["kind"] == "official_iso_member":
            url = urllib.parse.urlsplit(selector["url"])
            if (
                url.scheme != "https"
                or url.netloc != "dl-cdn.alpinelinux.org"
                or re.fullmatch(
                    r"/alpine/v3\.21/releases/x86_64/alpine-extended-3\.21\.[78]-x86_64\.iso",
                    url.path,
                )
                is None
                or url.query
                or url.fragment
                or type(selector.get("offset")) is not int
                or selector["offset"] < 0
                or selector["offset"] % 2048
                or type(selector.get("official_iso_size")) is not int
                or selector["offset"] + item["size"] > selector["official_iso_size"]
                or not valid_sha(selector.get("official_iso_expected_sha256"))
                or selector.get("whole_iso_sha256_verified") is not False
                or selector.get("range_required") is not True
                or member != "apks/x86_64/" + Path(name).name
            ):
                raise Failure("Invalid official ISO range selector")
        elif selector["kind"] == "dependency_bundle_member":
            if (
                member not in members
                or members[member].get("size") != item["size"]
                or members[member].get("sha256") != item["sha256"]
            ):
                raise Failure("Dependency container member differs from input pin")
            chosen_bundle.add(member)
        else:
            raise Failure("Unknown runtime input container kind")
    for name, record in members.items():
        if (
            not isinstance(record, dict)
            or str(relative_path(name)) != name
            or type(record.get("size")) is not int
            or not 0 <= record["size"] <= MAX_MEMBER
            or not valid_sha(record.get("sha256"))
        ):
            raise Failure("Invalid exact dependency container member pin")
    if len(chosen_bundle) != 3:
        raise Failure("Expected the three declared retained APK input members")
    return {**plan, "_lock_sha256": digest(path)}


def copy_bounded(response: Any, path: Path, expected_size: int) -> None:
    total = 0
    with path.open("wb") as output:
        while block := response.read(min(1024**2, expected_size + 1 - total)):
            total += len(block)
            if total > expected_size:
                raise Failure("Container response exceeded the exact pinned size")
            output.write(block)
    if total != expected_size:
        raise ShortReadFailure(expected_size, total)


def fetch_iso_member(
    item: Record, selector: Record, destination: Path, opener: Any
) -> Record:
    start = selector["offset"]
    end = start + item["size"] - 1
    request = urllib.request.Request(
        selector["url"],
        headers={
            "User-Agent": "tokenlogue-runtime-inputs/1",
            "Range": f"bytes={start}-{end}",
            "Accept-Encoding": "identity",
        },
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
        with opener.open(request, timeout=120) as response:
            expected_range = f"bytes {start}-{end}/{selector['official_iso_size']}"
            length = response.headers.get("Content-Length")
            if (
                response.status != 206
                or response.headers.get("Content-Range") != expected_range
                or response.headers.get("Content-Encoding") not in (None, "identity")
                or length is not None
                and length != str(item["size"])
            ):
                raise Failure("Official ISO requires exact HTTP 206 Content-Range")
            copy_bounded(response, temporary, item["size"])
        verify_file(temporary, item)
        temporary.replace(destination)
        return {
            "source_kind": "official-iso-member",
            "url": selector["url"],
            "member": selector["member"],
            "offset": start,
            "status": 206,
            "content_range": expected_range,
            "selected_member_sha256_verified": True,
            "official_iso_expected_sha256": selector["official_iso_expected_sha256"],
            "whole_iso_sha256_verified": False,
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checked_container(
    root: Path, bundle: Record, opener: Any, cache_states: dict[str, str]
) -> tuple[Path, str]:
    name = bundle["sha256"] + ".tar.gz"
    path = input_path(root, "containers/" + name)
    record = {
        "path": "containers/" + name,
        "size": bundle["size"],
        "sha256": bundle["sha256"],
    }
    if path.exists() or path.is_symlink():
        verify_file(path, record)
        return path, cache_states.get(name, "reverified-existing-container-cache")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
        request = urllib.request.Request(
            bundle["url"], headers={"User-Agent": "tokenlogue-runtime-inputs/1"}
        )
        with opener.open(request, timeout=120) as response:
            copy_bounded(response, temporary, bundle["size"])
        verify_file(temporary, record)
        temporary.replace(path)
        cache_states[name] = "downloaded-current-session"
        return path, cache_states[name]
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def extract_bundle_member(
    archive: Path, bundle: Record, selector: Record, item: Record, destination: Path
) -> None:
    verify_file(
        archive,
        {
            "path": "pinned dependency container",
            "size": bundle["size"],
            "sha256": bundle["sha256"],
        },
    )
    wanted = selector["member"]
    seen = set()
    found: bytes | None = None
    expanded = 0
    directories = {
        str(parent)
        for name in bundle["members"]
        for parent in PurePosixPath(name).parents
        if str(parent) != "."
    }
    try:
        with tarfile.open(archive, "r:gz") as source:
            for member in source:
                name = str(relative_path(member.name))
                if name != member.name.rstrip("/") or name == ".":
                    raise Failure("Non-canonical dependency container path")
                if name in seen or len(seen) >= MAX_ENTRIES:
                    raise Failure("Duplicate or excessive dependency container members")
                seen.add(name)
                if member.isdir():
                    if name not in directories or member.size:
                        raise Failure("Unexpected dependency container directory")
                    continue
                if not member.isfile() or name not in bundle["members"]:
                    raise Failure(
                        "Unexpected or non-regular dependency container member"
                    )
                record = bundle["members"][name]
                expanded += member.size
                if member.size != record["size"] or expanded > MAX_EXPANDED:
                    raise Failure("Invalid expanded dependency container size")
                stream = source.extractfile(member)
                if stream is None:
                    raise Failure("Missing dependency container member data")
                with stream:
                    data = stream.read(member.size + 1)
                if (
                    len(data) != member.size
                    or hashlib.sha256(data).hexdigest() != record["sha256"]
                ):
                    raise Failure(
                        "Dependency member SHA-256 differs from the exact inventory"
                    )
                if name == wanted:
                    found = data
    except (tarfile.TarError, EOFError, OSError):
        raise Failure("Invalid dependency container archive") from None
    files = {name for name in seen if name in bundle["members"]}
    if files != set(bundle["members"]) or found is None:
        raise Failure("Incomplete dependency container inventory")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(found)
        verify_file(temporary, item)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch_container_input(
    item: Record,
    selector: Record,
    destination: Path,
    root: Path,
    plan: Record,
    opener: Any,
    cache_states: dict[str, str],
) -> Record:
    iso = selector["kind"] == "official_iso_member"
    source_kind = "official-iso-member" if iso else "pinned-dependency-container-member"
    cached_container = (
        not iso
        and input_path(
            root, "containers/" + plan["dependency_bundle"]["sha256"] + ".tar.gz"
        ).exists()
    )
    prior_short_reads: list[Record] = []
    for attempt in (1, 2):
        try:
            if iso:
                origin = fetch_iso_member(item, selector, destination, opener)
            else:
                bundle = plan["dependency_bundle"]
                archive, state = checked_container(root, bundle, opener, cache_states)
                extract_bundle_member(archive, bundle, selector, item, destination)
                origin = {
                    "source_kind": source_kind,
                    "url": bundle["url"],
                    "member": selector["member"],
                    "container_size": bundle["size"],
                    "container_sha256": bundle["sha256"],
                    "whole_container_sha256_verified": True,
                    "container_cache": state,
                    "selected_member_sha256_verified": True,
                }
            return {
                **origin,
                "download_attempts": 0 if cached_container else attempt,
                "prior_short_read_counts": prior_short_reads,
            }
        except ShortReadFailure as error:
            if attempt == 2:
                raise ShortReadFailure(
                    error.expected_size,
                    error.received_size,
                    item_path=item["path"],
                    source_kind=source_kind,
                    download_attempts=attempt,
                    prior_short_read_counts=prior_short_reads,
                ) from None
            prior_short_reads.append(
                {
                    "expected_bytes": error.expected_size,
                    "received_bytes": error.received_size,
                }
            )
    raise AssertionError("The bounded container download must return or fail")
