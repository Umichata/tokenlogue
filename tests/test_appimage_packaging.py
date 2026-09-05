"""Tests for reproducible diagnostic AppImage packaging infrastructure."""

from __future__ import annotations

import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPIMAGE_DIR = PROJECT_ROOT / "packaging" / "linux" / "appimage"
SOURCE_DESKTOP = (
    PROJECT_ROOT / "packaging" / "linux" / "io.github.umichata.tokenlogue.desktop"
)
STAGED_DESKTOP_RELATIVE = Path(
    "usr/share/applications/io.github.umichata.tokenlogue.desktop"
)
EXPECTED_LOCK_VALUES = {
    "LINUXDEPLOY_TAG": "1-alpha-20251107-1",
    "LINUXDEPLOY_ASSET": "linuxdeploy-x86_64.AppImage",
    "LINUXDEPLOY_SHA256": "c20cd71e3a4e3b80c3483cef793cda3f4e990aca14014d23c544ca3ce1270b4d",
    "LINUXDEPLOY_LICENSE": "MIT",
    "APPIMAGETOOL_TAG": "1.9.1",
    "APPIMAGETOOL_ASSET": "appimagetool-x86_64.AppImage",
    "APPIMAGETOOL_SHA256": "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
    "APPIMAGETOOL_LICENSE": "MIT",
    "APPIMAGETOOL_RUNTIME_SIZE": "944632",
    "APPIMAGETOOL_RUNTIME_SHA256": "d30a3ba1388ef57be73faabf606e0d326682f48c87f666106a3c8d6b35b58b4f",
    "APPIMAGETOOL_RUNTIME_PROVENANCE": "embedded-prefix-of-tagged-appimagetool-asset",
    "PATCHELF_TAG": "0.19.1",
    "PATCHELF_ASSET": "patchelf-0.19.1-x86_64.tar.gz",
    "PATCHELF_SHA256": "a6818fef80128fb354423234ecacdcca3e993913d774e5d8346bc63f70fed4cf",
    "PATCHELF_BINARY_SHA256": "6526398feccd54ab150e49ef643376c6ae37445fdc28b3320baf4aea59f9d536",
    "PATCHELF_LICENSE": "GPL-3.0",
}
SCRIPT_NAMES = ("AppRun", "build_appimage.sh", "fetch_tools.sh")


