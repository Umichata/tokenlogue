"""Verify pinned native dependency inputs and their packaged payloads."""

from __future__ import annotations

import argparse
import base64
import csv
import email
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

LOCK = "packaging/native_wheels/wheels.lock.json"
PACKAGES = {
    "android": {"cffi": "2.0.0", "pycryptodomex": "3.23.0", "msgpack": "1.1.2"},
    "linux": {"cffi": "2.0.0", "pycryptodomex": "3.23.0"},
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(x in {"", ".", ".."} for x in path.parts)
    ):
        raise ValueError("Unsafe native input path")
    target = root
    for part in path.parts:
        target /= part
        if target.is_symlink():
            raise ValueError("Native input contains a symbolic link")
    if not target.is_file():
        raise ValueError(f"Required native input missing {relative}")
    return target


def load_lock(root: Path) -> dict:
    document = json.loads(checked_path(root, LOCK).read_text(encoding="utf-8"))
    if document.get("format_version") != 1:
        raise ValueError("Unknown native wheel lock format")
    rows = document.get("wheels", [])
    for platform, expected in PACKAGES.items():
        actual = [row for row in rows if row.get("platform") == platform]
        if (
            len(actual) != len(expected)
            or {row["package"]: row["version"] for row in actual} != expected
        ):
            raise ValueError("Incomplete or unexpected pinned native wheel set")
    if len(rows) != sum(map(len, PACKAGES.values())):
        raise ValueError("Unexpected native wheel platform")
    return document


def rows_for(document: dict, platform: str) -> list[dict]:
    if platform not in PACKAGES:
        raise ValueError("Unsupported native wheel platform")
    return [row for row in document["wheels"] if row["platform"] == platform]


def required_inputs(root: Path, platform: str) -> list[str]:
    document = load_lock(root)
    rows = rows_for(document, platform)
    return sorted({LOCK, *document["recipe_files"], *(row["path"] for row in rows)})


def zip_files(archive: zipfile.ZipFile) -> dict[str, bytes]:
    files = {}
    seen = set()
    for info in archive.infolist():
        relative = PurePosixPath(info.filename)
        if (
            info.filename in seen
            or relative.is_absolute()
            or ".." in relative.parts
            or stat.S_ISLNK(info.external_attr >> 16)
        ):
            raise ValueError("Unsafe or duplicate archive member")
        seen.add(info.filename)
        if not info.is_dir():
            files[info.filename] = archive.read(info)
    if archive.testzip() is not None:
        raise ValueError("ZIP CRC failed")
    return files


def check_record(files: dict[str, bytes]) -> None:
    records = [name for name in files if name.endswith(".dist-info/RECORD")]
    if len(records) != 1:
        raise ValueError("Wheel RECORD is missing or ambiguous")
    record = records[0]
    listed = set()
    for name, encoded, size in csv.reader(io.StringIO(files[record].decode("utf-8"))):
        if name in listed or name not in files:
            raise ValueError("Wheel RECORD has missing or duplicate entries")
        listed.add(name)
        if name == record:
            if encoded or size:
                raise ValueError("Wheel RECORD must not hash itself")
            continue
        expected = base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest())
        if encoded != "sha256=" + expected.rstrip(b"=").decode("ascii"):
            raise ValueError("Wheel RECORD content checksum mismatch")
        if int(size) != len(files[name]):
            raise ValueError("Wheel RECORD size mismatch")
    if listed != set(files):
        raise ValueError("Wheel contains files outside RECORD")


def check_wheel(path: Path, row: dict) -> dict[str, bytes]:
    data = path.read_bytes()
    if len(data) != row["bytes"] or digest(data) != row["sha256"]:
        raise ValueError(f"Pinned wheel checksum mismatch {row['package']}")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = zip_files(archive)
    check_record(files)
    info = f"{row['package']}-{row['version']}.dist-info"
    metadata = email.message_from_bytes(files[f"{info}/METADATA"])
    wheel = email.message_from_bytes(files[f"{info}/WHEEL"])
    if metadata["Name"].lower().replace("-", "_") != row["package"]:
        raise ValueError("Wheel component identity mismatch")
    if metadata["Version"] != row["version"] or wheel["Build"] != "1001":
        raise ValueError("Wheel version or build identity mismatch")
    if wheel.get_all("Tag") != row["tags"]:
        raise ValueError("Wheel platform or ABI mismatch")
    expected = {item["path"] for item in row["native_members"]}
    actual = {name for name, content in files.items() if content.startswith(b"\x7fELF")}
    if actual != expected:
        raise ValueError("Wheel native payload inventory mismatch")
    for item in row["native_members"]:
        native = files[item["path"]]
        if len(native) != item["bytes"] or digest(native) != item["sha256"]:
            raise ValueError("Native payload identity mismatch")
    for item in row["metadata_members"]:
        if digest(files[item["path"]]) != item["sha256"]:
            raise ValueError("Wheel metadata or original notice mismatch")
    return files


