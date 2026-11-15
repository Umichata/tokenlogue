"""Provider sessions and secure slots use only fake keys and in-memory storage."""

from __future__ import annotations

import asyncio
import sys
import unittest
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.openrouter import (  # noqa: E402
    CreditsResult,
    CreditsStatus,
    KeyValidationResult,
    KeyValidationStatus,
)
from auth.models import KeyLimitInfo, KeyValidityState  # noqa: E402
from chat.account_balance import AccountBalanceState  # noqa: E402
from providers.models import Currency, ProviderId, detect_key  # noqa: E402
from providers.session import ProviderProfiles, ProviderSessionExpired  # noqa: E402
from storage.secure_credentials import (  # noqa: E402
    ALL_PROVIDER_STORAGE_NAMES,
    API_KEY_STORAGE_NAME,
    DEFAULT_PROVIDER_STORAGE_NAME,
    PROVIDER_KEY_STORAGE_NAMES,
    PROVIDER_VALIDATION_STORAGE_NAMES,
    REGISTRATION_ID_STORAGE_NAME,
    FletSecureCredentials,
    SecureCredentialsError,
)

OR_OLD = "sk-or-v1-synthetic-old"
OR_NEW = "sk-or-v1-synthetic-new"
OR_OTHER = "sk-or-v1-synthetic-other"
VV_OLD = "sk-or-vv-synthetic-old"
VV_NEW = "sk-or-vv-synthetic-new"


@dataclass
class Gate:
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)

    async def wait(self) -> None:
        self.entered.set()
        await self.release.wait()


class MemoryStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.reads: list[str] = []
        self.writes: list[tuple[str, str]] = []
        self.pause_value: str | None = None
        self.write_gate = Gate()
        self.fail_new_value: str | None = None
        self.bad_read_after_write: str | None = None
        self.pending_bad_read = False
        self.fail_get_key: str | None = None

    async def contains_key(self, key: str) -> bool:
        return key in self.values

    async def get(self, key: str) -> str | None:
        self.reads.append(key)
        if key == self.fail_get_key:
            raise RuntimeError("synthetic read failure")
        if key == self.bad_read_after_write and self.pending_bad_read:
            self.pending_bad_read = False
            return "synthetic-wrong-readback"
        return self.values.get(key)

    async def set(self, key: str, value: Any) -> None:
        text = str(value)
        if text == self.pause_value:
            await self.write_gate.wait()
        if text == self.fail_new_value:
            raise RuntimeError("synthetic backend error with sk-or-v1-must-not-leak")
        self.values[key] = text
        self.writes.append((key, text))
        if key == self.bad_read_after_write:
            self.pending_bad_read = True

    async def remove(self, key: str) -> None:
        self.values.pop(key, None)


def validation(
    key: str, status: KeyValidationStatus | None = None
) -> KeyValidationResult:
    provider = detect_key(key)
    assert provider is not None
    return KeyValidationResult(
        status or KeyValidationStatus.ACCEPTED_WITHOUT_LIMIT,
        provider_id=provider,
    )


class FakeAPI:
    def __init__(self) -> None:
        self.validations: list[str] = []
        self.balances: list[str] = []
        self.validation_gates: dict[str, Gate] = {}
        self.balance_gates: dict[str, Gate] = {}
        self.results: dict[str, KeyValidationResult] = {}
        self.balance_results: dict[str, CreditsResult] = {}
        self.ignore_validation_cancellation: set[str] = set()
        self.ignore_balance_cancellation: set[str] = set()

    async def validate_key(self, api_key: str) -> KeyValidationResult:
        self.validations.append(api_key)
        if api_key in self.validation_gates:
            try:
                await self.validation_gates[api_key].wait()
            except asyncio.CancelledError:
                if api_key not in self.ignore_validation_cancellation:
                    raise
                await self.validation_gates[api_key].release.wait()
        return self.results.get(api_key, validation(api_key))

    async def get_credits(self, api_key: str, /) -> CreditsResult:
        self.balances.append(api_key)
        if api_key in self.balance_gates:
            try:
                await self.balance_gates[api_key].wait()
            except asyncio.CancelledError:
                if api_key not in self.ignore_balance_cancellation:
                    raise
                await self.balance_gates[api_key].release.wait()
        provider = detect_key(api_key)
        assert provider is not None
        return self.balance_results.get(
            api_key,
            CreditsResult(
                CreditsStatus.SUCCESS,
                balance_usd=Decimal("12.5")
                if provider is ProviderId.OPENROUTER
                else None,
                balance_amount=Decimal("12.5")
                if provider is ProviderId.OPENROUTER
                else Decimal("250"),
                currency=Currency.USD
                if provider is ProviderId.OPENROUTER
                else Currency.RUB,
                provider_id=provider,
            ),
        )


class SecureProviderSlotsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.storage = MemoryStorage()
        self.credentials = FletSecureCredentials(self.storage)

    async def test_vsegpt_only_registration_inspection_never_extracts_either_key(self):
        self.storage.values.update(
            {
                PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]: VV_OLD,
                REGISTRATION_ID_STORAGE_NAME: "synthetic-registration",
            }
        )
        state = await self.credentials.inspect_state()
        self.assertTrue(state.complete)
        self.assertEqual(self.storage.reads, [REGISTRATION_ID_STORAGE_NAME])
        self.assertEqual(
            await self.credentials.get_default_provider(), ProviderId.VSEGPT
        )
        self.assertEqual(await self.credentials.get_api_key(), VV_OLD)
        self.assertNotIn(API_KEY_STORAGE_NAME, self.storage.values)

    async def test_old_openrouter_alias_is_canonical_and_never_moved_or_removed(self):
        self.storage.values[API_KEY_STORAGE_NAME] = OR_OLD
        before = dict(self.storage.values)
        self.assertEqual(
            await self.credentials.get_default_provider(), ProviderId.OPENROUTER
        )
        self.assertEqual(await self.credentials.get_api_key(), OR_OLD)
        self.assertEqual(self.storage.values, before)
        await self.credentials.save_provider_key(
            ProviderId.VSEGPT, VV_NEW, authorization_confirmed=False
        )
        self.assertEqual(self.storage.values[API_KEY_STORAGE_NAME], OR_OLD)
        self.assertEqual(
            await self.credentials.get_default_provider(), ProviderId.OPENROUTER
        )

    async def test_two_slots_replacement_failure_keeps_old_key_metadata_and_default(
        self,
    ):
        self.storage.values.update(
            {
                API_KEY_STORAGE_NAME: OR_OLD,
                PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]: VV_OLD,
                DEFAULT_PROVIDER_STORAGE_NAME: "vsegpt",
                PROVIDER_VALIDATION_STORAGE_NAMES[
                    ProviderId.OPENROUTER
                ]: "old-metadata",
            }
        )
        before = dict(self.storage.values)
        self.storage.bad_read_after_write = API_KEY_STORAGE_NAME
        with self.assertRaises(SecureCredentialsError) as caught:
            await self.credentials.save_provider_key(
                ProviderId.OPENROUTER, OR_NEW, authorization_confirmed=True
            )
        self.assertEqual(self.storage.values, before)
        self.assertNotIn(OR_NEW, str(caught.exception))

    async def test_unknown_or_cross_provider_key_is_rejected_without_storage_access(
        self,
    ):
        for provider, key in (
            (ProviderId.OPENROUTER, VV_NEW),
            (ProviderId.VSEGPT, OR_NEW),
            (ProviderId.OPENROUTER, "sk-or-v1-"),
        ):
            with self.subTest(provider=provider):
                with self.assertRaises(SecureCredentialsError):
                    await self.credentials.save_provider_key(
                        provider, key, authorization_confirmed=True
                    )
        self.assertFalse(self.storage.reads)
        self.assertFalse(self.storage.writes)

    async def test_saved_metadata_has_revision_and_verification_without_key(self):
        revision = await self.credentials.save_provider_key(
            ProviderId.VSEGPT, "  " + VV_NEW + "  ", authorization_confirmed=False
        )
        metadata = await self.credentials.provider_metadata(ProviderId.VSEGPT)
        self.assertEqual(metadata["revision"], revision)
        self.assertFalse(metadata["authorization_confirmed"])
        self.assertIn("+00:00", metadata["checked_at"])
        self.assertNotIn(VV_NEW, str(metadata))
        self.assertEqual(
            await self.credentials.get_provider_key(ProviderId.VSEGPT), VV_NEW
        )

    async def test_default_is_persisted_and_missing_slot_falls_back_without_rewriting(
        self,
    ):
        self.storage.values.update(
            {
                API_KEY_STORAGE_NAME: OR_OLD,
                PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]: VV_OLD,
            }
        )
        await self.credentials.set_default_provider(ProviderId.VSEGPT)
        self.assertEqual(self.storage.values[DEFAULT_PROVIDER_STORAGE_NAME], "vsegpt")
        self.assertEqual(
            await FletSecureCredentials(self.storage).get_default_provider(),
            ProviderId.VSEGPT,
        )
        self.storage.values.pop(PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT])
        self.assertEqual(
            await self.credentials.get_default_provider(), ProviderId.OPENROUTER
        )
        self.assertEqual(self.storage.values[DEFAULT_PROVIDER_STORAGE_NAME], "vsegpt")

    async def test_default_readback_failure_restores_existing_metadata(self):
        self.storage.values.update(
            {
                API_KEY_STORAGE_NAME: OR_OLD,
                PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]: VV_OLD,
                DEFAULT_PROVIDER_STORAGE_NAME: "openrouter",
            }
        )
        self.storage.bad_read_after_write = DEFAULT_PROVIDER_STORAGE_NAME
        with self.assertRaises(SecureCredentialsError):
            await self.credentials.set_default_provider(ProviderId.VSEGPT)
        self.assertEqual(
            self.storage.values[DEFAULT_PROVIDER_STORAGE_NAME], "openrouter"
        )

    async def test_default_readback_failure_removes_unconfirmed_new_metadata(self):
        self.storage.values[PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]] = VV_OLD
        self.storage.bad_read_after_write = DEFAULT_PROVIDER_STORAGE_NAME
        with self.assertRaises(SecureCredentialsError):
            await self.credentials.set_default_provider(ProviderId.VSEGPT)
        self.assertNotIn(DEFAULT_PROVIDER_STORAGE_NAME, self.storage.values)
        self.assertEqual(
            self.storage.values[PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]], VV_OLD
        )

    async def test_delete_removes_all_provider_metadata_and_keeps_foreign_alias(self):
        self.storage.values.update(
            {name: "synthetic" for name in ALL_PROVIDER_STORAGE_NAMES}
        )
        self.storage.values[REGISTRATION_ID_STORAGE_NAME] = "synthetic-registration"
        self.storage.values["foreign.application.alias"] = "preserve"
        await self.credentials.delete_credentials()
        self.assertEqual(self.storage.values, {"foreign.application.alias": "preserve"})


class ProviderSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.storage = MemoryStorage()
        self.storage.values.update(
            {
                API_KEY_STORAGE_NAME: OR_OLD,
                PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]: VV_OLD,
                DEFAULT_PROVIDER_STORAGE_NAME: "openrouter",
            }
        )
        self.credentials = FletSecureCredentials(self.storage)
        self.api = FakeAPI()
        self.profiles = ProviderProfiles(self.credentials, self.api)
        self.addCleanup(self.profiles.deactivate)
        await self.profiles.activate(
            OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
        )

    async def test_activation_keeps_keys_provider_states_and_no_key_in_public_dto(self):
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_OLD)
        self.assertEqual(self.profiles.key_for(ProviderId.VSEGPT), VV_OLD)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.OPENROUTER),
            KeyValidityState.VALID,
        )
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.VSEGPT),
            KeyValidityState.UNVERIFIED,
        )
        for provider in ProviderId:
            self.assertTrue(self.profiles.state(provider).has_saved_key)
            self.assertNotIn(OR_OLD, repr(self.profiles.state(provider)))
            self.assertNotIn(VV_OLD, repr(self.profiles.state(provider)))

    async def test_failed_candidate_validation_does_not_replace_existing_key(self):
        self.api.results[OR_NEW] = validation(OR_NEW, KeyValidationStatus.INVALID)
        await self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        with self.assertRaises(ProviderSessionExpired):
            await self.profiles.save(
                ProviderId.OPENROUTER, OR_NEW, allow_unverified=False
            )
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_OLD)
        self.assertEqual(self.storage.values[API_KEY_STORAGE_NAME], OR_OLD)

    async def test_unverified_vsegpt_requires_explicit_save_and_keeps_other_provider(
        self,
    ):
        self.api.results[VV_NEW] = validation(VV_NEW, KeyValidationStatus.UNVERIFIED)
        await self.profiles.check(ProviderId.VSEGPT, VV_NEW)
        with self.assertRaises(ProviderSessionExpired):
            await self.profiles.save(ProviderId.VSEGPT, VV_NEW, allow_unverified=False)
        await self.profiles.save(ProviderId.VSEGPT, VV_NEW, allow_unverified=True)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.VSEGPT),
            KeyValidityState.UNVERIFIED,
        )
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_OLD)
        self.assertEqual(self.profiles.default_provider, ProviderId.OPENROUTER)

    async def test_late_validation_cannot_replace_a_newer_candidate_or_save_itself(
        self,
    ):
        gate = self.api.validation_gates[OR_NEW] = Gate()
        old = asyncio.create_task(self.profiles.check(ProviderId.OPENROUTER, OR_NEW))
        await gate.entered.wait()
        await self.profiles.check(ProviderId.OPENROUTER, OR_OTHER)
        gate.release.set()
        with self.assertRaises(ProviderSessionExpired):
            await old
        with self.assertRaises(ProviderSessionExpired):
            await self.profiles.save(
                ProviderId.OPENROUTER, OR_NEW, allow_unverified=False
            )
        await self.profiles.save(
            ProviderId.OPENROUTER, OR_OTHER, allow_unverified=False
        )
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_OTHER)

    async def test_validation_started_before_lock_cannot_leak_into_next_session(self):
        gate = self.api.validation_gates[OR_NEW] = Gate()
        pending = asyncio.create_task(
            self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        )
        await gate.entered.wait()
        revision = self.profiles.credential_revision(ProviderId.OPENROUTER)
        self.profiles.deactivate()
        await self.profiles.activate(
            OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
        )
        gate.release.set()
        with self.assertRaises(ProviderSessionExpired):
            await pending
        self.assertNotEqual(
            self.profiles.credential_revision(ProviderId.OPENROUTER), revision
        )
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_OLD)

    async def test_provider_checks_are_independent_during_concurrent_validation(self):
        gate = self.api.validation_gates[OR_NEW] = Gate()
        pending = asyncio.create_task(
            self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        )
        await gate.entered.wait()
        await self.profiles.check(ProviderId.VSEGPT, VV_NEW)
        await self.profiles.save(ProviderId.VSEGPT, VV_NEW, allow_unverified=False)
        gate.release.set()
        await pending
        await self.profiles.save(ProviderId.OPENROUTER, OR_NEW, allow_unverified=False)
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_NEW)
        self.assertEqual(self.profiles.key_for(ProviderId.VSEGPT), VV_NEW)

    async def test_deactivate_wipes_all_public_snapshots_and_rejects_candidate(self):
        await self.profiles.refresh(ProviderId.OPENROUTER)
        await self.profiles.check(ProviderId.VSEGPT, VV_NEW)
        self.assertEqual(
            self.profiles.balance_for(ProviderId.OPENROUTER).state,
            AccountBalanceState.CURRENT,
        )
        self.profiles.deactivate()
        self.assertFalse(self.profiles.active)
        for provider in ProviderId:
            self.assertIsNone(self.profiles.key_for(provider))
            self.assertFalse(self.profiles.state(provider).has_saved_key)
            self.assertEqual(
                self.profiles.key_validity_for(provider), KeyValidityState.UNKNOWN
            )
            self.assertIsNone(self.profiles.balance_for(provider).balance_amount)
            self.assertIsNone(self.profiles.state(provider).checked_at)
        with self.assertRaises(ProviderSessionExpired):
            await self.profiles.save(ProviderId.VSEGPT, VV_NEW, allow_unverified=True)

    async def test_coalesced_refresh_isolated_currency_and_restricted_balance_not_invalid_key(
        self,
    ):
        self.api.balance_results[OR_OLD] = CreditsResult(CreditsStatus.RESTRICTED)
        gate = self.api.balance_gates[OR_OLD] = Gate()
        first = asyncio.create_task(self.profiles.refresh(ProviderId.OPENROUTER))
        await gate.entered.wait()
        second = asyncio.create_task(self.profiles.refresh(ProviderId.OPENROUTER))
        await self.profiles.refresh(ProviderId.VSEGPT)
        gate.release.set()
        await asyncio.gather(first, second)
        self.assertEqual(self.api.balances.count(OR_OLD), 1)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.OPENROUTER),
            KeyValidityState.VALID,
        )
        self.assertIsNone(
            self.profiles.balance_for(ProviderId.OPENROUTER).balance_amount
        )
        self.assertEqual(
            self.profiles.balance_for(ProviderId.VSEGPT).currency, Currency.RUB
        )
        self.assertEqual(
            self.profiles.balance_for(ProviderId.VSEGPT).balance_amount, 250
        )

    async def test_late_old_balance_cannot_overwrite_replaced_key_snapshot(self):
        gate = self.api.balance_gates[OR_OLD] = Gate()
        pending = asyncio.create_task(self.profiles.refresh(ProviderId.OPENROUTER))
        await gate.entered.wait()
        await self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        await self.profiles.save(ProviderId.OPENROUTER, OR_NEW, allow_unverified=False)
        gate.release.set()
        await asyncio.gather(pending, return_exceptions=True)
        self.assertIsNone(
            self.profiles.balance_for(ProviderId.OPENROUTER).balance_amount
        )
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_NEW)

    async def test_two_overlapping_saves_never_leave_secure_key_different_from_session(
        self,
    ):
        await self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        self.storage.pause_value = OR_NEW
        first = asyncio.create_task(
            self.profiles.save(ProviderId.OPENROUTER, OR_NEW, allow_unverified=False)
        )
        await self.storage.write_gate.entered.wait()
        await self.profiles.check(ProviderId.OPENROUTER, OR_OTHER)
        second = asyncio.create_task(
            self.profiles.save(ProviderId.OPENROUTER, OR_OTHER, allow_unverified=False)
        )
        # The second coroutine reaches the secure writer before the first resumes.
        await asyncio.sleep(0)
        self.storage.write_gate.release.set()
        await asyncio.gather(first, second, return_exceptions=True)
        self.assertEqual(
            self.storage.values[API_KEY_STORAGE_NAME],
            self.profiles.key_for(ProviderId.OPENROUTER),
        )
        self.assertIn(self.storage.values[API_KEY_STORAGE_NAME], {OR_NEW, OR_OTHER})

    async def test_save_pending_at_lock_never_repopulates_inactive_private_state(self):
        await self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        self.storage.pause_value = OR_NEW
        pending = asyncio.create_task(
            self.profiles.save(ProviderId.OPENROUTER, OR_NEW, allow_unverified=False)
        )
        await self.storage.write_gate.entered.wait()
        self.profiles.deactivate()
        self.storage.write_gate.release.set()
        with self.assertRaises(ProviderSessionExpired):
            await pending
        self.assertFalse(self.profiles.active)
        self.assertIsNone(self.profiles.key_for(ProviderId.OPENROUTER))
        self.assertFalse(self.profiles.state(ProviderId.OPENROUTER).has_saved_key)
        self.assertIsNone(self.profiles.state(ProviderId.OPENROUTER).checked_at)

    async def test_next_activation_waits_for_prelock_save_before_loading_secure_key(
        self,
    ):
        await self.profiles.check(ProviderId.OPENROUTER, OR_NEW)
        self.storage.pause_value = OR_NEW
        pending = asyncio.create_task(
            self.profiles.save(ProviderId.OPENROUTER, OR_NEW, allow_unverified=False)
        )
        await self.storage.write_gate.entered.wait()
        self.profiles.deactivate()
        activation = asyncio.create_task(
            self.profiles.activate(
                OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
            )
        )
        await asyncio.sleep(0)
        self.assertFalse(activation.done())
        self.storage.write_gate.release.set()
        results = await asyncio.gather(pending, activation, return_exceptions=True)
        self.assertIsInstance(results[0], ProviderSessionExpired)
        self.assertIsNone(results[1])
        self.assertEqual(
            self.profiles.key_for(ProviderId.OPENROUTER),
            self.storage.values[API_KEY_STORAGE_NAME],
        )
        self.assertEqual(self.profiles.key_for(ProviderId.OPENROUTER), OR_NEW)

    async def test_explicit_vsegpt_save_after_network_errors_remains_unverified(self):
        for status in (
            KeyValidationStatus.TIMEOUT,
            KeyValidationStatus.NETWORK_ERROR,
            KeyValidationStatus.TLS_ERROR,
            KeyValidationStatus.RATE_LIMITED,
            KeyValidationStatus.SERVER_ERROR,
        ):
            with self.subTest(status=status):
                self.api.results[VV_NEW] = validation(VV_NEW, status)
                result = await self.profiles.check(ProviderId.VSEGPT, VV_NEW)
                self.assertEqual(result.status, status)
                with self.assertRaises(ProviderSessionExpired):
                    await self.profiles.save(
                        ProviderId.VSEGPT, VV_NEW, allow_unverified=False
                    )
                await self.profiles.save(
                    ProviderId.VSEGPT, VV_NEW, allow_unverified=True
                )
                self.assertEqual(
                    self.profiles.key_validity_for(ProviderId.VSEGPT),
                    KeyValidityState.UNVERIFIED,
                )
                self.assertFalse(
                    (await self.credentials.provider_metadata(ProviderId.VSEGPT))[
                        "authorization_confirmed"
                    ]
                )

    async def test_wrong_provider_validation_result_cannot_authorize_a_save(self):
        self.api.results[VV_NEW] = validation(OR_NEW)
        with self.assertRaises(ProviderSessionExpired):
            await self.profiles.check(ProviderId.VSEGPT, VV_NEW)
        with self.assertRaises(ProviderSessionExpired):
            await self.profiles.save(ProviderId.VSEGPT, VV_NEW, allow_unverified=True)
        self.assertEqual(self.profiles.key_for(ProviderId.VSEGPT), VV_OLD)
        self.assertEqual(
            self.storage.values[PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]], VV_OLD
        )

    async def test_failed_default_update_keeps_public_and_persisted_selection_equal(
        self,
    ):
        self.storage.bad_read_after_write = DEFAULT_PROVIDER_STORAGE_NAME
        with self.assertRaises(SecureCredentialsError):
            await self.profiles.set_default(ProviderId.VSEGPT)
        self.assertEqual(self.profiles.default_provider, ProviderId.OPENROUTER)
        self.assertEqual(
            self.storage.values[DEFAULT_PROVIDER_STORAGE_NAME], "openrouter"
        )

    async def test_reactivation_waits_for_prelock_default_write(self):
        self.storage.pause_value = "vsegpt"
        pending = asyncio.create_task(self.profiles.set_default(ProviderId.VSEGPT))
        await self.storage.write_gate.entered.wait()
        self.profiles.deactivate()
        activation = asyncio.create_task(
            self.profiles.activate(
                OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
            )
        )
        await asyncio.sleep(0)
        self.assertFalse(activation.done())
        self.storage.write_gate.release.set()
        results = await asyncio.gather(pending, activation, return_exceptions=True)
        self.assertIsInstance(results[0], ProviderSessionExpired)
        self.assertIsNone(results[1])
        self.assertEqual(self.profiles.default_provider, ProviderId.VSEGPT)
        self.assertEqual(self.storage.values[DEFAULT_PROVIDER_STORAGE_NAME], "vsegpt")

    async def test_uncancellable_old_vsegpt_balance_cannot_change_next_session_auth(
        self,
    ):
        gate = self.api.balance_gates[VV_OLD] = Gate()
        self.api.ignore_balance_cancellation.add(VV_OLD)
        self.api.balance_results[VV_OLD] = CreditsResult(
            CreditsStatus.UNAUTHORIZED,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
        )
        pending = asyncio.create_task(self.profiles.refresh(ProviderId.VSEGPT))
        await gate.entered.wait()
        self.profiles.deactivate()
        await self.profiles.activate(
            OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
        )
        gate.release.set()
        await asyncio.gather(pending, return_exceptions=True)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.VSEGPT),
            KeyValidityState.UNVERIFIED,
        )
        self.assertIsNone(self.profiles.balance_for(ProviderId.VSEGPT).balance_amount)

    async def test_uncancellable_old_key_validation_cannot_invalidate_next_session(
        self,
    ):
        gate = self.api.validation_gates[OR_OLD] = Gate()
        self.api.ignore_validation_cancellation.add(OR_OLD)
        self.api.results[OR_OLD] = validation(OR_OLD, KeyValidationStatus.INVALID)
        pending = asyncio.create_task(
            self.profiles.refresh(ProviderId.OPENROUTER, validate_key=True)
        )
        await gate.entered.wait()
        self.profiles.deactivate()
        await self.profiles.activate(
            OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
        )
        gate.release.set()
        await asyncio.gather(pending, return_exceptions=True)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.OPENROUTER),
            KeyValidityState.VALID,
        )
        self.assertFalse(self.api.balances)

    async def test_failed_activation_never_publishes_a_partly_unlocked_profile(self):
        self.storage.fail_get_key = PROVIDER_KEY_STORAGE_NAMES[ProviderId.VSEGPT]
        with self.assertRaises(SecureCredentialsError):
            await self.profiles.activate(
                OR_OLD, KeyValidityState.VALID, KeyLimitInfo.unknown()
            )
        self.assertFalse(self.profiles.active)
        for provider in ProviderId:
            self.assertIsNone(self.profiles.key_for(provider))
            self.assertFalse(self.profiles.state(provider).has_saved_key)
            self.assertIsNone(self.profiles.balance_for(provider).balance_amount)

    async def test_mismatched_balance_provider_cannot_confirm_another_service_key(self):
        self.api.balance_results[VV_OLD] = CreditsResult(
            CreditsStatus.SUCCESS, balance_usd=Decimal("12")
        )
        await self.profiles.refresh(ProviderId.VSEGPT)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.VSEGPT),
            KeyValidityState.UNVERIFIED,
        )
        self.assertIsNone(self.profiles.balance_for(ProviderId.VSEGPT).balance_amount)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.OPENROUTER),
            KeyValidityState.VALID,
        )

    async def test_authenticated_vsegpt_restrictions_keep_money_and_permission_separate(
        self,
    ):
        for status, amount in (
            (CreditsStatus.SUBSCRIPTION_REQUIRED, Decimal("250.125")),
            (CreditsStatus.INSUFFICIENT_FUNDS, Decimal("-0.125")),
            (CreditsStatus.ACCOUNT_DISABLED, Decimal("0")),
        ):
            with self.subTest(status=status):
                self.api.balance_results[VV_OLD] = CreditsResult(
                    status,
                    balance_amount=amount,
                    provider_id=ProviderId.VSEGPT,
                    currency=Currency.RUB,
                    warning=True,
                    subscription_active=False,
                )
                await self.profiles.refresh(ProviderId.VSEGPT)
                balance = self.profiles.balance_for(ProviderId.VSEGPT)
                self.assertEqual(balance.state, AccountBalanceState.CURRENT)
                self.assertEqual(balance.balance_amount, amount)
                self.assertIsNone(balance.balance_usd)
                self.assertEqual(balance.error, status)
                self.assertTrue(balance.warning)
                self.assertFalse(
                    self.profiles.state(ProviderId.VSEGPT).subscription_active
                )
                self.assertEqual(
                    self.profiles.key_validity_for(ProviderId.VSEGPT),
                    KeyValidityState.VALID,
                )

    async def test_vsegpt_restriction_without_valid_amount_does_not_invent_balance_or_auth(
        self,
    ):
        self.api.balance_results[VV_OLD] = CreditsResult(
            CreditsStatus.SUBSCRIPTION_REQUIRED,
            provider_id=ProviderId.VSEGPT,
            currency=Currency.RUB,
            subscription_active=False,
        )
        await self.profiles.refresh(ProviderId.VSEGPT)
        balance = self.profiles.balance_for(ProviderId.VSEGPT)
        self.assertEqual(balance.state, AccountBalanceState.UNAVAILABLE)
        self.assertIsNone(balance.balance_amount)
        self.assertEqual(balance.error, CreditsStatus.SUBSCRIPTION_REQUIRED)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.VSEGPT),
            KeyValidityState.UNVERIFIED,
        )

    async def test_vsegpt_account_statuses_do_not_authorize_an_openrouter_amount(self):
        self.api.balance_results[OR_OLD] = CreditsResult(
            CreditsStatus.ACCOUNT_DISABLED, balance_usd=Decimal("125")
        )
        await self.profiles.refresh(ProviderId.OPENROUTER)
        balance = self.profiles.balance_for(ProviderId.OPENROUTER)
        self.assertEqual(balance.state, AccountBalanceState.UNAVAILABLE)
        self.assertIsNone(balance.balance_amount)
        self.assertEqual(balance.error, CreditsStatus.ACCOUNT_DISABLED)
        self.assertEqual(
            self.profiles.key_validity_for(ProviderId.VSEGPT),
            KeyValidityState.UNVERIFIED,
        )
