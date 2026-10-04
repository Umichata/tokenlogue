#!/usr/bin/env python3
"""Prepare an isolated Flet 0.86.5 template and build one test x86_64 APK."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from zipfile import ZipFile

RECIPE_VERSION = "2"
TEMPLATE_SIZE = 489103
TEMPLATE_SHA256 = "8f95dc20ef6d901d9b5ee59f00e33d19f1d2bc6be8d6d3b800c4aab3d7315b73"
TEMPLATE_URL = (
    "https://github.com/flet-dev/flet/releases/download/v0.86.5/flet-build-template.zip"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OWN_FILES = ("packaging/android/build_apk.py", "tests/test_android_build.py")
OLD_AGP = 'id("com.android.application") version "8.11.1" apply false'
NEW_AGP = 'id("com.android.application") version "8.13.2" apply false'
SETTINGS = "build/{{cookiecutter.out_dir}}/android/settings.gradle.kts"
WRAPPER = (
    "build/{{cookiecutter.out_dir}}/android/gradle/wrapper/gradle-wrapper.properties"
)
APP_GRADLE = "build/{{cookiecutter.out_dir}}/android/app/build.gradle.kts"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", "utf-8")


def prepare_template(archive: Path, destination: Path) -> tuple[Path, str]:
    """Validate before extraction and include all derived bytes in the path identity."""
    if archive.stat().st_size != TEMPLATE_SIZE or sha256(archive) != TEMPLATE_SHA256:
        raise ValueError("Official Flet 0.86.5 template size or SHA-256 differs")
    files: dict[str, tuple[bytes, int]] = {}
    with ZipFile(archive) as zipped:
        for member in zipped.infolist():
            name = PurePosixPath(member.filename)
            mode = member.external_attr >> 16
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in member.filename
                or not name.parts
                or name.parts[0] != "build"
                or stat.S_ISLNK(mode)
            ):
                raise ValueError("Unsafe template member")
            if not member.is_dir():
                if name.as_posix() in files:
                    raise ValueError("Duplicate template member")
                files[name.as_posix()] = (zipped.read(member), mode & 0o777 or 0o644)
    if "build/cookiecutter.json" not in files:
        raise ValueError("Missing cookiecutter root")
    settings, mode = files[SETTINGS]
    if (
        settings.count(OLD_AGP.encode()) != 1
        or settings.count(b'id("com.android.application") version ') != 1
    ):
        raise ValueError("Expected exactly one original root AGP declaration")
    if settings.count(b'id("org.jetbrains.kotlin.android") version "2.2.20"') != 1:
        raise ValueError("Unexpected Kotlin template version")
    if b"gradle-8.14-all.zip" not in files[WRAPPER][0]:
        raise ValueError("Unexpected Gradle wrapper version")
    if b'signingConfig = signingConfigs.getByName("debug")' not in files[APP_GRADLE][0]:
        raise ValueError("Missing default test signing in official template")
    files[SETTINGS] = (settings.replace(OLD_AGP.encode(), NEW_AGP.encode()), mode)
    content = hashlib.sha256(RECIPE_VERSION.encode())
    for name, (data, file_mode) in sorted(files.items()):
        content.update(name.encode() + b"\0" + str(file_mode).encode() + b"\0")
        content.update(hashlib.sha256(data).digest())
    identity = content.hexdigest()
    target = destination / f"template-v{RECIPE_VERSION}-{identity}"
    target.mkdir(parents=True, exist_ok=False)
    for name, (data, file_mode) in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(file_mode)
    return target / "build", identity


def safe_source_name(name: str) -> bool:
    """Even tracked environment, database, key, and cache files stay outside snapshots."""
    path = PurePosixPath(name)
    return not (
        path.is_absolute()
        or ".." in path.parts
        or any(part in {".git", ".venv", "__pycache__", "build"} for part in path.parts)
        or path.name.startswith(".env")
        or path.suffix.lower()
        in {
            ".db",
            ".sqlite",
            ".sqlite3",
            ".jks",
            ".keystore",
            ".pem",
            ".key",
            ".p12",
            ".pfx",
            ".pyc",
        }
    )


def snapshot(repo: Path, destination: Path) -> list[dict[str, object]]:
    """Copy current tracked app bytes and an explicit list of this recipe's new files."""
    listed = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
            "--",
            "src",
            "packaging/icons/android",
            ".gitignore",
            "pyproject.toml",
            "uv.lock",
            "LICENSE",
        ],
        cwd=repo,
    )
    names = {os.fsdecode(name) for name in listed.split(b"\0") if name}
    names.update(OWN_FILES)
    destination.mkdir(parents=True, exist_ok=False)
    inventory: list[dict[str, object]] = []
    for name in sorted(names):
        if not safe_source_name(name):
            continue
        source = repo / name
        if source.is_symlink() or not source.resolve().is_relative_to(repo.resolve()):
            raise ValueError(f"Source snapshot refuses symlink or external path {name}")
        if not source.is_file():
            raise ValueError(f"Required snapshot source missing {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        inventory.append(
            {
                "path": name,
                "size": target.stat().st_size,
                "sha256": sha256(target),
                "mode": stat.S_IMODE(target.stat().st_mode),
            }
        )
    return inventory


