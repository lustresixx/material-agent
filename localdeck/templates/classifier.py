"""Deterministic narrative-role and layout-family classification heuristics."""

from __future__ import annotations

from localdeck.templates.models import NarrativeRole


def classify_slide(
    *, slide_number: int, text: str, image_count: int, body_slot_count: int
) -> tuple[NarrativeRole, str, float]:
    """Return a conservative role, family, and confidence for one source slide."""
    normalized = text.casefold()
    if slide_number == 1:
        return NarrativeRole.COVER, "cover", 0.95
    if any(token in normalized for token in ("目录", "议程", "agenda")):
        return NarrativeRole.AGENDA, "agenda", 0.9
    if any(token in normalized for token in ("谢谢", "thank you")):
        return NarrativeRole.CLOSING, "closing", 0.9
    if any(token in normalized for token in ("总结", "展望", "建议")):
        return NarrativeRole.SUMMARY, "summary", 0.75
    if image_count and body_slot_count:
        return NarrativeRole.CONTENT, "title-body-image", 0.8
    if body_slot_count > 1:
        return NarrativeRole.CONTENT, "title-multi-body", 0.7
    return NarrativeRole.CONTENT, "title-body", 0.65
