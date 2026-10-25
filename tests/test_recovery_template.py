"""Системный bridge собирается только из проверенных шаблонов и своих исходников."""

import importlib
import json
import sys
import tarfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "packaging/android"))

try:
    recipe = importlib.import_module("recovery_template")
finally:
    sys.path.pop(0)

PREFIX = recipe.PREFIX
add_device_recovery = recipe.add_device_recovery


class RecoveryTemplateTests(unittest.TestCase):
    def files(self):
        strings = {
            "lib/main.dart": "import 'flet_generated.dart';\n    pageUrl = nrt.initBridges(environmentVariables);",
            "pubspec.yaml": "dependencies:\n  flet: 0.86.5\n  serious_python: 4.5.1\n",
            "lib/flet_generated.dart": "import 'package:flet/flet.dart';\nList<FletExtension> extensions = [\n];",
            "android/app/src/main/kotlin/{{ cookiecutter.kotlin_dir }}/MainActivity.kt": "import io.flutter.embedding.android.FlutterActivity\n\nclass MainActivity : FlutterActivity()",
            "android/app/src/main/AndroidManifest.xml": '    xmlns:tools="http://schemas.android.com/tools">',
        }
        for folder, parent in (("values", "Light"), ("values-night", "Black")):
            strings[f"android/app/src/main/res/{folder}/styles.xml"] = (
                f'<style name="LaunchTheme" parent="@android:style/Theme.{parent}.NoTitleBar"/>'
                f'<style name="NormalTheme" parent="@android:style/Theme.{parent}.NoTitleBar"/>'
            )
        return {PREFIX + name: (text.encode(), 0o644) for name, text in strings.items()}

    def test_recipe_installs_actual_source_and_exact_pins(self):
        files = self.files()
        add_device_recovery(files, PROJECT)
        self.assertEqual(
            files[PREFIX + "lib/recovery_bridge.dart"][0],
            (PROJECT / "packaging/android/recovery_bridge.dart").read_bytes(),
        )
        self.assertIn(b"local_auth: 3.0.2", files[PREFIX + "pubspec.yaml"][0])
        self.assertIn(b"local_auth_android: 2.2.0", files[PREFIX + "pubspec.yaml"][0])
        self.assertIn(
            b"flutter_secure_storage: 10.3.1", files[PREFIX + "pubspec.yaml"][0]
        )
        self.assertIn(
            b"TokenlogueRecoveryExtension()",
            files[PREFIX + "lib/flet_generated.dart"][0],
        )
        self.assertEqual(
            files[
                PREFIX
                + "android/app/src/main/kotlin/{{ cookiecutter.kotlin_dir }}/MainActivity.kt"
            ][0].count(b"FlutterFragmentActivity"),
            2,
        )
        self.assertIn(
            b"USE_BIOMETRIC",
            files[PREFIX + "android/app/src/main/AndroidManifest.xml"][0],
        )

    def test_native_paths_use_selected_apk_abi_and_validate_own_zip(self):
        for abi in ("x86_64", "arm64-v8a"):
            with self.subTest(abi=abi):
                files = self.files()
                add_device_recovery(files, PROJECT, android_abi=abi)
                activity = files[
                    PREFIX
                    + "android/app/src/main/kotlin/{{ cookiecutter.kotlin_dir }}/MainActivity.kt"
                ][0].decode()
                self.assertIn(f'val abi = "{abi}"', activity)
                self.assertIn("applicationInfo.sourceDir", activity)
                self.assertIn("archive.getEntry(marker)", activity)
                self.assertNotIn("SUPPORTED_ABIS", activity)
                main = files[PREFIX + "lib/main.dart"][0].decode()
                self.assertLess(
                    main.index("await configureTokenlogueNativePaths"),
                    main.index("nrt.initBridges"),
                )
                self.assertEqual(
                    files[PREFIX + "lib/native_paths.dart"][0],
                    (PROJECT / "packaging/android/native_paths.dart").read_bytes(),
                )

    def test_unknown_native_abi_rejected_before_template_changes(self):
        files = self.files()
        original = dict(files)
        with self.assertRaisesRegex(ValueError, "Unsupported Android ABI"):
            add_device_recovery(files, PROJECT, android_abi="../../external")
        self.assertEqual(files, original)

    def test_unknown_template_is_rejected(self):
        files = self.files()
        name = PREFIX + "lib/flet_generated.dart"
        files[name] = (
            files[name][0].replace(b"List<FletExtension>", b"Changed"),
            0o644,
        )
        with self.assertRaisesRegex(ValueError, "Unexpected recovery template input"):
            add_device_recovery(files, PROJECT)

    def test_recipe_cannot_be_applied_twice(self):
        files = self.files()
        add_device_recovery(files, PROJECT)
        with self.assertRaisesRegex(ValueError, "Unexpected recovery template input"):
            add_device_recovery(files, PROJECT)

    def test_secure_storage_barrier_matches_pinned_backend_namespace(self):
        materials = PROJECT / "packaging/android/crypto"
        lock = json.loads((materials / "sources.lock.json").read_text())
        package = next(
            row
            for row in lock["dart_packages"]
            if row["name"] == "flutter_secure_storage"
        )
        self.assertEqual(
            package["version"], recipe.PINNED_PACKAGES["flutter_secure_storage"]
        )
        archive = (
            materials
            / "sources"
            / f"flutter_secure_storage-{package['version']}.tar.gz"
        )
        with tarfile.open(archive, "r:gz") as source:
            config_file = source.extractfile(
                "android/src/main/java/com/it_nomads/fluttersecurestorage/FlutterSecureStorageConfig.java"
            )
            names_file = source.extractfile(
                "android/src/main/java/com/it_nomads/fluttersecurestorage/NamespacedConfigSource.java"
            )
            self.assertIsNotNone(config_file)
            self.assertIsNotNone(names_file)
            assert config_file is not None and names_file is not None
            config = config_file.read().decode()
            names = names_file.read().decode()
        self.assertIn(
            "storageNamespace != null ? storageNamespace : sharedPreferencesName",
            config,
        )
        self.assertIn(': "FlutterSecureKeyStorage"', config)
        self.assertIn(
            '"FlutterSecureStorageConfiguration:" + sharedPreferencesName', names
        )
        import flet_secure_storage as fss

        from storage.secure_credentials import FletSecureCredentials

        backend = FletSecureCredentials().storage_backend
        assert isinstance(backend, fss.SecureStorage)
        self.assertEqual(
            backend.android_options.shared_preferences_name,
            "io.github.umichata.tokenlogue.secure_credentials",
        )
        activity = (PROJECT / "packaging/android/native_paths.kt").read_text()
        for name in (
            "FlutterSecureKeyStorage",
            "FlutterSecureStorageConfiguration:io.github.umichata.tokenlogue.secure_credentials",
            "io.github.umichata.tokenlogue.secure_credentials",
        ):
            self.assertIn('"' + name + '"', activity)
        self.assertIn("storageSyncIo.execute", activity)
        self.assertIn(".commit()", activity)
        self.assertNotIn(".apply()", activity)
        self.assertIn("success = written && success", activity)
        self.assertNotIn(".getAll(", activity)
        self.assertNotIn(".getString(", activity)
