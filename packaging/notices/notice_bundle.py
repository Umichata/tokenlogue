"""Validate and stage the small, checked-in supplemental notice bundle."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

PLATFORMS = {"android", "linux"}
REQUIRED_COMPONENTS = {
    "android": {"libffi-runtime", "dart-bridge", "katex-fonts", "material-icons"},
    "linux": {"material-icons"},
}
DIRECTORY = "packaging/notices"


class NoticeError(ValueError):
    """Required notice inputs or staged output do not match their registry."""


def _relative(name: Any) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise NoticeError("unsafe notice path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name:
        raise NoticeError(f"unsafe notice path {name!r}")
    return name


def _no_symlinks(path: Path) -> None:
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise NoticeError(f"symlink in notice path {path.name}")


def _file(root: Path, relative: str) -> Path:
    path = root / _relative(relative)
    _no_symlinks(path)
    if not path.is_file():
        raise NoticeError(f"missing required notice input {relative}")
    return path


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _notes(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(value.get(language), str) or not value[language].strip()
        for language in ("en", "ru")
    ):
        raise NoticeError("notice explanation must include English and Russian")
    return value


def _load(project_root: Path, platform: str) -> tuple[dict, list[dict]]:
    if platform not in PLATFORMS:
        raise NoticeError(f"unsupported notice platform {platform!r}")
    _file(project_root, DIRECTORY + "/notice_bundle.py")
    path = _file(project_root, DIRECTORY + "/sources.json")
    try:
        registry = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise NoticeError("cannot read notice source registry") from error
    if (
        not isinstance(registry, dict)
        or registry.get("schema") != 1
        or not isinstance(registry.get("components"), list)
    ):
        raise NoticeError("unsupported notice source registry")
    platform_notes = registry.get("platform_notes")
    if not isinstance(platform_notes, dict):
        raise NoticeError("missing platform notice explanations")
    _notes(platform_notes.get(platform))
    selected: list[dict] = []
    identities: set[str] = set()
    inputs: set[str] = set()
    outputs: set[str] = set()
    for component in registry["components"]:
        if not isinstance(component, dict):
            raise NoticeError("invalid notice component")
        identity = component.get("id")
        platforms = component.get("platforms")
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identity)
            or identity in identities
            or not isinstance(component.get("version"), str)
            or not component["version"]
            or not isinstance(component.get("source"), dict)
            or not component["source"]
            or not isinstance(platforms, list)
            or not platforms
            or any(
                not isinstance(value, str) or value not in PLATFORMS
                for value in platforms
            )
            or len(set(platforms)) != len(platforms)
            or not isinstance(component.get("files"), list)
            or not component["files"]
        ):
            raise NoticeError("invalid or repeated notice component")
        identities.add(identity)
        for record in component["files"]:
            if not isinstance(record, dict):
                raise NoticeError("invalid notice file record")
            input_path = _relative(record.get("input"))
            output_path = _relative(record.get("output"))
            if (
                not input_path.startswith("inputs/")
                or not output_path.startswith(("licenses/", "attribution/"))
                or input_path in inputs
                or output_path in outputs
                or not isinstance(record.get("size"), int)
                or isinstance(record["size"], bool)
                or record["size"] < 1
                or not isinstance(record.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
            ):
                raise NoticeError("invalid or repeated notice file record")
            inputs.add(input_path)
            outputs.add(output_path)
        if platform in platforms:
            notes = component.get("notes")
            if not isinstance(notes, dict):
                raise NoticeError("missing component notice explanations")
            _notes(notes.get(platform))
            selected.append(component)
    if any(
        str(parent) in paths
        for paths in (inputs, outputs)
        for name in paths
        for parent in PurePosixPath(name).parents
    ):
        raise NoticeError("conflicting notice file and directory paths")
    selected_ids = {component["id"] for component in selected}
    required_ids = REQUIRED_COMPONENTS[platform]
    if selected_ids != required_ids:
        missing = ", ".join(sorted(required_ids - selected_ids)) or "none"
        unexpected = ", ".join(sorted(selected_ids - required_ids)) or "none"
        raise NoticeError(
            f"required notice components for {platform} differ "
            f"(missing {missing}, unexpected {unexpected})"
        )
    return registry, selected


def _bundle(project_root: Path, platform: str) -> tuple[dict[str, bytes], dict]:
    registry, components = _load(project_root, platform)
    files: dict[str, bytes] = {}
    manifest: dict[str, Any] = {
        "schema": 1,
        "platform": platform,
        "components": [],
        "files": [],
    }
    for component in components:
        notice_paths = []
        for record in component["files"]:
            path = _file(project_root / DIRECTORY, record["input"])
            data = path.read_bytes()
            if len(data) != record["size"] or _digest(data) != record["sha256"]:
                raise NoticeError(f"notice input checksum mismatch {record['input']}")
            name = record["output"]
            files[name] = data
            notice_paths.append(name)
            manifest["files"].append(
                {
                    "path": name,
                    "size": len(data),
                    "sha256": _digest(data),
                    "component": component["id"],
                }
            )
        manifest["components"].append(
            {
                "id": component["id"],
                "version": component["version"],
                "source": component["source"],
                "notice_paths": notice_paths,
            }
        )
    readme = [
        "[English](#english) · [Русский](#русский)",
        "",
        "# Third-party notices",
        "",
    ]
    for language, title in (("en", "English"), ("ru", "Русский")):
        readme.extend(
            [f"## {title}", "", registry["platform_notes"][platform][language], ""]
        )
        for component in components:
            readme.extend(
                [
                    f"### {component['id']} {component['version']}",
                    "",
                    component["notes"][platform][language],
                    "",
                ]
            )
            readme.extend(
                f"- [{record['output']}]({record['output']})"
                for record in component["files"]
            )
            readme.append("")
    files["README.md"] = ("\n".join(readme).rstrip() + "\n").encode("utf-8")
    manifest["files"].append(
        {
            "path": "README.md",
            "size": len(files["README.md"]),
            "sha256": _digest(files["README.md"]),
            "component": "bundle",
        }
    )
    manifest["files"].sort(key=lambda item: item["path"])
    files["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    return files, manifest


def required_inputs(project_root: Path, platform: str) -> tuple[str, ...]:
    """Return validated repository-relative inputs used by a platform recipe."""
    _bundle(project_root, platform)
    _, components = _load(project_root, platform)
    return (
        DIRECTORY + "/notice_bundle.py",
        DIRECTORY + "/sources.json",
        *sorted(
            DIRECTORY + "/" + record["input"]
            for component in components
            for record in component["files"]
        ),
    )


def bundle_files(project_root: Path, platform: str) -> dict[str, bytes]:
    """Return complete original texts and their deterministic bundle metadata."""
    return _bundle(project_root, platform)[0]


def _check_destination(
    destination: Path, files: dict[str, bytes], complete: bool
) -> None:
    _no_symlinks(destination)
    if not destination.exists():
        if complete:
            raise NoticeError("missing staged notice bundle")
        return
    if not destination.is_dir():
        raise NoticeError("notice destination is not a directory")
    directories = {
        str(parent) for name in files for parent in PurePosixPath(name).parents
    }
    found = set()
    for path in destination.rglob("*"):
        name = path.relative_to(destination).as_posix()
        if path.is_symlink():
            raise NoticeError(f"symlink in staged notice bundle {name}")
        if path.is_dir() and name in directories:
            continue
        if not path.is_file() or name not in files:
            raise NoticeError(f"unexpected staged notice output {name}")
        if path.read_bytes() != files[name]:
            raise NoticeError(f"staged notice checksum mismatch {name}")
        found.add(name)
    if complete and found != set(files):
        raise NoticeError("missing staged notice output")


def stage_notices(project_root: Path, platform: str, destination: Path) -> dict:
    """Validate every input before writing an exclusive, idempotent bundle."""
    files, manifest = _bundle(project_root, platform)
    _check_destination(destination, files, complete=False)
    for name, data in files.items():
        path = destination / name
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    _check_destination(destination, files, complete=True)
    return manifest


def verify_notices(project_root: Path, platform: str, destination: Path) -> dict:
    """Verify exact staged bytes, file set and original input provenance."""
    files, manifest = _bundle(project_root, platform)
    _check_destination(destination, files, complete=True)
    return manifest
