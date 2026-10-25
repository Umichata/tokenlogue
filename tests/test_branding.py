"""Ресурсы оформления и остановка индикатора без настоящего клиента."""

from __future__ import annotations

import asyncio
import hashlib
import struct
import sys
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_brand_assets import _read_rgba8_png  # noqa: E402

from ui import branding  # noqa: E402


class FakePage:
    def __init__(self):
        self.app_visible = True
        self.tasks = []
        self.on_app_lifecycle_state_change = object()

    def run_task(self, callback, *args):
        task = asyncio.create_task(callback(*args))
        self.tasks.append(task)
        return task


class MountedLoader(branding.BrandLoader):
    test_page: FakePage
    frames: list[str | bytes]
    _parent: weakref.ReferenceType[ft.Control]

    @property
    def page(self) -> ft.Page:
        return cast(ft.Page, self.test_page)

    def update(self):
        self.before_update()
        self.frames.append(self._logo.src)


class Features:
    def __init__(self):
        self.calls = 0
        self.disabled = self.reduced = self.fail = False

    async def get_accessibility_features(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("Искусственно недоступный канал accessibility")
        return SimpleNamespace(
            disable_animations=self.disabled, reduce_motion=self.reduced
        )


class BrandingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.page = FakePage()
        self.features = Features()
        self.service_patch = patch.object(
            branding.ft, "SemanticsService", return_value=self.features
        )
        self.service_patch.start()
        self.loaders = []

    async def asyncTearDown(self):
        for loader in self.loaders:
            loader.dispose()
        await asyncio.gather(*self.page.tasks, return_exceptions=True)
        self.service_patch.stop()
        branding._pages.clear()

    def loader(self, **kwargs):
        loader = MountedLoader(**kwargs)
        loader.test_page = self.page
        loader.frames = []
        self.loaders.append(loader)
        return loader

    async def settled(self):
        await asyncio.wait_for(asyncio.gather(*self.page.tasks), timeout=1)

    def assert_static(self, loader):
        self.assertEqual(loader._logo.src, "branding/tokenlogue-loading-static.png")
        self.assertIsNone(loader._task)

    def test_header_and_loaders_use_transparent_bounded_resources(self):
        logo = branding.BrandHeader().controls[0]
        self.assertIsInstance(logo, ft.Image)
        assert isinstance(logo, ft.Image)
        self.assertEqual((logo.width, logo.height), (32, 32))
        self.assertEqual(logo.src, "branding/tokenlogue-logo-transparent.png")
        for size in (26, 56):
            loader = self.loader(size=size)
            self.assertEqual((loader.width, loader.height), (size, size))
            self.assertEqual((loader._logo.width, loader._logo.height), (size, size))
            self.assertEqual(loader._logo.fit, ft.BoxFit.CONTAIN)
            self.assertIsNone(loader.bgcolor)
            self.assertIsNone(loader._logo.rotate)
            self.assertIsNone(loader._logo.animate_rotation)
            self.assertIsInstance(loader.content, ft.Semantics)
            self.assert_static(loader)
        self.assertEqual(self.page.tasks, [])

    async def test_accessibility_failure_does_not_claim_reduced_motion(self):
        self.features.fail = True
        loader = self.loader()
        loader.did_mount()
        await self.settled()
        self.assertEqual(loader._logo.src, "branding/tokenlogue-loading.webp")
        self.assertEqual(loader._motion_status, "unavailable")
        self.assertIsNone(branding._page_motion(loader.page).reduce_motion)
        self.assertIsNone(loader._task)

    async def test_webp_plays_without_python_frame_loop_or_second_transform(self):
        loader = self.loader()
        lifecycle = self.page.on_app_lifecycle_state_change
        loader.did_mount()
        await self.settled()
        self.assertEqual(loader._logo.src, "branding/tokenlogue-loading.webp")
        self.assertEqual(loader.frames, ["branding/tokenlogue-loading.webp"])
        self.assertIsNone(loader._task)
        self.assertIsNone(loader.rotate)
        self.assertIsNone(loader._logo.rotate)
        self.assertIsNone(loader._logo.animate_opacity)
        self.assertEqual(self.features.calls, 1)
        self.assertIs(self.page.on_app_lifecycle_state_change, lifecycle)
        for _ in range(5):
            loader.before_update()
            loader.set_active(True)
        self.assertEqual(len(self.page.tasks), 1)

    async def test_accessibility_timeout_has_same_unknown_policy_and_cancels_read(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def timeout_features():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with (
            patch.object(self.features, "get_accessibility_features", timeout_features),
            patch.object(branding, "_ACCESSIBILITY_TIMEOUT_SECONDS", 0.01),
        ):
            loader = self.loader()
            loader.did_mount()
            await asyncio.wait_for(started.wait(), timeout=1)
            await self.settled()
        self.assertTrue(cancelled.is_set())
        self.assertEqual(loader._motion_status, "unavailable")
        self.assertEqual(loader._logo.src, "branding/tokenlogue-loading.webp")

    async def test_reduced_motion_flags_remain_static_and_keep_no_task(self):
        for flag in ("disabled", "reduced"):
            with self.subTest(flag=flag):
                self.features.disabled = flag == "disabled"
                self.features.reduced = flag == "reduced"
                loader = self.loader()
                loader.did_mount()
                await self.settled()
                self.assert_static(loader)
                self.assertEqual(loader._motion_status, "reduced")
                count = self.features.calls
                loader.before_update()
                loader.before_update()
                self.assertEqual(self.features.calls, count)

    async def test_last_confirmed_reduced_motion_survives_unavailable_read(self):
        self.features.disabled = True
        loader = self.loader()
        loader.did_mount()
        await self.settled()
        branding.set_page_animations_active(loader.page, False)
        self.features.fail = True
        branding.set_page_animations_active(loader.page, True)
        await self.settled()
        self.assert_static(loader)
        self.assertEqual(loader._motion_status, "unavailable")
        self.assertTrue(branding._page_motion(loader.page).reduce_motion)

    async def test_hide_publishes_static_and_resume_rechecks_once(self):
        loader = self.loader()
        loader.did_mount()
        await self.settled()
        branding.set_page_animations_active(loader.page, False)
        self.assert_static(loader)
        self.assertEqual(loader.frames[-1], "branding/tokenlogue-loading-static.png")
        self.features.disabled = True
        branding.set_page_animations_active(loader.page, True)
        branding.set_page_animations_active(loader.page, True)
        await self.settled()
        self.assertEqual(len(self.page.tasks), 2)
        self.assert_static(loader)
        self.assertEqual(self.features.calls, 2)

    async def test_ancestor_hide_dialog_close_unmount_and_dispose_stop(self):
        for state in ("ancestor", "dialog", "unmount", "dispose", "inactive"):
            with self.subTest(state=state):
                loader = self.loader()
                parent = ft.AlertDialog(open=True) if state == "dialog" else ft.Column()
                loader._parent = weakref.ref(parent)
                loader.did_mount()
                await self.settled()
                if state == "ancestor":
                    parent.visible = False
                    loader.before_update()
                elif state == "dialog":
                    assert isinstance(parent, ft.AlertDialog)
                    parent.open = False
                    loader.before_update()
                elif state == "unmount":
                    loader.will_unmount()
                elif state == "dispose":
                    loader.dispose()
                else:
                    loader.set_active(False)
                self.assert_static(loader)

    async def test_pending_read_is_singleflight_and_late_reply_cannot_reanimate(self):
        for stop in ("hide", "unmount", "inactive", "dispose"):
            with self.subTest(stop=stop):
                started, release = asyncio.Event(), asyncio.Event()

                async def delayed_features():
                    started.set()
                    try:
                        await release.wait()
                    except asyncio.CancelledError:
                        await release.wait()
                    return SimpleNamespace(
                        disable_animations=False, reduce_motion=False
                    )

                branding.set_page_animations_active(cast(ft.Page, self.page), True)
                with patch.object(
                    self.features, "get_accessibility_features", delayed_features
                ):
                    loader = self.loader()
                    loader.did_mount()
                    await asyncio.wait_for(started.wait(), timeout=1)
                    task = loader._task
                    count = len(self.page.tasks)
                    for _ in range(3):
                        loader.before_update()
                        loader.set_active(True)
                    self.assertEqual(len(self.page.tasks), count)
                    self.assertIs(loader._task, task)
                    if stop == "hide":
                        branding.set_page_animations_active(loader.page, False)
                    elif stop == "unmount":
                        loader.will_unmount()
                    elif stop == "inactive":
                        loader.set_active(False)
                    else:
                        loader.dispose()
                    release.set()
                    await asyncio.wait_for(
                        asyncio.gather(*self.page.tasks, return_exceptions=True),
                        timeout=1,
                    )
                    self.assert_static(loader)
                    self.assertNotIn("branding/tokenlogue-loading.webp", loader.frames)
                    loader.dispose()

    async def test_multiple_loaders_have_independent_visibility_without_duplicate_tasks(
        self,
    ):
        first, second = self.loader(size=26), self.loader(size=56)
        first.did_mount()
        second.did_mount()
        await self.settled()
        first.set_active(False)
        self.assert_static(first)
        self.assertEqual(second._logo.src, "branding/tokenlogue-loading.webp")
        second.before_update()
        self.assertEqual(len(self.page.tasks), 2)
        first.set_active(True)
        await self.settled()
        self.assertEqual(len(self.page.tasks), 3)

    async def test_first_show_starts_loader_mounted_before_page_became_visible(self):
        self.page.app_visible = False
        loader = self.loader()
        loader.did_mount()
        self.assertEqual(self.page.tasks, [])
        self.page.app_visible = True
        branding.set_page_animations_active(loader.page, True)
        await self.settled()
        self.assertEqual(loader._logo.src, "branding/tokenlogue-loading.webp")
        branding.set_page_animations_active(loader.page, True)
        self.assertEqual(len(self.page.tasks), 1)

    async def test_new_loader_in_hidden_page_never_starts(self):
        branding.set_page_animations_active(cast(ft.Page, self.page), False)
        loader = self.loader()
        loader.did_mount()
        self.assertEqual(self.page.tasks, [])
        self.assert_static(loader)
        branding.set_page_animations_active(cast(ft.Page, self.page), True)
        await self.settled()
        self.assertEqual(len(self.page.tasks), 1)


class BrandingResourceTests(unittest.TestCase):
    assets = Path(__file__).resolve().parents[1] / "src/assets/branding"

    def test_supplied_asset_bytes_are_preserved(self):
        expected = {
            "tokenlogue-logo-transparent.png": "ffb489a8459949f9b76d7742f195f309df75f79d690ebcdcbd5717ebc5d2d4af",
            "tokenlogue-loading-static.png": "b1401c2830521746acb991db736cc23f48b8e97c46c54ecf8b3dd5f46f8e5fe2",
            "tokenlogue-loading.webp": "8f17b4c7251f48030a072a93b1eb38cec16605df3ff91803589a92976854f646",
        }
        for name, checksum in expected.items():
            with self.subTest(name=name):
                self.assertEqual(
                    hashlib.sha256((self.assets / name).read_bytes()).hexdigest(),
                    checksum,
                )

    def test_static_logos_have_real_transparency_and_colored_soft_edges(self):
        for name, size in (
            ("tokenlogue-logo-transparent.png", 1024),
            ("tokenlogue-loading-static.png", 256),
        ):
            with self.subTest(name=name):
                image = _read_rgba8_png(self.assets / name)
                self.assertEqual((image.width, image.height), (size, size))
                alpha = image.rgba[3::4]
                self.assertGreater(alpha.count(0), size * size // 2)
                self.assertGreater(sum(0 < value < 255 for value in alpha), 100)
                self.assertTrue(
                    all(value == 0 for value in alpha[:size] + alpha[-size:])
                )
                self.assertTrue(
                    all(
                        alpha[row * size] == alpha[(row + 1) * size - 1] == 0
                        for row in range(size)
                    )
                )
                for index, value in enumerate(alpha):
                    if 0 < value < 255:
                        self.assertNotIn(
                            image.rgba[4 * index : 4 * index + 3],
                            (b"\0\0\0", b"\xff\xff\xff"),
                        )

    def test_webp_contains_transparent_infinite_72_frame_cycle_around_2_4_seconds(self):
        data = (self.assets / "tokenlogue-loading.webp").read_bytes()
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(data[8:12], b"WEBP")
        self.assertEqual(struct.unpack_from("<I", data, 4)[0] + 8, len(data))
        chunks = []
        cursor = 12
        while cursor < len(data):
            length = struct.unpack_from("<I", data, cursor + 4)[0]
            payload = data[cursor + 8 : cursor + 8 + length]
            self.assertEqual(len(payload), length)
            chunks.append((data[cursor : cursor + 4], payload))
            cursor += 8 + length + length % 2
        self.assertEqual(cursor, len(data))
        extended = next(value for kind, value in chunks if kind == b"VP8X")
        self.assertTrue(extended[0] & 0x10)
        self.assertTrue(extended[0] & 0x02)
        self.assertEqual(
            (
                int.from_bytes(extended[4:7], "little") + 1,
                int.from_bytes(extended[7:10], "little") + 1,
            ),
            (256, 256),
        )
        animation = next(value for kind, value in chunks if kind == b"ANIM")
        self.assertEqual(int.from_bytes(animation[4:6], "little"), 0)
        frames = [value for kind, value in chunks if kind == b"ANMF"]
        self.assertEqual(len(frames), 72)
        self.assertEqual(
            sum(int.from_bytes(frame[12:15], "little") for frame in frames), 2399
        )
        self.assertGreater(len({frame[16:] for frame in frames}), 60)


if __name__ == "__main__":
    unittest.main()
