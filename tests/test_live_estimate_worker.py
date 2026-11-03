"""Per-edit responsiveness, bounded work and revocation without network effects."""

from __future__ import annotations

import asyncio
import sys
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chat.context import prepare_history  # noqa: E402
from chat.estimates import (  # noqa: E402
    DraftEstimate,
    EstimateState,
    estimate_draft,
)
from chat.live_estimate import EstimateRevision, LiveEstimateWorker  # noqa: E402
from chat.models import ChatMode  # noqa: E402
from tests import test_chat_ui_integration as fixtures  # noqa: E402
from tests.test_live_estimates import _snapshot  # noqa: E402


class LiveEstimateWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_busy_burst_keeps_one_pending_and_only_latest_result(self):
        started, release = threading.Event(), threading.Event()
        expired = threading.Event()
        calculated: list[int] = []
        published: list[tuple[EstimateRevision, DraftEstimate]] = []

        def calculate(snapshot, text):
            calculated.append(len(text))
            if len(calculated) == 1:
                started.set()
                if not release.wait(3):
                    expired.set()
                    raise TimeoutError("Тест не освободил вычисление оценки")
            return estimate_draft(snapshot, text)

        worker = LiveEstimateWorker(
            lambda _key: True,
            lambda k, r: published.append((k, r)),
            calculate=calculate,
        )
        self.addAsyncCleanup(worker.wait_idle)
        worker.submit(_revision(1), _snapshot(), "a")
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        try:
            for index in range(2, 1002):
                worker.submit(_revision(index), _snapshot(), "a" * index)
                self.assertEqual(worker.pending_count, 1)
            self.assertTrue(worker.running)
        finally:
            release.set()
        await asyncio.wait_for(worker.wait_idle(), 3)
        self.assertFalse(expired.is_set(), "Истёк барьер вычисления оценки")
        self.assertEqual(calculated, [1, 1001])
        self.assertEqual([key.draft for key, _ in published], [1001])
        self.assertEqual(worker.pending_count, 0)
        self.assertFalse(worker.running)

    async def test_invalidate_drops_private_pending_and_rejects_running_result(self):
        started, release = threading.Event(), threading.Event()
        expired = threading.Event()
        published = []

        def calculate(snapshot, text):
            started.set()
            if not release.wait(3):
                expired.set()
                raise TimeoutError("Тест не освободил вычисление оценки")
            return estimate_draft(snapshot, text)

        worker = LiveEstimateWorker(
            lambda _key: True,
            lambda k, r: published.append((k, r)),
            calculate=calculate,
        )
        worker.submit(_revision(1), _snapshot(), "synthetic first")
        self.assertTrue(await asyncio.to_thread(started.wait, 2))
        worker.submit(_revision(2), _snapshot(), "synthetic pending")
        worker.invalidate()
        self.assertEqual(worker.pending_count, 0)
        try:
            self.assertIsNone(worker._latest)
            self.assertIsNone(worker._pending)
        finally:
            release.set()
        await asyncio.wait_for(worker.wait_idle(), 3)
        self.assertFalse(expired.is_set(), "Истёк барьер вычисления оценки")
        self.assertEqual(published, [])

    async def test_every_origin_dimension_can_reject_a_late_result(self):
        for field, value in (
            ("session", 2),
            ("workspace", 2),
            ("view", 2),
            ("context", 2),
            ("chat_id", "other"),
            ("draft", 2),
        ):
            with self.subTest(field=field):
                current = replace(_revision(1), **{field: value})
                published = []
                worker = LiveEstimateWorker(
                    lambda key: key == current, lambda k, r: published.append((k, r))
                )
                worker.submit(_revision(1), _snapshot(), "synthetic")
                await worker.wait_idle()
                self.assertEqual(published, [])

    async def test_calculator_error_has_safe_unavailable_result_no_exception_text(self):
        def broken(_snapshot, _text):
            raise RuntimeError("synthetic private input must not be displayed")

        published = []
        worker = LiveEstimateWorker(
            lambda _key: True,
            lambda _k, result: published.append(result),
            calculate=broken,
        )
        worker.submit(_revision(1), _snapshot(), "synthetic")
        await worker.wait_idle()
        self.assertEqual(published, [DraftEstimate(EstimateState.UNAVAILABLE)])


class LiveEstimateWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = fixtures.ChatUiIntegrationTests()
        await self.fixture.asyncSetUp()
        self.addCleanup(self.fixture.temp_dir.cleanup)
        updates = patch.object(ft.Control, "update", return_value=None)
        updates.start()
        self.addCleanup(updates.stop)
        self.a = await self.fixture._create_chat(ChatMode.FREE)
        self.b = await self.fixture._create_chat(ChatMode.FREE)
        self.controller, self.client = self.fixture._controller([])
        self.addCleanup(self.controller.dispose)
        await self.fixture._activate(self.controller)
        await self.controller.select_chat(self.a)
        self.workspace = self.controller._workspace_controller
        await self.workspace.wait_estimate_idle()

    async def type_text(self, text):
        view = self.controller._workspace_view
        assert view is not None and view.composer is not None
        field = view.composer.message_field
        field.value = text
        await view.composer._handle_change(ft.Event(name="change", control=field))

    def view(self):
        view = self.controller._workspace_view
        assert view is not None and view.composer is not None
        return view

    async def test_each_edit_updates_while_sqlite_save_remains_blocked(self):
        view = self.view()
        composer = view.composer
        assert composer is not None
        field = composer.message_field
        selection = ft.TextSelection(base_offset=1, extent_offset=2)
        field.selection = selection
        started, release = threading.Event(), threading.Event()
        expired = threading.Event()
        original = self.fixture.draft_repository.save_draft

        def save(draft):
            started.set()
            if not release.wait(3):
                expired.set()
                raise TimeoutError("Тест не освободил запись черновика")
            return original(draft)

        delivered = []
        original_setter = view.set_estimate

        def publish(result):
            delivered.append(result)
            original_setter(result)

        tasks = []
        with (
            patch.object(self.fixture.draft_repository, "save_draft", save),
            patch.object(view, "set_estimate", publish),
        ):
            try:
                for text in (
                    "a",
                    "ab",
                    "a",
                    "replacement",
                    "paste\n🙂",
                    "Привет 👩🏽‍💻",
                    "paste\n🙂",
                    "",
                ):
                    task = asyncio.create_task(self.type_text(text))
                    tasks.append(task)
                    await asyncio.sleep(0)
                    await asyncio.wait_for(self.workspace.wait_estimate_idle(), 2)
                    self.assertTrue(delivered)
                    snapshot = self.workspace._estimate_snapshot
                    assert snapshot is not None
                    self.assertEqual(delivered[-1], estimate_draft(snapshot, text))
                    self.assertEqual(view.editor_value, text)
                    self.assertIs(self.view(), view)
                    self.assertIs(view.composer, composer)
                    self.assertIs(composer.message_field, field)
                    self.assertEqual(field.selection, selection)
                self.assertTrue(started.is_set())
                self.assertFalse(tasks[0].done())
                self.assertEqual(self.client.calls, 0)
                self.assertEqual(self.fixture.message_repository.list_turns(self.a), [])
            finally:
                release.set()
                await asyncio.gather(*tasks)
        self.assertFalse(expired.is_set(), "Истёк барьер записи черновика")

    async def test_limits_and_restored_draft_recalculate_without_new_typing(
        self,
    ):
        await self.type_text("same visible draft")
        await self.workspace.wait_estimate_idle()
        view = self.view()
        before = self.workspace._estimate_snapshot
        assert before is not None
        values = []
        with patch.object(view, "set_estimate", lambda value: values.append(value)):
            await self.controller.request_edit_limits(self.a)
            await self.controller.submit_existing_chat_limits("16384", "64", None)
            await self.workspace.wait_estimate_idle()
        self.assertTrue(values)
        self.assertEqual(values[-1].max_completion_tokens, 64)
        self.assertEqual(view.editor_value, "same visible draft")
        await self.controller.select_chat(self.b)
        await self.type_text("second chat")
        await self.controller.select_chat(self.a)
        await self.workspace.wait_estimate_idle()
        current = self.workspace._estimate_snapshot
        assert current is not None
        self.assertEqual(current.chat.id, self.a)
        self.assertEqual(self.view().editor_value, "same visible draft")

    async def test_lock_clears_estimate_cache_and_old_worker_cannot_publish(self):
        view = self.view()
        started, release = threading.Event(), threading.Event()
        expired = threading.Event()
        publications = []

        def calculate(snapshot, text):
            started.set()
            if not release.wait(3):
                expired.set()
                raise TimeoutError("Тест не освободил вычисление оценки")
            return estimate_draft(snapshot, text)

        self.workspace._estimate_worker._calculate = calculate
        with patch.object(
            view, "set_estimate", lambda value: publications.append(value)
        ):
            task = asyncio.create_task(self.type_text("synthetic lock draft"))
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            self.controller.begin_lock()
            self.assertIsNone(self.workspace._estimate_snapshot)
            self.assertIsNone(self.workspace._estimate_history)
            self.assertIsNone(self.workspace._estimate_history_messages)
            self.assertEqual(self.workspace._estimate_worker.pending_count, 0)
            release.set()
            await task
            await self.workspace.wait_estimate_idle()
        self.assertFalse(expired.is_set(), "Истёк барьер вычисления оценки")
        self.assertEqual(publications, [])
        self.assertEqual(self.client.calls, 0)

    async def test_history_preparation_is_cached_across_typing(self):
        with patch(
            "chat_workspace_controller.prepare_history", wraps=prepare_history
        ) as prepare:
            for index in range(40):
                await self.type_text("synthetic " + str(index))
            await self.workspace.wait_estimate_idle()
        self.assertEqual(prepare.call_count, 0)
        self.assertEqual(self.client.calls, 0)

    async def test_typing_does_not_enter_any_financial_or_remote_path(self):
        repository = self.fixture.message_repository
        before = repository.get_chat_budget(self.a)
        sending = self.controller._interaction._sending_service
        with (
            patch.object(sending, "_preflight", wraps=sending._preflight) as preflight,
            patch.object(
                repository, "reserve_turn", wraps=repository.reserve_turn
            ) as reserve,
            patch.object(
                repository,
                "update_price_snapshot",
                wraps=repository.update_price_snapshot,
            ) as price,
            patch.object(
                self.fixture.chat_service,
                "paid_consent",
                wraps=self.fixture.chat_service.paid_consent,
            ) as consent,
            patch.object(
                repository, "get_chat_budget", wraps=repository.get_chat_budget
            ) as budget_reads,
            patch.object(
                self.fixture.chat_repository,
                "list_messages",
                wraps=self.fixture.chat_repository.list_messages,
            ) as history_reads,
        ):
            for index in range(60):
                await self.type_text("synthetic no-send " + str(index))
            await self.workspace.wait_estimate_idle()
        for spy in (preflight, reserve, price, consent, budget_reads, history_reads):
            self.assertEqual(spy.call_count, 0)
        self.assertEqual(self.client.calls, 0)
        self.assertEqual(repository.get_chat_budget(self.a), before)
        self.assertEqual(repository.list_turns(self.a), [])

    async def test_new_cached_price_recalculates_without_an_edit(self):
        paid = await self.fixture._create_chat(ChatMode.PAID)
        await self.controller.select_chat(paid)
        metadata_task = self.controller._estimate_metadata_task
        if metadata_task is not None:
            await metadata_task
        self.workspace.set_estimate_metadata(
            self.fixture.paid_model, self.controller.key_limit, None
        )
        await self.type_text("synthetic same text")
        await self.workspace.wait_estimate_idle()
        old = self.workspace._estimate_snapshot
        assert old is not None
        expected_before = estimate_draft(old, self.view().editor_value)
        changed = replace(
            self.fixture.paid_model,
            prompt_price_per_token=self.fixture.paid_model.prompt_price_per_token * 2,
        )
        delivered = []
        view = self.view()
        with patch.object(
            view, "set_estimate", lambda result: delivered.append(result)
        ):
            self.workspace.set_estimate_metadata(
                changed, self.controller.key_limit, None
            )
            await self.workspace.wait_estimate_idle()
        self.assertTrue(delivered)
        self.assertEqual(view.editor_value, "synthetic same text")
        self.assertIsNotNone(expected_before.cost_upper_usd)
        self.assertIsNotNone(delivered[-1].cost_upper_usd)
        assert expected_before.cost_upper_usd is not None
        self.assertGreater(delivered[-1].cost_upper_usd, expected_before.cost_upper_usd)

    async def test_completed_history_enters_next_estimate_without_repository_reads(
        self,
    ):
        self.client.results.append(fixtures._success("synthetic reply"))
        await self.controller.submit_message("synthetic first question")
        await self.workspace.wait_estimate_idle()
        snapshot = self.workspace._estimate_snapshot
        assert snapshot is not None
        self.assertGreater(snapshot.history.estimated_tokens, 0)
        with patch.object(
            self.fixture.chat_repository,
            "list_messages",
            wraps=self.fixture.chat_repository.list_messages,
        ) as reads:
            await self.type_text("next")
            await self.workspace.wait_estimate_idle()
        current = self.workspace._estimate_snapshot
        assert current is not None
        self.assertEqual(current.history, snapshot.history)
        tokens = estimate_draft(current, "next").prompt_tokens
        assert tokens is not None
        self.assertGreater(tokens, 44)
        self.assertEqual(reads.call_count, 0)
        self.assertEqual(self.client.calls, 1)


def _revision(draft):
    return EstimateRevision(1, 1, 1, 1, "chat", draft)