def verify_inputs(root: Path, platform: str) -> dict:
    document = load_lock(root)
    for item in document["recipe_inputs"]:
        path = checked_path(root, item["path"])
        if digest(path.read_bytes()) != item["sha256"]:
            raise ValueError(f"Native recipe input mismatch {item['path']}")
    verified = []
    for row in rows_for(document, platform):
        check_wheel(checked_path(root, row["path"]), row)
        verified.append(
            {key: row[key] for key in ("package", "version", "path", "bytes", "sha256")}
        )
    return {"status": "PASS", "platform": platform, "wheels": verified}


def verify_stage(root: Path, platform: str, stage: Path) -> dict:
    verify_inputs(root, platform)
    document = load_lock(root)
    members = []
    for row in rows_for(document, platform):
        for item in row["native_members"] + row["metadata_members"]:
            path = checked_path(stage, item["path"])
            if digest(path.read_bytes()) != item["sha256"]:
                raise ValueError(f"Selected native stage differs {item['path']}")
            members.append(item["path"])
    return {"status": "PASS", "platform": platform, "verified_members": members}


def apk_native_name(name: str, abi: str) -> str:
    path = PurePosixPath(name)
    leaf = path.name.split(".")[0]
    mangled = "-".join((*path.parts[:-1], leaf))
    return f"lib/{abi}/lib{mangled}.so"


def verify_apk(apk: Path, root: Path, abi: str = "arm64-v8a") -> dict:
    if abi != "arm64-v8a":
        raise ValueError("Pinned native wheel ABI is arm64-v8a")
    verify_inputs(root, "android")
    data = apk.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = zip_files(archive)
    try:
        with zipfile.ZipFile(io.BytesIO(files["assets/sitepackages.zip"])) as archive:
            site = zip_files(archive)
    except KeyError as error:
        raise ValueError("Final APK sitepackages.zip is missing") from error
    results = []
    metadata_count = 0
    for row in rows_for(load_lock(root), "android"):
        for item in row["native_members"]:
            member = apk_native_name(item["path"], abi)
            if member not in files:
                raise ValueError(f"Final APK native member missing {member}")
            actual = digest(files[member])
            variants = {
                item["sha256"]: "original",
                item["agp_stripped_sha256"]: "NDK strip-unneeded",
            }
            if actual not in variants:
                raise ValueError(f"Final APK native payload differs {member}")
            results.append(
                {"member": member, "sha256": actual, "transformation": variants[actual]}
            )
        for item in row["metadata_members"]:
            if item["path"] not in site or digest(site[item["path"]]) != item["sha256"]:
                raise ValueError(f"Final APK metadata or notice differs {item['path']}")
            metadata_count += 1
    return {
        "status": "PASS",
        "artifact_sha256": digest(data),
        "native_members": results,
        "metadata_members_verified": metadata_count,
        "nested_container": "assets/sitepackages.zip",
    }


def verify_linux(bundle: Path, root: Path) -> dict:
    result = verify_stage(root, "linux", bundle / "site-packages")
    result["carrier"] = "Linux bundle site-packages"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("inputs", "stage", "apk", "linux"))
    parser.add_argument("--root", "--project", dest="root", type=Path, required=True)
    parser.add_argument("--platform", choices=tuple(PACKAGES))
    parser.add_argument("--stage", type=Path)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--abi", default="arm64-v8a")
    parser.add_argument("--output", "--report", dest="output", type=Path)
    args = parser.parse_args()
    if args.operation == "inputs" and args.platform:
        result = verify_inputs(args.root, args.platform)
    elif args.operation == "stage" and args.platform and args.stage:
        result = verify_stage(args.root, args.platform, args.stage)
    elif args.operation == "apk" and args.apk:
        result = verify_apk(args.apk, args.root, args.abi)
    elif args.operation == "linux" and args.bundle:
        result = verify_linux(args.bundle, args.root)
    else:
        parser.error("Missing operation-specific arguments")
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