class AppImagePackagingTests(unittest.TestCase):
    def test_expected_infrastructure_files_exist(self) -> None:
        for name in (
            *SCRIPT_NAMES,
            "README.md",
            "build_linux_bundle.sh",
            "sanitize_paths.py",
            "smoke_appimage.sh",
            "tools.lock",
            "verify_bundle.py",
        ):
            with self.subTest(name=name):
                self.assertTrue((APPIMAGE_DIR / name).is_file())

    def test_tool_lock_pins_exact_tagged_assets(self) -> None:
        values = _parse_shell_assignments(APPIMAGE_DIR / "tools.lock")
        for key, expected in EXPECTED_LOCK_VALUES.items():
            with self.subTest(key=key):
                self.assertEqual(values.get(key), expected)

        for prefix in ("LINUXDEPLOY", "APPIMAGETOOL", "PATCHELF"):
            url = values[f"{prefix}_URL"]
            tag = values[f"{prefix}_TAG"]
            asset = values[f"{prefix}_ASSET"]
            self.assertEqual(
                url,
                f"https://github.com/{_repository(prefix)}/releases/download/{tag}/{asset}",
            )
            self.assertNotIn("/latest/", url)
            self.assertNotIn("/continuous/", url)
            self.assertRegex(values[f"{prefix}_SHA256"], r"^[0-9a-f]{64}$")
            provenance = values[f"{prefix}_PROVENANCE"]
            self.assertIn("github-release-api-digest", provenance)
            self.assertIn("attestation-absent", provenance)
            self.assertIn("tofu", provenance)

    def test_shell_scripts_are_strict_executable_and_proxy_safe(self) -> None:
        for name in SCRIPT_NAMES:
            with self.subTest(name=name):
                path = APPIMAGE_DIR / name
                text = _clean_utf8_text(path)
                self.assertTrue(text.startswith("#!/usr/bin/env bash\n"))
                self.assertIn("set -Eeuo pipefail", text)
                self.assertIn("PATH='/usr/bin:/bin'", text)
                self.assertTrue(path.stat().st_mode & stat.S_IXUSR)
                self.assertNotRegex(
                    text,
                    re.compile(r"(^|\s)(sudo|apt|apt-get|dnf|rpm)(\s|$)", re.MULTILINE),
                )

        for script_name in ("build_appimage.sh", "fetch_tools.sh"):
            text = (APPIMAGE_DIR / script_name).read_text(encoding="utf-8")
            for variable in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                self.assertIn(variable, text)

    def test_fetch_script_verifies_before_publishing_tools(self) -> None:
        text = (APPIMAGE_DIR / "fetch_tools.sh").read_text(encoding="utf-8")
        self.assertIn("verify_sha256", text)
        self.assertIn("curl --disable --noproxy '*'", text)
        self.assertIn("--proto '=https'", text)
        self.assertIn(".part.XXXXXX", text)
        self.assertIn("PATCHELF_BINARY_SHA256", text)
        self.assertIn("--appimage-offset", text)
        self.assertIn("APPIMAGETOOL_RUNTIME_SHA256", text)
        self.assertIn("/usr/bin/install", text)

    def test_build_script_uses_existing_bundle_and_staging_only(self) -> None:
        text = (APPIMAGE_DIR / "build_appimage.sh").read_text(encoding="utf-8")
        self.assertIn('source_bundle="$repo_root/build/linux"', text)
        self.assertIn('cp -a -- "$source_bundle/."', text)
        self.assertIn('staging_root="$(mktemp -d', text)
        self.assertIn("Tokenlogue.AppDir", text)
        self.assertIn("Tokenlogue-${version}-x86_64.AppImage", text)
        self.assertNotIn("0.1.0", text)
        self.assertIn("tomllib", text)
        self.assertIn("SOURCE_DATE_EPOCH", text)
        self.assertIn("--deploy-deps-only", text)
        self.assertIn("--appimage-extract-and-run", text)
        self.assertIn("--runtime-file", text)
        self.assertIn("--exclude-library='libflutter_linux_gtk.so'", text)
        self.assertIn("--exclude-library='libpython3.12.so.1.0'", text)
        self.assertIn("Restore the project's deterministic root links", text)
        self.assertIn('is_elf "$candidate" && continue', text)
        self.assertIn("-----BEGIN [A-Z ]*PRIVATE KEY-----", text)
        self.assertNotIn("zsync", text.lower())

    def test_build_script_handles_tkinter_runpaths_documents_and_metadata(self) -> None:
        text = (APPIMAGE_DIR / "build_appimage.sh").read_text(encoding="utf-8")
        self.assertIn("_tkinter.cpython-312-*.so", text)
        self.assertIn('[[ "${#tkinter_extensions[@]}" -eq 1 ]]', text)
        self.assertIn("libtcl9tk9", text)
        self.assertIn("libtcl9", text)
        self.assertIn("$ORIGIN/../..", text)
        self.assertIn("THIRD_PARTY_NOTICES.md", text)
        self.assertIn("usr/share/doc/tokenlogue", text)
        self.assertIn("usr/share/icons/hicolor", text)
        self.assertIn("Exec=tokenlogue", text)
        self.assertIn("/^TryExec=\\/usr\\/bin\\/tokenlogue$/d", text)
        self.assertNotIn("TryExec=tokenlogue", text)

    def test_optional_jni_removal_preserves_source_bridge_and_neighbors(self) -> None:
        self._check_jni_staging_removal(present=True)

    def test_optional_jni_removal_allows_absent_file(self) -> None:
        self._check_jni_staging_removal(present=False)

    def _check_jni_staging_removal(self, *, present: bool) -> None:
        text = (APPIMAGE_DIR / "build_appimage.sh").read_text(encoding="utf-8")
        function = re.search(
            r"^remove_optional_jni\(\) \{\n.*?^\}", text, re.MULTILINE | re.DOTALL
        )
        assert function is not None
        copy_command = 'cp -a -- "$source_bundle/." "$appdir/usr/lib/tokenlogue/"'
        remove_command = 'remove_optional_jni "$appdir"'
        self.assertLess(text.index(copy_command), text.index(remove_command))
        self.assertLess(
            text.index(remove_command),
            text.index('"$linuxdeploy" "${linuxdeploy_args[@]}"'),
        )
        self.assertEqual(text.count(remove_command), 1)

        # Exercise only the real copy and removal fragment, never the build.
        program = (
            "set -Eeuo pipefail\n"
            + function.group(0)
            + "\nsource_bundle=$1\nappdir=$2\n"
            + copy_command
            + "\n"
            + remove_command
            + "\n"
        )
        source_contents = {
            "tokenlogue": b"executable fixture",
            "lib/libdart_bridge.so": b"required Python bridge",
            "lib/libflutter_linux_gtk.so": b"Flutter fixture",
            "lib/libdartjni.so.extra": b"similar filename must remain",
            "lib/nested/libdartjni.so": b"only the exact path may be removed",
        }
        if present:
            source_contents["lib/libdartjni.so"] = b"optional JNI fixture"
        with tempfile.TemporaryDirectory(prefix="tokenlogue JNI staging ") as temp:
            source = Path(temp) / "source bundle"
            appdir = Path(temp) / "Tokenlogue.AppDir"
            staging_bundle = appdir / "usr/lib/tokenlogue"
            staging_bundle.mkdir(parents=True)
            for relative, content in source_contents.items():
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            subprocess.run(
                ["bash", "-c", program, "jni-fixture", str(source), str(appdir)],
                check=True,
                capture_output=True,
                text=True,
            )

            actual_source = {
                path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*")
                if path.is_file()
            }
            actual_staging = {
                path.relative_to(staging_bundle).as_posix(): path.read_bytes()
                for path in staging_bundle.rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual_source, source_contents)
            self.assertEqual(
                actual_staging,
                {
                    name: data
                    for name, data in source_contents.items()
                    if name != "lib/libdartjni.so"
                },
            )

    def test_source_desktop_keeps_system_exec_and_try_exec(self) -> None:
        text = _clean_utf8_text(SOURCE_DESKTOP)
        lines = text.splitlines()

        self.assertEqual(
            [line for line in lines if line.startswith("Exec=")],
            ["Exec=/usr/bin/tokenlogue"],
        )
        self.assertEqual(
            [line for line in lines if line.startswith("TryExec=")],
            ["TryExec=/usr/bin/tokenlogue"],
        )

    def test_built_appdir_desktop_is_portable(self) -> None:
        desktop = (
            PROJECT_ROOT
            / "build"
            / "appimage"
            / "Tokenlogue.AppDir"
            / STAGED_DESKTOP_RELATIVE
        )
        if not desktop.is_file():
            self.skipTest("diagnostic AppDir has not been built")

        self._assert_portable_appimage_desktop(desktop)

    def test_extracted_appimage_desktop_is_portable(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
            version = tomllib.load(stream)["project"]["version"]
        appimage = (
            PROJECT_ROOT
            / "build"
            / "appimage"
            / f"Tokenlogue-{version}-x86_64.AppImage"
        )
        if not appimage.is_file():
            self.skipTest("diagnostic AppImage has not been built")

        with tempfile.TemporaryDirectory(prefix="tokenlogue-appimage-desktop-") as temp:
            subprocess.run(
                [
                    str(appimage),
                    "--appimage-extract",
                    STAGED_DESKTOP_RELATIVE.as_posix(),
                ],
                cwd=temp,
                check=True,
                capture_output=True,
                text=True,
            )
            desktop = Path(temp) / "squashfs-root" / STAGED_DESKTOP_RELATIVE
            self._assert_portable_appimage_desktop(desktop)

    def _assert_portable_appimage_desktop(self, desktop: Path) -> None:
        text = _clean_utf8_text(desktop)
        lines = text.splitlines()

        self.assertEqual(
            [line for line in lines if line.startswith("Exec=")],
            ["Exec=tokenlogue"],
        )
        self.assertFalse(any(line.startswith("TryExec=") for line in lines))
        self.assertNotIn("/usr/bin/tokenlogue", text)

        validator = shutil.which("desktop-file-validate")
        if validator is not None:
            subprocess.run(
                [validator, str(desktop)],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_apprun_is_relocatable_and_preserves_arguments(self) -> None:
        text = (APPIMAGE_DIR / "AppRun").read_text(encoding="utf-8")
        self.assertIn("BASH_SOURCE[0]", text)
        self.assertIn("$appdir/usr/bin/tokenlogue", text)
        self.assertIn('"$@"', text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("/tmp/", text)

    def test_gitignore_has_only_exact_appimage_infrastructure_exceptions(self) -> None:
        text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for name in (
            "AppRun",
            "README.md",
            "build_appimage.sh",
            "build_linux_bundle.sh",
            "fetch_tools.sh",
            "sanitize_paths.py",
            "smoke_appimage.sh",
            "tools.lock",
            "verify_bundle.py",
        ):
            self.assertIn(f"!packaging/linux/appimage/{name}", text)
        self.assertNotIn("!packaging/linux/appimage/**", text)

    def test_path_sanitizer_preserves_size_and_handles_spaced_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tokenlogue path test ") as temp_dir:
            root = Path(temp_dir)
            appdir = root / "Tokenlogue.AppDir"
            source_root = root / "source tree with spaces"
            appdir.mkdir()
            source_root.mkdir()
            fixture = appdir / "fixture.bin"
            original = (
                b"prefix "
                + str(source_root).encode()
                + b" /tmp/serious_python_tempABC123 "
                + str(source_root).encode()
                + b"/build/flutter/ephemeral suffix"
            )
            fixture.write_bytes(original)

            subprocess.run(
                [
                    sys.executable,
                    str(APPIMAGE_DIR / "sanitize_paths.py"),
                    str(appdir),
                    str(source_root),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            sanitized = fixture.read_bytes()
            self.assertEqual(len(sanitized), len(original))
            self.assertNotIn(str(source_root).encode(), sanitized)
            self.assertNotIn(b"/tmp/serious_python_temp", sanitized)
            self.assertNotIn(b"build/flutter", sanitized)

    def test_documentation_marks_output_as_diagnostic(self) -> None:
        text = (APPIMAGE_DIR / "README.md").read_text(encoding="utf-8").lower()
        for statement in (
            "diagnostic",
            "unsigned",
            "glibc 2.38",
            "anyio",
            "cross-distribution",
            "fuse",
            "trust-on-first-use",
        ):
            self.assertIn(statement, text)
        self.assertNotIn("published", text)


def _repository(prefix: str) -> str:
    return {
        "LINUXDEPLOY": "linuxdeploy/linuxdeploy",
        "APPIMAGETOOL": "AppImage/appimagetool",
        "PATCHELF": "NixOS/patchelf",
    }[prefix]


def _parse_shell_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, raw_value = stripped.partition("=")
        if not separator or not key.isidentifier():
            raise AssertionError(f"Invalid tools.lock line: {line}")
        parsed = shlex.split(raw_value)
        if len(parsed) != 1:
            raise AssertionError(f"Invalid tools.lock value: {line}")
        values[key] = parsed[0]
    return values


def _clean_utf8_text(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("utf-8")
    if not text.endswith("\n"):
        raise AssertionError(f"Missing final newline: {path}")
    if any(line != line.rstrip(" \t") for line in text.splitlines()):
        raise AssertionError(f"Trailing whitespace: {path}")
    return text


if __name__ == "__main__":
    unittest.main()
