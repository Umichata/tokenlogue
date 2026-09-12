"""Locked inputs and read-only checks for the standalone runtime (Python 3.10+)."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

Record = dict[str, Any]


class Failure(RuntimeError):
    """A failed mandatory check, with a message safe to put in a report."""


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise Failure(f"Unsafe relative path: {value!r}")
    if any(ord(character) < 32 for character in value):
        raise Failure("Control character in path")
    return path


def input_path(root: Path, name: str) -> Path:
    path = root / relative_path(name)
    if not path.resolve().is_relative_to(root.resolve()):
        raise Failure(f"Path escapes input directory: {name}")
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise Failure(f"Symlink in input path: {name}")
    return path


def verify_file(path: Path, record: Record) -> None:
    if path.is_symlink() or not path.is_file():
        raise Failure(f"Missing regular input: {record['path']}")
    if path.stat().st_size != record["size"] or digest(path) != record["sha256"]:
        raise Failure(f"Input size/SHA-256 mismatch: {record['path']}")


def load_lock(path: Path) -> Record:
    lock = json.loads(path.read_text())
    if lock["schema"] != 1 or lock["builder"]["platform"] != "linux/amd64":
        raise Failure("Unsupported lock schema/platform")
    files = lock["files"]
    names = [str(item["path"]) for item in files]
    if len(names) != len(set(names)):
        raise Failure("Duplicate locked input")
    for item in files:
        relative_path(item["path"])
        if not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]) or item["size"] <= 0:
            raise Failure(f"Invalid input pin: {item['path']}")
        url = urllib.parse.urlsplit(item["url"])
        if url.scheme != "https" or url.username or url.password or url.query:
            raise Failure(
                "Only public HTTPS URLs without credentials/query are allowed"
            )
    packages = {p["name"]: p for p in lock["packages"]}
    if len(packages) != len(lock["packages"]):
        raise Failure("Duplicate APK name")
    if set(packages) != set(lock["required_packages"]):
        raise Failure("Missing or unexpected locked package")
    provided = set(packages)
    for package in packages.values():
        provided.update(re.split(r"[<>=~]", name, 1)[0] for name in package["provides"])
    for package in packages.values():
        for dependency in package["depends"]:
            if dependency.startswith("!"):
                continue
            if re.split(r"[<>=~]", dependency, 1)[0] not in provided:
                raise Failure(
                    f"Missing locked APK dependency: {package['name']} -> {dependency}"
                )
    inherited = {p["name"]: p for p in lock["builder"]["inherited_packages"]}
    expected_inventory = []
    for package in packages.values():
        item = {
            key: package[key]
            for key in ("name", "version", "arch", "origin", "aports_commit")
        }
        previous = inherited.get(package["name"])
        if previous is not None and previous["version"] == package["version"]:
            item["arch"] = previous["arch"]
        expected_inventory.append(item)
    check_inventory(lock["installed_inventory"], expected_inventory)
    components = {c["name"]: c for c in lock["components"]}
    if set(components) != {
        "type2-runtime",
        "libfuse",
        "squashfuse",
        "musl",
        "gcc",
        "zlib",
        "zstd",
        "mimalloc2",
    }:
        raise Failure("Missing required source component")
    for package in packages.values():
        if package["path"] not in names or package["arch"] not in {"x86_64", "noarch"}:
            raise Failure(f"Missing APK or invalid architecture: {package['name']}")
        if not re.fullmatch(r"[a-f0-9]{40}", package["aports_commit"]):
            raise Failure("Missing APK aports commit")
    for component in components.values():
        if component["source"] not in names or not component["licenses"]:
            raise Failure(f"Missing required source/license: {component['name']}")
        if "aports_commit" in component:
            if component["recipe"] + "/APKBUILD" not in names:
                raise Failure(f"Missing required recipe: {component['name']}")
            for name in component["packages"]:
                p = packages[name]
                if (p["origin"], p["version"], p["aports_commit"]) != (
                    component["name"],
                    component["package_version"],
                    component["aports_commit"],
                ):
                    raise Failure(f"APK/source origin mismatch: {name}")
    return lock


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise Failure("Non-HTTPS download redirect")
        result = super().redirect_request(req, fp, code, msg, headers, newurl)
        if result is not None and req.host != result.host:
            result.remove_header("Authorization")
        return result


def fetch_inputs(lock: Record, root: Path) -> None:
    # Proxies and ambient auth handlers are intentionally not inherited.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), PublicRedirect()
    )
    registry_token: str | None = None
    for item in lock["files"]:
        path = input_path(root, item["path"])
        if path.exists() or path.is_symlink():
            verify_file(path, item)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = {"User-Agent": "tokenlogue-runtime-inputs/1"}
        if item["url"].startswith("https://registry-1.docker.io/v2/library/alpine/"):
            if registry_token is None:
                with opener.open(
                    "https://auth.docker.io/token?service=registry.docker.io"
                    "&scope=repository:library/alpine:pull",
                    timeout=60,
                ) as response:
                    registry_token = json.load(response)["token"]
            headers["Authorization"] = "Bearer " + str(registry_token)
            headers["Accept"] = "application/vnd.oci.image.manifest.v1+json"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                request = urllib.request.Request(item["url"], headers=headers)
                with opener.open(request, timeout=120) as response:
                    remaining = item["size"] + 1
                    while remaining:
                        chunk = response.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        stream.write(chunk)
                        remaining -= len(chunk)
            verify_file(temporary, item)
            temporary.replace(path)
        except urllib.error.HTTPError as error:
            raise Failure(
                f"Download failed: {item['path']} (HTTP {error.code})"
            ) from None
        except (urllib.error.URLError, TimeoutError) as error:
            # Never put redirect URLs, registry tokens or proxy credentials in reports.
            raise Failure(
                f"Download failed: {item['path']} ({type(error).__name__})"
            ) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def tar_members(path: Path, names: list[str]) -> dict[str, bytes]:
    wanted = set(names)
    result = {}
    with tarfile.open(path, "r:*", ignore_zeros=True) as archive:
        for member in archive:
            name = str(PurePosixPath(member.name))
            if name not in wanted:
                continue
            if name in result or not member.isfile():
                raise Failure(f"Duplicate/non-regular archive member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise Failure(f"Missing archive member: {name}")
            result[name] = stream.read()
    if set(result) != wanted:
        raise Failure(
            f"Missing archive members in {path.name}: {sorted(wanted - set(result))}"
        )
    return result


def extract_source(path: Path, destination: Path, epoch: int) -> None:
    """Extract into a new directory, with links last and no writes through links."""
    if destination.exists() or destination.is_symlink():
        raise Failure(f"Source extraction needs a fresh directory: {destination.name}")
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        paths: dict[PurePosixPath, tarfile.TarInfo] = {}
        links: dict[PurePosixPath, PurePosixPath] = {}
        for member in members:
            name = relative_path(member.name)
            if name in paths:
                raise Failure(f"Duplicate tar path: {name}")
            if not (
                member.isfile() or member.isdir() or member.issym() or member.islnk()
            ):
                raise Failure(f"Special tar file: {name}")
            paths[name] = member
            if member.issym() or member.islnk():
                if (
                    PurePosixPath(member.linkname).is_absolute()
                    or "\\" in member.linkname
                ):
                    raise Failure(f"Unsafe tar link: {name}")
                base = str(name.parent) if member.issym() else "."
                links[name] = relative_path(
                    posixpath.normpath(posixpath.join(base, member.linkname))
                )
        for name in paths:
            if any(parent in links for parent in name.parents):
                raise Failure(f"Tar path goes through link: {name}")
        for name, target in links.items():
            seen = {name}
            while target in links:
                if target in seen:
                    raise Failure(f"Cyclic tar link: {name}")
                seen.add(target)
                target = links[target]
            if target not in paths or any(parent in links for parent in target.parents):
                raise Failure(f"Unresolved tar link: {name}")
        destination.mkdir(parents=True)
        for name, member in paths.items():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                target.mkdir(exist_ok=True)
            elif member.isfile():
                stream = archive.extractfile(member)
                assert stream is not None
                with target.open("xb") as output:
                    shutil.copyfileobj(stream, output)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
                os.utime(target, (epoch, epoch))
        for name, member in paths.items():
            target = destination / name
            if member.issym():
                target.symlink_to(member.linkname)
            elif member.islnk():
                linked = destination / links[name]
                if not stat.S_ISREG(linked.lstat().st_mode):
                    raise Failure(f"Hardlink target is not a regular file: {name}")
                os.link(linked, target)
        for directory in sorted(destination.rglob("*"), reverse=True):
            if directory.is_dir() and not directory.is_symlink():
                os.utime(directory, (epoch, epoch))


def parse_inventory(text: str) -> list[Record]:
    result = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
        if "P" in fields:
            result.append(
                {
                    "name": fields["P"],
                    "version": fields["V"],
                    "arch": fields["A"],
                    "origin": fields["o"],
                    "aports_commit": fields["c"],
                }
            )
    return sorted(result, key=lambda item: item["name"])


def check_inventory(actual: list[Record], expected: list[Record]) -> None:
    actual_names = [p["name"] for p in actual]
    expected_names = [p["name"] for p in expected]
    if len(actual_names) != len(set(actual_names)) or set(actual_names) != set(
        expected_names
    ):
        raise Failure(
            f"Inventory mismatch: missing={sorted(set(expected_names) - set(actual_names))}; "
            f"unexpected={sorted(set(actual_names) - set(expected_names))}"
        )
    expected_by_name = {p["name"]: p for p in expected}
    for package in actual:
        wanted = expected_by_name[package["name"]]
        for key in ("version", "arch", "origin", "aports_commit"):
            if package[key] != wanted[key]:
                raise Failure(f"Inventory mismatch: {package['name']} {key}")


def check_inputs(lock: Record, root: Path, materials: Path | None = None) -> Record:
    by_path = {item["path"]: item for item in lock["files"]}
    for item in lock["files"]:
        verify_file(input_path(root, item["path"]), item)
    builder = lock["builder"]
    manifest = json.loads((root / builder["manifest"]).read_text())
    if "sha256:" + by_path[builder["manifest"]]["sha256"] != builder["digest"]:
        raise Failure("Builder manifest digest mismatch")
    for descriptor, name in [
        (manifest["config"], builder["config"]),
        *zip(manifest["layers"], builder["layers"]),
    ]:
        if (descriptor["digest"], descriptor["size"]) != (
            "sha256:" + by_path[name]["sha256"],
            by_path[name]["size"],
        ):
            raise Failure("Builder blob does not match manifest")
    if len(manifest["layers"]) != len(builder["layers"]) or len(builder["layers"]) != 1:
        raise Failure("Unsupported builder layers")
    config = json.loads((root / builder["config"]).read_text())
    if (config["os"], config["architecture"]) != ("linux", "amd64"):
        raise Failure("Wrong builder config architecture")
    base_names = ["lib/apk/db/installed", *builder["keys"]]
    base = tar_members(root / builder["layers"][0], base_names)
    check_inventory(
        parse_inventory(base[base_names[0]].decode()), builder["inherited_packages"]
    )
    for name, expected in builder["keys"].items():
        if hashlib.sha256(base[name]).hexdigest() != expected:
            raise Failure("Builder APK trust key mismatch")
    for package in lock["packages"]:
        raw = tar_members(root / package["path"], [".PKGINFO"])[".PKGINFO"]
        metadata = dict(
            line.split(" = ", 1) for line in raw.decode().splitlines() if " = " in line
        )
        for key, field in [
            ("pkgname", "name"),
            ("pkgver", "version"),
            ("arch", "arch"),
            ("origin", "origin"),
            ("commit", "aports_commit"),
        ]:
            if metadata[key] != package[field]:
                raise Failure(f"APK metadata mismatch: {package['name']} {field}")
        if materials is not None:
            target = materials / "metadata" / (package["name"] + ".PKGINFO")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    for component in lock["components"]:
        source = root / component["source"]
        license_files = tar_members(source, component["licenses"])
        if "recipe" in component:
            recipe = root / component["recipe"]
            text = (recipe / "APKBUILD").read_text()
            version = re.search(r"^pkgver=([^\s]+)$", text, re.M)
            release = re.search(r"^pkgrel=([0-9]+)$", text, re.M)
            if (
                version is None
                or release is None
                or f"{version[1]}-r{release[1]}" != component["package_version"]
            ):
                raise Failure(f"APKBUILD version mismatch: {component['name']}")
            sums = re.findall(r"^([a-f0-9]{128})  (\S+)$", text, re.M)
            if not sums:
                raise Failure(f"Missing APKBUILD source checksums: {component['name']}")
            for expected, name in sums:
                candidate = source if name == source.name else input_path(recipe, name)
                if not candidate.is_file() or digest(candidate, "sha512") != expected:
                    raise Failure(
                        f"APKBUILD source/patch mismatch: {component['name']}/{name}"
                    )
        if materials is not None:
            for name, data in license_files.items():
                target = (
                    materials
                    / "licenses"
                    / component["name"]
                    / PurePosixPath(name).name
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    upstream_files = tar_members(
        root / "sources/type2-runtime.tar.gz", list(lock["upstream_files"])
    )
    for name, expected in lock["upstream_files"].items():
        if hashlib.sha256(upstream_files[name]).hexdigest() != expected:
            raise Failure(f"Upstream recipe/patch mismatch: {name}")
        if materials is not None:
            target = (
                materials
                / "upstream"
                / Path(name).relative_to(lock["upstream"]["root"])
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(upstream_files[name])
    return {
        "result": "PASS",
        "scope": "locked file integrity and source correspondence",
        "files": len(by_path),
        "packages": len(lock["packages"]),
        "apk_signatures": "NOT_RUN (requires native apk in pinned container)",
    }