def check_configuration(repo: Path, environment: dict[str, str]) -> None:
    metadata = tomllib.loads((repo / "pyproject.toml").read_text("utf-8"))
    flet = metadata["tool"]["flet"]
    android = flet["android"]
    if android.get("signing") or any(
        name.startswith("FLET_ANDROID_SIGNING_") and value
        for name, value in environment.items()
    ):
        raise ValueError("Production signing settings present, test APK build refused")
    if flet.get("template", {}).get("url"):
        raise ValueError(
            "Global template override present, Android-local template required"
        )
    if (
        metadata["project"]["requires-python"] != ">=3.12,<3.13"
        or not {"flet==0.86.5", "flet-secure-storage==0.86.5"}.issubset(
            metadata["project"]["dependencies"]
        )
        or android.get("dependencies") != ["msgpack==1.1.2"]
        or android.get("min_sdk_version") != 24
        or flet.get("bundle_id") != "io.github.umichata.tokenlogue"
        or flet["flutter"]["pubspec"]["dependency_overrides"].get("jni_flutter")
        != "1.0.3"
        or android.get("manifest_application")
        != {"allowBackup": "false", "fullBackupContent": "false"}
        or android.get("permission", {}).get("android.permission.INTERNET") is not True
        or any(
            value
            for name, value in android.get("permission", {}).items()
            if name != "android.permission.INTERNET"
        )
    ):
        raise ValueError("Required pinned Android configuration differs")


def removed_socks_proxy_names(environment: Mapping[str, str]) -> list[str]:
    """Pip's bundled HTTPX does not include the optional SOCKS dependency."""
    return [
        name
        for name in ("ALL_PROXY", "all_proxy")
        if urlsplit(environment.get(name, "")).scheme.startswith("socks")
    ]


