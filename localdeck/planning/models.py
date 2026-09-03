"""Validated contracts shared by both visual generation routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from localdeck.templates.models import NarrativeRole


class PlanningModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class ContentBlock(PlanningModel):
    """Structured audience-facing content independent of visual layout."""

    kind: Literal["text", "bullets", "metric", "image", "source"]
    heading: str | None = None
    text: str | None = None
    items: tuple[str, ...] = ()


class SlideSpec(PlanningModel):
    """One evidence-backed slide consumed identically by both routes."""

    index: int = Field(ge=1)
    slide_id: str = Field(min_length=1)
    role: NarrativeRole
    chapter_index: int | None = Field(default=None, ge=1)
    section_index: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1)
    core_message: str = Field(min_length=1)
    content_blocks: tuple[ContentBlock, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    visual_intent: str = Field(min_length=1)
    preferred_layouts: tuple[str, ...] = ()
    source_footer: str | None = None


class SlidePlan(PlanningModel):
    """Accepted ordered slide plan with a hard publication limit."""

    max_slides: int = Field(ge=1, le=30)
    slides: tuple[SlideSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_budget_and_indices(self) -> SlidePlan:
        if len(self.slides) > self.max_slides:
            raise ValueError("slide plan exceeds max_slides")
        if [slide.index for slide in self.slides] != list(
            range(1, len(self.slides) + 1)
        ):
            raise ValueError("slide indices must be consecutive")
        return self
