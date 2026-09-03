"""Immutable data models for an inspected PowerPoint template package."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NarrativeRole(StrEnum):
    """Narrative purposes supported by template frames and slide plans."""

    COVER = "cover"
    AGENDA = "agenda"
    CHAPTER = "chapter"
    CONTENT = "content"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    DATA = "data"
    CASE_STUDY = "case-study"
    SOLUTION = "solution"
    SUMMARY = "summary"
    CLOSING = "closing"


class SlotType(StrEnum):
    """Semantic types for replaceable template regions."""

    TITLE = "title"
    BODY = "body"
    IMAGE = "image"
    METRIC = "metric"
    TABLE = "table"
    CHART = "chart"
    SOURCE = "source"
    OTHER = "other"


class EditPolicy(StrEnum):
    """Permitted operations for a source shape or reusable component."""

    PRESERVE_ONLY = "preserve_only"
    REPLACE_TEXT = "replace_text"
    REPLACE_IMAGE = "replace_image"
    REPLACE_DATA = "replace_data"
    DELETE = "delete"


class ImmutableTemplateModel(BaseModel):
    """Common immutable configuration for template package records."""

    model_config = ConfigDict(frozen=True)


class CapacityProfile(ImmutableTemplateModel):
    """Content limits used to avoid shrinking typography silently."""

    max_characters: int = Field(default=0, ge=0)
    max_items: int = Field(default=0, ge=0)
    max_images: int = Field(default=0, ge=0)


class EditableSlot(ImmutableTemplateModel):
    """One editable source shape in a reusable layout frame."""

    source_shape_id: int = Field(ge=1)
    name: str = Field(min_length=1)
    slot_type: SlotType
    edit_policy: EditPolicy
    capacity: CapacityProfile = Field(default_factory=CapacityProfile)
    x: float = 0
    y: float = 0
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)


class LayoutFrame(ImmutableTemplateModel):
    """A source slide that can be cloned for a planned narrative role."""

    layout_id: str = Field(min_length=1)
    source_slide_number: int = Field(ge=1)
    role: NarrativeRole
    family: str = Field(min_length=1)
    capacity: CapacityProfile = Field(default_factory=CapacityProfile)
    editable_slots: tuple[EditableSlot, ...] = ()
    preserve_shape_ids: tuple[int, ...] = ()
    source_shape_ids: tuple[int, ...] = ()
    classification_confidence: float = Field(default=0.0, ge=0, le=1)

    @field_validator("preserve_shape_ids")
    @classmethod
    def validate_shape_ids(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        """Keep source shape references positive and unambiguous."""
        if any(value < 1 for value in values):
            raise ValueError("source shape IDs must be positive")
        if len(values) != len(set(values)):
            raise ValueError("source shape IDs cannot contain duplicates")
        return values


class ComponentSpec(ImmutableTemplateModel):
    """Reusable group of source shapes approved for derived layouts."""

    component_id: str = Field(min_length=1)
    source_slide_number: int = Field(ge=1)
    source_shape_ids: tuple[int, ...] = Field(min_length=1)
    slot_type: SlotType
    edit_policy: EditPolicy
    capacity: CapacityProfile = Field(default_factory=CapacityProfile)
    x: float = 0
    y: float = 0
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)

    @field_validator("source_shape_ids")
    @classmethod
    def validate_source_shape_ids(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        """Reject invalid or repeated component shape references."""
        if any(value < 1 for value in values):
            raise ValueError("source shape IDs must be positive")
        if len(values) != len(set(values)):
            raise ValueError("source shape IDs cannot contain duplicates")
        return values


class TemplateManifest(ImmutableTemplateModel):
    """Identity and inventory summary for one imported source deck."""

    template_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    slide_count: int = Field(ge=1)
    format_version: int = Field(default=1, ge=1)


class ThemeProfile(ImmutableTemplateModel):
    """Template-derived page geometry and constrained design tokens."""

    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    font_families: tuple[str, ...] = Field(min_length=1)
    palette: tuple[str, ...] = Field(min_length=1)
    spacing: tuple[float, ...] = Field(min_length=1)


class TemplatePackage(ImmutableTemplateModel):
    """Resolved paths for all durable artifacts of an imported template."""

    root: Path
    manifest: Path
    theme: Path
    layouts: Path
    components: Path
    source: Path

    @field_validator("root", "manifest", "theme", "layouts", "components", "source")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        """Resolve paths before enforcing the package boundary."""
        return value.expanduser().resolve()

    @model_validator(mode="after")
    def ensure_artifacts_are_inside_root(self) -> TemplatePackage:
        """Prevent a package manifest from referencing arbitrary local files."""
        artifact_paths = (
            self.manifest,
            self.theme,
            self.layouts,
            self.components,
            self.source,
        )
        if any(not path.is_relative_to(self.root) for path in artifact_paths):
            raise ValueError("artifact path is outside template package root")
        return self


class TemplateInspection(ImmutableTemplateModel):
    """Complete deterministic inventory produced before package persistence."""

    manifest: TemplateManifest
    theme: ThemeProfile
    layouts: tuple[LayoutFrame, ...]
    components: tuple[ComponentSpec, ...]
