"""Backend-neutral contracts for template-derived PPTX generation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from localdeck.templates.models import TemplateManifest


class FrameMap(BaseModel):
    """Ordered one-based source slide numbers used to build a new deck."""

    model_config = ConfigDict(frozen=True)

    source_slide_numbers: tuple[int, ...] = Field(min_length=1)

    @field_validator("source_slide_numbers")
    @classmethod
    def validate_slide_numbers(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        """Reject zero-based or negative references at the API boundary."""
        if any(value < 1 for value in values):
            raise ValueError("source slide numbers must be positive")
        return values


class TemplateDeckBackend(Protocol):
    """Common operations required by the template component route."""

    def inspect(self, source: Path) -> TemplateManifest:
        """Return a compact inventory for an editable source deck."""
        ...

    def create_from_map(
        self, source: Path, frame_map: FrameMap, output: Path
    ) -> Path:
        """Create an editable working deck from ordered source frames."""
        ...

    def replace_text(self, slide_index: int, shape_id: int, text: str) -> None:
        """Replace text in one stable source shape."""
        ...

    def replace_image(self, slide_index: int, shape_id: int, image: Path) -> None:
        """Replace one picture while retaining its frame geometry and crop."""
        ...

    def save(self, output: Path) -> Path:
        """Save the current working presentation."""
        ...
