"""Content completeness and ordering checks for accepted slide plans."""

from __future__ import annotations

from localdeck.inputs.models import OutlineDocument
from localdeck.planning.models import SlidePlan
from localdeck.quality.deck import QualityIssue, QualityReport


def inspect_content(
    outline: OutlineDocument, plan: SlidePlan
) -> QualityReport:
    """Validate section coverage, order, and evidence display requirements."""
    issues: list[QualityIssue] = []
    expected = [
        (chapter_index, section_index)
        for chapter_index, chapter in enumerate(outline.chapters, start=1)
        for section_index, _ in enumerate(chapter.sections, start=1)
    ]
    actual = [
        (slide.chapter_index, slide.section_index)
        for slide in plan.slides
        if slide.chapter_index is not None and slide.section_index is not None
    ]
    unique_actual = list(dict.fromkeys(actual))
    missing = [section for section in expected if section not in unique_actual]
    for chapter_index, section_index in missing:
        issues.append(
            QualityIssue(
                code="missing-section",
                message=(
                    f"Outline section {chapter_index}.{section_index} has no slide"
                ),
            )
        )
    present_expected_order = [item for item in expected if item in unique_actual]
    if unique_actual != present_expected_order:
        issues.append(
            QualityIssue(
                code="section-order",
                message="Slides do not preserve the outline section order",
            )
        )
    for slide in plan.slides:
        if slide.evidence_ids and not (slide.source_footer or "").strip():
            issues.append(
                QualityIssue(
                    code="missing-source-footer",
                    message="Evidence-backed slide has no visible source footer",
                    slide_index=slide.index,
                )
            )
    return QualityReport(passed=not issues, issues=tuple(issues))
