"""Точное исключение проверенных SelfTest только из staging текущей сборки."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import marshal
import os
import runpy
import stat
import struct
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from types import CodeType
from typing import Any, Iterator

POLICY_NAME = "packaging/android/crypto-selftest-policy.json"
MODULE_NAME = "packaging/android/package_stage.py"
HOOK_NAME = "packaging/android/package_stage.gradle.kts"
NOTICES_MODULE = "packaging/notices/notice_bundle.py"
NOTICES_ASSETS = "src/assets/third-party-notices"
NOTICES_APP_STAGE = "build/python-app/assets/third-party-notices"
STAGE = "compiled-site-packages-before-native-packaging"
NAMESPACE = "Cryptodome/SelfTest/"


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _code_value(value: object) -> object:
    """Канонические поля кода без зависимого от staging co_filename."""
    if isinstance(value, CodeType):
        names = (
            "co_argcount",
            "co_posonlyargcount",
            "co_kwonlyargcount",
            "co_nlocals",
            "co_stacksize",
            "co_flags",
            "co_code",
            "co_consts",
            "co_names",
            "co_varnames",
            "co_freevars",
            "co_cellvars",
            "co_name",
            "co_qualname",
            "co_firstlineno",
            "co_linetable",
            "co_exceptiontable",
        )
        return [
            "code-fields-v1",
            [[name, _code_value(getattr(value, name))] for name in names],
        ]
    if value is None or value is Ellipsis:
        return ["None" if value is None else "Ellipsis"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, complex):
        return ["complex", value.real.hex(), value.imag.hex()]
    if isinstance(value, tuple):
        return ["tuple", [_code_value(item) for item in value]]
    if isinstance(value, frozenset):
        items = [_code_value(item) for item in value]
        return ["frozenset", sorted(items, key=lambda item: _json_bytes(item))]
    raise ValueError("Неподдержанный тип константы bytecode")


def _code_fingerprint(code: CodeType) -> str:
    return _digest(_json_bytes(_code_value(code)))


def _filenames_match(code: CodeType, filename: str) -> bool:
    return code.co_filename == filename and all(
        _filenames_match(value, filename)
        for value in code.co_consts
        if isinstance(value, CodeType)
    )


def _check_components(path: Path) -> None:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Требуется абсолютный путь без выхода за scope")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Symlink-компонент запрещён в staging")


@contextmanager
def _parent_fd(path: Path) -> Iterator[tuple[int, str]]:
    """Открывает каждый каталог отдельно без следования symlink при гонке путей."""
    _check_components(path)
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        yield descriptor, path.name
    finally:
        os.close(descriptor)


def _read_regular(path: Path, *, maximum: int | None = None) -> bytes:
    with _parent_fd(path) as (parent, name):
        if not stat.S_ISREG(
            os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode
        ):
            raise ValueError("Ожидался обычный файл staging")
        with os.fdopen(
            os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent),
            "rb",
        ) as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or maximum is not None
                and info.st_size > maximum
            ):
                raise ValueError("Неподдержанный тип или размер файла staging")
            return stream.read()


def _hash_file(path: Path) -> str:
    with _parent_fd(path) as (parent, name):
        if not stat.S_ISREG(
            os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode
        ):
            raise ValueError("Ожидался обычный файл staging")
        with os.fdopen(
            os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent),
            "rb",
        ) as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Ожидался обычный файл staging")
            return hashlib.file_digest(stream, "sha256").hexdigest()


def _inventory(stage: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _check_components(stage)
    if not stage.is_dir():
        raise ValueError("Подтверждённый staging отсутствует")
    files: list[dict[str, Any]] = []
    directories: list[dict[str, Any]] = []

    def walk(descriptor: int, prefix: str) -> None:
        with os.scandir(descriptor) as listing:
            entries = sorted(listing, key=lambda entry: entry.name)
        for entry in entries:
            info = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
            relative = prefix + entry.name
            if stat.S_ISLNK(info.st_mode):
                raise ValueError("Symlink запрещён внутри staging")
            if stat.S_ISDIR(info.st_mode):
                directories.append(
                    {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
                )
                child = os.open(
                    entry.name,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
                try:
                    walk(child, relative + "/")
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode):
                with os.fdopen(
                    os.open(
                        entry.name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=descriptor,
                    ),
                    "rb",
                ) as stream:
                    opened = os.fstat(stream.fileno())
                    if not stat.S_ISREG(opened.st_mode) or (
                        info.st_dev,
                        info.st_ino,
                    ) != (opened.st_dev, opened.st_ino):
                        raise ValueError("Файл staging изменился во время чтения")
                    files.append(
                        {
                            "path": relative,
                            "size": opened.st_size,
                            "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                            "mode": stat.S_IMODE(opened.st_mode),
                        }
                    )
            else:
                raise ValueError("Специальный файл запрещён внутри staging")

    with _parent_fd(stage) as (parent, name):
        descriptor = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        try:
            walk(descriptor, "")
        finally:
            os.close(descriptor)
    return sorted(files, key=lambda row: row["path"]), sorted(
        directories, key=lambda row: row["path"]
    )


def _safe_policy_path(name: object) -> str:
    if not isinstance(name, str):
        raise ValueError("Некорректный относительный путь политики")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or path.as_posix() != name
        or not name.startswith(NAMESPACE)
        or not name.endswith(".pyc")
    ):
        raise ValueError("Политика выходит за точный scope SelfTest")
    return name


def _authenticate(
    run: Path, abi: str, policy_path: Path | None
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    _check_components(run)
    if abi not in {"arm64-v8a", "x86_64"}:
        raise ValueError("Неподдержанный ABI")
    module_root = Path(__file__).absolute().parents[2]
    if run.is_relative_to(module_root):
        raise ValueError("Staging должен находиться вне исходного репозитория")
    preparation_bytes = _read_regular(run / "preparation.json", maximum=2 * 1024 * 1024)
    preparation = json.loads(preparation_bytes)
    if not isinstance(preparation, dict):
        raise ValueError("Некорректный manifest входов recipe")
    source = run / "source"
    if (
        preparation.get("recipe_version") != "7"
        or preparation.get("arch") != abi
        or preparation.get("source") != str(source)
    ):
        raise ValueError("Не подтверждён staging текущего штатного recipe")
    expected_policy_path = source / POLICY_NAME
    if policy_path is not None and policy_path != expected_policy_path:
        raise ValueError("Политика должна принадлежать снимку текущей сборки")
    policy_bytes = _read_regular(expected_policy_path, maximum=2 * 1024 * 1024)
    policy = json.loads(policy_bytes)
    if not isinstance(policy, dict):
        raise ValueError("Некорректный объект политики")
    identity = {
        "schema": 1,
        "id": "pycryptodomex-selftest",
        "version": 1,
        "sha256": _digest(policy_bytes),
        "stage": STAGE,
    }
    if preparation.get("package_policy") != identity:
        raise ValueError("Политика не совпала с provenance текущей сборки")
    inputs = preparation.get("files", [])
    if not isinstance(inputs, list) or any(not isinstance(row, dict) for row in inputs):
        raise ValueError("Некорректный manifest входов recipe")
    by_name = {row["path"]: row for row in inputs}
    if len(by_name) != len(inputs):
        raise ValueError("Неоднозначный manifest входов recipe")

    def authenticate_input(name: str) -> None:
        path = source / name
        info = path.lstat()
        row = by_name.get(name, {})
        if (
            row.get("sha256") != _hash_file(path)
            or row.get("size") != info.st_size
            or row.get("mode") != stat.S_IMODE(info.st_mode)
        ):
            raise ValueError("Изменён собственный вход штатной подготовки")

    for name in (MODULE_NAME, POLICY_NAME, HOOK_NAME, NOTICES_MODULE):
        authenticate_input(name)
    if _hash_file(source / MODULE_NAME) != _hash_file(Path(__file__).absolute()):
        raise ValueError("Исполняется модуль вне подтверждённого снимка")
    notices = runpy.run_path(str(source / NOTICES_MODULE))
    for name in notices["required_inputs"](source, "android"):
        authenticate_input(name)
    notice_manifest = notices["verify_notices"](
        source, "android", source / NOTICES_ASSETS
    )
    for path in (source / NOTICES_ASSETS).rglob("*"):
        if path.is_file():
            authenticate_input(path.relative_to(source).as_posix())
    if preparation.get("packaged_notices") != notice_manifest:
        raise ValueError("Уведомления не совпали с provenance текущей сборки")
    # serious_python_android packageApp archives this processed app directory.
    # Checking only src/assets would miss losses during Flet's staging step.
    _check_components(source / "build/python-app")
    if (
        notices["verify_notices"](source, "android", source / NOTICES_APP_STAGE)
        != notice_manifest
    ):
        raise ValueError("Уведомления отсутствуют в конечном app staging")
    stage = source / "build/site-packages" / abi
    _check_components(stage)
    for sibling in stage.parent.iterdir():
        if sibling.name != abi and (sibling.is_dir() or sibling.is_symlink()):
            raise ValueError("Неожиданный дополнительный ABI staging")
    proof = {
        "policy": identity,
        "preparation_sha256": _digest(preparation_bytes),
        "stage_identity": _digest(str(stage).encode()),
    }
    return stage, policy, proof


def _validate_policy(
    policy: dict[str, Any], abi: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if (
        policy.get("schema") != 1
        or policy.get("id") != "pycryptodomex-selftest"
        or policy.get("version") != 1
        or policy.get("stage") != STAGE
    ):
        raise ValueError("Неподдержанная версия политики")
    bytecode = policy["bytecode"]
    if not isinstance(bytecode, dict):
        raise ValueError("Некорректный формат bytecode политики")
    if (
        bytecode.get("python") != [3, 12]
        or sys.version_info[:2] != (3, 12)
        or bytecode.get("magic") != "cb0d0d0a"
        or bytecode.get("flags") != 0
        or bytecode.get("optimize") != 0
        or bytecode.get("fingerprint") != "code-fields-v1"
        or bytecode.get("timestamp") != "staging-generated"
        or bytecode.get("filename") != "absolute-stage-source-path"
    ):
        raise ValueError("Неподдержанный формат или Python bytecode")
    distribution = policy["distribution"]
    if not isinstance(distribution, dict):
        raise ValueError("Некорректная запись пакета политики")
    if (
        distribution.get("name") != "pycryptodomex"
        or distribution.get("version") != "3.23.0"
        or distribution.get("metadata_path")
        != "pycryptodomex-3.23.0.dist-info/METADATA"
    ):
        raise ValueError("Неподдержанная версия пакета")
    sources = policy["sources"]
    if not isinstance(sources, dict) or not isinstance(sources.get(abi), dict):
        raise ValueError("Неподдержанный источник wheel")
    variant = sources[abi]
    if variant.get("wheel_metadata_path") != "pycryptodomex-3.23.0.dist-info/WHEEL":
        raise ValueError("Неподдержанный источник wheel")
    expected = {}
    items = policy["files"]
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Некорректный список файлов политики")
    for item in items:
        name = _safe_policy_path(item["path"])
        if (
            name in expected
            or item.get("type") != "regular"
            or item.get("source_path") != name[:-1]
            or not isinstance(item.get("source_size"), int)
            or item["source_size"] < 0
            or any(
                not isinstance(item.get(key), str)
                or len(item[key]) != 64
                or any(c not in "0123456789abcdef" for c in item[key])
                for key in ("source_sha256", "code_sha256")
            )
        ):
            raise ValueError("Некорректная точная запись политики SelfTest")
        expected[name] = item
    if not expected:
        raise ValueError("Пустая политика SelfTest запрещена")
    return expected, variant


def _validate_package(
    stage: Path, policy: dict[str, Any], variant: dict[str, Any]
) -> dict[str, Any]:
    distribution = policy["distribution"]
    metadata = _read_regular(stage / distribution["metadata_path"], maximum=1024 * 1024)
    wheel = _read_regular(stage / variant["wheel_metadata_path"], maximum=1024 * 1024)
    candidates = sorted(path.name for path in stage.glob("pycryptodomex-*.dist-info"))
    if (
        candidates != ["pycryptodomex-3.23.0.dist-info"]
        or _digest(metadata) != distribution["metadata_sha256"]
        or _digest(wheel) != variant["wheel_metadata_sha256"]
    ):
        raise ValueError("Версия или проверенные METADATA/WHEEL пакета не совпали")
    return {
        "name": distribution["name"],
        "version": distribution["version"],
        "reference_wheel": {
            key: variant[key] for key in ("wheel_filename", "wheel_sha256")
        },
        "observed_metadata_sha256": _digest(metadata),
        "observed_WHEEL_sha256": _digest(wheel),
    }


def _validate_pyc(path: Path, item: dict[str, Any], stage: Path) -> dict[str, Any]:
    data = _read_regular(path, maximum=2 * 1024 * 1024)
    if (
        len(data) < 16
        or data[:4] != bytes.fromhex("cb0d0d0a")
        or struct.unpack_from("<I", data, 4)[0] != 0
        or struct.unpack_from("<I", data, 12)[0] != item["source_size"]
    ):
        raise ValueError("Изменён заголовок или размер исходника bytecode SelfTest")
    payload = io.BytesIO(data[16:])
    code = marshal.load(payload)
    if (
        payload.tell() != len(data) - 16
        or not isinstance(code, CodeType)
        or not _filenames_match(code, str(stage / item["source_path"]))
        or _code_fingerprint(code) != item["code_sha256"]
    ):
        raise ValueError("Изменены байты, путь или код SelfTest")
    return {
        "path": item["path"],
        "size": len(data),
        "sha256": _digest(data),
        "source_sha256": item["source_sha256"],
        "code_sha256": item["code_sha256"],
    }


def _receipt_digest(receipt: dict[str, Any]) -> str:
    return _digest(
        _json_bytes(
            {key: value for key, value in receipt.items() if key != "proof_sha256"}
        )
    )


def _unlink_checked(
    stage: Path, name: str, item: dict[str, Any], record: dict[str, Any]
) -> None:
    path = stage / name
    if _validate_pyc(path, item, stage) != {
        key: value for key, value in record.items() if key != "mode"
    }:
        raise ValueError("SelfTest изменился перед удалением")
    with _parent_fd(path) as (parent, filename):
        info = os.stat(filename, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != record["mode"]
        ):
            raise ValueError("Тип или права SelfTest изменились перед удалением")
        os.unlink(filename, dir_fd=parent)


def prepare_stage(
    run: Path, abi: str, *, policy_path: Path | None = None
) -> dict[str, Any]:
    """Проверяет весь stage перед первым удалением и сохраняет доказательство успеха."""
    stage, policy, proof = _authenticate(run, abi, policy_path)
    expected, variant = _validate_policy(policy, abi)
    source = _validate_package(stage, policy, variant)
    before, directories = _inventory(stage)
    selftests = {row["path"] for row in before if row["path"].startswith(NAMESPACE)}
    receipt_dir = run / "package-preparation"
    receipt_path = receipt_dir / f"{abi}.json"
    seal_path = receipt_dir / f"{abi}.success.json"
    if (
        receipt_path.exists()
        or receipt_path.is_symlink()
        or seal_path.exists()
        or seal_path.is_symlink()
    ):
        if not receipt_path.exists() or not seal_path.exists():
            raise ValueError(
                "Предыдущая успешная подготовка этих входов не подтверждена"
            )
        receipt_bytes = _read_regular(receipt_path, maximum=8 * 1024 * 1024)
        receipt = json.loads(receipt_bytes)
        seal = json.loads(_read_regular(seal_path, maximum=8192))
        if not isinstance(receipt, dict) or not isinstance(seal, dict):
            raise ValueError("Некорректное подтверждение подготовки")
        excluded = receipt.get("excluded", [])
        if not isinstance(excluded, list) or any(
            not isinstance(row, dict) for row in excluded
        ):
            raise ValueError("Некорректное подтверждение исключённых файлов")
        recovered_before = sorted(
            before
            + [
                {key: row[key] for key in ("path", "size", "sha256", "mode")}
                for row in excluded
            ],
            key=lambda row: row["path"],
        )
        matching = (
            receipt.get("status") == "PREPARED"
            and receipt.get("abi") == abi
            and receipt.get("stage") == STAGE
            and receipt.get("source") == source
            and all(receipt.get(key) == value for key, value in proof.items())
            and not selftests
            and receipt.get("retained") == before
            and receipt.get("directories") == directories
            and len(excluded) == len(expected)
            and {row["path"] for row in excluded} == set(expected)
            and all(
                row.get("code_sha256") == expected[row["path"]]["code_sha256"]
                and row.get("source_sha256") == expected[row["path"]]["source_sha256"]
                for row in excluded
            )
            and receipt.get("proof_sha256") == _receipt_digest(receipt)
            and receipt.get("before_inventory_sha256")
            == _digest(_json_bytes(recovered_before))
            and receipt.get("after_inventory_sha256") == _digest(_json_bytes(before))
            and seal == {"schema": 1, "receipt_sha256": _digest(receipt_bytes), **proof}
        )
        if not matching:
            raise ValueError(
                "Предыдущая успешная подготовка этих входов не подтверждена"
            )
        return receipt
    if selftests != set(expected):
        raise ValueError(
            "Точный состав SelfTest не совпал. Добавленные или отсутствующие файлы запрещены"
        )
    before_by_name = {row["path"]: row for row in before}
    excluded = [
        {
            **_validate_pyc(stage / name, expected[name], stage),
            "mode": before_by_name[name]["mode"],
        }
        for name in sorted(expected)
    ]
    retained = [row for row in before if row["path"] not in expected]
    if _inventory(stage) != (before, directories):
        raise ValueError("Staging изменился во время проверки")
    # Каталог результата проверяется до удаления. Никакие данные stage сюда не копируются.
    if receipt_dir.exists() or receipt_dir.is_symlink():
        _check_components(receipt_dir)
        if not receipt_dir.is_dir():
            raise ValueError("Некорректный каталог результата подготовки")
    else:
        receipt_dir.mkdir()
    _check_components(receipt_dir)
    for record in excluded:
        _unlink_checked(stage, record["path"], expected[record["path"]], record)
    after, after_directories = _inventory(stage)
    if after != retained or after_directories != directories:
        raise ValueError("Изменён сохраняемый состав staging. Упаковка запрещена")
    receipt = {
        "status": "PREPARED",
        "abi": abi,
        "stage": STAGE,
        **proof,
        "source": source,
        "excluded": excluded,
        "retained": retained,
        "directories": directories,
        "before_inventory_sha256": _digest(_json_bytes(before)),
        "after_inventory_sha256": _digest(_json_bytes(after)),
    }
    receipt["proof_sha256"] = _receipt_digest(receipt)
    temporary = receipt_path.with_suffix(".pending")
    with temporary.open("xb") as stream:
        stream.write(_json_bytes(receipt))
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(receipt_path)
    # Отдельная запись является последним шагом подтверждения успешного применения.
    seal_temporary = seal_path.with_suffix(".pending")
    with seal_temporary.open("xb") as stream:
        stream.write(
            _json_bytes(
                {"schema": 1, "receipt_sha256": _digest(_json_bytes(receipt)), **proof}
            )
        )
        stream.flush()
        os.fsync(stream.fileno())
    seal_temporary.replace(seal_path)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), required=True)
    args = parser.parse_args(argv)
    try:
        receipt = prepare_stage(args.run_dir, args.abi)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        EOFError,
        RecursionError,
    ) as error:
        # Сообщение не содержит содержимое файлов или значения найденных маркеров.
        print(f"Подготовка SelfTest остановлена. {error}", file=sys.stderr)
        return 1
    print(
        f"Подготовка SelfTest подтверждена. Исключено файлов {len(receipt['excluded'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
