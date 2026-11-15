"""One-way, nonpersistent presentation of an already unlocked credential."""

from __future__ import annotations

from providers.models import ProviderId, detect_key, provider_spec

HIDDEN_KEY = "••••"


def masked_key_display(provider: ProviderId, key: str | None) -> str | None:
    """Reveal at most four characters after hiding eight secret characters."""
    if not key:
        return None
    normalized = key.strip()
    if detect_key(normalized) is not provider:
        return HIDDEN_KEY
    prefix = next(
        prefix
        for prefix in provider_spec(provider).key_prefixes
        if normalized.startswith(prefix)
    )
    # A separator following sk-or-vis is not counted as a hidden secret.
    secret = normalized[len(prefix) :].lstrip("-")
    return f"{HIDDEN_KEY} {normalized[-4:]}" if len(secret) >= 12 else HIDDEN_KEY


def safe_key_display(value: str | None) -> str | None:
    """Accept only the display grammar, never arbitrary caller text in a UI."""
    if value is None or value == HIDDEN_KEY:
        return value
    if (
        value.startswith(HIDDEN_KEY + " ")
        and len(value) == len(HIDDEN_KEY) + 5
        and all(33 <= ord(character) <= 126 for character in value[-4:])
    ):
        return value
    return HIDDEN_KEY
