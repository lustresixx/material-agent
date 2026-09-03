"""Static compatibility checks for model-generated slide HTML."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_REMOTE_URL = re.compile(
    r"(?:src|href)\s*=\s*['\"]\s*(?:https?:)?//|url\(\s*['\"]?\s*https?://",
    re.IGNORECASE,
)


class CompatibilityIssue(BaseModel):
    """One converter or local-security violation."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class CompatibilityReport(BaseModel):
    """Deterministic acceptance report for one complete HTML document."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    issues: tuple[CompatibilityIssue, ...] = ()


def inspect_html(source: str) -> CompatibilityReport:
    """Reject unsupported or network-active markup before browser rendering."""
    lowered = source.casefold()
    issues: dict[str, CompatibilityIssue] = {}
    if "<!doctype html" not in lowered or "<body" not in lowered:
        issues["incomplete-document"] = CompatibilityIssue(
            code="incomplete-document",
            message="Slide must be a complete HTML document with doctype and body",
        )
    if re.search(r"<\s*script\b", source, re.IGNORECASE):
        issues["script-not-allowed"] = CompatibilityIssue(
            code="script-not-allowed",
            message="Scripts are not allowed in slide HTML",
        )
    if re.search(r"<\s*(?:iframe|object|embed)\b", source, re.IGNORECASE):
        issues["embedded-content-not-allowed"] = CompatibilityIssue(
            code="embedded-content-not-allowed",
            message="Embedded active content is not allowed",
        )
    if _REMOTE_URL.search(source):
        issues["remote-resource"] = CompatibilityIssue(
            code="remote-resource",
            message="Remote resources are forbidden; use local assets only",
        )
    if "@font-face" in lowered or "@import" in lowered:
        issues["network-font-not-allowed"] = CompatibilityIssue(
            code="network-font-not-allowed",
            message="Font loading and CSS imports are forbidden",
        )
    result = tuple(issues.values())
    return CompatibilityReport(passed=not result, issues=result)
