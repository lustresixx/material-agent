"""Visible source-footer formatting without losing full evidence metadata."""

from __future__ import annotations


def shorten_source_footer(value: str | None, limit: int) -> str | None:
    """Fit a visible footer while leaving the evidence registry untouched."""
    if value is None:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    if limit < 2:
        raise ValueError("source footer limit must be at least 2")
    return f"{normalized[: limit - 1].rstrip()}…"
