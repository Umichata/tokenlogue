"""Independent device results and an explicit sleep action use real UI boundaries."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from i18n import configure_localization, set_language, tr  # noqa: E402
from platform_security.local_protection import (  # noqa: E402
    SCREEN_CONTRACT,
    SLEEP_CONTRACT,
    AppLockState,
    CheckResult,
    CheckState,
    DeviceCheckRecord,
    DeviceProtectionHistory,
    LocalProtectionChecks,
    ObserverContext,
    ProtectionSnapshot,
)
from preferences import PreferencesStore  # noqa: E402
from storage.draft_repository import SqliteDraftRepository  # noqa: E402
from tests import test_app as generic_app_fixtures  # noqa: E402
from tests import test_chat_menu as menu_fixtures  # noqa: E402
from tests import test_linux_parity as app_fixtures  # noqa: E402
from ui.security_status import mechanism_label  # noqa: E402
from ui.styles import WARNING_COLOR  # noqa: E402


def confirmed_snapshot() -> ProtectionSnapshot:
    return ProtectionSnapshot(
        CheckResult(CheckState.CONFIRMED, "screen_confirmed"),
        CheckResult(CheckState.CONFIRMED, "sleep_confirmed"),
        True,
        True,
        False,
        screen_history=DeviceCheckRecord(
            CheckState.CONFIRMED, 1735689600, 1735689600, SCREEN_CONTRACT
        ),
        sleep_history=DeviceCheckRecord(
            CheckState.CONFIRMED, 1735689660, 1735689660, SLEEP_CONTRACT
        ),
    )


class DeviceProtectionMenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fx = menu_fixtures.ChatMenuTests()
        self.fx.setUp()
        self.addCleanup(configure_localization, PreferencesStore())

    def view(self, **kwargs):
        view = self.fx.view(**kwargs)
        self.addCleanup(view.dispose)
        return view

    async def test_empty_workspace_has_explanation_then_sleep_button_without_auto_request(
        self,
    ):
        sleep = AsyncMock()
        view = self.view(
            protection_status=ProtectionSnapshot(
                CheckResult(), CheckResult(), False, True, False
            ),
            on_test_screen_lock=AsyncMock(),
            on_test_sleep=sleep,
        )
        view.update_workspace(
            [],
            None,
            None,
            key_validity=view._key_validity,
            key_limit=view._key_limit,
            key_validation_in_progress=False,
        )
        for language in ("en", "ru"):
            set_language(language)
            await view.open_protection()
            view.refresh_menu_language()
            button = view.sleep_test_button
            assert button is not None
            self.assertFalse(button.disabled)
            assert view.protection_panel.content is not None
            displayed = menu_fixtures.texts(view.protection_panel.content)
            self.assertLess(
                displayed.index(tr("local_protection.sleep_test_explanation")),
                displayed.index(tr("local_protection.test_sleep")),
            )
            sleep.assert_not_awaited()
            view.protection_panel.close()
        await view.open_protection()
        assert view.sleep_test_button is not None
        await self.fx.click(view.sleep_test_button)
        sleep.assert_awaited_once()
        self.assertFalse(view.protection_open)

    async def test_either_active_trial_disables_both_buttons(self):
        for mechanism in ("screen", "sleep"):
            snapshot = replace(
                confirmed_snapshot(),
                screen_test_running=mechanism == "screen",
                sleep_test_running=mechanism == "sleep",
            )
            view = self.view(
                protection_status=snapshot,
                on_test_screen_lock=AsyncMock(),
                on_test_sleep=AsyncMock(),
            )
            await view.open_protection()
            assert view.screen_test_button is not None
            assert view.sleep_test_button is not None
            self.assertTrue(view.screen_test_button.disabled)
            self.assertTrue(view.sleep_test_button.disabled)

    async def test_real_model_restored_history_does_not_invent_attempt_during_attach_or_reconnect(
        self,
    ):
        snapshot = confirmed_snapshot()
        checks = LocalProtectionChecks(
            lambda: AppLockState(7, True, True, False), lambda: None
        )
        self.addAsyncCleanup(checks.aclose)
        checks.set_history(DeviceProtectionHistory(screen=snapshot.screen_history))
        first = ObserverContext("linux", "synthetic-desktop", 1, "synthetic-owner")
        second = ObserverContext("linux", "synthetic-desktop", 2, "synthetic-new-owner")
        checks.update_observers(first, first)
        view = self.view(protection_status=checks.snapshot, on_test_sleep=AsyncMock())
        await view.open_protection()
        for context in (first, None, second):
            checks.update_observers(context, context)
            for language in ("en", "ru"):
                set_language(language)
                view.set_protection_status(checks.snapshot)
                assert view.protection_panel.content is not None
                displayed = menu_fixtures.texts(view.protection_panel.content)
                self.assertIn(
                    mechanism_label("screen", checks.snapshot.screen), displayed
                )
                self.assertNotIn(tr("local_protection.attempt_unconfirmed"), displayed)
                self.assertNotIn(
                    tr("local_protection.observer_changed_notice"), displayed
                )
                self.assertNotIn(
                    tr("local_protection.sleep_observer_changed"), displayed
                )
                assert view.protection_button is not None
                self.assertEqual(
                    view.protection_button.icon_color,
                    ft.Colors.GREEN_300 if context is not None else WARNING_COLOR,
                )
        self.assertFalse(checks.snapshot.test_running)
        self.assertEqual(checks.snapshot.screen_attempt.code, "not_checked")
        self.assertEqual(checks.snapshot.sleep_attempt.code, "not_checked")

    async def test_real_model_reconnect_preserves_an_actual_unconfirmed_request_reason(
        self,
    ):
        snapshot = confirmed_snapshot()
        checks = LocalProtectionChecks(
            lambda: AppLockState(7, True, True, False), lambda: None
        )
        self.addAsyncCleanup(checks.aclose)
        checks.set_history(
            DeviceProtectionHistory(snapshot.screen_history, snapshot.sleep_history)
        )
        context = ObserverContext("linux", "synthetic-desktop", 1, "synthetic-owner")
        checks.update_observers(context, context)
        checks.preparation_unavailable("request_unavailable")
        checks.sleep_preparation_unavailable("sleep_permission_required")
        checks.update_observers(None, None)
        checks.update_observers(context, context)
        view = self.view(protection_status=checks.snapshot)
        await view.open_protection()
        for language in ("en", "ru"):
            set_language(language)
            view.set_protection_status(checks.snapshot)
            assert view.protection_panel.content is not None
            displayed = menu_fixtures.texts(view.protection_panel.content)
            self.assertIn(tr("local_protection.attempt_unconfirmed"), displayed)
            self.assertIn(tr("local_protection.request_unavailable"), displayed)
            self.assertIn(tr("local_protection.sleep_permission_denied"), displayed)
        self.assertEqual(checks.snapshot.screen_attempt.code, "request_unavailable")
        self.assertEqual(
            checks.snapshot.sleep_attempt.code, "sleep_permission_required"
        )
        self.assertEqual(checks.snapshot.screen.state, CheckState.CONFIRMED)
        self.assertEqual(checks.snapshot.sleep.state, CheckState.CONFIRMED)

    async def test_saved_results_remain_visible_while_readiness_reconnects(self):
        snapshot = confirmed_snapshot()
        view = self.view(protection_status=snapshot, on_test_sleep=AsyncMock())
        await view.open_protection()
        assert view.protection_button is not None
        self.assertEqual(view.protection_button.icon_color, ft.Colors.GREEN_300)
        view.set_protection_status(replace(snapshot, screen_connected=False))
        assert view.protection_panel.content is not None
        displayed = menu_fixtures.texts(view.protection_panel.content)
        self.assertIn(mechanism_label("screen", snapshot.screen), displayed)
        self.assertIn(mechanism_label("sleep", snapshot.sleep), displayed)
        self.assertIn(tr("local_protection.screen_monitor_warning"), displayed)
        self.assertEqual(view.protection_button.icon_color, WARNING_COLOR)
        self.assertEqual(len([text for text in displayed if "2025-01-01" in text]), 2)
        view.set_protection_status(snapshot)
        self.assertEqual(view.protection_button.icon_color, ft.Colors.GREEN_300)
        assert view._protection_status is not None
        self.assertIs(view._protection_status.screen_history, snapshot.screen_history)

    async def test_failure_has_own_red_row_and_preserves_other_success_and_success_time(
        self,
    ):
        snapshot = confirmed_snapshot()
        failed = replace(
            snapshot,
            sleep=CheckResult(CheckState.PROBLEM, "normal_seal_failed"),
            sleep_history=DeviceCheckRecord(
                CheckState.PROBLEM, 1735776000, 1735689660, SLEEP_CONTRACT
            ),
        )
        view = self.view(protection_status=failed)
        await view.open_protection()
        assert view.protection_panel.content is not None
        labels = {
            c.value: c.color
            for c in menu_fixtures.walk(view.protection_panel.content)
            if isinstance(c, ft.Text)
        }
        self.assertEqual(
            labels[mechanism_label("screen", failed.screen)], ft.Colors.GREEN_300
        )
        self.assertEqual(
            labels[mechanism_label("sleep", failed.sleep)], ft.Colors.RED_300
        )
        self.assertTrue(any("2025-01-01" in text for text in labels))
        self.assertTrue(any("2025-01-02" in text for text in labels))

    async def test_unfinished_attempt_and_stale_contract_do_not_hide_prior_result(self):
        snapshot = confirmed_snapshot()
        view = self.view(
            protection_status=replace(
                snapshot,
                sleep_attempt=CheckResult(
                    CheckState.UNTESTED, "sleep_permission_required"
                ),
            )
        )
        await view.open_protection()
        assert view.protection_panel.content is not None
        displayed = menu_fixtures.texts(view.protection_panel.content)
        self.assertIn(mechanism_label("sleep", snapshot.sleep), displayed)
        self.assertIn(tr("local_protection.attempt_unconfirmed"), displayed)
        self.assertIn(tr("local_protection.sleep_permission_denied"), displayed)
        view.set_protection_status(
            replace(
                snapshot,
                screen=CheckResult(CheckState.UNTESTED, "contract_changed"),
                screen_stale=True,
            )
        )
        displayed = menu_fixtures.texts(view.protection_panel.content)
        self.assertIn(tr("local_protection.contract_changed"), displayed)
        self.assertIn(
            tr(
                "local_protection.previous_result",
                result=mechanism_label("screen", snapshot.screen),
            ),
            displayed,
        )

    async def test_observed_sleep_origin_is_explicit_in_both_languages(self):
        snapshot = confirmed_snapshot()
        assert snapshot.sleep_history is not None
        view = self.view(
            protection_status=replace(
                snapshot,
                sleep_history=replace(snapshot.sleep_history, origin="observed"),
            )
        )
        await view.open_protection()
        for language in ("en", "ru"):
            set_language(language)
            view.refresh_menu_language()
            assert view.protection_panel.content is not None
            self.assertIn(
                tr("local_protection.sleep_observed"),
                menu_fixtures.texts(view.protection_panel.content),
            )

    async def test_unrepresentable_time_does_not_break_menu_or_expose_exception(self):
        view = self.view(protection_status=confirmed_snapshot())
        with patch("ui.security_status.datetime") as clock:
            clock.fromtimestamp.side_effect = OverflowError("private-system-message")
            await view.open_protection()
        assert view.protection_panel.content is not None
        displayed = menu_fixtures.texts(view.protection_panel.content)
        self.assertIn(tr("local_protection.check_time_unavailable"), displayed)
        self.assertFalse(any("private-system-message" in text for text in displayed))

    async def test_latest_failure_stays_red_across_reconnect_and_stale_history_stays_visible_red(
        self,
    ):
        snapshot = confirmed_snapshot()
        failed_record = DeviceCheckRecord(
            CheckState.PROBLEM, 1735776000, 1735689660, SLEEP_CONTRACT
        )
        failed = replace(
            snapshot,
            sleep=CheckResult(CheckState.PROBLEM, "normal_seal_failed"),
            sleep_history=failed_record,
        )
        view = self.view(protection_status=failed)
        await view.open_protection()
        assert view.protection_panel.content is not None
        for connected in (False, True):
            view.set_protection_status(replace(failed, sleep_connected=connected))
            labels = {
                c.value: c.color
                for c in menu_fixtures.walk(view.protection_panel.content)
                if isinstance(c, ft.Text)
            }
            self.assertEqual(
                labels[mechanism_label("sleep", failed.sleep)], ft.Colors.RED_300
            )
            self.assertEqual(
                labels[mechanism_label("screen", snapshot.screen)], ft.Colors.GREEN_300
            )
        view.set_protection_status(
            replace(
                failed,
                sleep=CheckResult(CheckState.UNTESTED, "contract_changed"),
                sleep_stale=True,
            )
        )
        labels = {
            c.value: c.color
            for c in menu_fixtures.walk(view.protection_panel.content)
            if isinstance(c, ft.Text)
        }
        previous = tr(
            "local_protection.previous_result",
            result=mechanism_label("sleep", failed.sleep),
        )
        self.assertEqual(labels[previous], ft.Colors.RED_300)
        assert view.protection_button is not None
        self.assertEqual(view.protection_button.icon_color, WARNING_COLOR)

    async def test_current_pass_with_write_failure_has_warning_without_saved_claim(
        self,
    ):
        view = self.view(
            protection_status=replace(confirmed_snapshot(), persistence_error=True)
        )
        await view.open_protection()
        assert view.protection_panel.content is not None
        assert view.protection_button is not None
        displayed = menu_fixtures.texts(view.protection_panel.content)
        self.assertIn(tr("local_protection.save_failed"), displayed)
        self.assertEqual(view.protection_button.icon_color, WARNING_COLOR)

    async def test_language_refresh_preserves_the_live_panel_action_without_auto_request(
        self,
    ):
        sleep = AsyncMock()
        view = self.view(protection_status=confirmed_snapshot(), on_test_sleep=sleep)
        await view.open_protection()
        old = view.sleep_test_button
        assert old is not None
        set_language("en")
        view.refresh_menu_language()
        sleep.assert_not_awaited()
        self.assertIs(view.sleep_test_button, old)
        assert view.sleep_test_button is not None
        self.assertEqual(view.sleep_test_button.content, "Test sleep protection")
        await self.fx.click(view.sleep_test_button)
        sleep.assert_awaited_once()


class DeferredSleepReply:
    def __init__(self, app, repository, chat_id):
        self.app = app
        self.repository = repository
        self.chat_id = chat_id
        self.sleep_context = ObserverContext("linux", "synthetic", 3, "synthetic")
        self.requested = asyncio.Event()
        self.release = asyncio.Event()
        self.requests = 0
        self.test_id = None
        self.before = None
        self.operation_locked = None
        self.draft_at_request = None

    async def prepare_sleep_test(self, *, timeout=8.0):
        return self.sleep_context

    def bind_sleep_test(self, context, test_id):
        self.test_id = test_id

    async def request_sleep(self, context):
        self.requests += 1
        self.before = self.app.protection_app_state()
        self.operation_locked = self.app._operation_lock.locked()
        self.draft_at_request = self.repository.get_draft(self.chat_id).text
        self.app.prepare_system_lock("sleep")
        self.app.record_normal_protection("sleep", context, self.before)
        self.requested.set()
        await self.release.wait()


class DeviceProtectionAppBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fx = app_fixtures.LinuxRecoveryIntegrationTests()
        await self.fx.asyncSetUp()
        # The nested IsolatedAsyncioTestCase has no runner of its own. Register
        # its actual resources on this running case rather than nested doCleanups.
        self.addCleanup(self.fx.fixture.temporary.cleanup)
        self.addCleanup(configure_localization, PreferencesStore())
        self.addCleanup(self.fx.updates.stop)
        self.app = self.fx.controller
        self.addCleanup(self.app.dispose)
        self.addAsyncCleanup(self.app.close_protection_checks)
        await self.app.submit_pin("0123")
        chat_id = self.app._chat_controller.selected_chat_id
        assert chat_id is not None
        repository = SqliteDraftRepository(
            self.fx.fixture.database.path, access=self.fx.fixture.access
        )
        self.adapter = DeferredSleepReply(self.app, repository, chat_id)
        self.app.set_screen_lock_adapter(None, self.adapter.sleep_context)
        self.app.set_sleep_adapter(self.adapter)

    async def test_explicit_sleep_flushes_encrypted_draft_then_normal_seal_reaches_PIN_without_operation_lock(
        self,
    ):
        view = self.app._chat_controller._workspace_view
        assert view is not None
        view.restore_editor("SYNTHETIC_SLEEP_DRAFT — 🙂")
        self.assertEqual(self.adapter.requests, 0)
        task = asyncio.create_task(self.app.request_sleep_test())
        try:
            await asyncio.wait_for(self.adapter.requested.wait(), 0.5)
            await self.app.wait_system_lock()
            self.assertEqual(
                self.adapter.draft_at_request, "SYNTHETIC_SLEEP_DRAFT — 🙂"
            )
            assert self.adapter.before is not None
            self.assertTrue(self.adapter.before.opened)
            self.assertFalse(self.adapter.operation_locked)
            self.assertTrue(self.app.protection_app_state().sealed_pin)
            self.assertFalse(self.app._operation_lock.locked())
            await self.app.request_sleep_test()
            await self.app.request_screen_lock_test()
            self.assertEqual(self.adapter.requests, 1)
            self.assertIsNotNone(self.adapter.test_id)
        finally:
            self.adapter.release.set()
            await task

    async def test_pending_sleep_preparation_blocks_both_requests_before_any_seal(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def prepare(*, timeout=8.0):
            entered.set()
            await release.wait()
            return self.adapter.sleep_context

        with patch.object(self.adapter, "prepare_sleep_test", prepare):
            task = asyncio.create_task(self.app.request_sleep_test())
            try:
                await asyncio.wait_for(entered.wait(), 0.5)
                self.assertTrue(self.app.protection_app_state().opened)
                self.assertFalse(self.app._operation_lock.locked())
                await self.app.request_sleep_test()
                await self.app.request_screen_lock_test()
                self.assertEqual(self.adapter.requests, 0)
                release.set()
                await asyncio.wait_for(self.adapter.requested.wait(), 0.5)
                self.assertEqual(self.adapter.requests, 1)
            finally:
                release.set()
                self.adapter.release.set()
                await task
                await self.app.wait_system_lock()

    async def test_failed_draft_flush_does_not_request_sleep_or_preseal(self):
        with patch.object(
            self.app._chat_controller._workspace_controller,
            "flush_editor",
            AsyncMock(return_value=False),
        ):
            await self.app.request_sleep_test()
        self.assertEqual(self.adapter.requests, 0)
        self.assertTrue(self.app.protection_app_state().opened)

    async def test_session_boundary_during_flush_rejects_late_sleep_request(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def flush():
            entered.set()
            await release.wait()
            return True

        with patch.object(
            self.app._chat_controller._workspace_controller, "flush_editor", flush
        ):
            task = asyncio.create_task(self.app.request_sleep_test())
            await asyncio.wait_for(entered.wait(), 0.5)
            self.app.prepare_system_lock("screen_lock")
            release.set()
            await task
            await self.app.wait_system_lock()
        self.assertEqual(self.adapter.requests, 0)
        self.assertTrue(self.app.protection_app_state().sealed_pin)

    async def test_Android_direct_call_cannot_suspend(self):
        self.app._page.platform = ft.PagePlatform.ANDROID
        await self.app.request_sleep_test()
        self.assertEqual(self.adapter.requests, 0)
        self.assertTrue(self.app.protection_app_state().opened)


class DeviceProtectionAndroidCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_Android_composition_has_no_device_checks_or_sleep_callback(self):
        page = generic_app_fixtures.FakePage()
        setattr(page, "platform", ft.PagePlatform.ANDROID)
        app = generic_app_fixtures._make_controller(
            page, generic_app_fixtures.FakeAuthService()
        )
        self.addCleanup(app.dispose)
        self.assertIsNone(app._local_protection)
        self.assertIsNone(app._chat_controller._on_test_sleep)
