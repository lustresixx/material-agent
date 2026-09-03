from __future__ import annotations

from localdeck.inputs.models import OutlineChapter, OutlineDocument
from localdeck.planning.models import SlidePlan, SlideSpec
from localdeck.quality.content import inspect_content
from localdeck.templates.models import NarrativeRole


def test_reports_missing_and_out_of_order_outline_sections() -> None:
    outline = OutlineDocument(
        title="合作交流",
        chapters=[
            OutlineChapter(chapter_title="第一章", sections=["第一节", "第二节"]),
            OutlineChapter(chapter_title="第二章", sections=["第三节"]),
        ],
    )
    plan = SlidePlan(
        max_slides=30,
        slides=(
            _slide(1, "cover", NarrativeRole.COVER),
            _slide(2, "section-02-01", NarrativeRole.CONTENT, 2, 1),
            _slide(3, "section-01-02", NarrativeRole.CONTENT, 1, 2),
        ),
    )

    report = inspect_content(outline, plan)

    assert not report.passed
    assert "missing-section" in report.codes
    assert "section-order" in report.codes


def test_requires_source_footer_when_slide_uses_evidence() -> None:
    outline = OutlineDocument(
        title="合作交流",
        chapters=[OutlineChapter(chapter_title="第一章", sections=["第一节"])],
    )
    plan = SlidePlan(
        max_slides=30,
        slides=(
            _slide(
                1,
                "section-01-01",
                NarrativeRole.CONTENT,
                1,
                1,
                evidence_ids=("evidence-1",),
            ),
        ),
    )

    report = inspect_content(outline, plan)

    assert "missing-source-footer" in report.codes


def _slide(
    index: int,
    slide_id: str,
    role: NarrativeRole,
    chapter_index: int | None = None,
    section_index: int | None = None,
    *,
    evidence_ids: tuple[str, ...] = (),
) -> SlideSpec:
    return SlideSpec(
        index=index,
        slide_id=slide_id,
        role=role,
        chapter_index=chapter_index,
        section_index=section_index,
        title=slide_id,
        core_message="核心信息",
        evidence_ids=evidence_ids,
        visual_intent="quality fixture",
    )