def build_environment(jdk: Path, sdk: Path, run: Path) -> dict[str, str]:
    legacy = Path.home() / ".flutter_settings"
    if legacy.exists() or legacy.is_symlink():
        raise ValueError("Legacy Flutter settings override scoped XDG_CONFIG_HOME")
    environment = os.environ.copy()
    for name in removed_socks_proxy_names(environment):
        environment.pop(name)
    environment.update(
        JAVA_HOME=str(jdk),
        ANDROID_HOME=str(sdk),
        ANDROID_SDK_ROOT=str(sdk),
        ANDROID_USER_HOME=str(run / "android-user"),
        XDG_CONFIG_HOME=str(run / "flutter-config"),
        GRADLE_USER_HOME=str(run / "gradle-user-home"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    environment["PATH"] = os.pathsep.join(
        (
            str(jdk / "bin"),
            str(sdk / "cmdline-tools/latest/bin"),
            str(sdk / "platform-tools"),
            str(Path.home() / "flutter/3.44.8/bin"),
            environment.get("PATH", ""),
        )
    )
    return environment


def check_tools(repo: Path, jdk: Path, sdk: Path) -> None:
    javac = subprocess.run(
        [str(jdk / "bin/javac"), "-version"], capture_output=True, text=True, check=True
    )
    if not re.fullmatch(
        r"javac 17(?:\.[\w.+-]+)*", (javac.stdout + javac.stderr).strip()
    ):
        raise ValueError("Selected JAVA_HOME does not provide javac 17")
    versions = subprocess.check_output(
        [
            str(repo / ".venv/bin/python"),
            "-B",
            "-c",
            "from importlib.metadata import version; "
            "print(*(version(n) for n in ('flet', 'flet-cli', 'flet-secure-storage')))",
        ],
        text=True,
    ).strip()
    if versions != "0.86.5 0.86.5 0.86.5":
        raise ValueError("Original .venv versions differ from 0.86.5")
    flutter = Path.home() / "flutter/3.44.8/bin/cache/flutter.version.json"
    if (
        not flutter.is_file()
        or json.loads(flutter.read_text())["flutterVersion"] != "3.44.8"
    ):
        raise ValueError("Existing pinned Flutter 3.44.8 SDK is unavailable")
    required = (
        "cmdline-tools/latest/bin/sdkmanager",
        "platform-tools/adb",
        "platforms/android-35/android.jar",
        "platforms/android-36/android.jar",
        "build-tools/34.0.0/aapt2",
        "build-tools/35.0.0/aapt2",
        "ndk/28.2.13676358/source.properties",
    )
    missing = [name for name in required if not (sdk / name).is_file()]
    if missing:
        raise ValueError("Selected SDK packages missing " + ", ".join(missing))


def run_logged(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    run: Path,
    *,
    mirror: bool = True,
) -> int:
    """Merge streams as raw bytes and record the child exit status without pipelines."""
    write_json(run / "command.json", {"argv": command, "cwd": str(cwd)})
    with (run / "build.log").open("xb") as log:
        with subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as process:
            assert process.stdout is not None
            while chunk := os.read(process.stdout.fileno(), 65536):
                log.write(chunk)
                log.flush()
                if mirror:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
            code = process.wait()
    write_json(run / "exit-code.json", {"exit_code": code})
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--jdk-home", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument(
        "--template-zip",
        type=Path,
        default=(
            Path.home() / ".flet/cache/build-template/v0.86.5/flet-build-template.zip"
        ),
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.expanduser().resolve()
    if run.is_relative_to(PROJECT_ROOT):
        parser.error("Run directory must stay outside the source repository")
    run.mkdir(parents=True, exist_ok=False)
    try:
        jdk, sdk = (
            args.jdk_home.expanduser().resolve(),
            args.sdk_root.expanduser().resolve(),
        )
        environment = build_environment(jdk, sdk, run)
        check_configuration(PROJECT_ROOT, environment)
        template, identity = prepare_template(args.template_zip.expanduser(), run)
        source = run / "source"
        inventory = snapshot(PROJECT_ROOT, source)
        command = [
            str(PROJECT_ROOT / ".venv/bin/flet"),
            "build",
            "apk",
            "--arch",
            "x86_64",
            "--template",
            str(template),
            "-vv",
        ]
        write_json(
            run / "preparation.json",
            {
                "recipe_version": RECIPE_VERSION,
                "template_url": TEMPLATE_URL,
                "template_zip": str(args.template_zip),
                "template_zip_sha256": TEMPLATE_SHA256,
                "template_identity": identity,
                "template": str(template),
                "source": str(source),
                "head": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
                ).strip(),
                "files": inventory,
                "command": command,
                "signing": "default debug certificate",
                "removed_proxy_variable_names": removed_socks_proxy_names(os.environ),
                "environment": {
                    name: environment[name]
                    for name in (
                        "JAVA_HOME",
                        "ANDROID_HOME",
                        "ANDROID_SDK_ROOT",
                        "ANDROID_USER_HOME",
                        "XDG_CONFIG_HOME",
                        "GRADLE_USER_HOME",
                        "PATH",
                    )
                },
                "build": "NOT_RUN" if args.prepare_only else "PENDING",
            },
        )
        if args.prepare_only:
            print(f"Prepared snapshot {source}\nTemplate {template}\nBuild NOT_RUN")
            return 0
        check_tools(PROJECT_ROOT, jdk, sdk)
        return run_logged(command, source, environment, run)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        write_json(run / "error.json", {"error": str(error), "result": "BLOCKED"})
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
