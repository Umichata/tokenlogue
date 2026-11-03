"""Metadata refresh is bounded, session fenced and separate from editor input."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import patch

import flet as ft
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.models import ModelCatalogClient, ModelCatalogService  # noqa: E402
from api.openrouter import (  # noqa: E402
    KeyValidationResult,
    KeyValidationStatus,
    OpenRouterClient,
)
from auth.contracts import KeyValidator  # noqa: E402
from auth.models import KeyLimitInfo, KeyLimitState, KeyValidityState  # noqa: E402
from chat.accounting import ChatBudgetService  # noqa: E402
from chat.drafts import ChatDraftService  # noqa: E402
from chat.metrics import (  # noqa: E402
    ChatMetricsSnapshot,
    LastRequestMetrics,
    LastRequestState,
)
from chat.models import CatalogModel, ChatMode  # noqa: E402
from chat.sending import MessageSendingService  # noqa: E402
from chat.service import ChatService  # noqa: E402
from chat_controller import ChatSessionController  # noqa: E402
from tests.draft_fakes import MemoryDraftRepository  # noqa: E402
from tests.test_chat_controller import (  # noqa: E402
    BlockingKeyValidator,
    FakeBudgetService,
    FakeChatService,
    FakeKeyValidator,
    FakePage,
)
from tests.test_live_estimates import _budget, _chat, _model  # noqa: E402


class ControlledCatalogClient:
    def __init__(
        self, *, blocked: bool = False, ignore_cancellation: bool = False
    ) -> None:
        self.calls = 0
        self.models = (_model(),)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.ignore_cancellation = ignore_cancellation
        if not blocked:
            self.release.set()

    async def fetch_models(self, _api_key: str) -> tuple[CatalogModel, ...]:
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            if not self.ignore_cancellation:
                raise
            await self.release.wait()
        return self.models


class CatalogCacheFenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_peek_is_read_only_and_respects_expiry(self) -> None:
        clock = [100.0]
        client = ControlledCatalogClient()
        service = ModelCatalogService(
            cast(ModelCatalogClient, client), ttl_seconds=30, clock=lambda: clock[0]
        )
        self.assertIsNone(service.peek_catalog())
        self.assertEqual(client.calls, 0)
        loaded = await service.get_catalog("public synthetic first")
        self.assertIs(service.peek_catalog(), loaded)
        self.assertEqual(client.calls, 1)
        clock[0] = 130.0
        self.assertIsNone(service.peek_catalog())
        self.assertEqual(client.calls, 1)
        refreshed = await service.get_catalog("public synthetic first")
        self.assertIs(service.peek_catalog(), refreshed)
        self.assertEqual(client.calls, 2)

    async def test_clear_cache_fences_old_inflight_result_and_queued_old_waiter(
        self,
    ) -> None:
        client = ControlledCatalogClient(blocked=True)
        service = ModelCatalogService(cast(ModelCatalogClient, client))
        old = asyncio.create_task(service.get_catalog("public synthetic old"))
        await asyncio.wait_for(client.started.wait(), 1)
        queued_old = asyncio.create_task(service.get_catalog("public synthetic old"))
        await asyncio.sleep(0)
        service.clear_cache()
        self.assertIsNone(service.peek_catalog())
        fresh = asyncio.create_task(service.get_catalog("public synthetic new"))
        client.release.set()
        old_result, queued_result, new_result = await asyncio.gather(
            old, queued_old, fresh
        )
        self.assertFalse(old_result.available)
        self.assertFalse(queued_result.available)
        self.assertTrue(new_result.available)
        self.assertIs(service.peek_catalog(), new_result)
        self.assertEqual(client.calls, 2)

    async def test_concurrent_gets_are_single_flight_without_storing_a_key(
        self,
    ) -> None:
        client = ControlledCatalogClient(blocked=True)
        service = ModelCatalogService(cast(ModelCatalogClient, client))
        tasks = [
            asyncio.create_task(service.get_catalog("public synthetic shared"))
            for _ in range(20)
        ]
        await asyncio.wait_for(client.started.wait(), 1)
        client.release.set()
        results = await asyncio.gather(*tasks)
        self.assertEqual(client.calls, 1)
        self.assertTrue(all(item is results[0] for item in results))
        self.assertNotIn("public synthetic shared", repr(vars(service)))


class ControllerEstimateMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.page = FakePage()
        self.budgets = FakeBudgetService()
        self.budgets.budgets["chat"] = _budget()
        self.chats = FakeChatService([_chat(_model(), ChatMode.PAID)], self.budgets)
        self.client = ControlledCatalogClient()
        self.catalogs = ModelCatalogService(cast(ModelCatalogClient, self.client))
        self.validator = FakeKeyValidator(
            KeyValidationResult(KeyValidationStatus.ACCEPTED, Decimal("5"))
        )
        self.drafts = ChatDraftService(MemoryDraftRepository())
        self.controller = self.make_controller()
        self.addCleanup(self.controller.dispose)

    def make_controller(self) -> ChatSessionController:
        async def noop() -> None:
            return None

        return ChatSessionController(
            cast(ft.Page, self.page),
            cast(KeyValidator, self.validator),
            cast(ChatService, self.chats),
            self.catalogs,
            cast(ChatBudgetService, self.budgets),
            cast(MessageSendingService, object()),
            self.drafts,
            on_lock=noop,
            on_replace_key=noop,
            on_storage_error=lambda _message: self.fail("unexpected storage error"),
        )

    async def activate(self) -> None:
        await self.controller.activate(
            "public synthetic session",
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(Decimal("5")),
        )

    async def wait_metadata(self) -> None:
        task = self.controller._estimate_metadata_task
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), 1)

    async def wait_key_metrics(self, limit: KeyLimitInfo) -> ChatMetricsSnapshot:
        async def wait_for_snapshot() -> ChatMetricsSnapshot:
            while True:
                view = self.controller._workspace_view
                if view is not None and view.metrics_strip is not None:
                    snapshot = view.metrics_strip._snapshot
                    if snapshot is not None and snapshot.key_limit == limit:
                        return snapshot
                await asyncio.sleep(0)

        return await asyncio.wait_for(wait_for_snapshot(), 1)

    async def test_activation_refreshes_only_metadata_and_typing_never_fetches(
        self,
    ) -> None:
        self.client.release.clear()
        await self.activate()
        view = self.controller._workspace_view
        assert view is not None and view.composer is not None
        composer = view.composer
        await asyncio.wait_for(self.client.started.wait(), 1)
        self.assertIsNone(self.controller._key_metadata_updated_at)
        self.assertEqual(self.validator.calls, 0)
        for text in ("a", "ab", "a", "public paste🙂", "", "new draft"):
            await self.controller._workspace_controller.update_draft("chat", text)
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(self.validator.calls, 0)
        self.client.release.set()
        await self.wait_metadata()
        self.assertIs(self.controller._workspace_view, view)
        self.assertIs(view.composer, composer)
        self.assertEqual(self.drafts.current("chat").text, "new draft")
        for _ in range(20):
            await self.controller._refresh_workspace_from_interaction(False)
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(self.validator.calls, 0)

    async def test_receipt_timestamp_is_not_inherited_from_cached_auth_state(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        self.assertIsNone(self.controller._key_metadata_updated_at)
        await self.controller.request_key_revalidation()
        task = self.controller._key_validation_task
        if task is not None:
            await task
        receipt = self.controller._key_metadata_updated_at
        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertIsNotNone(receipt.tzinfo)
        self.assertLess(abs((datetime.now(UTC) - receipt).total_seconds()), 5)
        self.controller.deactivate()
        self.assertIsNone(self.controller._key_metadata_updated_at)
        self.assertIsNone(self.catalogs.peek_catalog())

    async def test_explicit_refresh_routes_parsed_key_states_and_receipt_to_workspace(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        paths: list[str] = []
        response_body = b""

        def handle(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            self.assertEqual(str(request.url), "https://openrouter.ai/api/v1/key")
            paths.append(request.url.path)
            return httpx.Response(200, content=response_body)

        self.controller._key_validator = OpenRouterClient(
            transport=httpx.MockTransport(handle)
        )
        cases = (
            (b"7.12", KeyLimitState.AVAILABLE, Decimal("7.12")),
            (b"0", KeyLimitState.EXHAUSTED, Decimal("0")),
            (b"-0.01", KeyLimitState.EXHAUSTED, Decimal("-0.01")),
            (b"null", KeyLimitState.NOT_SET, None),
            (b"true", KeyLimitState.UNKNOWN, None),
        )
        for index, (raw, expected_state, expected_remaining) in enumerate(cases):
            with self.subTest(state=expected_state):
                response_body = b'{"data":{"limit_remaining":' + raw + b"}}"
                receipt = datetime(2026, 11, 1, 0, 0, index, tzinfo=UTC)
                with patch("chat_controller.datetime") as clock:
                    clock.now.return_value = receipt
                    await self.controller.request_key_revalidation()
                    task = self.controller._key_validation_task
                    if task is not None:
                        await asyncio.wait_for(task, 1)
                    snapshot = await self.wait_key_metrics(
                        KeyLimitInfo(expected_state, expected_remaining)
                    )
                view = self.controller._workspace_view
                assert view is not None and view.metrics_strip is not None
                self.assertEqual(snapshot.key_limit.state, expected_state)
                self.assertEqual(snapshot.key_limit.remaining, expected_remaining)
                self.assertEqual(snapshot.remaining.cost_usd, Decimal("1"))
                self.assertIsNone(snapshot.account_balance_usd)
                expected_time = (
                    None if expected_state is KeyLimitState.UNKNOWN else receipt
                )
                self.assertEqual(snapshot.metadata_updated_at, expected_time)
                self.controller.handle_language_change()
                self.assertIs(view.metrics_strip._snapshot, snapshot)
                self.assertEqual(len(paths), index + 1)
        self.assertEqual(paths, ["/api/v1/key"] * len(cases))
        self.assertTrue(self.controller.session_active)
        self.assertEqual(self.chats.chats[0].id, "chat")

    async def test_old_key_validation_cannot_replace_new_workspace_limit_or_time(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        old_validator = BlockingKeyValidator(
            KeyValidationResult(KeyValidationStatus.ACCEPTED, Decimal("41")),
            ignore_cancellation=True,
        )
        self.controller._key_validator = cast(KeyValidator, old_validator)
        await self.controller.request_key_revalidation()
        await asyncio.wait_for(old_validator.started.wait(), 1)
        old_task = self.controller._key_validation_task
        assert old_task is not None

        self.controller.deactivate()
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED, Decimal("11")
        )
        self.controller._key_validator = cast(KeyValidator, self.validator)
        await self.controller.activate(
            "public synthetic replacement",
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(Decimal("9")),
        )
        await self.wait_metadata()
        await self.controller.request_key_revalidation()
        task = self.controller._key_validation_task
        if task is not None:
            await asyncio.wait_for(task, 1)
        snapshot = await self.wait_key_metrics(
            KeyLimitInfo.from_validated_remaining(Decimal("11"))
        )
        view = self.controller._workspace_view
        assert view is not None and view.metrics_strip is not None
        self.assertEqual(snapshot.key_limit.remaining, Decimal("11"))
        self.assertIsNotNone(snapshot.metadata_updated_at)

        old_validator.release.set()
        await asyncio.wait_for(asyncio.shield(old_task), 1)
        self.assertIs(self.controller._workspace_view, view)
        self.assertIs(view.metrics_strip._snapshot, snapshot)
        self.assertEqual(self.controller.key_limit.remaining, Decimal("11"))
        self.assertIs(
            self.controller._key_metadata_updated_at, snapshot.metadata_updated_at
        )

    async def test_interaction_echo_or_delayed_result_does_not_invent_receipt_time(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        limit = self.controller.key_limit
        self.controller._apply_interaction_key_state(KeyValidityState.VALID, limit)
        self.assertIsNone(self.controller._key_metadata_updated_at)
        old_time = datetime(2026, 10, 31, tzinfo=UTC)
        self.controller._key_metadata_updated_at = old_time
        self.controller._apply_interaction_key_state(KeyValidityState.VALID, limit)
        self.assertIs(self.controller._key_metadata_updated_at, old_time)
        self.controller._apply_interaction_key_state(
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(Decimal("3")),
        )
        self.assertIsNone(self.controller._key_metadata_updated_at)
        self.assertEqual(self.controller.key_limit.remaining, Decimal("3"))
        self.assertEqual(self.validator.calls, 0)

    async def test_background_metadata_errors_keep_working_key_and_stale_time(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        timestamp = datetime(2026, 10, 31, tzinfo=UTC)
        self.controller._key_metadata_updated_at = timestamp
        previous_limit = self.controller.key_limit
        view = self.controller._workspace_view
        assert view is not None and view.composer is not None
        composer = view.composer
        for status in (
            KeyValidationStatus.RESTRICTED,
            KeyValidationStatus.RATE_LIMITED,
            KeyValidationStatus.NETWORK_ERROR,
            KeyValidationStatus.TIMEOUT,
        ):
            self.validator.result = KeyValidationResult(status)
            self.assertTrue(self.controller._start_key_validation(metadata_only=True))
            self.assertFalse(self.controller.key_validation_in_progress)
            task = self.controller._key_validation_task
            assert task is not None
            await task
            self.assertEqual(self.controller.key_validity, KeyValidityState.VALID)
            self.assertEqual(self.controller.key_limit, previous_limit)
            self.assertIs(self.controller._key_metadata_updated_at, timestamp)
            self.assertIs(self.controller._workspace_view, view)
            self.assertIs(view.composer, composer)
            self.assertEqual(self.client.calls, 1)
            assert view.metrics_strip is not None
            snapshot = view.metrics_strip._snapshot
            assert snapshot is not None
            self.assertEqual(snapshot.key_limit, previous_limit)
            self.assertIs(snapshot.metadata_updated_at, timestamp)
            self.assertIsNone(snapshot.account_balance_usd)

    async def test_metadata_null_limit_remains_not_set_instead_of_account_balance(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        self.validator.result = KeyValidationResult(
            KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT
        )
        self.controller._start_key_validation(metadata_only=True)
        task = self.controller._key_validation_task
        assert task is not None
        await task
        self.assertEqual(self.controller.key_validity, KeyValidityState.VALID)
        self.assertIsNone(self.controller.key_limit.remaining)
        self.assertIsNotNone(self.controller._key_metadata_updated_at)
        self.assertEqual(self.client.calls, 1)

    async def test_expiry_during_continuous_typing_only_invalidates_without_http(
        self,
    ) -> None:
        clock = [100.0]
        self.catalogs._clock = lambda: clock[0]
        await self.activate()
        await self.wait_metadata()
        workspace = self.controller._workspace_controller
        self.assertIsNotNone(workspace._estimate_model)
        handle = self.controller._estimate_metadata_expiry
        assert handle is not None
        handle.cancel()
        previous_limit = self.controller.key_limit
        previous_validity = self.controller.key_validity
        clock[0] += 301
        self.controller._expire_estimate_metadata(
            self.controller.session_generation,
            self.controller._estimate_metadata_request,
        )
        self.assertIsNone(workspace._estimate_model)
        for index in range(100):
            await workspace.update_draft("chat", "public synthetic text " + "x" * index)
        await asyncio.sleep(0)
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(self.validator.calls, 0)
        self.assertEqual(self.controller.key_limit, previous_limit)
        self.assertEqual(self.controller.key_validity, previous_validity)
        self.assertIsNone(self.controller._estimate_metadata_task)
        self.assertIsNone(self.controller._estimate_metadata_expiry)

    async def test_old_ignored_cancellation_cannot_repopulate_new_key_metadata(
        self,
    ) -> None:
        self.client.release.clear()
        self.client.ignore_cancellation = True
        await self.activate()
        await asyncio.wait_for(self.client.started.wait(), 1)
        old_task = self.controller._estimate_metadata_task
        self.controller.deactivate()
        self.assertIsNone(self.catalogs.peek_catalog())
        await self.controller.activate(
            "public synthetic replacement",
            KeyValidityState.VALID,
            KeyLimitInfo.from_validated_remaining(Decimal("9")),
        )
        view = self.controller._workspace_view
        self.client.release.set()
        if old_task is not None:
            await asyncio.wait_for(asyncio.shield(old_task), 1)
        await self.wait_metadata()
        self.assertIs(self.controller._workspace_view, view)
        self.assertEqual(self.controller.key_limit.remaining, Decimal("9"))
        self.assertEqual(self.client.calls, 2)
        self.assertIsNotNone(self.catalogs.peek_catalog())

    async def test_deactivation_cancels_refresh_and_clears_model_cache(self) -> None:
        self.client.release.clear()
        await self.activate()
        await asyncio.wait_for(self.client.started.wait(), 1)
        task = self.controller._estimate_metadata_task
        self.controller.deactivate()
        self.assertIsNone(self.controller._estimate_metadata_task)
        self.assertIsNone(self.catalogs.peek_catalog())
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), 1)
        self.assertIsNone(self.controller._workspace_view)

    async def test_only_completed_attempt_refreshes_and_cooldown_has_one_task(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        state = self.controller._workspace_state
        assert state is not None
        sent_at = datetime.now(UTC)
        pending = replace(
            state,
            sending=True,
            last_request=LastRequestMetrics(
                LastRequestState.PENDING, turn_id="public turn", sent_at=sent_at
            ),
        )
        self.controller._set_workspace_state(pending)
        self.assertEqual(self.client.calls, 1)
        self.assertIsNone(self.controller._estimate_metadata_task)
        self.assertIsNotNone(self.catalogs.peek_catalog())
        completed = replace(
            pending,
            sending=False,
            last_request=replace(
                pending.last_request,
                state=LastRequestState.FINAL,
                cost_usd=Decimal("0.01"),
                total_tokens=12,
            ),
        )
        self.controller._set_workspace_state(completed)
        queued = self.controller._estimate_metadata_task
        self.assertIsNotNone(queued)
        self.assertIsNone(self.catalogs.peek_catalog())
        for _ in range(50):
            self.controller._set_workspace_state(completed)
            self.controller._start_estimate_metadata_refresh()
        await asyncio.sleep(0)
        self.assertIs(self.controller._estimate_metadata_task, queued)
        self.assertEqual(self.client.calls, 1)
        self.assertEqual(self.validator.calls, 0)
        self.controller.deactivate()
        if queued is not None:
            await asyncio.wait_for(asyncio.shield(queued), 1)

    async def test_pre_http_rollback_does_not_refresh_but_equal_time_retry_does(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        state = self.controller._workspace_state
        assert state is not None
        timestamp = datetime.now(UTC)
        completed = replace(
            state,
            last_request=LastRequestMetrics(
                LastRequestState.FINAL,
                turn_id="public old turn",
                sent_at=timestamp,
                attempt_sequence=1,
            ),
        )
        self.controller._observed_attempt = None
        self.controller._set_workspace_state(completed)
        pending = replace(
            completed,
            sending=True,
            last_request=LastRequestMetrics(
                LastRequestState.PENDING,
                turn_id="public new turn",
                sent_at=timestamp,
                attempt_sequence=2,
            ),
        )
        self.controller._set_workspace_state(pending)
        self.controller._set_workspace_state(completed)
        self.assertIsNone(self.controller._estimate_metadata_task)
        self.assertIsNotNone(self.catalogs.peek_catalog())
        self.assertEqual(self.client.calls, 1)
        retry = replace(
            completed,
            sending=True,
            last_request=replace(
                completed.last_request,
                state=LastRequestState.PENDING,
                attempt_sequence=3,
            ),
        )
        self.controller._set_workspace_state(retry)
        self.controller._set_workspace_state(
            replace(
                retry,
                sending=False,
                last_request=replace(retry.last_request, state=LastRequestState.FINAL),
            )
        )
        self.assertIsNotNone(self.controller._estimate_metadata_task)
        self.assertIsNone(self.catalogs.peek_catalog())
        self.assertEqual(self.client.calls, 1)

    async def test_completion_refreshes_catalog_and_key_once_when_cooldown_elapsed(
        self,
    ) -> None:
        await self.activate()
        await self.wait_metadata()
        state = self.controller._workspace_state
        assert state is not None
        self.controller._estimate_metadata_after = 0
        completed = replace(
            state,
            last_request=LastRequestMetrics(
                LastRequestState.UNKNOWN,
                turn_id="public sent",
                sent_at=datetime.now(UTC),
            ),
        )
        self.controller._set_workspace_state(completed)
        await self.wait_metadata()
        key_task = self.controller._key_validation_task
        if key_task is not None:
            await key_task
        self.assertEqual(self.client.calls, 2)
        self.assertEqual(self.validator.calls, 1)
        self.assertIsNotNone(self.controller._key_metadata_updated_at)


class SynchronousMetadataCleanupTests(unittest.TestCase):
    def test_finished_task_cleanup_does_not_require_a_running_loop(self) -> None:
        async def finished() -> None:
            return None

        loop = asyncio.new_event_loop()
        task = loop.create_task(finished())
        loop.run_until_complete(task)
        loop.close()
        controller = object.__new__(ChatSessionController)
        controller._estimate_metadata_request = 0
        controller._estimate_metadata_expiry = None
        controller._estimate_metadata_task = task
        controller._cancel_estimate_metadata()
        self.assertIsNone(controller._estimate_metadata_task)
        self.assertEqual(controller._estimate_metadata_request, 1)


if __name__ == "__main__":
    unittest.main()
