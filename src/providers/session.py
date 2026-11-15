"""Unlocked, revision-fenced provider credentials and account snapshots."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from api.openrouter import CreditsResult, CreditsStatus, KeyValidationResult
from auth.key_validation import interpret_key_validation
from auth.models import KeyLimitInfo, KeyValidityState
from chat.account_balance import (
    AccountBalanceService,
    AccountBalanceSnapshot,
    has_authenticated_vsegpt_balance,
)
from providers.credentials import masked_key_display
from providers.models import ProviderId, detect_key, provider_spec
from storage.secure_credentials import FletSecureCredentials


class ProviderAPI(Protocol):
    async def validate_key(self, api_key: str) -> KeyValidationResult: ...
    async def get_credits(self, api_key: str, /) -> CreditsResult: ...


class ProviderSessionExpired(RuntimeError):
    def __init__(self) -> None:
        super().__init__("provider_session_expired")


@dataclass(frozen=True)
class ProviderState:
    provider_id: ProviderId
    has_saved_key: bool = False
    key_display: str | None = None
    key_validity: KeyValidityState = KeyValidityState.UNKNOWN
    key_limit: KeyLimitInfo = field(default_factory=KeyLimitInfo.unknown)
    balance: AccountBalanceSnapshot = field(default_factory=AccountBalanceSnapshot)
    checked_at: datetime | None = None
    warning: bool = False
    subscription_active: bool | None = None


class _Reader:
    def __init__(self, owner: ProviderProfiles, provider: ProviderId) -> None:
        self.owner = owner
        self.provider = provider

    async def get_credits(self, api_key: str, /) -> CreditsResult:
        revision = self.owner.credential_revision(self.provider)
        result = await self.owner._api.get_credits(api_key)
        if revision == self.owner.credential_revision(
            self.provider
        ) and self.owner.key_is_current(self.provider, api_key):
            self.owner._balance_authorization(self.provider, result)
        return result


class ProviderProfiles:
    """No keys enter public DTOs, preferences, database rows or exception text."""

    def __init__(self, credentials: FletSecureCredentials, api: ProviderAPI) -> None:
        self._credentials = credentials
        self._api = api
        self._epoch = 0
        self._active = False
        self._default_provider = ProviderId.OPENROUTER
        self._keys: dict[ProviderId, str] = {}
        self._revisions: dict[ProviderId, str] = {}
        self._checks: dict[ProviderId, tuple[str, KeyValidationResult, object]] = {}
        self._check_sequence = dict.fromkeys(ProviderId, 0)
        self._states = {p: ProviderState(p) for p in ProviderId}
        self._refresh_tasks: dict[ProviderId, asyncio.Task[None]] = {}
        self._write_locks = {provider: asyncio.Lock() for provider in ProviderId}
        self._default_lock = asyncio.Lock()
        self._on_change: Callable[[], None] = lambda: None
        self._balances = {
            p: AccountBalanceService(
                _Reader(self, p),
                lambda snapshot, provider=p: self._set_balance(provider, snapshot),
                post_response_delay=2.1 if p is ProviderId.VSEGPT else 1.0,
            )
            for p in ProviderId
        }

    @property
    def active(self) -> bool:
        return self._active

    @property
    def default_provider(self) -> ProviderId:
        return self._default_provider

    def set_on_change(self, callback: Callable[[], None]) -> None:
        self._on_change = callback

    def state(self, provider: ProviderId) -> ProviderState:
        return replace(
            self._states[provider],
            balance=self._balances[provider].snapshot,
            key_display=self.key_display(provider),
        )

    def key_for(self, provider: ProviderId) -> str | None:
        return self._keys.get(provider) if self._active else None

    def key_display(self, provider: ProviderId) -> str | None:
        """No additional storage read or copy of the credential leaves this boundary."""
        return masked_key_display(provider, self.key_for(provider))

    def key_is_current(self, provider: ProviderId, key: str) -> bool:
        current = self.key_for(provider)
        return current is not None and secrets.compare_digest(
            current.encode("utf-8"), key.encode("utf-8")
        )

    def credential_revision(self, provider: ProviderId) -> object:
        return self._epoch, self._revisions.get(provider)

    def key_validity_for(self, provider: ProviderId) -> KeyValidityState:
        return self._states[provider].key_validity

    def key_limit_for(self, provider: ProviderId) -> KeyLimitInfo:
        return self._states[provider].key_limit

    def balance_for(self, provider: ProviderId) -> AccountBalanceSnapshot:
        return self._balances[provider].snapshot

    async def activate(
        self,
        initial_key: str,
        validity: KeyValidityState,
        limit: KeyLimitInfo,
    ) -> None:
        self.deactivate()
        epoch = self._epoch
        keys: dict[ProviderId, str] = {}
        revisions: dict[ProviderId, str] = {}
        states = {provider: ProviderState(provider) for provider in ProviderId}
        for provider in ProviderId:
            # A save accepted before locking may finish in secure storage. Wait
            # for it before loading a new unlocked session's key/revision pair.
            async with self._write_locks[provider]:
                key = await self._credentials.get_provider_key(provider)
            if epoch != self._epoch:
                raise ProviderSessionExpired()
            if key:
                keys[provider] = key
                revisions[provider] = secrets.token_urlsafe(18)
                states[provider] = ProviderState(
                    provider,
                    has_saved_key=True,
                    key_validity=KeyValidityState.UNVERIFIED
                    if provider is ProviderId.VSEGPT
                    else KeyValidityState.UNKNOWN,
                )
        async with self._default_lock:
            default = await self._credentials.get_default_provider()
        if epoch != self._epoch:
            raise ProviderSessionExpired()
        provider = detect_key(initial_key)
        if (
            provider is not None
            and provider in keys
            and secrets.compare_digest(
                keys[provider].encode("utf-8"), initial_key.encode("utf-8")
            )
            and (
                provider is ProviderId.OPENROUTER
                or validity is not KeyValidityState.UNKNOWN
            )
        ):
            states[provider] = replace(
                states[provider], key_validity=validity, key_limit=limit
            )
        # Publish only after every secure read succeeds. An unavailable slot
        # cannot leave a partly activated profile with private keys in memory.
        self._keys = keys
        self._revisions = revisions
        self._states = states
        self._default_provider = default
        for provider in ProviderId:
            self._balances[provider].begin_session(provider)
        self._active = True
        self._notify()

    def deactivate(self) -> None:
        self._active = False
        self._epoch += 1
        self._keys.clear()
        self._revisions.clear()
        self._checks.clear()
        for task in self._refresh_tasks.values():
            task.cancel()
        self._refresh_tasks.clear()
        self._states = {p: ProviderState(p) for p in ProviderId}
        for service in self._balances.values():
            service.invalidate()

    async def check(self, provider: ProviderId, candidate: str) -> KeyValidationResult:
        normalized = candidate.strip()
        if not self._active or detect_key(normalized) is not provider:
            raise ProviderSessionExpired()
        self._check_sequence[provider] += 1
        sequence = self._check_sequence[provider]
        revision = self.credential_revision(provider)
        result = await self._api.validate_key(normalized)
        if (
            not self._active
            or revision != self.credential_revision(provider)
            or sequence != self._check_sequence[provider]
            or result.provider_id is not provider
        ):
            raise ProviderSessionExpired()
        self._checks[provider] = (self._digest(normalized), result, revision)
        return result

    async def save(
        self, provider: ProviderId, candidate: str, *, allow_unverified: bool
    ) -> None:
        async with self._write_locks[provider]:
            normalized = candidate.strip()
            record = self._checks.get(provider)
            if (
                not self._active
                or detect_key(normalized) is not provider
                or record is None
                or record[0] != self._digest(normalized)
                or record[2] != self.credential_revision(provider)
            ):
                raise ProviderSessionExpired()
            result = record[1]
            if not result.accepted and not (
                provider is ProviderId.VSEGPT
                and result.save_allowed
                and allow_unverified
            ):
                raise ProviderSessionExpired()
            revision = self.credential_revision(provider)
            saved_revision = await self._credentials.save_provider_key(
                provider,
                normalized,
                authorization_confirmed=result.authorization_confirmed,
            )
            if not self._active or revision != self.credential_revision(provider):
                raise ProviderSessionExpired()
            self._keys[provider] = normalized
            self._revisions[provider] = saved_revision
            self._checks.pop(provider, None)
            previous_refresh = self._refresh_tasks.pop(provider, None)
            if previous_refresh is not None:
                previous_refresh.cancel()
            self._balances[provider].invalidate()
            self._balances[provider].begin_session(provider)
            self.apply_validation(provider, normalized, result)

    async def set_default(self, provider: ProviderId) -> None:
        async with self._default_lock:
            if not self._active or not self.key_for(provider):
                raise ProviderSessionExpired()
            epoch = self._epoch
            await self._credentials.set_default_provider(provider)
            if not self._active or epoch != self._epoch:
                raise ProviderSessionExpired()
            self._default_provider = provider
            self._notify()

    def apply_validation(
        self, provider: ProviderId, key: str, result: KeyValidationResult
    ) -> None:
        if not self.key_is_current(provider, key) or result.provider_id is not provider:
            return
        validity, limit = interpret_key_validation(result)
        self._states[provider] = replace(
            self._states[provider],
            has_saved_key=True,
            key_validity=validity,
            key_limit=limit,
            checked_at=datetime.now(UTC),
            warning=result.warning,
            subscription_active=result.subscription_active,
        )
        self._notify()

    async def refresh(
        self,
        provider: ProviderId,
        *,
        after_response: bool = False,
        validate_key: bool = False,
    ) -> None:
        key = self.key_for(provider)
        if key is None:
            return
        previous = self._refresh_tasks.get(provider)
        if previous is not None and not previous.done():
            await asyncio.shield(previous)
            return

        revision = self.credential_revision(provider)

        async def read() -> None:
            if validate_key and provider is ProviderId.OPENROUTER:
                result = await self._api.validate_key(key)
                if revision == self.credential_revision(provider):
                    self.apply_validation(provider, key, result)
            if revision == self.credential_revision(provider) and self.key_is_current(
                provider, key
            ):
                await self._balances[provider].refresh(
                    key, after_response=after_response
                )

        task = asyncio.create_task(read())
        self._refresh_tasks[provider] = task
        try:
            await asyncio.shield(task)
        finally:
            if self._refresh_tasks.get(provider) is task and task.done():
                self._refresh_tasks.pop(provider, None)

    def _balance_authorization(
        self, provider: ProviderId, result: CreditsResult
    ) -> None:
        if (
            provider is not ProviderId.VSEGPT
            or result.provider_id is not provider
            or result.currency is not provider_spec(provider).currency
        ):
            return
        state = self._states[provider]
        if result.status is CreditsStatus.SUCCESS or has_authenticated_vsegpt_balance(
            result
        ):
            state = replace(state, key_validity=KeyValidityState.VALID)
        elif result.status is CreditsStatus.UNAUTHORIZED:
            state = replace(state, key_validity=KeyValidityState.INVALID)
        self._states[provider] = replace(
            state,
            checked_at=datetime.now(UTC),
            warning=result.warning,
            subscription_active=result.subscription_active,
        )

    def _set_balance(
        self, provider: ProviderId, snapshot: AccountBalanceSnapshot
    ) -> None:
        if self._active:
            self._states[provider] = replace(self._states[provider], balance=snapshot)
            self._notify()

    def _notify(self) -> None:
        self._on_change()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()
