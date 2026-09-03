"""Normalization helpers for outline payloads copied from external systems."""

from __future__ import annotations

from html import unescape
from typing import Any


def normalize_outline_payload(payload: object) -> dict[str, Any]:
    """Return a normalized copy of an outline JSON object.

    Some chat and browser surfaces escape underscores in JSON keys or preserve
    HTML space entities. Normalizing recursively keeps those transport details
    out of the validated domain model without mutating the caller's payload.
    """
    if not isinstance(payload, dict):
        raise ValueError("outline payload must be a JSON object")
    return _normalize_mapping(payload)


def _normalize_mapping(value: dict[object, object]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise ValueError("outline object keys must be strings")
        key = unescape(raw_key).replace("\\_", "_").strip()
        normalized[key] = _normalize_value(raw_value)
    return normalized


def _normalize_value(value: object) -> Any:
    if isinstance(value, str):
        return unescape(value).strip()
    if isinstance(value, dict):
        return _normalize_mapping(value)
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value
