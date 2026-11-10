"""Exact source selectors cannot widen the build network or weaken APK pins."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "packaging/linux/appimage/runtime"
sys.path.insert(0, str(MODULE))
import runtime_inputs as inputs  # noqa: E402  # pyright: ignore[reportMissingImports]
import source_containers as containers  # noqa: E402  # pyright: ignore[reportMissingImports]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Response(io.BytesIO):
    def __init__(
        self, data: bytes, *, status: int = 200, headers: dict[str, str] | None = None
    ):
        super().__init__(data)
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value


class Opener:
    def __init__(
        self, body: bytes, *, status: int = 200, headers: dict[str, str] | None = None
    ):
        self.body, self.status, self.headers = body, status, headers
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, **kwargs: object) -> Response:
        self.requests.append(request)
        return Response(self.body, status=self.status, headers=self.headers)


class ContainerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="runtime-containers-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = b"exact APK bytes"
        self.item = {
            "path": "apks/input.apk",
            "size": len(self.data),
            "sha256": sha(self.data),
        }
        self.destination = self.root / "input.apk"
        self.selector = {
            "kind": "official_iso_member",
            "url": "https://dl-cdn.alpinelinux.org/alpine/v3.21/releases/x86_64/alpine-extended-3.21.7-x86_64.iso",
            "member": "apks/x86_64/input.apk",
            "offset": 2048,
            "official_iso_size": 8192,
            "official_iso_expected_sha256": "a" * 64,
            "whole_iso_sha256_verified": False,
            "range_required": True,
            "size": len(self.data),
            "sha256": sha(self.data),
        }
        self.headers = {
            "Content-Range": f"bytes 2048-{2048 + len(self.data) - 1}/8192",
            "Content-Length": str(len(self.data)),
        }

    def test_exact_iso_range_never_claims_whole_image_verification(self) -> None:
        opener = Opener(self.data, status=206, headers=self.headers)
        result = containers.fetch_iso_member(
            self.item, self.selector, self.destination, opener
        )
        self.assertEqual(self.destination.read_bytes(), self.data)
        self.assertEqual(
            opener.requests[0].headers["Range"],
            f"bytes=2048-{2048 + len(self.data) - 1}",
        )
        self.assertEqual(opener.requests[0].headers["Accept-encoding"], "identity")
        self.assertTrue(result["selected_member_sha256_verified"])
        self.assertFalse(result["whole_iso_sha256_verified"])

    def test_ignored_or_incorrect_ranges_and_corrupted_bytes_never_publish_input(
        self,
    ) -> None:
        cases = [
            (self.data, 200, self.headers),
            (self.data, 206, {**self.headers, "Content-Range": "bytes 0-14/8192"}),
            (
                self.data,
                206,
                {
                    **self.headers,
                    "Content-Range": self.headers["Content-Range"].replace(
                        "8192", "8193"
                    ),
                },
            ),
            (self.data, 206, {"Content-Length": str(len(self.data))}),
            (self.data, 206, {**self.headers, "Content-Length": "1"}),
            (self.data, 206, {**self.headers, "Content-Encoding": "gzip"}),
            (self.data[:-1], 206, self.headers),
            (self.data + b"extra", 206, self.headers),
            (b"X" + self.data[1:], 206, self.headers),
        ]
        for body, status, headers in cases:
            with self.subTest(status=status, headers=headers, body=body):
                with self.assertRaises(inputs.Failure):
                    containers.fetch_iso_member(
                        self.item,
                        self.selector,
                        self.destination,
                        Opener(body, status=status, headers=headers),
                    )
                self.assertFalse(self.destination.exists())
                self.assertEqual(list(self.root.iterdir()), [])

    def bundle(self, *, special: str | None = None) -> tuple[bytes, dict, list[dict]]:
        files = {
            "apks/one.apk": b"one",
            "apks/two.apk": b"two",
            "apks/three.apk": b"three",
            "licenses/LICENSE": b"Original copyright and license\n",
        }
        content = io.BytesIO()
        with tarfile.open(fileobj=content, mode="w:gz") as archive:
            for name, data in files.items():
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            if special:
                member = tarfile.TarInfo(
                    special
                    if special not in {"symlink", "hardlink", "device", "duplicate"}
                    else "unsafe"
                )
                if special == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "/outside"
                elif special == "hardlink":
                    member.type = tarfile.LNKTYPE
                    member.linkname = "apks/one.apk"
                elif special == "device":
                    member.type = tarfile.CHRTYPE
                elif special == "duplicate":
                    member.name = "apks/one.apk"
                archive.addfile(member, io.BytesIO(b""))
        body = content.getvalue()
        bundle = {
            "url": inputs.CURRENT_DEPENDENCY_URL,
            "size": len(body),
            "sha256": sha(body),
            "members": {
                name: {"size": len(data), "sha256": sha(data)}
                for name, data in files.items()
            },
        }
        items = [
            {"path": name, "size": len(data), "sha256": sha(data)}
            for name, data in files.items()
            if name.startswith("apks/")
        ]
        return body, bundle, items

    def test_pinned_small_container_downloaded_once_and_only_selected_APKs_published(
        self,
    ) -> None:
        body, bundle, items = self.bundle()
        opener = Opener(body)
        states = {}
        plan = {"dependency_bundle": bundle}
        for item in items:
            selected = {"kind": "dependency_bundle_member", "member": item["path"]}
            target = self.root / Path(item["path"]).name
            result = containers.fetch_container_input(
                item, selected, target, self.root, plan, opener, states
            )
            self.assertEqual(sha(target.read_bytes()), item["sha256"])
            self.assertTrue(result["whole_container_sha256_verified"])
            self.assertEqual(result["container_cache"], "downloaded-current-session")
        self.assertEqual(len(opener.requests), 1)
        self.assertFalse((self.root / "licenses").exists())
        archive = self.root / "containers" / (bundle["sha256"] + ".tar.gz")
        self.assertEqual(archive.read_bytes(), body)
        archive.write_bytes(body[:-1] + b"X")
        with self.assertRaises(inputs.Failure):
            containers.checked_container(self.root, bundle, opener, {})
        self.assertEqual(archive.read_bytes(), body[:-1] + b"X")

    def test_real_input_fetcher_uses_the_pinned_container_and_distinguishes_later_input_cache(
        self,
    ) -> None:
        body, bundle, items = self.bundle()
        opener = Opener(body)
        lock = {
            "files": [
                {**item, "url": "https://obsolete.invalid/never-fetch.apk"}
                for item in items
            ]
        }
        plan = {
            "dependency_bundle": bundle,
            "selectors": {
                item["path"]: {
                    "kind": "dependency_bundle_member",
                    "member": item["path"],
                }
                for item in items
            },
        }
        audit = self.root / "audit.json"
        with patch.object(inputs.urllib.request, "build_opener", return_value=opener):
            inputs.fetch_inputs(lock, self.root, audit, acquisition=plan)
        first = json.loads(audit.read_text())
        self.assertEqual(first["result"], "PASS")
        self.assertEqual(
            [request.full_url for request in opener.requests],
            [inputs.CURRENT_DEPENDENCY_URL],
        )
        self.assertTrue(
            all(
                entry["mode"] == "downloaded-and-verified"
                and entry["whole_container_sha256_verified"]
                for entry in first["inputs"]
            )
        )
        self.assertTrue(
            all(
                entry["source_kind"] == "pinned-dependency-container-member"
                for entry in first["inputs"]
            )
        )
        with patch.object(inputs.urllib.request, "build_opener", return_value=opener):
            inputs.fetch_inputs(lock, self.root, audit, acquisition=plan)
        repeated = json.loads(audit.read_text())
        self.assertTrue(
            all(entry["mode"] == "verified-cache" for entry in repeated["inputs"])
        )
        self.assertEqual(len(opener.requests), 1)

    def test_tampered_whole_container_fails_before_tar_parse_or_input_publication(
        self,
    ) -> None:
        body, bundle, _ = self.bundle()
        opener = Opener(body[:-1] + b"X")
        with patch.object(
            containers.tarfile, "open", side_effect=AssertionError("not authenticated")
        ):
            with self.assertRaises(inputs.Failure):
                containers.checked_container(self.root, bundle, opener, {})
        self.assertFalse(self.destination.exists())

    def test_unsafe_container_paths_types_duplicates_and_unexpected_files_are_rejected(
        self,
    ) -> None:
        for special in (
            "../escape",
            "/absolute",
            "symlink",
            "hardlink",
            "device",
            "duplicate",
            "unexpected",
        ):
            with self.subTest(special=special):
                body, bundle, items = self.bundle(special=special)
                archive = self.root / "bad.tar.gz"
                archive.write_bytes(body)
                with self.assertRaises(inputs.Failure):
                    containers.extract_bundle_member(
                        archive,
                        bundle,
                        {"member": items[0]["path"]},
                        items[0],
                        self.destination,
                    )
                self.assertFalse(self.destination.exists())

    def test_member_bytes_and_complete_inventory_are_required_even_with_matching_container_hash(
        self,
    ) -> None:
        body, bundle, items = self.bundle()
        archive = self.root / "kit.tar.gz"
        archive.write_bytes(body)
        changed = copy.deepcopy(bundle)
        changed["members"]["licenses/LICENSE"]["sha256"] = "0" * 64
        with self.assertRaises(inputs.Failure):
            containers.extract_bundle_member(
                archive,
                changed,
                {"member": items[0]["path"]},
                items[0],
                self.destination,
            )
        changed = copy.deepcopy(bundle)
        changed["members"]["missing"] = {"size": 1, "sha256": "0" * 64}
        with self.assertRaises(inputs.Failure):
            containers.extract_bundle_member(
                archive,
                changed,
                {"member": items[0]["path"]},
                items[0],
                self.destination,
            )
        self.assertFalse(self.destination.exists())


class SourceContractTests(unittest.TestCase):
    def test_checked_in_plan_covers_only_the_sixteen_exact_retained_APKs(self) -> None:
        lock = inputs.load_lock(MODULE / "runtime.lock.json")
        plan = containers.load_acquisition_plan(MODULE / "acquisition.lock.json", lock)
        kinds = [entry["kind"] for entry in plan["selectors"].values()]
        self.assertEqual(kinds.count("official_iso_member"), 13)
        self.assertEqual(kinds.count("dependency_bundle_member"), 3)
        self.assertTrue(
            {
                "licenses/musl/COPYRIGHT",
                "licenses/zlib/LICENSE",
                "licenses/GPL-2.0.txt",
                "sources/musl-1.2.5.tar.gz",
                "sources/zlib-1.3.2.tar.gz",
            }.issubset(plan["dependency_bundle"]["members"])
        )

    def test_new_repository_exception_requires_exact_asset_and_pin_and_never_opens_old_releases(
        self,
    ) -> None:
        pin = {"url": inputs.CURRENT_DEPENDENCY_URL, "size": 20, "sha256": "a" * 64}
        events = []
        guard = inputs.OfficialInputGuard(events, pin)
        guard.https_request(urllib.request.Request(pin["url"]))
        for url in (
            pin["url"] + "?anything=1",
            pin["url"].replace(".tar.gz", "-other.tar.gz"),
            "https://github.com/Umichata/tokenlogue/releases/download/v0.1.0-linux-preview.986c6ad/runtime.zip",
            "https://github.com/%55michata/tokenlogue/releases/download/old/runtime.zip",
        ):
            with self.subTest(url=url), self.assertRaises(inputs.Failure):
                guard.https_request(urllib.request.Request(url))
        with self.assertRaises(inputs.Failure):
            inputs.OfficialInputGuard([]).https_request(
                urllib.request.Request(pin["url"])
            )
        with self.assertRaises(inputs.Failure):
            inputs.OfficialInputGuard(
                [], {**pin, "url": pin["url"].replace("20261110", "20261109")}
            )
        self.assertEqual(events[0]["allowed"], True)
        self.assertTrue(all(event["allowed"] is False for event in events[1:]))

    def test_wrong_selector_or_container_pins_fail_loading_before_any_network(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runtime.lock.json").write_bytes(
                (MODULE / "runtime.lock.json").read_bytes()
            )
            original = json.loads((MODULE / "acquisition.lock.json").read_text())
            lock = inputs.load_lock(root / "runtime.lock.json")
            for change in (
                "input-hash",
                "range-bounds",
                "whole-iso-claim",
                "container-url",
                "container-sha",
            ):
                plan = copy.deepcopy(original)
                iso = next(
                    v
                    for v in plan["selectors"].values()
                    if v["kind"] == "official_iso_member"
                )
                if change == "input-hash":
                    iso["sha256"] = "0" * 64
                elif change == "range-bounds":
                    iso["offset"] = iso["official_iso_size"]
                elif change == "whole-iso-claim":
                    iso["whole_iso_sha256_verified"] = True
                elif change == "container-url":
                    plan["dependency_bundle"]["url"] += "?token=not-allowed"
                else:
                    plan["dependency_bundle"]["sha256"] = "bad"
                path = root / "acquisition.lock.json"
                path.write_text(json.dumps(plan))
                with self.subTest(change=change), self.assertRaises(inputs.Failure):
                    containers.load_acquisition_plan(path, lock)


if __name__ == "__main__":
    unittest.main()
