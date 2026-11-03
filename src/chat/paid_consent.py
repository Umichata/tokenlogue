"""Per-chat, revocable permission for automatic paid dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PaidConsent:
    chat_id: str
    revision: str
    epoch: int
    scope: object = field(repr=False)
    session_epoch: int | None = None


class PaidConsentRevoked(RuntimeError):
    """The saved permission no longer authorizes this particular request."""
