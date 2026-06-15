"""Namespace name hygiene. Stdlib-only: hooks import this on their hot path."""
from __future__ import annotations


def sanitize_namespace(value: str) -> str:
    """ASCII [a-z0-9_-] only, others become '-', edges must be alphanumeric, max 64.

    chromadb collection names (verified against 1.5.9) require characters from
    [a-zA-Z0-9._-] and must start AND end alphanumeric; we prefix
    'subconscious_' so the start is safe, but the end must be stripped.
    """
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    cleaned = "".join(c if c in allowed else "-" for c in value.lower())
    cleaned = cleaned[:64].strip("-_")
    return cleaned or "default"
