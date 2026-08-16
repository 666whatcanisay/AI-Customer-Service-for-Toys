from __future__ import annotations

_PLATFORM_ALIASES = {
    "pdd": "pinduoduo",
    "pinduoduo": "pinduoduo",
    "拼多多": "pinduoduo",
}


def canonical_catalog_platform(value: str) -> str:
    """Return the AI-CS catalog identity without changing the channel wire value."""

    normalized = value.strip()
    return _PLATFORM_ALIASES.get(normalized.casefold(), normalized)
