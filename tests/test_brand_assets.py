"""Structural checks for the Tokenlogue brand assets."""

from __future__ import annotations

import struct
import unittest
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BRAND_COLORS = ("#151A1F", "#27D3C2", "#8AF1E5")
SVG_FILES = (
    "tokenlogue-icon.svg",
    "tokenlogue-icon-foreground.svg",
    "tokenlogue-icon-background.svg",
    "tokenlogue-icon-monochrome.svg",
)
LINUX_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)


class PngImage(NamedTuple):
    width: int
    height: int
    rgba: bytes


class BrandAssetTests(unittest.TestCase):
    def test_flet_assets_exist(self) -> None:
        for name in (
            "icon.png",
            "icon_android.png",
            "icon_windows.ico",
            "icon_linux.png",
        ):
            with self.subTest(name=name):
                self.assertTrue((PROJECT_ROOT / "src" / "assets" / name).is_file())

    def test_flet_png_signatures_and_dimensions(self) -> None:
        expected = {
            "icon.png": (1024, 1024),
            "icon_android.png": (1024, 1024),
            "icon_linux.png": (256, 256),
        }
        for name, dimensions in expected.items():
            with self.subTest(name=name):
                path = PROJECT_ROOT / "src" / "assets" / name
                self.assertEqual(path.read_bytes()[:8], PNG_SIGNATURE)
                image = _read_rgba8_png(path)
                self.assertEqual((image.width, image.height), dimensions)

    def test_windows_icon_header_and_sizes(self) -> None:
        path = PROJECT_ROOT / "src" / "assets" / "icon_windows.ico"
        data = path.read_bytes()
        self.assertGreaterEqual(len(data), 6)
        reserved, image_type, count = struct.unpack_from("<HHH", data)
        self.assertEqual((reserved, image_type), (0, 1))
        self.assertGreater(count, 0)
        self.assertGreaterEqual(len(data), 6 + count * 16)

        dimensions: set[int] = set()
        for index in range(count):
            offset = 6 + index * 16
            width, height = data[offset], data[offset + 1]
            dimensions.add(width or 256)
            self.assertEqual(height or 256, width or 256)
            payload_size, payload_offset = struct.unpack_from("<II", data, offset + 8)
            self.assertGreater(payload_size, 0)
            self.assertLessEqual(payload_offset + payload_size, len(data))

        self.assertEqual(dimensions, set(LINUX_ICON_SIZES[:-1]))

    def test_svg_sources_are_safe_flat_vectors(self) -> None:
        source_dir = PROJECT_ROOT / "branding" / "source"
        for name in SVG_FILES:
            with self.subTest(name=name):
                root = ET.parse(source_dir / name).getroot()
                self.assertEqual(_local_name(root.tag), "svg")
                for element in root.iter():
                    element_name = _local_name(element.tag)
                    self.assertNotIn("gradient", element_name)
                    self.assertNotIn(
                        element_name,
                        {"filter", "image", "script", "foreignobject"},
                    )
                    for attribute, value in element.attrib.items():
                        attribute_name = _local_name(attribute)
                        self.assertNotEqual(attribute_name, "filter")
                        if attribute_name == "href":
                            self.assertTrue(value.startswith("#"))
                        self.assertNotIn("data:image", value.lower())
                        if "url(" in value.lower():
                            self.assertIn("url(#", value.lower())

    def test_master_svg_contains_complete_brand_palette(self) -> None:
        master = (
            PROJECT_ROOT / "branding" / "source" / "tokenlogue-icon.svg"
        ).read_text(encoding="utf-8")
        for color in BRAND_COLORS:
            with self.subTest(color=color):
                self.assertIn(color, master)

    def test_android_layers_have_expected_alpha(self) -> None:
        android_dir = PROJECT_ROOT / "packaging" / "icons" / "android"
        foreground = _read_rgba8_png(android_dir / "icon-foreground.png")
        background = _read_rgba8_png(android_dir / "icon-background.png")

        self.assertEqual((foreground.width, foreground.height), (1024, 1024))
        self.assertEqual((background.width, background.height), (1024, 1024))
        self.assertTrue(any(alpha < 255 for alpha in foreground.rgba[3::4]))
        self.assertTrue(all(alpha == 255 for alpha in background.rgba[3::4]))

    def test_all_linux_hicolor_sizes_exist(self) -> None:
        hicolor = PROJECT_ROOT / "packaging" / "icons" / "linux" / "hicolor"
        for size in LINUX_ICON_SIZES:
            with self.subTest(size=size):
                path = hicolor / f"{size}x{size}" / "apps" / "tokenlogue.png"
                self.assertTrue(path.is_file())
                image = _read_rgba8_png(path)
                self.assertEqual((image.width, image.height), (size, size))


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _read_rgba8_png(path: Path) -> PngImage:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature")

    cursor = len(PNG_SIGNATURE)
    width: int | None = None
    height: int | None = None
    bit_depth: int | None = None
    color_type: int | None = None
    interlace: int | None = None
    compressed = bytearray()

    while cursor < len(data):
        if cursor + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        length = struct.unpack_from(">I", data, cursor)[0]
        chunk_type = data[cursor + 4 : cursor + 8]
        payload_start = cursor + 8
        payload_end = payload_start + length
        crc_end = payload_end + 4
        if crc_end > len(data):
            raise ValueError("PNG chunk exceeds file boundary")
        payload = data[payload_start:payload_end]
        expected_crc = struct.unpack_from(">I", data, payload_end)[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(payload, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("Invalid PNG chunk CRC")

        if chunk_type == b"IHDR":
            if length != 13:
                raise ValueError("Invalid PNG IHDR")
            (
                width,
                height,
                bit_depth,
                color_type,
                compression_method,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", payload)
            if compression_method != 0 or filter_method != 0:
                raise ValueError("Unsupported PNG encoding")
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            break
        cursor = crc_end

    if width is None or height is None:
        raise ValueError("PNG has no IHDR")
    if bit_depth != 8 or color_type != 6 or interlace != 0:
        raise ValueError("Expected a non-interlaced 8-bit RGBA PNG")

    decoded = zlib.decompress(compressed)
    bytes_per_pixel = 4
    stride = width * bytes_per_pixel
    expected_length = height * (stride + 1)
    if len(decoded) != expected_length:
        raise ValueError("Unexpected PNG image data length")

    pixels = bytearray()
    previous = bytearray(stride)
    position = 0
    for _ in range(height):
        filter_type = decoded[position]
        position += 1
        filtered = decoded[position : position + stride]
        position += stride
        reconstructed = bytearray(stride)
        for index, value in enumerate(filtered):
            left = reconstructed[index - bytes_per_pixel] if index >= 4 else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= 4 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise ValueError("Unsupported PNG filter")
            reconstructed[index] = (value + predictor) & 0xFF
        pixels.extend(reconstructed)
        previous = reconstructed

    return PngImage(width, height, bytes(pixels))


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


if __name__ == "__main__":
    unittest.main()
