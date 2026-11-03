"""Запускает текущий bridge и его тесты вне generated-каталогов приложения.

Проверяются Flet service, fake LocalAuthPlatform и MethodChannel в Flutter VM.
Это не проверка Android, Linux, системного prompt или настоящего хранилища.
Полный Flet app, secure-storage extension и Android toolchain здесь не нужны.
Зависимости harness закреплены независимо от generated pubspec приложения.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def _required_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Отсутствует обычный тестовый вход {path.name}")
    return path.read_bytes()


def _run(root: Path, sdk: Path, workspace: Path, pub_cache: Path) -> None:
    recipe = root / "packaging/android"
    harness = recipe / "recovery_test_harness"
    pinned_sdk = json.loads(_required_file(harness / "flutter-sdk.json"))
    actual_sdk = json.loads(_required_file(sdk / "bin/cache/flutter.version.json"))
    for key in ("flutterVersion", "frameworkRevision", "dartSdkVersion"):
        if actual_sdk.get(key) != pinned_sdk[key]:
            raise ValueError(f"Закреплённый Flutter SDK не совпал по {key}")
    metadata = tomllib.loads(_required_file(root / "pyproject.toml").decode())
    dependencies = metadata["project"]["dependencies"]
    if (
        "flet==0.86.5" not in dependencies
        or "flet-secure-storage==0.86.5" not in dependencies
    ):
        raise ValueError("Flet приложения отличается от закреплённого harness")
    overrides = metadata["tool"]["flet"]["flutter"]["pubspec"]["dependency_overrides"]
    if (
        overrides.get("jni_flutter") != "1.0.3"
        or overrides.get("shared_preferences_android") != "2.4.28"
    ):
        raise ValueError("JNI overrides приложения отличаются от harness")
    recovery_pins = {
        "local_auth": "3.0.2",
        "local_auth_android": "2.2.0",
        "flutter_secure_storage": "10.3.1",
    }
    template = ast.parse(_required_file(recipe / "recovery_template.py"))
    declared_pins = [
        ast.literal_eval(node.value)
        for node in template.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "PINNED_PACKAGES"
            for target in node.targets
        )
    ]
    if declared_pins != [recovery_pins]:
        raise ValueError("Прямые зависимости recovery recipe отличаются от harness")
    inputs = {
        "pubspec.yaml": harness / "pubspec.yaml",
        "pubspec.lock": harness / "pubspec.lock",
        "recovery_bridge.dart": recipe / "recovery_bridge.dart",
        "test/recovery_bridge_test.dart": recipe / "test/recovery_bridge_test.dart",
    }
    hashes = {}
    for relative, source in inputs.items():
        data = _required_file(source)
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    home = workspace / "home"
    home.mkdir()
    pub_cache.mkdir(parents=True, exist_ok=True)
    environment = dict(
        os.environ,
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
        PUB_CACHE=str(pub_cache),
        PUB_HOSTED_URL="https://pub.dev",
        FLUTTER_ROOT=str(sdk),
        FLUTTER_SUPPRESS_ANALYTICS="true",
        PUB_ENVIRONMENT="flutter_bot",
    )
    dart = sdk / "bin/cache/dart-sdk/bin/dart"
    tools = sdk / "bin/cache/flutter_tools.snapshot"
    for path in (
        dart,
        tools,
        sdk / "bin/cache/artifacts/engine/linux-x64/flutter_tester",
    ):
        if not path.is_file():
            raise ValueError(
                f"Существующий Flutter SDK не подготовлен для VM tests {path.name}"
            )
    # Прямой snapshot не запускает bootstrap и обновление SDK на машине владельца.
    flutter = [str(dart), str(tools), "--no-version-check", "--suppress-analytics"]
    subprocess.run(
        [*flutter, "pub", "get", "--enforce-lockfile"],
        cwd=workspace,
        env=environment,
        check=True,
    )
    graph = json.loads((workspace / ".dart_tool/package_graph.json").read_bytes())
    versions = {package["name"]: package["version"] for package in graph["packages"]}
    expected_versions = {
        "flet": "0.86.5",
        "local_auth": recovery_pins["local_auth"],
        "local_auth_android": recovery_pins["local_auth_android"],
        "local_auth_platform_interface": "1.1.0",
        "jni": "1.0.0",
        "jni_flutter": overrides["jni_flutter"],
        "screen_retriever": "0.2.2",
        "shared_preferences_android": overrides["shared_preferences_android"],
    }
    if any(
        versions.get(name) != version for name, version in expected_versions.items()
    ):
        raise ValueError(
            "Фактический Dart graph отличается от закреплённых зависимостей"
        )
    result = subprocess.run(
        [
            *flutter,
            "test",
            "--no-pub",
            "--reporter=json",
            "test/recovery_bridge_test.dart",
        ],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    cases = [
        event
        for event in events
        if event.get("type") == "testDone" and not event.get("hidden")
    ]
    if not cases or any(
        case.get("skipped") or case.get("result") != "success" for case in cases
    ):
        raise ValueError("Ожидались непустые успешные тесты без пропусков")
    if not any(
        event.get("type") == "done" and event.get("success") is True for event in events
    ):
        raise ValueError("Flutter не подтвердил успешное завершение тестов")
    if (workspace / "pubspec.lock").read_bytes() != inputs["pubspec.lock"].read_bytes():
        raise ValueError("Закреплённый pubspec.lock был изменён")
    report = {
        "status": "PASS",
        "test_cases": len(cases),
        "skips": 0,
        "sdk": pinned_sdk,
        "resolved_pins": expected_versions,
        "recovery_recipe_pins": recovery_pins,
        "inputs_sha256": hashes,
        "scope": "Flutter VM, fake LocalAuthPlatform и MethodChannel, без устройства и приложения",
    }
    (workspace / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"PASS {len(cases)} Flutter VM tests, skips 0")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flutter-sdk", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--pub-cache", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    sdk = args.flutter_sdk.resolve()
    if args.work_dir is None:
        with tempfile.TemporaryDirectory(
            prefix="tokenlogue-recovery-tests-"
        ) as directory:
            workspace = Path(directory)
            _run(
                root,
                sdk,
                workspace,
                (args.pub_cache or workspace / "pub-cache").resolve(),
            )
    else:
        workspace = args.work_dir.resolve()
        workspace.mkdir(parents=True, exist_ok=False)
        _run(
            root, sdk, workspace, (args.pub_cache or workspace / "pub-cache").resolve()
        )


if __name__ == "__main__":
    main()
