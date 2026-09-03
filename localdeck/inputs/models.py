"""Validated contracts for structured presentation outlines."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class OutlineChapter(BaseModel):
    """One ordered chapter and its required section headings."""

    chapter_title: str = Field(min_length=1, max_length=200)
    sections: list[str] = Field(min_length=1, max_length=30)

    @field_validator("chapter_title")
    @classmethod
    def normalize_chapter_title(cls, value: str) -> str:
        """Trim a chapter title and reject whitespace-only input."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("chapter_title cannot be blank")
        return normalized

    @field_validator("sections")
    @classmethod
    def normalize_sections(cls, values: list[str]) -> list[str]:
        """Trim section headings and reject blank entries."""
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("sections cannot contain blank values")
        return normalized


class OutlineDocument(BaseModel):
    """Top-level structured input used to plan a presentation."""

    title: str = Field(min_length=1, max_length=300)
    chapters: list[OutlineChapter] = Field(min_length=1, max_length=20)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """Trim the document title and reject whitespace-only input."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("title cannot be blank")
        return normalized
