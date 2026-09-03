"""Small telemetry models used by the local comparison report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RouteMetrics(BaseModel):
    """Non-sensitive timing and repair counters for one visual route."""

    model_config = ConfigDict(frozen=True)

    route: Literal["template", "html"]
    duration_seconds: float = Field(ge=0)
    model_calls: int = Field(default=0, ge=0)
    repairs: int = Field(default=0, ge=0)
    fallback_slides: tuple[str, ...] = ()
