"""Validated data contracts shared by CLI, agents, tools, and renderers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RunStage(StrEnum):
    """Stable names for the observable pipeline stages."""

    RESEARCH = "research"
    DESIGN = "design"
    EXPORT = "export"
    VERIFY = "verify"


class TemplateRunStage(StrEnum):
    """Observable stages of the structured template-aware pipeline."""

    INPUT = "input"
    TEMPLATE = "template"
    RESEARCH = "research"
    PLAN = "plan"
    TEMPLATE_ROUTE = "template-route"
    HTML_ROUTE = "html-route"
    QUALITY = "quality"
    COMPARISON = "comparison"
    PUBLISH = "publish"


class GenerationRoute(StrEnum):
    """Available visual generation engines for a template-aware run."""

    TEMPLATE = "template"
    HTML = "html"


class StageRecord(BaseModel):
    """Status and diagnostic output for one pipeline stage."""

    status: Literal["pending", "running", "completed", "failed"] = "pending"
    artifact: Path | None = None
    error: str | None = None


class TemplateRouteRecord(BaseModel):
    """Terminal state and safe telemetry for one visual route."""

    status: Literal["pending", "running", "completed", "failed", "skipped"] = (
        "pending"
    )
    artifact: Path | None = None
    error: str | None = None
    plan_digest: str | None = None
    duration_seconds: float = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    repairs: int = Field(default=0, ge=0)
    fallback_slides: tuple[str, ...] = ()
    quality_issues: tuple[str, ...] = ()


class TemplateRunManifest(BaseModel):
    """Durable state for a dual-route run, written after every stage."""

    run_id: str
    workspace: Path
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stage_order: list[str] = Field(default_factory=list)
    stages: dict[str, StageRecord] = Field(default_factory=dict)
    routes: dict[GenerationRoute, TemplateRouteRecord] = Field(
        default_factory=lambda: {
            route: TemplateRouteRecord() for route in GenerationRoute
        }
    )
    timings: dict[str, float] = Field(default_factory=dict)
    plan_digest: str | None = None


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


class TemplateGenerationRequest(BaseModel):
    """Validated request for structured, template-aware deck generation."""

    model_config = ConfigDict(frozen=True)

    outline: Path
    template: str
    routes: tuple[GenerationRoute, ...] = (
        GenerationRoute.TEMPLATE,
        GenerationRoute.HTML,
    )
    max_slides: int = Field(default=30, ge=1, le=30)
    language: Literal["zh", "en"] = "zh"
    output_dir: Path

    @field_validator("outline", "output_dir")
    @classmethod
    def resolve_request_path(cls, value: Path) -> Path:
        """Resolve request paths so downstream stages share stable locations."""
        return value.expanduser().resolve()

    @field_validator("template")
    @classmethod
    def resolve_template_path(cls, value: str) -> str:
        """Resolve the editable source template supplied by the user."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("template cannot be blank")
        return str(Path(normalized).expanduser().resolve())

    @field_validator("routes")
    @classmethod
    def validate_routes(
        cls, values: tuple[GenerationRoute, ...]
    ) -> tuple[GenerationRoute, ...]:
        """Require at least one unique supported generation route."""
        if not values:
            raise ValueError("routes must contain at least one route")
        if len(values) != len(set(values)):
            raise ValueError("routes cannot contain duplicates")
        return values


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


class TemplateGenerationResult(BaseModel):
    """Published and retained artifacts from a template-aware run."""

    output_dir: Path
    workspace: Path
    manifest: Path
    plan: Path
    template_output: Path | None = None
    html_output: Path | None = None
    comparison: Path | None = None
