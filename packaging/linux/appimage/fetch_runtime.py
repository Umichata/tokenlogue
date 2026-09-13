#!/usr/bin/env python3
"""Получение выбранного runtime и проверка комплекта без исполнения его файлов."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.error
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from source_artifact import GitHub, VerificationError

DIRECTORY = Path(__file__).resolve().parent
LOCK = DIRECTORY / "runtime-artifact.lock.json"
REPOSITORY_ROOT = DIRECTORY.parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "build/appimage/runtime-selected"
STAGES = ("fetch", "prepare", "build-one", "build-two", "compare", "verify", "smoke")
MAX_FILES = 4096
MAX_EXPANDED = 2 * 1024**3
MAX_FILE = 512 * 1024**2
MAX_JSON = 16 * 1024**2
WORKFLOW_MEMBER = "materials/recipe/.github/workflows/build-appimage-runtime.yml"

# Используем существующую проверку ELF, не меняя standalone-рецепт и его импорты.
sys.path.insert(0, str(DIRECTORY / "runtime"))
try:
    runtime_checks = importlib.import_module("runtime_checks")
finally:
    sys.path.pop(0)


class RuntimeArtifactError(VerificationError):
    def __init__(self, category: str, reason: str):
        super().__init__(reason)
        self.category = category


class RuntimeGitHub(GitHub):
    """Ограничивает загрузку точным размером ZIP, сохраняя безопасные redirects."""

    def __init__(self, token: str, archive_size: int):
        super().__init__(token)
        self.archive_size = archive_size

    def download(self, artifact_id: int, destination: Path) -> None:
        with self.response(f"/actions/artifacts/{artifact_id}/zip") as response:
            with destination.open("xb") as output:
                total = 0
                for block in iter(lambda: response.read(1024**2), b""):
                    total += len(block)
                    require(
                        total <= self.archive_size,
                        "ZIP превысил закреплённый размер",
                        "archive_integrity",
                    )
                    output.write(block)


def require(condition: bool, reason: str, category: str = "identity") -> None:
    if not condition:
        raise RuntimeArtifactError(category, reason)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            value.update(block)
    return value.hexdigest()


def load_lock(path: Path = LOCK) -> dict[str, Any]:
    lock = json.loads(path.read_text())
    require(lock["schema"] == 1, "Неизвестный формат runtime artifact lock")
    require(lock["repository"] == "Umichata/tokenlogue", "Другой репозиторий runtime")
    require(
        lock["workflow"] == ".github/workflows/build-appimage-runtime.yml",
        "Другой workflow runtime",
    )
    for field in ("producer_commit", "upstream_commit"):
        require(
            bool(re.fullmatch(r"[a-f0-9]{40}", lock[field])),
            "Нужен полный source commit",
        )
    for field in (
        "archive_sha256",
        "runtime_sha256",
        "manifest_sha256",
        "runtime_lock_sha256",
        "recipe_fingerprint",
    ):
        require(
            bool(re.fullmatch(r"[a-f0-9]{64}", lock[field])),
            "Некорректная закреплённая сумма",
        )
    for field in (
        "source_run_id",
        "run_attempt",
        "artifact_id",
        "archive_size",
        "runtime_size",
    ):
        require(
            type(lock[field]) is int and lock[field] > 0, "Некорректный ID или размер"
        )
    require(lock["runtime_path"] == "runtime-x86_64", "Неверное имя runtime")
    require(lock["archive_size"] <= MAX_FILE, "ZIP превышает допустимый размер")
    return lock


def checked_file(root: Path, name: str) -> Path:
    safe_name(name)
    path = root / name
    require(
        path.is_file() and not path.is_symlink(),
        f"Отсутствует обычный файл {name}",
        "missing_file",
    )
    require(
        path.resolve().is_relative_to(root.resolve()),
        "Путь выходит за каталог комплекта",
        "archive_path",
    )
    for parent in path.parents:
        if parent == root:
            break
        require(not parent.is_symlink(), "Ссылка в пути комплекта", "archive_path")
    return path


def safe_name(name: str) -> None:
    require(
        bool(name)
        and not name.startswith("/")
        and all(p not in ("", ".", "..") for p in name.split("/"))
        and not any(c in name for c in "\\:\x00")
        and all(ord(c) >= 32 for c in name),
        "Небезопасный путь в комплекте runtime",
        "archive_path",
    )


def verify_archive_identity(archive: Path, lock: dict) -> None:
    require(
        archive.is_file() and not archive.is_symlink(),
        "Не найден закреплённый локальный ZIP",
        "missing_file",
    )
    require(
        archive.stat().st_size == lock["archive_size"],
        "Размер ZIP не совпал с lock",
        "archive_integrity",
    )
    require(
        digest(archive) == lock["archive_sha256"],
        "SHA-256 ZIP не совпал с lock",
        "archive_integrity",
    )


def select_artifact(
    run: dict,
    workflow: dict,
    artifact: dict,
    lock: dict,
    *,
    now: datetime | None = None,
) -> None:
    require(run.get("id") == lock["source_run_id"], "Не совпал source run ID")
    require(run.get("run_attempt") == lock["run_attempt"], "Не совпал run attempt")
    require(
        run.get("repository", {}).get("full_name") == lock["repository"],
        "Другой source repository",
    )
    require(
        run.get("status") == "completed" and run.get("conclusion") == "success",
        "Source run не завершился успешно",
    )
    require(
        run.get("head_sha") == lock["producer_commit"], "Не совпал commit производителя"
    )
    require(
        run.get("path") == lock["workflow"]
        and workflow.get("path") == lock["workflow"],
        "Другой workflow производителя",
    )
    require(
        run.get("workflow_id") == workflow.get("id") and workflow.get("id") is not None,
        "Не совпал workflow ID",
    )
    for key, locked in (
        ("id", "artifact_id"),
        ("name", "artifact_name"),
        ("size_in_bytes", "archive_size"),
    ):
        require(artifact.get(key) == lock[locked], f"Не совпало поле artifact {key}")
    association = artifact.get("workflow_run", {})
    require(
        association.get("id") == lock["source_run_id"]
        and association.get("head_sha") == lock["producer_commit"],
        "Artifact принадлежит другому запуску или commit",
    )
    require(
        artifact.get("digest") == "sha256:" + lock["archive_sha256"],
        "Не совпал API digest артефакта",
    )
    require(artifact.get("expired") is False, "Истёк срок хранения артефакта")
    try:
        expiry = datetime.fromisoformat(artifact["expires_at"].replace("Z", "+00:00"))
        require(
            expiry.tzinfo is not None and expiry > (now or datetime.now(timezone.utc)),
            "Истёк срок хранения артефакта",
        )
    except (KeyError, TypeError, ValueError):
        raise RuntimeArtifactError(
            "identity", "Некорректный срок хранения артефакта"
        ) from None


def read_json(root: Path, name: str) -> dict:
    path = checked_file(root, name)
    require(
        path.stat().st_size <= MAX_JSON, "Слишком большой JSON", "archive_integrity"
    )
    result = json.loads(path.read_text())
    require(isinstance(result, dict), "Ожидался объект JSON", "archive_integrity")
    return result


def checksum_records(text: str) -> dict[str, str]:
    records = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([a-f0-9]{64}) [ *](.+)", line)
        require(
            match is not None, "Некорректная запись SHA256SUMS", "archive_integrity"
        )
        assert match is not None
        safe_name(match[2])
        require(match[2] not in records, "Дубликат в SHA256SUMS", "archive_integrity")
        records[match[2]] = match[1]
    require(bool(records), "Пустой SHA256SUMS", "missing_file")
    return records


def verify_runtime(runtime: Path, lock: dict) -> dict:
    require(
        runtime.is_file() and not runtime.is_symlink(),
        "Не найден выбранный runtime",
        "missing_file",
    )
    require(
        runtime.stat().st_size == lock["runtime_size"]
        and digest(runtime) == lock["runtime_sha256"],
        "Размер или SHA-256 runtime не совпал",
        "runtime_integrity",
    )
    try:
        return runtime_checks.elf_report(runtime)
    except (RuntimeError, ValueError, struct.error) as error:
        raise RuntimeArtifactError(
            "elf", "Неверный ELF runtime. " + str(error)
        ) from None


def verify_manifest_identity(
    root: Path, manifest: dict, lock: dict, files: dict[str, dict]
) -> dict:
    require(
        manifest.get("schema") == 1 and manifest.get("result") == "PASS",
        "Неверный manifest runtime",
    )
    require(
        manifest.get("runtime")
        == {
            "path": lock["runtime_path"],
            "size": lock["runtime_size"],
            "sha256": lock["runtime_sha256"],
        },
        "Идентичность runtime в manifest не совпала",
    )
    require(
        manifest.get("upstream_source_commit") == lock["upstream_commit"],
        "Не совпал upstream commit",
    )
    recipe = manifest["tokenlogue_recipe"]
    require(
        recipe.get("commit") == lock["producer_commit"]
        and recipe.get("sha256") == lock["recipe_fingerprint"]
        and recipe.get("dirty") is False,
        "Не совпал commit/fingerprint или чистота рецепта",
    )
    require(
        hashlib.sha256(json.dumps(recipe["files"], sort_keys=True).encode()).hexdigest()
        == lock["recipe_fingerprint"],
        "Не совпал вычисленный fingerprint рецепта",
    )
    require(
        isinstance(manifest.get("source_materials"), str)
        and manifest["source_materials"].startswith("REVIEW_REQUIRED"),
        "Утрачен общий статус REVIEW_REQUIRED",
    )
    for stage in STAGES:
        report = manifest.get("checks", {}).get(stage, {})
        require(
            report.get("result") == "PASS"
            and report.get("recipe_sha256") == lock["recipe_fingerprint"],
            f"Обязательный этап не PASS для рецепта. {stage}",
        )
        require(
            read_json(root, f"reports/reports/{stage}.json") == report,
            f"Отчёт этапа отличается от manifest. {stage}",
        )
    checks = manifest["checks"]
    require(
        checks["prepare"].get("apk_signatures") == "PASS"
        and checks["prepare"].get("inventory") == "PASS",
        "Нет подтверждённых APK signatures/inventory",
    )
    for name in ("build-one", "build-two"):
        require(
            checks[name].get("sha256") == lock["runtime_sha256"]
            and checks[name].get("size") == lock["runtime_size"],
            "Неверный результат независимой сборки",
        )
    compare = checks["compare"]
    require(
        compare.get("byte_identical") is True
        and compare.get("builds")
        == [{"size": lock["runtime_size"], "sha256": lock["runtime_sha256"]}] * 2,
        "Не подтверждены две одинаковые сборки",
    )
    smoke = checks["smoke"]
    require(
        smoke.get("runtime_sha256") == lock["runtime_sha256"]
        and all(
            smoke.get(k) == "PASS"
            for k in (
                "new_runtime_prefix",
                "extract",
                "extract_and_run",
                "argument_marker",
            )
        ),
        "Не подтверждён обязательный тест runtime",
    )
    require(
        WORKFLOW_MEMBER in files, "Нет workflow в материалах рецепта", "missing_file"
    )
    recipe_entries = {"materials/recipe/" + f["path"]: f for f in recipe["files"]}
    require(
        WORKFLOW_MEMBER in recipe_entries,
        "Нет workflow в fingerprint рецепта",
        "missing_file",
    )
    for name, entry in recipe_entries.items():
        require(
            name in files
            and all(files[name][k] == entry[k] for k in ("sha256", "size")),
            "Не совпал файл рецепта",
        )
    build_lock = read_json(root, "runtime.lock.json")
    require(
        build_lock.get("upstream", {}).get("commit") == lock["upstream_commit"],
        "Другой исходный runtime lock",
    )
    components = {c["name"]: c for c in build_lock["components"]}
    require(
        set(components) == set(lock["components"]),
        "Неполный набор исходных компонентов",
    )
    source_files = {f["path"]: f for f in build_lock["files"]}
    for name, record in source_files.items():
        member = "materials/inputs/" + name
        require(
            member in files
            and all(files[member][k] == record[k] for k in ("size", "sha256")),
            "Отсутствует или отличается закреплённый исходный вход",
            "missing_file",
        )
    licenses = set()
    for name, component in components.items():
        expected = lock["components"][name]
        version = component.get(
            "package_version", component.get("version", component.get("commit"))
        )
        require(version == expected["version"], f"Другая версия компонента {name}")
        names = {PurePosixPath(p).name for p in component["licenses"]}
        require(
            names == set(expected["licenses"]), f"Неполные лицензии компонента {name}"
        )
        licenses.update(f"materials/licenses/{name}/{filename}" for filename in names)
    require(
        licenses == {n for n in files if n.startswith("materials/licenses/")},
        "Неполный или лишний набор лицензий",
        "missing_file",
    )
    coverage = manifest["runtime_source_materials"]
    require(
        coverage.get("result") == "PASS" and not coverage.get("unresolved"),
        "Неподтверждённые входы линковки",
    )
    require(
        {f.get("component") for f in coverage["files"]} == set(components),
        "Неполная привязка линкованных компонентов",
    )
    require(
        read_json(root, "reports/build-one/linked-inputs.json") == coverage,
        "Отчёт линковки отличается от manifest",
    )
    for entry in coverage["files"]:
        saved = PurePosixPath(entry["saved_as"])
        require(
            len(saved.parts) == 2 and saved.parts[0] == "linked-inputs",
            "Неверный путь сохранённого входа линковки",
        )
        name = "materials/linked-inputs/build-one/" + saved.name
        require(
            name in files
            and all(files[name][k] == entry[k] for k in ("size", "sha256")),
            "Не совпал сохранённый вход линковки",
        )
        if "package" in entry:
            package = entry["package"]
            component = components[entry["component"]]
            require(
                package["origin"] == component["name"]
                and package["version"] == component["package_version"]
                and package["aports_commit"] == component["aports_commit"],
                "Не совпала связь APK с aports",
            )
    return build_lock


def verify_bundle(root: Path, lock: dict) -> dict:
    require(
        root.is_dir() and not root.is_symlink(),
        "Не найден подготовленный комплект",
        "missing_file",
    )

    def scan_error(_error: OSError) -> None:
        raise RuntimeArtifactError(
            "archive_integrity", "Не удалось прочитать каталог комплекта"
        )

    paths = {}
    for directory, folders, names in os.walk(
        root, followlinks=False, onerror=scan_error
    ):
        for name in folders + names:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            safe_name(relative)
            require(
                not path.is_symlink(),
                "Ссылка в подготовленном комплекте",
                "archive_path",
            )
            if name in names:
                require(
                    stat.S_ISREG(path.stat().st_mode),
                    "Необычный тип файла комплекта",
                    "archive_path",
                )
                paths[relative] = path
    require(
        len(paths) <= MAX_FILES, "Слишком много файлов комплекта", "archive_integrity"
    )
    for name, field in (
        ("manifest.json", "manifest_sha256"),
        ("runtime.lock.json", "runtime_lock_sha256"),
    ):
        require(
            digest(checked_file(root, name)) == lock[field],
            f"SHA-256 {name} не совпал",
            "archive_integrity",
        )
    manifest = read_json(root, "manifest.json")
    files = {}
    for record in manifest["files"]:
        name = record["path"]
        safe_name(name)
        require(
            name not in files and name not in {"manifest.json", "SHA256SUMS"},
            "Неверная или повторная запись manifest",
            "archive_integrity",
        )
        require(
            type(record["size"]) is int and 0 <= record["size"] <= MAX_FILE,
            "Некорректный размер файла manifest",
            "archive_integrity",
        )
        require(
            bool(re.fullmatch(r"[a-f0-9]{64}", record["sha256"])),
            "Некорректный хеш manifest",
            "archive_integrity",
        )
        files[name] = record
    require(
        set(paths) == set(files) | {"manifest.json", "SHA256SUMS"},
        "Отсутствующий или неожиданный файл комплекта",
        "missing_file",
    )
    sums_path = checked_file(root, "SHA256SUMS")
    require(
        sums_path.stat().st_size <= MAX_JSON,
        "Слишком большой SHA256SUMS",
        "archive_integrity",
    )
    sums = checksum_records(sums_path.read_text())
    require(
        set(sums) == set(paths) - {"SHA256SUMS"},
        "Неполный или лишний перечень SHA256SUMS",
        "missing_file",
    )
    for name, path in paths.items():
        if name == "SHA256SUMS":
            continue
        if name in files:
            require(
                path.stat().st_size == files[name]["size"],
                f"Размер файла отличается от manifest. {name}",
                "archive_integrity",
            )
        actual = digest(path)
        require(
            actual == sums[name], f"Нарушен SHA256SUMS. {name}", "archive_integrity"
        )
        if name in files:
            require(
                path.stat().st_size == files[name]["size"]
                and actual == files[name]["sha256"],
                f"Нарушен manifest. {name}",
                "archive_integrity",
            )
    verify_manifest_identity(root, manifest, lock, files)
    elf = verify_runtime(checked_file(root, lock["runtime_path"]), lock)
    return {
        "result": "PASS",
        "files": len(paths),
        "manifest": "PASS",
        "sha256sums": "PASS",
        "elf": "PASS",
        "runtime_sha256": elf["sha256"],
    }


def unpack_verified(archive_path: Path, destination: Path, lock: dict) -> dict:
    verify_archive_identity(archive_path, lock)
    require(
        not destination.exists() and not destination.is_symlink(),
        "Каталог публикации уже существует",
    )
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        require(
            len(members) <= MAX_FILES, "Слишком много записей ZIP", "archive_integrity"
        )
        seen = set()
        total = 0
        for member in members:
            name = member.filename.rstrip("/")
            safe_name(name)
            require(name not in seen, "Дубликат пути ZIP", "archive_path")
            seen.add(name)
            mode = stat.S_IFMT(member.external_attr >> 16)
            require(
                mode in (0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG),
                "Ссылка или неподдерживаемый тип ZIP",
                "archive_path",
            )
            require(
                not member.flag_bits & 1,
                "Зашифрованный ZIP не поддерживается",
                "archive_integrity",
            )
            require(
                member.orig_filename == member.filename
                and (not member.is_dir() or member.file_size == 0),
                "Неверное имя или содержимое каталога ZIP",
                "archive_path",
            )
            total += member.file_size
            require(
                0 <= member.file_size <= MAX_FILE and total <= MAX_EXPANDED,
                "Превышен лимит распаковки ZIP",
                "archive_integrity",
            )
        directory_names = {m.filename.rstrip("/") for m in members if m.is_dir()}
        file_names = seen - directory_names
        for name in seen:
            require(
                not any(str(p) in file_names for p in PurePosixPath(name).parents),
                "Конфликт файла и каталога ZIP",
                "archive_path",
            )
        destination.mkdir(parents=True)
        for member in members:
            target = destination / member.filename
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Полное чтение каждого члена одновременно проверяет CRC средствами zipfile.
            with archive.open(member) as stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output, 1024**2)
            target.chmod(0o644)
    result = verify_bundle(destination, lock)
    result["crc"] = "PASS"
    return result


def obtain(
    lock: dict,
    output: Path,
    *,
    archive: Path | None = None,
    client: GitHub | None = None,
) -> dict:
    mode = "archive" if archive is not None else "github-api"
    if archive is not None:
        verify_archive_identity(archive, lock)
    else:
        require(client is not None, "Нет клиента GitHub API")
        assert client is not None
        run = client.json(
            f"/actions/runs/{lock['source_run_id']}/attempts/{lock['run_attempt']}"
        )
        workflow = client.json("/actions/workflows/build-appimage-runtime.yml")
        artifact = client.json(f"/actions/artifacts/{lock['artifact_id']}")
        select_artifact(run, workflow, artifact, lock)
    if output.exists() or output.is_symlink():
        result = verify_bundle(output, lock)
        result["cache"] = "REVERIFIED"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="runtime-input-", dir=output.parent
        ) as temporary:
            work = Path(temporary)
            if archive is None:
                assert client is not None
                archive = work / "artifact.zip"
                client.download(lock["artifact_id"], archive)
            result = unpack_verified(archive, work / "verified", lock)
            (work / "verified" / lock["runtime_path"]).chmod(0o755)
            (work / "verified").rename(output)
        result["cache"] = "PUBLISHED"
    return {
        **result,
        "mode": mode,
        "api_metadata": "PASS" if mode == "github-api" else "NOT_CHECKED",
        "archive_sha256": lock["archive_sha256"],
        "manifest_sha256": lock["manifest_sha256"],
        "producer_commit": lock["producer_commit"],
        "source_run_id": lock["source_run_id"],
        "run_attempt": lock["run_attempt"],
        "artifact_id": lock["artifact_id"],
    }


def compact_provenance(root: Path, lock: dict) -> dict:
    verify_bundle(root, lock)
    manifest = read_json(root, "manifest.json")
    build_lock = read_json(root, "runtime.lock.json")
    records = {r["path"]: r for r in manifest["files"]}
    inputs = {r["path"]: r for r in build_lock["files"]}
    components = []
    for component in build_lock["components"]:
        name = component["name"]
        source = inputs[component["source"]]
        components.append(
            {
                "name": name,
                "version": lock["components"][name]["version"],
                "source": {k: source[k] for k in ("url", "sha256", "size")},
                "aports_commit": component.get("aports_commit"),
                "licenses": [
                    {
                        "path": f"materials/licenses/{name}/{filename}",
                        "sha256": records[f"materials/licenses/{name}/{filename}"][
                            "sha256"
                        ],
                    }
                    for filename in lock["components"][name]["licenses"]
                ],
                "linked_inputs": [
                    {
                        "name": PurePosixPath(f["saved_as"]).name,
                        "sha256": f["sha256"],
                        "size": f["size"],
                    }
                    for f in manifest["runtime_source_materials"]["files"]
                    if f["component"] == name
                ],
            }
        )
    return {
        "schema": 1,
        "repository": lock["repository"],
        "workflow": lock["workflow"],
        "source_run_id": lock["source_run_id"],
        "run_attempt": lock["run_attempt"],
        "artifact_id": lock["artifact_id"],
        "artifact_name": lock["artifact_name"],
        "archive_sha256": lock["archive_sha256"],
        "manifest_sha256": lock["manifest_sha256"],
        "runtime_lock_sha256": lock["runtime_lock_sha256"],
        "producer_commit": lock["producer_commit"],
        "recipe_fingerprint": lock["recipe_fingerprint"],
        "upstream_commit": lock["upstream_commit"],
        "runtime": {"sha256": lock["runtime_sha256"], "size": lock["runtime_size"]},
        "components": components,
        "runtime_source_materials": "PASS",
        "fuse": "NOT_RUN",
    }


def check_prefix(runtime: Path, appimage: Path, lock: dict) -> dict:
    verify_runtime(runtime, lock)
    require(
        appimage.is_file()
        and not appimage.is_symlink()
        and appimage.stat().st_size > lock["runtime_size"],
        "AppImage усечён или отсутствует",
        "prefix",
    )
    try:
        runtime_checks.check_appimage_prefix(runtime, appimage)
    except (RuntimeError, ValueError, struct.error) as error:
        raise RuntimeArtifactError("prefix", str(error)) from None
    return {
        "result": "PASS",
        "runtime_sha256": lock["runtime_sha256"],
        "runtime_size": lock["runtime_size"],
        "allowed_change": ".digest_md5 (16 bytes)",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("fetch", "verify", "prefix"), nargs="?", default="fetch"
    )
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--appimage", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        lock = load_lock()
        if args.action == "prefix":
            require(
                args.runtime is not None and args.appimage is not None,
                "Нужны --runtime и --appimage",
            )
            assert args.runtime is not None and args.appimage is not None
            result = check_prefix(args.runtime, args.appimage, lock)
        elif args.action == "verify":
            result = verify_bundle(args.output, lock)
        else:
            client = (
                None
                if args.archive is not None
                else RuntimeGitHub(os.environ.get("GH_TOKEN", ""), lock["archive_size"])
            )
            result = obtain(lock, args.output, archive=args.archive, client=client)
        result["application_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT, text=True
        ).strip()
    except RuntimeArtifactError as error:
        result = {"result": "FAIL", "category": error.category, "reason": str(error)}
    except urllib.error.HTTPError as error:
        result = {
            "result": "FAIL",
            "category": "http",
            "reason": f"GitHub API вернул HTTP {error.code}",
        }
    except urllib.error.URLError:
        result = {
            "result": "FAIL",
            "category": "http",
            "reason": "Не удалось связаться с GitHub API",
        }
    except (zipfile.BadZipFile, UnicodeError, EOFError, json.JSONDecodeError):
        result = {
            "result": "FAIL",
            "category": "archive_integrity",
            "reason": "Повреждены ZIP, CRC или метаданные комплекта",
        }
    except (OSError, VerificationError, KeyError, TypeError, ValueError):
        result = {
            "result": "FAIL",
            "category": "input",
            "reason": "Неполные или некорректные входы runtime",
        }
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n"
            )
        except OSError:
            print("Не удалось записать отчёт runtime", file=sys.stderr)
            if result["result"] == "PASS":
                result = {
                    "result": "FAIL",
                    "reason": "Не удалось сохранить обязательный отчёт",
                }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
