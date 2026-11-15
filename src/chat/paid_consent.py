"""Per-chat, revocable permission for automatic paid dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field

from providers.models import ProviderId


@dataclass(frozen=True)
class PaidConsent:
    chat_id: str
    revision: str
    epoch: int
    scope: object = field(repr=False)
    session_epoch: int | None = None
    provider_id: ProviderId = ProviderId.OPENROUTER
    connection_revision: int = 0


class PaidConsentRevoked(RuntimeError):
    """The saved permission no longer authorizes this particular request."""
