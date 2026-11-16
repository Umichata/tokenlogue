"""New-chat policy is independent of service identity and the login key slot."""

from __future__ import annotations

from enum import StrEnum

from providers.models import ProviderId


class NewChatPolicy(StrEnum):
    MANUAL = "manual"
    OPENROUTER = "openrouter"
    VSEGPT = "vsegpt"

    @property
    def provider_id(self) -> ProviderId | None:
        return None if self is NewChatPolicy.MANUAL else ProviderId(self.value)

    @classmethod
    def for_provider(cls, provider: ProviderId) -> NewChatPolicy:
        return cls(provider.value)
