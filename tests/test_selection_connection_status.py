"""Offline selection UI behavior with controlled callbacks and synthetic metadata."""

from __future__ import annotations

import asyncio
import sys
import unittest
from collections.abc import Awaitable, Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.models import (  # noqa: E402
    FREE_ROUTER_MODEL,
    CatalogModel,
    ChatMode,
    ModelCatalog,
)
from i18n import configure_localization, localize_tree, set_language, tr  # noqa: E402
from preferences import PreferencesStore  # noqa: E402
from providers.models import Currency, ProviderId  # noqa: E402
from tests.test_chat_menu import texts, walk  # noqa: E402
from ui.model_selection_view import (  # noqa: E402
    ModelSelectionView,
    ModeSelectionView,
    key_access_mode_notice,
)


def _model(name="alpha", provider=ProviderId.VSEGPT):
    return CatalogModel(
        f"fixture/{name}",
        name.title(),
        Decimal("0.01"),
        Decimal("0.02"),
        provider_id=provider,
        currency=Currency.RUB if provider is ProviderId.VSEGPT else Currency.USD,
    )


def _select_buttons(view):
    return [
        c
        for c in walk(view.results)
        if isinstance(c, ft.Button) and c.content == tr("catalog.select")
    ]


async def _click(button):
    callback = cast(Callable[[ft.Event], Awaitable[None]], button.on_click)
    await callback(ft.Event(name="click", control=button))


class SelectionConnectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        configure_localization(PreferencesStore())
        self.addCleanup(configure_localization, PreferencesStore())
        self.updates = patch.object(ft.Control, "update", return_value=None)
        self.updates.start()
        self.addCleanup(self.updates.stop)

    def mode(self, **kwargs):
        paid = _model(provider=ProviderId.OPENROUTER)
        return ModeSelectionView(
            ModelCatalog((FREE_ROUTER_MODEL,), (paid,), True),
            kwargs.pop("validity", KeyValidityState.UNKNOWN),
            kwargs.pop("limit", KeyLimitInfo.unknown()),
            kwargs.pop("on_select", AsyncMock()),
            kwargs.pop("on_cancel", AsyncMock()),
            **kwargs,
        )

    def models(self, **kwargs):
        models = kwargs.pop("models", (_model(), _model("beta")))
        return ModelSelectionView(
            ChatMode.PAID,
            models,
            kwargs.pop("on_select", AsyncMock()),
            kwargs.pop("on_cancel", AsyncMock()),
            provider_id=kwargs.pop("provider_id", ProviderId.VSEGPT),
            key_validity=kwargs.pop("validity", KeyValidityState.UNVERIFIED),
            **kwargs,
        )

    async def test_short_viewport_can_scroll_search_back_and_connection_actions(self):
        cancel = AsyncMock()
        view = self.models(
            on_cancel=cancel,
            on_check_key=AsyncMock(),
            on_refresh=AsyncMock(),
        )
        viewport = next(
            control
            for control in walk(view.control)
            if isinstance(control, ft.ListView)
        )
        actions = (
            view.search,
            view.cancel_button,
            view.check_key_button,
            view.refresh_button,
        )

        def assert_actions_can_scroll_together():
            controls = list(walk(viewport))
            for action in actions:
                self.assertIsNotNone(action)
                self.assertTrue(any(control is action for control in controls))

        assert_actions_can_scroll_together()
        original_search, original_back = view.search, view.cancel_button
        view.search.value = "beta"
        view._filter(ft.Event(name="change", control=view.search))
        view.set_connection_state(KeyValidityState.INVALID, KeyLimitInfo.unknown())
        view.set_catalog(ModelCatalog((), (), False))
        assert_actions_can_scroll_together()
        self.assertIs(view.search, original_search)
        self.assertIs(view.cancel_button, original_back)
        self.assertIs(view.results, viewport)
        self.assertEqual(view.search.value, "beta")
        self.assertEqual(
            sum(control is original_search for control in walk(view.control)), 1
        )
        self.assertEqual(
            sum(control is original_back for control in walk(view.control)), 1
        )
        await _click(view.cancel_button)
        cancel.assert_awaited_once()

    async def test_mode_check_is_real_callback_busy_once_then_updates_current_access(
        self,
    ):
        entered, finish = asyncio.Event(), asyncio.Event()
        selected, refreshed, canceled = AsyncMock(), AsyncMock(), AsyncMock()

        async def validate():
            entered.set()
            await finish.wait()
            view.set_connection_state(
                KeyValidityState.VALID, KeyLimitInfo.from_validated_remaining(None)
            )

        check = AsyncMock(side_effect=validate)
        view = self.mode(
            on_select=selected,
            on_refresh=refreshed,
            on_check_key=check,
            on_cancel=canceled,
        )
        self.assertFalse(view.connection_status.progress.visible)
        self.assertEqual(
            view.connection_status.status.value,
            tr("selection.key.not_checked", provider="OpenRouter"),
        )
        self.assertTrue(view.paid_button.disabled)
        self.assertFalse(view.free_button.disabled)
        task = asyncio.create_task(_click(view.check_key_button))
        await entered.wait()
        self.assertTrue(view.connection_status.progress.visible)
        self.assertTrue(view.check_key_button.disabled)
        self.assertTrue(view.free_button.disabled)
        self.assertTrue(view.paid_button.disabled)
        self.assertFalse(view.cancel_button.disabled)
        await _click(view.check_key_button)
        await _click(view.paid_button)
        await _click(view.cancel_button)
        check.assert_awaited_once()
        canceled.assert_awaited_once()
        selected.assert_not_awaited()
        refreshed.assert_not_awaited()
        finish.set()
        await task
        self.assertFalse(view.connection_status.progress.visible)
        self.assertFalse(view.paid_button.disabled)
        self.assertEqual(
            view.connection_status.status.value,
            tr("selection.key.accepted", provider="OpenRouter"),
        )
        selected.assert_not_awaited()
        await _click(view.paid_button)
        selected.assert_awaited_once_with(ChatMode.PAID)

    async def test_unknown_idle_never_looks_busy_in_either_language(self):
        for language in ("ru", "en"):
            set_language(language)
            for provider in ProviderId:
                text, _ = key_access_mode_notice(
                    KeyValidityState.UNKNOWN,
                    KeyLimitInfo.unknown(),
                    provider_id=provider,
                )
                self.assertEqual(
                    text,
                    tr(
                        "selection.key.not_checked",
                        provider="OpenRouter"
                        if provider is ProviderId.OPENROUTER
                        else "VSEGPT",
                    ),
                )
                view = self.models(
                    provider_id=provider,
                    models=(_model(provider=provider),),
                    validity=KeyValidityState.UNKNOWN,
                    on_check_key=AsyncMock(),
                )
                self.assertFalse(view.connection_status.progress.visible)
                self.assertFalse(view.check_key_button.disabled)
                self.assertEqual(_select_buttons(view), [])
                view.set_connection_state(
                    KeyValidityState.UNKNOWN,
                    KeyLimitInfo.unknown(),
                    key_check_busy=True,
                )
                self.assertTrue(view.connection_status.progress.visible)
                self.assertNotEqual(view.connection_status.status.value, text)

    async def test_model_key_check_preserves_search_and_is_separate_from_refresh(self):
        checked, refreshed, selected = AsyncMock(), AsyncMock(), AsyncMock()
        view = self.models(
            on_check_key=checked, on_refresh=refreshed, on_select=selected
        )
        results = view.results
        view.search.value = "beta"
        view._filter(ft.Event(name="change", control=view.search))
        self.assertEqual(len(_select_buttons(view)), 1)
        await _click(view.check_key_button)
        checked.assert_awaited_once()
        refreshed.assert_not_awaited()
        await _click(view.refresh_button)
        refreshed.assert_awaited_once()
        selected.assert_not_awaited()
        view.set_connection_state(KeyValidityState.VALID, KeyLimitInfo.unknown())
        self.assertIs(view.results, results)
        self.assertEqual(view.search.value, "beta")
        self.assertEqual(len(_select_buttons(view)), 1)
        await _click(_select_buttons(view)[0])
        selected.assert_awaited_once_with(_model("beta"))

    async def test_safe_failure_allows_retry_without_echoing_exception_or_refreshing_catalog(
        self,
    ):
        secret_like = "DO_NOT_RENDER_THIS_PRIVATE_RESPONSE"
        check = AsyncMock(side_effect=[RuntimeError(secret_like), None])
        refreshed = AsyncMock()
        view = self.mode(on_check_key=check, on_refresh=refreshed)
        await _click(view.check_key_button)
        self.assertFalse(view.connection_status.progress.visible)
        self.assertFalse(view.check_key_button.disabled)
        self.assertIn(tr("selection.key.failed"), texts(view.control))
        self.assertNotIn(secret_like, " ".join(texts(view.control)))
        await _click(view.check_key_button)
        self.assertEqual(check.await_count, 2)
        refreshed.assert_not_awaited()

    async def test_late_local_finally_cannot_clear_new_controller_owned_busy(self):
        entered, finish = asyncio.Event(), asyncio.Event()

        async def delayed() -> None:
            entered.set()
            await finish.wait()

        view = self.mode(on_check_key=delayed)
        task = asyncio.create_task(_click(view.check_key_button))
        await entered.wait()
        view.set_connection_state(
            KeyValidityState.UNKNOWN, KeyLimitInfo.unknown(), key_check_busy=True
        )
        finish.set()
        await task
        self.assertTrue(view.connection_status.progress.visible)
        self.assertTrue(view.check_key_button.disabled)
        view.set_connection_state(KeyValidityState.UNKNOWN, KeyLimitInfo.unknown())
        self.assertFalse(view.connection_status.progress.visible)

    async def test_back_works_during_check_and_disposed_view_ignores_late_result(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        canceled = AsyncMock()

        async def delayed() -> None:
            entered.set()
            await finish.wait()
            view.set_connection_state(KeyValidityState.VALID, KeyLimitInfo.unknown())

        view = self.models(on_check_key=delayed, on_cancel=canceled)
        task = asyncio.create_task(_click(view.check_key_button))
        await entered.wait()
        self.assertFalse(view.cancel_button.disabled)
        self.assertTrue(all(button.disabled for button in _select_buttons(view)))
        await _click(view.cancel_button)
        canceled.assert_awaited_once()
        view.dispose()
        finish.set()
        await task
        self.assertEqual(view.results.controls, [])
        self.assertEqual(view.connection_status.status.value, "")
        self.assertFalse(view.connection_status.progress.visible)

    async def test_invalid_key_and_unavailable_or_empty_catalog_have_distinct_safe_recovery(
        self,
    ):
        selected = AsyncMock()
        timeout = tr("catalog.error.timeout")
        view = self.models(
            on_select=selected, on_check_key=AsyncMock(), on_refresh=AsyncMock()
        )
        stale_button = _select_buttons(view)[0]
        view.set_connection_state(
            KeyValidityState.INVALID,
            KeyLimitInfo.unknown(),
            key_notice=tr("catalog.error.tls"),
        )
        self.assertEqual(_select_buttons(view), [])
        await _click(stale_button)
        selected.assert_not_awaited()
        self.assertIn(tr("catalog.error.tls"), texts(view.control))
        view.set_connection_state(KeyValidityState.UNVERIFIED, KeyLimitInfo.unknown())
        view.set_catalog(ModelCatalog((), (), False, warning=timeout, retry_after=17))
        self.assertEqual(_select_buttons(view), [])
        self.assertIn(timeout, texts(view.control))
        self.assertIn(tr("catalog.retry_wait", seconds=17), texts(view.control))
        assert view.refresh_button is not None
        self.assertFalse(view.refresh_button.disabled)
        view.set_catalog(ModelCatalog((), (), True))
        self.assertIn(tr("catalog.empty"), texts(view.control))
        view.set_catalog(ModelCatalog((), (_model(),), True))
        view.search.value = "not-present"
        view._filter(ft.Event(name="change", control=view.search))
        self.assertIn(tr("catalog.none"), texts(view.control))
        self.assertNotIn(tr("catalog.empty"), texts(view.control))

    async def test_access_rules_preserve_authorization_and_limit_distinction(self):
        for provider, validity, limit, allowed in (
            (
                ProviderId.OPENROUTER,
                KeyValidityState.VALID,
                KeyLimitInfo.unknown(),
                False,
            ),
            (
                ProviderId.OPENROUTER,
                KeyValidityState.VALID,
                KeyLimitInfo.from_validated_remaining(None),
                True,
            ),
            (
                ProviderId.OPENROUTER,
                KeyValidityState.UNVERIFIED,
                KeyLimitInfo.from_validated_remaining(None),
                False,
            ),
            (ProviderId.VSEGPT, KeyValidityState.VALID, KeyLimitInfo.unknown(), True),
            (
                ProviderId.VSEGPT,
                KeyValidityState.UNVERIFIED,
                KeyLimitInfo.unknown(),
                True,
            ),
            (
                ProviderId.VSEGPT,
                KeyValidityState.UNKNOWN,
                KeyLimitInfo.unknown(),
                False,
            ),
            (
                ProviderId.VSEGPT,
                KeyValidityState.INVALID,
                KeyLimitInfo.unknown(),
                False,
            ),
            (
                ProviderId.VSEGPT,
                KeyValidityState.RESTRICTED,
                KeyLimitInfo.unknown(),
                False,
            ),
        ):
            view = self.models(
                models=(_model(provider=provider),),
                provider_id=provider,
                validity=validity,
                key_limit=limit,
            )
            self.assertEqual(bool(_select_buttons(view)), allowed)
        view = self.mode(validity=KeyValidityState.VALID, limit=KeyLimitInfo.unknown())
        self.assertEqual(
            view.connection_status.status.value,
            tr("selection.key.accepted", provider="OpenRouter"),
        )
        self.assertFalse(view.free_button.disabled)
        self.assertTrue(view.paid_button.disabled)

    async def test_only_exact_new_openrouter_router_survives_missing_catalog(self):
        selected = AsyncMock()
        other = replace(FREE_ROUTER_MODEL, id="fixture/other:free")
        for changing in (False, True):
            view = ModelSelectionView(
                ChatMode.FREE,
                (FREE_ROUTER_MODEL, other),
                selected,
                AsyncMock(),
                catalog=ModelCatalog((FREE_ROUTER_MODEL, other), (), False),
                changing_provider=changing,
            )
            buttons = _select_buttons(view)
            self.assertEqual(len(buttons), 0 if changing else 1)
            if buttons:
                await _click(buttons[0])
        selected.assert_awaited_once_with(FREE_ROUTER_MODEL)
        vsegpt = replace(
            FREE_ROUTER_MODEL, provider_id=ProviderId.VSEGPT, currency=Currency.RUB
        )
        view = ModelSelectionView(
            ChatMode.FREE,
            (vsegpt,),
            selected,
            AsyncMock(),
            provider_id=ProviderId.VSEGPT,
            catalog=ModelCatalog((vsegpt,), (), False),
        )
        self.assertEqual(_select_buttons(view), [])

    async def test_vsegpt_model_screen_back_never_promises_a_mode_page(self):
        canceled = AsyncMock()
        view = self.models(on_cancel=canceled, on_check_key=AsyncMock())
        self.assertEqual(view.cancel_button.content, tr("common.back"))
        labels = texts(view.control)
        self.assertNotIn(tr("mode.choose_first"), labels)
        self.assertNotIn(tr("mode.choose_free"), labels)
        self.assertNotIn(tr("mode.choose_paid"), labels)
        await _click(view.cancel_button)
        canceled.assert_awaited_once()

    async def test_foreign_models_and_stale_model_callbacks_never_select(self):
        first = _model()
        selected = AsyncMock()
        view = self.models(
            models=(first, _model(provider=ProviderId.OPENROUTER)), on_select=selected
        )
        self.assertEqual(len(_select_buttons(view)), 1)
        old_button = _select_buttons(view)[0]
        view.set_catalog(ModelCatalog((), (_model("beta"),), True))
        await _click(old_button)
        selected.assert_not_awaited()
        self.assertNotIn(first.id, texts(view.control))
        self.assertTrue(isinstance(view.control, ft.SafeArea))
        self.assertTrue(view.control.maintain_bottom_view_padding)
        set_language("en")
        localize_tree(view.control)
        self.assertEqual(view.search.label, tr("catalog.search"))
