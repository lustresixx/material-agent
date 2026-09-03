from __future__ import annotations

import pytest

from localdeck.planning.copywriter import SharedCopy, prepare_shared_copy
from localdeck.planning.models import ContentBlock, SlidePlan, SlideSpec
from localdeck.research.models import EvidenceRecord, PageEvidence
from localdeck.templates.models import NarrativeRole


def _slide(*, text: str, evidence_ids: tuple[str, ...] = ("e-1",)) -> SlideSpec:
    return SlideSpec(
        index=1,
        slide_id="section-01-01-01",
        role=NarrativeRole.CONTENT,
        chapter_index=1,
        section_index=1,
        title="经营情况",
        core_message=text,
        content_blocks=(ContentBlock(kind="text", text=text),),
        evidence_ids=evidence_ids,
        visual_intent="Executive fact",
        source_footer="来源\uFF1A一份非常长的官方报告标题需要被压缩以适应模板底部来源区域",
    )


def _evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="e-1",
        page=PageEvidence(
            url="https://huawei.com/report",
            title="Huawei Annual Report",
            text="Verified public evidence.",
            publisher="Huawei",
        ),
    )


def test_both_routes_receive_byte_identical_shared_copy() -> None:
    shared = prepare_shared_copy(
        SlidePlan(max_slides=1, slides=(_slide(text="Revenue increased."),)),
        [_evidence()],
        footer_limit=36,
    )

    assert isinstance(shared, SharedCopy)
    assert shared.for_route("template") == shared.for_route("html")
    assert len(shared.plan.slides[0].source_footer or "") <= 36
    assert shared.evidence["e-1"].page.url == "https://huawei.com/report"


@pytest.mark.parametrize(
    "text",
    ["TODO: choose a layout", "Internal note: add chart", "此页需要放一张图"],
)
def test_internal_production_language_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="audience-facing"):
        prepare_shared_copy(
            SlidePlan(max_slides=1, slides=(_slide(text=text),)), [_evidence()]
        )


def test_precise_number_requires_evidence_id() -> None:
    with pytest.raises(ValueError, match="precise number"):
        prepare_shared_copy(
            SlidePlan(
                max_slides=1,
                slides=(
                    _slide(
                        text="Revenue reached 123.45 billion.", evidence_ids=()
                    ),
                ),
            ),
            [],
        )
