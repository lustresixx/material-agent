from __future__ import annotations

from localdeck.generation.template_engine.matcher import ReuseMode, match_plan
from localdeck.planning.models import ContentBlock, SlidePlan, SlideSpec
from localdeck.templates.models import CapacityProfile, LayoutFrame, NarrativeRole


def _slide(index: int, *, text: str, image_count: int = 0) -> SlideSpec:
    blocks = [ContentBlock(kind="text", text=text)]
    blocks.extend(ContentBlock(kind="image") for _ in range(image_count))
    return SlideSpec(
        index=index,
        slide_id=f"slide-{index}",
        role=NarrativeRole.CONTENT,
        chapter_index=1,
        section_index=index,
        title=f"Section {index}",
        core_message=text,
        content_blocks=tuple(blocks),
        visual_intent="Content",
    )


def _frame(
    slide_number: int,
    family: str,
    *,
    characters: int,
    items: int = 4,
    images: int = 0,
    role: NarrativeRole = NarrativeRole.CONTENT,
) -> LayoutFrame:
    return LayoutFrame(
        layout_id=f"frame-{slide_number}",
        source_slide_number=slide_number,
        role=role,
        family=family,
        capacity=CapacityProfile(
            max_characters=characters, max_items=items, max_images=images
        ),
    )


def test_frame_that_cannot_fit_never_outranks_frame_that_can() -> None:
    plan = SlidePlan(max_slides=1, slides=(_slide(1, text="x" * 120),))
    frames = [
        _frame(1, "perfect-role-small", characters=40),
        _frame(2, "roomy", characters=200),
    ]

    decision = match_plan(plan, frames).decisions[0]

    assert decision.reuse_mode == ReuseMode.SOURCE_FRAME
    assert decision.source_slide_number == 2
    assert decision.score_breakdown["capacity"] > 0


def test_matcher_accounts_for_images_and_adjacent_silhouette() -> None:
    plan = SlidePlan(
        max_slides=2,
        slides=(
            _slide(1, text="first", image_count=1),
            _slide(2, text="second", image_count=1),
        ),
    )
    frames = [
        _frame(1, "image-left", characters=100, images=1),
        _frame(2, "image-right", characters=100, images=1),
        _frame(3, "text-only", characters=100, images=0),
    ]

    decisions = match_plan(plan, frames).decisions

    assert [decision.family for decision in decisions] == ["image-left", "image-right"]
    assert all(decision.source_slide_number != 3 for decision in decisions)


def test_matcher_emits_explicit_derived_layout_when_no_frame_fits() -> None:
    plan = SlidePlan(max_slides=1, slides=(_slide(1, text="x" * 200),))

    decision = match_plan(
        plan, [_frame(1, "small", characters=10)]
    ).decisions[0]

    assert decision.reuse_mode == ReuseMode.DERIVED_LAYOUT
    assert decision.source_slide_number is None
