from __future__ import annotations

from localdeck.inputs.models import OutlineDocument
from localdeck.planning.planner import SlidePlanner
from localdeck.research.models import (
    EvidenceRecord,
    PageEvidence,
    ResearchClaim,
    ResearchPacket,
)
from localdeck.templates.models import NarrativeRole


def test_slide_planner_orders_structure_and_preserves_lineage() -> None:
    outline = OutlineDocument(
        title="Partnership",
        chapters=[
            {"chapter_title": "Chapter One", "sections": ["Section A", "Section B"]},
            {"chapter_title": "Chapter Two", "sections": ["Section C"]},
        ],
    )
    packets = [
        _packet(1, 1, "Chapter One", "Section A"),
        _packet(1, 2, "Chapter One", "Section B"),
        _packet(2, 1, "Chapter Two", "Section C"),
    ]

    plan = SlidePlanner().plan(outline, packets, max_slides=12)

    assert plan.slides[0].role == NarrativeRole.COVER
    assert plan.slides[1].role == NarrativeRole.AGENDA
    assert plan.slides[-1].role == NarrativeRole.CLOSING
    content = [slide for slide in plan.slides if slide.role == NarrativeRole.CONTENT]
    first_pages = [slide for slide in content if slide.slide_id.endswith("-01")]
    assert [slide.title for slide in first_pages] == [
        "Section A",
        "Section B",
        "Section C",
    ]
    assert all(slide.evidence_ids for slide in content)
    assert [slide.index for slide in plan.slides] == list(
        range(1, len(plan.slides) + 1)
    )
    assert len(plan.slides) <= 12


def _packet(
    chapter_index: int,
    section_index: int,
    chapter_title: str,
    section_title: str,
) -> ResearchPacket:
    page = PageEvidence(
        url=f"https://huawei.com/{chapter_index}/{section_index}",
        title="Official source",
        text="Verified evidence for the planned slide.",
    )
    return ResearchPacket(
        chapter_index=chapter_index,
        section_index=section_index,
        chapter_title=chapter_title,
        section_title=section_title,
        claims=(
            ResearchClaim(
                claim_id=f"c-{chapter_index}-{section_index}",
                text="Audience-facing conclusion",
                evidence_ids=(f"e-{chapter_index}-{section_index}",),
            ),
        ),
        evidence=(
            EvidenceRecord(
                evidence_id=f"e-{chapter_index}-{section_index}", page=page
            ),
        ),
    )
