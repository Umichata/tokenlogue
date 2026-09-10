"""Сбор и проверка лицензионного реестра фактического AppDir."""

from __future__ import annotations

import argparse
import csv
import email.parser
import gzip
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from notice_inputs import (
    NoticeError,
    extract_python,
    fetch_asset,
    font_names,
    load_lock,
    reject_proxies,
    relative_file,
    same_binary,
    sha256,
)

DIRECTORY = Path(__file__).resolve().parent
DOC = "usr/share/doc/tokenlogue"
MANIFEST = f"{DOC}/notices.json"
BUNDLE = "usr/lib/tokenlogue"
FLUTTER_LIBS = {
    "libapp.so",
    "libflutter_linux_gtk.so",
    "libflutter_secure_storage_linux_plugin.so",
    "libpasteboard_plugin.so",
    "libscreen_retriever_linux_plugin.so",
    "libserious_python_linux_plugin.so",
    "liburl_launcher_linux_plugin.so",
    "libwindow_manager_plugin.so",
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise NoticeError(f"{command[0]} failed while locating native package metadata")
    return result.stdout


def native_origin(binary: Path) -> tuple[dict, Path]:
    candidates = []
    for line in run(["/sbin/ldconfig", "-p"]).splitlines():
        if " => " in line and line.split()[0] == binary.name:
            candidates.append(Path(line.split(" => ", 1)[1]))
    for candidate in sorted(set(candidates)):
        try:
            same_binary(binary, candidate)
        except NoticeError:
            continue
        for owner_path in dict.fromkeys([candidate, candidate.resolve()]):
            query = subprocess.run(
                ["dpkg-query", "-S", str(owner_path)], capture_output=True, text=True
            )
            owners = [
                line.rsplit(": ", 1)[0]
                for line in query.stdout.splitlines()
                if line.endswith(": " + str(owner_path))
            ]
            if len(owners) != 1:
                continue
            fields = (
                run(
                    [
                        "dpkg-query",
                        "-W",
                        "-f=${binary:Package}\t${Version}\t${source:Package}\t${source:Version}",
                        owners[0],
                    ]
                )
                .strip()
                .split("\t")
            )
            if len(fields) != 4:
                raise NoticeError("incomplete Debian source package metadata")
            package, version, source, source_version = fields
            copyright_file = (
                Path("/usr/share/doc") / package.split(":")[0] / "copyright"
            )
            if not copyright_file.is_file():
                raise NoticeError(f"missing copyright for Debian package {package}")
            return {
                "package": package,
                "version": version,
                "source_package": source,
                "source_version": source_version,
                "binary_sha256_before_patching": sha256(candidate),
                "match": "ELF code/constants/build-id",
            }, copyright_file
    raise NoticeError(f"no matching installed Debian package for {binary.name}")


def subjects(root: Path) -> set[str]:
    result = set()
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if (
            magic == b"\x7fELF"
            or path.suffix.lower() in {".ttf", ".otf"}
            or path.name == "METADATA"
            and path.parent.name.endswith(".dist-info")
        ):
            result.add(path.relative_to(root).as_posix())
    return result


class Collector:
    def __init__(self, root: Path, lock: dict):
        self.root = root
        self.lock = lock
        self.components: list[dict] = []
        self.covered: set[str] = set()
        self.notice_paths: set[str] = set()

    def copy(self, source: Path, target: str) -> str:
        if not source.is_file() or source.stat().st_size < 20:
            raise NoticeError(f"empty or absent notice: {source.name}")
        name = f"{DOC}/licenses/{target}"
        output = self.root / name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        self.notice_paths.add(name)
        return name

    def text(self, target: str, value: str) -> str:
        name = f"{DOC}/licenses/{target}"
        output = self.root / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(value, encoding="utf-8")
        self.notice_paths.add(name)
        return name

    def add(
        self, name: str, paths: list[str], licenses: list[str], origin: dict
    ) -> None:
        if not licenses:
            raise NoticeError(f"component has no notices: {name}")
        for path in paths + licenses:
            relative_file(self.root, path)
        self.components.append(
            {
                "id": name,
                "files": sorted(paths),
                "notices": sorted(set(licenses)),
                "origin": origin,
            }
        )
        self.covered.update(paths)

    def group(self, name: str) -> list[str]:
        return [
            self.copy(DIRECTORY / r["path"], "upstream/" + Path(r["path"]).name)
            for r in self.lock["texts"]
            if r["group"] == name
        ]

    def collect_native(self) -> None:
        for binary in sorted((self.root / "usr/lib").glob("*.so*")):
            if binary.is_symlink():
                continue
            info, copyright_file = native_origin(binary)
            notice = self.copy(copyright_file, f"debian/{info['package']}/copyright")
            self.add(
                "debian:" + info["package"] + ":" + binary.name,
                [binary.relative_to(self.root).as_posix()],
                [notice],
                info,
            )
        # Сохраняем полные тексты, на которые ссылаются Debian copyright.
        common = Path("/usr/share/common-licenses")
        for path in sorted(common.iterdir()):
            if path.is_file():
                self.copy(path, "common-licenses/" + path.name)
        for name in sorted(self.notice_paths):
            if "/debian/" not in name:
                continue
            text = (self.root / name).read_text()
            for ref in re.findall(
                r"/usr/share/common-licenses/([A-Za-z0-9.+-]+)", text
            ):
                relative_file(
                    self.root, f"{DOC}/licenses/common-licenses/{ref.rstrip('.')}"
                )

    def collect_python(self, cache: Path) -> None:
        archive = relative_file(cache, self.lock["python"]["sha256"])
        if sha256(archive) != self.lock["python"]["sha256"]:
            raise NoticeError("Python reference archive checksum mismatch")
        with tempfile.TemporaryDirectory(prefix="python-notices-") as td:
            extract_python(archive, Path(td))
            reference = Path(td) / "python"
            meta = json.loads((reference / "PYTHON.json").read_text())
            if (
                meta["python_version"] != self.lock["python"]["version"]
                or meta["target_triple"] != self.lock["python"]["target"]
            ):
                raise NoticeError("Python metadata target/version mismatch")
            licenses = [
                self.copy(p, "python-runtime/" + p.name)
                for p in sorted((reference / "licenses").glob("LICENSE.*.txt"))
            ]
            if not licenses:
                raise NoticeError("Python dependency license set is empty")
            self.copy(reference / "PYTHON.json", "python-runtime/PYTHON.json")
            mapped = []
            for name in ("libpython3.12.so.1.0", "libpython3.so"):
                rel = f"{BUNDLE}/lib/{name}"
                same_binary(
                    relative_file(self.root, rel), reference / "install/lib" / name
                )
                mapped.append(rel)
            for extension in sorted(
                (self.root / BUNDLE / "python3.12/lib-dynload").glob("*.so")
            ):
                same_binary(
                    extension,
                    reference / "install/lib/python3.12/lib-dynload" / extension.name,
                )
                mapped.append(extension.relative_to(self.root).as_posix())
            # Metadata PBS содержит альтернативы, например zlib-ng для других сборок.
            # Сохраняем весь фактически поставленный upstream набор и точные metadata.
            self.add("cpython-runtime", mapped, licenses, self.lock["python"])

    def collect_packages(self, flutter_notice: str) -> None:
        packages = self.root / BUNDLE / "site-packages"
        for info in sorted(packages.glob("*.dist-info")):
            metadata = relative_file(info, "METADATA")
            parsed = email.parser.Parser().parsestr(metadata.read_text())
            name, version = parsed["Name"], parsed["Version"]
            if not name or not version or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                raise NoticeError("invalid distribution metadata")
            licenses = []
            for file in sorted(info.rglob("*")):
                if file.is_file() and (
                    "license" in file.name.lower() or "copying" in file.name.lower()
                ):
                    licenses.append(
                        self.copy(
                            file,
                            f"python-packages/{info.name}/{file.relative_to(info).as_posix()}",
                        )
                    )
            if not licenses and name.lower() == "flet" and version == "0.86.5":
                licenses = self.group("flet") + [flutter_notice]
            if not licenses:
                raise NoticeError(f"distribution notice missing: {name}=={version}")
            owned = [metadata.relative_to(self.root).as_posix()]
            record = info / "RECORD"
            if record.is_file():
                with record.open(newline="") as stream:
                    for row in csv.reader(stream):
                        if not row or not row[0].endswith(".so"):
                            continue
                        file = relative_file(packages, row[0])
                        owned.append(file.relative_to(self.root).as_posix())
            self.add(
                "python:" + name,
                owned,
                licenses,
                {"version": version, "metadata": owned[0]},
            )

    def collect_fonts(self, flutter_notice: str) -> None:
        font_licenses = self.group("fonts")
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".ttf", ".otf"}:
                continue
            names = font_names(path)
            rel = path.relative_to(self.root).as_posix()
            if path.name.startswith("KaTeX_"):
                declaration = "\n".join(names.get("13", []))
                if (
                    "SIL Open Font License, Version 1.1" not in declaration
                    or "Reserved Font Name" not in declaration
                ):
                    raise NoticeError("unexpected KaTeX font license declaration")
                copyright = self.text(
                    "fonts/" + path.name + ".txt",
                    "\n".join(names.get("0", []) + names.get("13", [])) + "\n",
                )
                licenses = font_licenses + [copyright]
            elif path.name in {"MaterialIcons-Regular.otf", "CupertinoIcons.ttf"}:
                licenses = [flutter_notice]
            else:
                raise NoticeError(f"unregistered font: {rel}")
            self.add("font:" + path.name, [rel], licenses, {"font_names": names})

    def collect(self, cache: Path, runtime: Path, pubspec: Path) -> None:
        if sha256(runtime) != self.lock["runtime"]["sha256"]:
            raise NoticeError(
                "AppImage runtime checksum does not match notice registry"
            )
        self.add("appimage-runtime", [], self.group("runtime"), self.lock["runtime"])
        self.copy(DIRECTORY / "notices.lock.json", "upstream/notices.lock.json")
        if "serious_python_linux:" not in pubspec.read_text():
            raise NoticeError(
                "resolved Flutter pubspec.lock is missing serious_python_linux"
            )
        self.copy(pubspec, "flutter/pubspec.lock")
        notices = relative_file(self.root, f"{BUNDLE}/data/flutter_assets/NOTICES.Z")
        text = gzip.decompress(notices.read_bytes()).decode("utf-8")
        if "serious_python" not in text or "flutter" not in text.lower():
            raise NoticeError("incomplete Flutter notices")
        flutter_notice = self.text("flutter/NOTICES.txt", text)
        self.notice_paths.add(notices.relative_to(self.root).as_posix())
        self.add(
            "tokenlogue", [f"{BUNDLE}/tokenlogue"], ["LICENSE"], {"license": "MIT"}
        )
        self.notice_paths.add("LICENSE")
        flutter_files = []
        for name in sorted(FLUTTER_LIBS):
            path = relative_file(self.root, f"{BUNDLE}/lib/{name}")
            flutter_files.append(path.relative_to(self.root).as_posix())
        self.add(
            "flutter-and-plugins",
            flutter_files,
            [flutter_notice],
            {"resolved_packages": f"{DOC}/licenses/flutter/pubspec.lock"},
        )
        bridge = relative_file(cache, self.lock["bridge"]["sha256"])
        if sha256(bridge) != self.lock["bridge"]["sha256"]:
            raise NoticeError("bridge reference checksum mismatch")
        same_binary(relative_file(self.root, f"{BUNDLE}/lib/libdart_bridge.so"), bridge)
        self.add(
            "dart-bridge",
            [f"{BUNDLE}/lib/libdart_bridge.so"],
            self.group("bridge") + [flutter_notice],
            self.lock["bridge"],
        )
        self.collect_native()
        self.collect_python(cache)
        self.collect_packages(flutter_notice)
        self.collect_fonts(flutter_notice)
        missing = subjects(self.root) - self.covered
        if missing:
            raise NoticeError(
                "unregistered packaged components: " + ", ".join(sorted(missing))
            )
        index = "# Third-party notices\n\n"
        index += "This index describes this AppImage. Full license texts are in `usr/share/doc/tokenlogue/licenses/`.\n"
        index += "Debian copyright files also describe source-package files that may not be included here.\n"
        index += "Python license files preserve the complete upstream distribution set, including unused optional modules.\n"
        index += "The source-material review is recorded separately in notices.json; this is not a source archive.\n\n"
        for component in self.components:
            index += "## " + component["id"] + "\n\n"
            index += (
                "\n".join("- `" + name + "`" for name in component["notices"]) + "\n\n"
            )
        for name in ("THIRD_PARTY_NOTICES.md", f"{DOC}/THIRD_PARTY_NOTICES.md"):
            (self.root / name).write_text(index, encoding="utf-8")
            self.notice_paths.add(name)
        all_paths = self.covered | self.notice_paths
        manifest = {
            "schema": 1,
            "result": "PASS",
            "scope": "notice presence, exact binary provenance where pinned, and file integrity; not a release approval",
            "source_materials": self.lock["release_source_status"],
            "components": self.components,
            "subjects": sorted(subjects(self.root)),
            "files": {
                name: sha256(relative_file(self.root, name))
                for name in sorted(all_paths)
            },
        }
        write_json(self.root / MANIFEST, manifest)
        verify(self.root)


