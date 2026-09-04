"""Tests for Linux desktop integration metadata."""

from __future__ import annotations

import configparser
import re
import shlex
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LINUX_METADATA_DIR = PROJECT_ROOT / "packaging" / "linux"
DESKTOP_FILE = LINUX_METADATA_DIR / "io.github.umichata.tokenlogue.desktop"
METAINFO_FILE = LINUX_METADATA_DIR / "io.github.umichata.tokenlogue.metainfo.xml"
COMPONENT_ID = "io.github.umichata.tokenlogue"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
HICOLOR_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
EXPECTED_DESKTOP_VALUES = {
    "Type": "Application",
    "Version": "1.5",
    "Name": "Tokenlogue",
    "GenericName": "AI Chat Client",
    "GenericName[ru]": "Клиент чата с ИИ",
    "Comment": "Chat with AI models through OpenRouter",
    "Comment[ru]": "Общение с моделями ИИ через OpenRouter",
    "Exec": "/usr/bin/tokenlogue",
    "TryExec": "/usr/bin/tokenlogue",
    "Icon": "tokenlogue",
    "Terminal": "false",
    "Categories": "Network;Chat;",
    "Keywords": "AI;Chat;OpenRouter;",
    "Keywords[ru]": "ИИ;Чат;OpenRouter;",
}


class CaseSensitiveConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


class LinuxMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.desktop_text = _read_utf8_text(DESKTOP_FILE)
        cls.metainfo_text = _read_utf8_text(METAINFO_FILE)

        parser = CaseSensitiveConfigParser(interpolation=None, strict=True)
        parser.read_string(cls.desktop_text)
        cls.desktop = dict(parser["Desktop Entry"])
        cls.component = ET.fromstring(cls.metainfo_text)

    def test_metadata_files_exist_and_are_clean_utf8(self) -> None:
        for path, text in (
            (DESKTOP_FILE, self.desktop_text),
            (METAINFO_FILE, self.metainfo_text),
        ):
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertTrue(text.endswith("\n"))
                self.assertFalse(
                    any(line != line.rstrip(" \t") for line in text.splitlines())
                )

    def test_desktop_entry_has_only_expected_values(self) -> None:
        self.assertEqual(self.desktop, EXPECTED_DESKTOP_VALUES)

    def test_desktop_categories_are_exact_and_registered(self) -> None:
        self.assertEqual(
            _semicolon_values(self.desktop["Categories"]),
            ("Network", "Chat"),
        )

    def test_desktop_exec_is_a_plain_executable_path(self) -> None:
        command = self.desktop["Exec"]
        self.assertEqual(shlex.split(command), ["/usr/bin/tokenlogue"])
        self.assertIsNone(re.search(r"[;&|><`]|\$\(|\n|\r", command))

    def test_metainfo_identity_licenses_and_developer(self) -> None:
        component = self.component
        self.assertEqual(component.tag, "component")
        self.assertEqual(component.attrib.get("type"), "desktop-application")
        self.assertEqual(_required_text(component, "id"), COMPONENT_ID)
        self.assertEqual(_required_text(component, "name"), "Tokenlogue")
        self.assertEqual(_required_text(component, "metadata_license"), "MIT")
        self.assertEqual(_required_text(component, "project_license"), "MIT")

        developer = component.find("developer")
        self.assertIsNotNone(developer)
        assert developer is not None
        self.assertEqual(developer.attrib.get("id"), "io.github.umichata")
        self.assertEqual(_required_text(developer, "name"), "Viktor Zemkov")

    def test_metainfo_has_localized_summary_and_description(self) -> None:
        summaries = {
            summary.attrib.get(XML_LANG, "en"): (summary.text or "").strip()
            for summary in self.component.findall("summary")
        }
        self.assertTrue(summaries.get("en"))
        self.assertTrue(summaries.get("ru"))

        description = self.component.find("description")
        self.assertIsNotNone(description)
        assert description is not None
        paragraph_languages = {
            paragraph.attrib.get(XML_LANG, "en")
            for paragraph in description.findall("p")
            if (paragraph.text or "").strip()
        }
        self.assertEqual(paragraph_languages, {"en", "ru"})

    def test_metainfo_launchable_urls_and_categories(self) -> None:
        launchable = self.component.find("launchable")
        self.assertIsNotNone(launchable)
        assert launchable is not None
        self.assertEqual(launchable.attrib.get("type"), "desktop-id")
        self.assertEqual((launchable.text or "").strip(), f"{COMPONENT_ID}.desktop")

        urls = {
            element.attrib.get("type"): (element.text or "").strip()
            for element in self.component.findall("url")
        }
        self.assertEqual(
            urls,
            {
                "homepage": "https://github.com/Umichata/tokenlogue",
                "bugtracker": "https://github.com/Umichata/tokenlogue/issues",
            },
        )
        categories = {
            (category.text or "").strip()
            for category in self.component.findall("categories/category")
        }
        self.assertEqual(categories, {"Network", "Chat"})

    def test_component_desktop_id_and_hicolor_icons_agree(self) -> None:
        self.assertEqual(DESKTOP_FILE.stem, COMPONENT_ID)
        icon_name = self.desktop["Icon"]
        hicolor = PROJECT_ROOT / "packaging" / "icons" / "linux" / "hicolor"
        for size in HICOLOR_SIZES:
            with self.subTest(size=size):
                icon = hicolor / f"{size}x{size}" / "apps" / f"{icon_name}.png"
                self.assertTrue(icon.is_file())

    def test_metainfo_has_no_unverified_release_or_screenshot_data(self) -> None:
        self.assertIsNone(self.component.find("releases"))
        self.assertIsNone(self.component.find("screenshots"))

    def test_metadata_has_no_user_paths_or_forbidden_project_mentions(self) -> None:
        combined = f"{self.desktop_text}\n{self.metainfo_text}"
        lowered = combined.lower()
        for forbidden in (
            "/home/",
            "/users/",
            "51-lesson",
            "codex",
            "cursor",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)
        self.assertIsNone(
            re.search(r"[a-z]:[\\/](?:users|documents and settings)[\\/]", lowered)
        )


def _read_utf8_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _semicolon_values(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split(";") if item)


def _required_text(element: ET.Element, path: str) -> str:
    value = element.findtext(path)
    if value is None or not value.strip():
        raise AssertionError(f"Missing XML value: {path}")
    return value.strip()


if __name__ == "__main__":
    unittest.main()
