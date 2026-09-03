"""Deterministic allocation of mandatory and optional presentation pages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from localdeck.inputs.models import OutlineDocument
from localdeck.research.models import ResearchPacket


class SectionAllocation(BaseModel):
    model_config = ConfigDict(frozen=True)

    chapter_index: int = Field(ge=1)
    section_index: int = Field(ge=1)
    section_title: str = Field(min_length=1)
    pages: int = Field(ge=1, le=3)


class Pagination(BaseModel):
    model_config = ConfigDict(frozen=True)

    sections: tuple[SectionAllocation, ...]
    chapter_dividers: tuple[int, ...]
    total_slides: int = Field(ge=1, le=30)


def paginate(
    outline: OutlineDocument,
    packets: list[ResearchPacket],
    *,
    max_slides: int,
) -> Pagination:
    """Allocate pages without ever dropping or reordering a user section."""
    if not 1 <= max_slides <= 30:
        raise ValueError("max_slides must be between 1 and 30")
    packet_map = {
        (packet.chapter_index, packet.section_index): packet for packet in packets
    }
    section_keys = [
        (chapter_index, section_index, section)
        for chapter_index, chapter in enumerate(outline.chapters, start=1)
        for section_index, section in enumerate(chapter.sections, start=1)
    ]
    mandatory = 3 + len(section_keys)
    if mandatory > max_slides:
        raise ValueError(
            f"max_slides={max_slides} cannot cover all {len(section_keys)} sections"
        )
    remaining = max_slides - mandatory
    desired = {
        (chapter_index, section_index): _desired_pages(
            packet_map.get((chapter_index, section_index))
        )
        for chapter_index, section_index, _ in section_keys
    }
    pages = {key: 1 for key in desired}
    candidates = sorted(
        desired,
        key=lambda key: _priority(key, desired, packet_map),
        reverse=True,
    )
    for key in candidates:
        while pages[key] < desired[key] and remaining > 0:
            pages[key] += 1
            remaining -= 1
    divider_count = min(len(outline.chapters), remaining)
    dividers = tuple(range(1, divider_count + 1))
    allocations = tuple(
        SectionAllocation(
            chapter_index=chapter_index,
            section_index=section_index,
            section_title=section,
            pages=pages[(chapter_index, section_index)],
        )
        for chapter_index, section_index, section in section_keys
    )
    total = 3 + len(dividers) + sum(item.pages for item in allocations)
    return Pagination(
        sections=allocations,
        chapter_dividers=dividers,
        total_slides=total,
    )


def _desired_pages(packet: ResearchPacket | None) -> int:
    if packet is None:
        return 1
    if len(packet.claims) >= 6 or len(packet.assets) >= 3:
        return 3
    if len(packet.claims) >= 3 or packet.assets:
        return 2
    return 1


def _priority(
    key: tuple[int, int],
    desired: dict[tuple[int, int], int],
    packets: dict[tuple[int, int], ResearchPacket],
) -> tuple[int, int]:
    packet = packets.get(key)
    return desired[key], len(packet.claims) if packet is not None else 0
