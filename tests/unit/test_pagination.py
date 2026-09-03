from __future__ import annotations

from localdeck.inputs.models import OutlineDocument
from localdeck.planning.pagination import paginate
from localdeck.research.models import ResearchClaim, ResearchPacket


def _outline() -> OutlineDocument:
    return OutlineDocument(
        title="携手同济大学\uFF0C共建数智化新生态",
        chapters=[
            {"chapter_title": "1. 华为公司介绍", "sections": ["1.1 经营", "1.2 教育"]},
            {"chapter_title": "2. AI赋能", "sections": ["2.1 中心", "2.2 AIPL"]},
            {"chapter_title": "3. 案例", "sections": ["3.1 高校案例"]},
            {"chapter_title": "4. 合作展望", "sections": ["4.1 机会", "4.2 建议"]},
        ],
    )


def _packets(outline: OutlineDocument) -> list[ResearchPacket]:
    packets = []
    for chapter_index, chapter in enumerate(outline.chapters, start=1):
        for section_index, section in enumerate(chapter.sections, start=1):
            claim_count = 7 if (chapter_index, section_index) == (2, 1) else 2
            claims = tuple(
                ResearchClaim(
                    claim_id=f"c-{chapter_index}-{section_index}-{number}",
                    text=f"Claim {number}",
                    evidence_ids=(f"e-{number}",),
                )
                for number in range(1, claim_count + 1)
            )
            packets.append(
                ResearchPacket(
                    chapter_index=chapter_index,
                    section_index=section_index,
                    chapter_title=chapter.chapter_title,
                    section_title=section,
                    claims=claims,
                )
            )
    return packets


def test_pagination_preserves_sections_and_allocates_one_to_three_pages() -> None:
    outline = _outline()

    pagination = paginate(outline, _packets(outline), max_slides=30)

    assert pagination.total_slides <= 30
    assert [item.section_title for item in pagination.sections] == [
        section for chapter in outline.chapters for section in chapter.sections
    ]
    assert all(1 <= item.pages <= 3 for item in pagination.sections)
    complex_section = next(
        item
        for item in pagination.sections
        if (item.chapter_index, item.section_index) == (2, 1)
    )
    assert complex_section.pages == 3


def test_tight_budget_removes_dividers_before_required_sections() -> None:
    outline = _outline()
    mandatory = 3 + sum(len(chapter.sections) for chapter in outline.chapters)

    pagination = paginate(outline, _packets(outline), max_slides=mandatory)

    assert pagination.chapter_dividers == ()
    assert all(item.pages == 1 for item in pagination.sections)
    assert pagination.total_slides == mandatory
