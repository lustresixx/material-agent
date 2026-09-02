"""Validated data contracts shared by CLI, agents, tools, and renderers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RunStage(StrEnum):
    """Stable names for the observable pipeline stages."""

    RESEARCH = "research"
    DESIGN = "design"
    EXPORT = "export"
    VERIFY = "verify"


class StageRecord(BaseModel):
    """Status and diagnostic output for one pipeline stage."""

    status: Literal["pending", "running", "completed", "failed"] = "pending"
    artifact: Path | None = None
    error: str | None = None


class GenerationRequest(BaseModel):
    """User-controlled presentation request after CLI validation."""

    topic: str = Field(min_length=1, max_length=2000)
    slides: int = Field(default=6, ge=1, le=30)
    language: Literal["zh", "en"] = "zh"
    aspect_ratio: Literal["16:9", "4:3"] = "16:9"
    output: Path

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, value: str) -> str:
        """Trim surrounding whitespace while preserving intentional line breaks."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("topic cannot be empty")
        return normalized

    @field_validator("output")
    @classmethod
    def normalize_output(cls, value: Path) -> Path:
        """Require the only output format supported by the MVP."""

        if value.suffix.lower() != ".pptx":
            raise ValueError("output must use the .pptx extension")
        return value.expanduser().resolve()


class InspectionIssue(BaseModel):
    """One machine-readable problem found in a generated HTML slide."""

    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    selector: str | None = None


class InspectionReport(BaseModel):
    """Quality result and evidence for a single HTML slide."""

    html_file: Path
    passed: bool
    width: int
    height: int
    issues: list[InspectionIssue] = Field(default_factory=list)
    screenshot: Path | None = None


class RunManifest(BaseModel):
    """Durable, incrementally updated record of one generation run."""

    run_id: str
    workspace: Path
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stages: dict[RunStage, StageRecord] = Field(
        default_factory=lambda: {stage: StageRecord() for stage in RunStage}
    )

    def start_stage(self, stage: RunStage) -> None:
        """Mark a stage as running while clearing stale terminal fields."""

        self.stages[stage] = StageRecord(status="running")

    def complete_stage(self, stage: RunStage, artifact: Path) -> None:
        """Record successful completion and its primary artifact."""

        self.stages[stage] = StageRecord(status="completed", artifact=artifact)

    def fail_stage(self, stage: RunStage, error: str) -> None:
        """Record a concise user-facing failure reason."""

        self.stages[stage] = StageRecord(status="failed", error=error)


class GenerationResult(BaseModel):
    """Final paths returned to API and CLI callers."""

    output: Path
    workspace: Path
    manuscript: Path
    slides_dir: Path
    manifest: Path
