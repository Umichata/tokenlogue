"""Explicit provider identity; a recognized prefix never proves authorization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderId(StrEnum):
    OPENROUTER = "openrouter"
    VSEGPT = "vsegpt"


class Currency(StrEnum):
    USD = "USD"
    RUB = "RUB"


class PriceUnit(StrEnum):
    TOKEN = "token"
    CHARACTER = "character"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: ProviderId
    name: str
    currency: Currency
    base_url: str
    key_prefix: str
    supports_key_limit: bool
    supports_provider_routing: bool
    catalog_is_public: bool


_SPECS = {
    ProviderId.OPENROUTER: ProviderSpec(
        ProviderId.OPENROUTER,
        "OpenRouter",
        Currency.USD,
        "https://openrouter.ai/api/v1",
        "sk-or-v1-",
        True,
        True,
        False,
    ),
    ProviderId.VSEGPT: ProviderSpec(
        ProviderId.VSEGPT,
        "VSEGPT",
        Currency.RUB,
        "https://api.vsegpt.ru/v1",
        "sk-or-vv-",
        False,
        False,
        True,
    ),
}


def provider_spec(provider_id: ProviderId | str) -> ProviderSpec:
    """Return only one of the application's fixed HTTPS endpoint definitions."""
    return _SPECS[ProviderId(provider_id)]


def detect_key(api_key: str) -> ProviderId | None:
    """Classify locally, without rewriting case/content or accepting a prefix alone."""
    normalized = api_key.strip()
    if (
        not normalized
        or not normalized.isascii()
        or any(
            character.isspace() or ord(character) < 33 or ord(character) == 127
            for character in normalized
        )
    ):
        return None
    for provider_id, spec in _SPECS.items():
        if normalized.startswith(spec.key_prefix) and len(normalized) > len(
            spec.key_prefix
        ):
            return provider_id
    return None
