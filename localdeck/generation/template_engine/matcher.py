"""Transparent deterministic matching of planned slides to source frames."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from localdeck.planning.models import SlidePlan, SlideSpec
from localdeck.templates.models import LayoutFrame, SlotType


class ReuseMode(StrEnum):
    """Whether a slide clones a source frame or composes approved components."""

    SOURCE_FRAME = "source-frame"
    DERIVED_LAYOUT = "derived-layout"


class FrameMatchDecision(BaseModel):
    """Auditable source-frame decision for one planned output slide."""

    model_config = ConfigDict(frozen=True)

    slide_id: str
    reuse_mode: ReuseMode
    source_slide_number: int | None = Field(default=None, ge=1)
    source_layout_id: str | None = None
    family: str
    score: float
    score_breakdown: dict[str, float]
    edit_targets: tuple[int, ...] = ()
    reasons: tuple[str, ...] = ()


class FrameMatchMap(BaseModel):
    """Ordered route-B frame decisions plus unused-source diagnostics."""

    model_config = ConfigDict(frozen=True)

    decisions: tuple[FrameMatchDecision, ...]
    omitted_source_slides: dict[int, str]


class _Requirements(BaseModel):
    model_config = ConfigDict(frozen=True)

    characters: int
    blocks: int
    images: int
    data_blocks: int


def match_plan(plan: SlidePlan, frames: list[LayoutFrame]) -> FrameMatchMap:
    """Match every slide, excluding frames that cannot fit before scoring."""
    decisions: list[FrameMatchDecision] = []
    used_source_slides: set[int] = set()
    previous_family: str | None = None
    for slide in plan.slides:
        requirements = _requirements(slide)
        candidates = [
            _score(slide, requirements, frame, previous_family)
            for frame in frames
            if _fits(requirements, frame)
        ]
        if not candidates:
            decision = FrameMatchDecision(
                slide_id=slide.slide_id,
                reuse_mode=ReuseMode.DERIVED_LAYOUT,
                family="derived-layout",
                score=0,
                score_breakdown={
                    "role": 0,
                    "capacity": 0,
                    "blocks": 0,
                    "images": 0,
                    "data": 0,
                    "diversity": 0,
                },
                reasons=("No source frame satisfies all hard capacity limits",),
            )
        else:
            decision = max(
                candidates,
                key=lambda item: (
                    item.score,
                    -int(item.source_slide_number or 0),
                ),
            )
            if decision.source_slide_number is not None:
                used_source_slides.add(decision.source_slide_number)
        decisions.append(decision)
        previous_family = decision.family

    omitted = {
        frame.source_slide_number: "Not selected by the deterministic frame matcher"
        for frame in frames
        if frame.source_slide_number not in used_source_slides
    }
    return FrameMatchMap(
        decisions=tuple(decisions), omitted_source_slides=omitted
    )


def _requirements(slide: SlideSpec) -> _Requirements:
    characters = len(slide.title)
    item_count = 0
    image_blocks = 0
    data_blocks = 0
    for block in slide.content_blocks:
        characters += len(block.heading or "") + len(block.text or "")
        characters += sum(len(item) for item in block.items)
        item_count += max(1, len(block.items))
        image_blocks += block.kind == "image"
        data_blocks += block.kind == "metric"
    return _Requirements(
        characters=characters,
        blocks=max(len(slide.content_blocks), item_count),
        images=max(image_blocks, len(slide.asset_ids)),
        data_blocks=data_blocks,
    )


def _fits(requirements: _Requirements, frame: LayoutFrame) -> bool:
    capacity = frame.capacity
    return (
        requirements.characters <= capacity.max_characters
        and requirements.blocks <= capacity.max_items
        and requirements.images <= capacity.max_images
    )


def _score(
    slide: SlideSpec,
    requirements: _Requirements,
    frame: LayoutFrame,
    previous_family: str | None,
) -> FrameMatchDecision:
    capacity = frame.capacity
    character_headroom = capacity.max_characters - requirements.characters
    block_headroom = capacity.max_items - requirements.blocks
    image_headroom = capacity.max_images - requirements.images
    supports_data = any(
        slot.slot_type in {SlotType.METRIC, SlotType.CHART, SlotType.TABLE}
        for slot in frame.editable_slots
    )
    breakdown = {
        "role": 40.0 if frame.role == slide.role else 4.0,
        "capacity": 20.0 + min(character_headroom / 100, 5.0),
        "blocks": 12.0 - min(block_headroom, 8),
        "images": 14.0 - min(image_headroom * 2, 10),
        "data": (
            10.0 if requirements.data_blocks and supports_data else 0.0
        ),
        "diversity": -25.0 if frame.family == previous_family else 5.0,
    }
    score = sum(breakdown.values()) + frame.classification_confidence * 5
    return FrameMatchDecision(
        slide_id=slide.slide_id,
        reuse_mode=ReuseMode.SOURCE_FRAME,
        source_slide_number=frame.source_slide_number,
        source_layout_id=frame.layout_id,
        family=frame.family,
        score=round(score, 3),
        score_breakdown=breakdown,
        edit_targets=tuple(slot.source_shape_id for slot in frame.editable_slots),
        reasons=(
            "Passed character, block, and image capacity gates",
            "Selected by deterministic weighted score",
        ),
    )
