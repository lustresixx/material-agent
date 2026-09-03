"""Build a validated shared slide plan from outline and research packets."""

from __future__ import annotations

import json
from pathlib import Path

from localdeck.inputs.models import OutlineDocument
from localdeck.planning.models import ContentBlock, SlidePlan, SlideSpec
from localdeck.planning.pagination import paginate
from localdeck.research.models import ResearchPacket
from localdeck.templates.models import NarrativeRole

_SOURCE_SEPARATOR = "\uFF1B"


class SlidePlanner:
    """Create deterministic, evidence-linked slides within the hard budget."""

    def plan(
        self,
        outline: OutlineDocument,
        packets: list[ResearchPacket],
        *,
        max_slides: int,
        output: Path | None = None,
    ) -> SlidePlan:
        """Build and optionally persist an accepted shared slide plan."""
        pagination = paginate(outline, packets, max_slides=max_slides)
        packet_map = {
            (packet.chapter_index, packet.section_index): packet
            for packet in packets
        }
        allocation_map = {
            (item.chapter_index, item.section_index): item
            for item in pagination.sections
        }
        slides: list[SlideSpec] = []
        slides.append(
            _slide(
                slides,
                slide_id="cover",
                role=NarrativeRole.COVER,
                title=outline.title,
                core_message=outline.title,
                visual_intent="Minimal executive cover using template brand furniture",
                preferred_layouts=("cover",),
            )
        )
        slides.append(
            _slide(
                slides,
                slide_id="agenda",
                role=NarrativeRole.AGENDA,
                title="议程",
                core_message="围绕能力、方案、实践与合作形成完整交流路径",
                content_blocks=(
                    ContentBlock(
                        kind="bullets",
                        items=tuple(
                            chapter.chapter_title for chapter in outline.chapters
                        ),
                    ),
                ),
                visual_intent="Ordered chapter overview",
                preferred_layouts=("agenda", "title-multi-body"),
            )
        )
        for chapter_index, chapter in enumerate(outline.chapters, start=1):
            if chapter_index in pagination.chapter_dividers:
                slides.append(
                    _slide(
                        slides,
                        slide_id=f"chapter-{chapter_index:02d}",
                        role=NarrativeRole.CHAPTER,
                        chapter_index=chapter_index,
                        title=chapter.chapter_title,
                        core_message=chapter.chapter_title,
                        visual_intent="Restrained chapter transition",
                        preferred_layouts=("chapter", "cover"),
                    )
                )
            for section_index, section_title in enumerate(chapter.sections, start=1):
                packet = packet_map[(chapter_index, section_index)]
                allocation = allocation_map[(chapter_index, section_index)]
                for page_number in range(1, allocation.pages + 1):
                    slides.append(
                        _content_slide(
                            slides,
                            packet,
                            section_title,
                            page_number,
                            allocation.pages,
                        )
                    )
        slides.append(
            _slide(
                slides,
                slide_id="closing",
                role=NarrativeRole.CLOSING,
                title="合作展望与下一步",
                core_message="以可验证场景为起点\uFF0C形成联合规划与分阶段行动",
                content_blocks=(
                    ContentBlock(
                        kind="bullets",
                        items=("明确优先场景", "共建验证计划", "形成阶段性路线图"),
                    ),
                ),
                visual_intent="Executive action summary and closing",
                preferred_layouts=("closing", "summary"),
            )
        )
        plan = SlidePlan(max_slides=max_slides, slides=tuple(slides))
        if output is not None:
            destination = output.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return plan


def _content_slide(
    slides: list[SlideSpec],
    packet: ResearchPacket,
    section_title: str,
    page_number: int,
    page_count: int,
) -> SlideSpec:
    claims = list(packet.claims)
    selected = claims[page_number - 1 :: page_count] or claims[:1]
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id for claim in selected for evidence_id in claim.evidence_ids
        )
    )
    asset_ids = tuple(asset.asset_id for asset in packet.assets)
    title = (
        section_title
        if page_number == 1
        else f"{section_title}\uFF08{page_number}\uFF09"
    )
    footer_titles = [
        record.page.title
        for record in packet.evidence
        if record.evidence_id in evidence_ids
    ]
    return _slide(
        slides,
        slide_id=(
            f"section-{packet.chapter_index:02d}-{packet.section_index:02d}-"
            f"{page_number:02d}"
        ),
        role=NarrativeRole.CONTENT,
        chapter_index=packet.chapter_index,
        section_index=packet.section_index,
        title=title,
        core_message=selected[0].text if selected else section_title,
        content_blocks=(
            ContentBlock(kind="bullets", items=tuple(claim.text for claim in selected)),
        ),
        evidence_ids=evidence_ids,
        asset_ids=asset_ids,
        visual_intent="Evidence-led executive content with one dominant visual idea",
        preferred_layouts=("title-body-image", "title-body"),
        source_footer=(
            f"来源\uFF1A{_SOURCE_SEPARATOR.join(footer_titles[:2])}"
            if footer_titles
            else None
        ),
    )


def _slide(
    slides: list[SlideSpec],
    *,
    slide_id: str,
    role: NarrativeRole,
    title: str,
    core_message: str,
    visual_intent: str,
    preferred_layouts: tuple[str, ...],
    chapter_index: int | None = None,
    section_index: int | None = None,
    content_blocks: tuple[ContentBlock, ...] = (),
    evidence_ids: tuple[str, ...] = (),
    asset_ids: tuple[str, ...] = (),
    source_footer: str | None = None,
) -> SlideSpec:
    return SlideSpec(
        index=len(slides) + 1,
        slide_id=slide_id,
        role=role,
        chapter_index=chapter_index,
        section_index=section_index,
        title=title,
        core_message=core_message,
        content_blocks=content_blocks,
        evidence_ids=evidence_ids,
        asset_ids=asset_ids,
        visual_intent=visual_intent,
        preferred_layouts=preferred_layouts,
        source_footer=source_footer,
    )
