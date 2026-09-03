"""Tests for public project, license, and release metadata."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PRODUCTION_DEPENDENCIES = {
    "flet==0.86.5",
    "flet-secure-storage==0.86.5",
    "httpx==0.28.1",
}
EXPECTED_DEV_DEPENDENCIES = {
    "flet-cli==0.86.5",
    "flet-desktop==0.86.5",
    "pyright==1.1.411",
    "ruff==0.16.5",
}
EXPECTED_APP_EXCLUDES = {
    ".flet",
    ".env",
    ".env.local",
    "tokenlogue.sqlite3",
    "__pycache__",
    "api/__pycache__",
    "auth/__pycache__",
    "chat/__pycache__",
    "storage/__pycache__",
    "ui/__pycache__",
}


class ProjectMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

    def test_mit_license_has_expected_owner_and_year(self) -> None:
        license_path = PROJECT_ROOT / "LICENSE"
        self.assertTrue(license_path.is_file())
        license_text = license_path.read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 Viktor Zemkov", license_text)

    def test_project_identity_and_pep639_metadata(self) -> None:
        project = self.metadata["project"]
        self.assertEqual(project["name"], "tokenlogue")
        self.assertEqual(project["version"], "0.1.0")
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(set(project["license-files"]), {"LICENSE"})
        self.assertEqual(
            {author["name"] for author in project["authors"]},
            {"Viktor Zemkov"},
        )
        self.assertTrue(all(set(author) == {"name"} for author in project["authors"]))

    def test_flet_identity_and_publisher_metadata(self) -> None:
        flet = self.metadata["tool"]["flet"]
        self.assertEqual(flet["product"], "Tokenlogue")
        self.assertEqual(flet["artifact"], "tokenlogue")
        self.assertEqual(flet["org"], "io.github.umichata")
        self.assertEqual(flet["bundle_id"], "io.github.umichata.tokenlogue")
        self.assertEqual(flet["build_number"], 1)
        self.assertEqual(flet["company"], "Umichata")
        self.assertEqual(flet["copyright"], "Copyright © 2026 Viktor Zemkov")

    def test_dependency_groups_are_exact_and_reproducible(self) -> None:
        self.assertEqual(
            set(self.metadata["project"]["dependencies"]),
            EXPECTED_PRODUCTION_DEPENDENCIES,
        )
        self.assertEqual(
            set(self.metadata["dependency-groups"]["dev"]),
            EXPECTED_DEV_DEPENDENCIES,
        )
        self.assertTrue(
            all("==" in dependency for dependency in EXPECTED_DEV_DEPENDENCIES)
        )

    def test_flet_app_excludes_are_exact_paths_without_globs(self) -> None:
        flet = self.metadata["tool"]["flet"]
        self.assertNotIn("exclude", flet)
        self.assertEqual(set(flet["app"]["exclude"]), EXPECTED_APP_EXCLUDES)
        for value in flet["app"]["exclude"]:
            self.assertFalse(any(character in value for character in "*?[]"))

    def test_android_configuration_is_unchanged(self) -> None:
        android = self.metadata["tool"]["flet"]["android"]
        self.assertEqual(android["min_sdk_version"], 24)
        self.assertNotIn("target_sdk_version", android)
        self.assertNotIn("adaptive_icon_background", android)
        self.assertEqual(
            android["manifest_application"],
            {"allowBackup": "false", "fullBackupContent": "false"},
        )
        self.assertEqual(
            android["permission"],
            {
                "android.permission.INTERNET": True,
                "android.permission.ACCESS_NETWORK_STATE": False,
                "android.permission.READ_EXTERNAL_STORAGE": False,
                "android.permission.WRITE_EXTERNAL_STORAGE": False,
            },
        )

    def test_third_party_registry_exists(self) -> None:
        self.assertTrue((PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").is_file())


if __name__ == "__main__":
    unittest.main()