def verify(root: Path) -> dict:
    manifest = json.loads(relative_file(root, MANIFEST).read_text())
    if manifest["schema"] != 1 or manifest["result"] != "PASS":
        raise NoticeError("invalid notices manifest")
    actual = subjects(root)
    if set(manifest["subjects"]) != actual:
        raise NoticeError("packaged component set differs from notices manifest")
    covered = set()
    for component in manifest["components"]:
        if not component["notices"]:
            raise NoticeError("component has no license references")
        for name in component["files"] + component["notices"]:
            if name not in manifest["files"]:
                raise NoticeError("unhashed component file/notice")
            relative_file(root, name)
        covered.update(component["files"])
    if actual - covered:
        raise NoticeError("component has no notice association")
    for name, expected in manifest["files"].items():
        if sha256(relative_file(root, name)) != expected:
            raise NoticeError(f"notice or packaged component checksum changed: {name}")
    return {
        "result": "PASS",
        "components": len(manifest["components"]),
        "subjects": len(actual),
        "source_materials": manifest["source_materials"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fetch", "collect", "verify"))
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--appdir", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--pubspec-lock", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "verify":
            if args.appdir is None:
                raise NoticeError("--appdir required")
            result = verify(args.appdir.resolve())
        else:
            lock = load_lock(DIRECTORY)
            if args.cache is None:
                raise NoticeError("--cache required")
            if args.action == "fetch":
                reject_proxies()
                for name in ("python", "bridge"):
                    fetch_asset(lock[name], args.cache)
                result = {
                    "result": "PASS",
                    "action": "fetch",
                    "inputs": {name: lock[name] for name in ("python", "bridge")},
                }
            else:
                if (
                    args.appdir is None
                    or args.runtime is None
                    or args.pubspec_lock is None
                ):
                    raise NoticeError("--appdir, --runtime and --pubspec-lock required")
                Collector(args.appdir.resolve(), lock).collect(
                    args.cache, args.runtime, args.pubspec_lock
                )
                result = verify(args.appdir.resolve())
    except (ValueError, OSError, KeyError, TypeError, EOFError, struct.error) as exc:
        result = {"result": "FAIL", "reason": str(exc)}
    if args.report:
        write_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
