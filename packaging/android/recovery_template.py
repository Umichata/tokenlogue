"""Воспроизводимый bridge восстановления в проверенном шаблоне Flet 0.86.5."""

from pathlib import Path

PREFIX = "build/{{cookiecutter.out_dir}}/"
PINNED_PACKAGES = {
    "local_auth": "3.0.2",
    "local_auth_android": "2.2.0",
    "flutter_secure_storage": "10.3.1",
}


def add_device_recovery(
    files: dict[str, tuple[bytes, int]], source: Path, *, android_abi: str = "x86_64"
) -> None:
    """Изменяем только известные входы шаблона и собственный Dart service."""

    if android_abi not in {"x86_64", "arm64-v8a"}:
        raise ValueError("Unsupported Android ABI")

    def replace(name: str, old: str, new: str, *, count: int = 1) -> None:
        data, mode = files[PREFIX + name]
        if data.count(old.encode()) != count:
            raise ValueError(f"Unexpected recovery template input {name}")
        files[PREFIX + name] = (data.replace(old.encode(), new.encode()), mode)

    replace(
        "pubspec.yaml",
        "  flet: 0.86.5\n  serious_python:",
        "  flet: 0.86.5\n  local_auth: 3.0.2\n"
        "  local_auth_android: 2.2.0\n  flutter_secure_storage: 10.3.1\n  serious_python:",
    )
    replace(
        "lib/flet_generated.dart",
        "import 'package:flet/flet.dart';",
        "import 'package:flet/flet.dart';\nimport 'recovery_bridge.dart';",
    )
    replace(
        "lib/flet_generated.dart",
        "List<FletExtension> extensions = [",
        "List<FletExtension> extensions = [\n  TokenlogueRecoveryExtension(),",
    )
    replace(
        "android/app/src/main/kotlin/{{ cookiecutter.kotlin_dir }}/MainActivity.kt",
        "FlutterActivity",
        "FlutterFragmentActivity",
        count=2,
    )
    activity_source = source / "packaging/android/native_paths.kt"
    dart_source = source / "packaging/android/native_paths.dart"
    if any(
        path.is_symlink() or not path.is_file()
        for path in (activity_source, dart_source)
    ):
        raise ValueError("Missing owned native path bridge")
    activity = activity_source.read_text("utf-8")
    if activity.count("__TOKENLOGUE_ANDROID_ABI__") != 1:
        raise ValueError("Unexpected native ABI template")
    activity = activity.replace("__TOKENLOGUE_ANDROID_ABI__", android_abi)
    replace(
        "android/app/src/main/kotlin/{{ cookiecutter.kotlin_dir }}/MainActivity.kt",
        "import io.flutter.embedding.android.FlutterFragmentActivity\n\n"
        "class MainActivity : FlutterFragmentActivity()",
        activity.rstrip(),
    )
    files[PREFIX + "lib/native_paths.dart"] = (dart_source.read_bytes(), 0o644)
    replace(
        "lib/main.dart",
        "import 'flet_generated.dart';",
        "import 'flet_generated.dart';\nimport 'native_paths.dart';",
    )
    replace(
        "lib/main.dart",
        "    pageUrl = nrt.initBridges(environmentVariables);",
        "    await configureTokenlogueNativePaths(environmentVariables);\n"
        "    pageUrl = nrt.initBridges(environmentVariables);",
    )
    for directory, parent in (
        ("values", "@android:style/Theme.Light.NoTitleBar"),
        ("values-night", "@android:style/Theme.Black.NoTitleBar"),
    ):
        replace(
            f"android/app/src/main/res/{directory}/styles.xml",
            f'parent="{parent}"',
            'parent="Theme.AppCompat.DayNight.NoActionBar"',
            count=2,
        )
    replace(
        "android/app/src/main/AndroidManifest.xml",
        '    xmlns:tools="http://schemas.android.com/tools">',
        '    xmlns:tools="http://schemas.android.com/tools">\n'
        '    <uses-permission android:name="android.permission.USE_BIOMETRIC" />',
    )
    bridge = source / "packaging/android/recovery_bridge.dart"
    if bridge.is_symlink() or not bridge.is_file():
        raise ValueError("Missing owned recovery bridge")
    files[PREFIX + "lib/recovery_bridge.dart"] = (bridge.read_bytes(), 0o644)
