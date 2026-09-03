"""Contracts for public visual assets collected during section research."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchAsset(BaseModel):
    """Locally cached official image with complete public provenance."""

    model_config = ConfigDict(frozen=True)

    asset_id: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_page: str
    direct_url: str
    local_path: Path

    @field_validator("source_page", "direct_url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        parts = urlsplit(value.strip())
        if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
            raise ValueError("asset URL must use HTTP or HTTPS")
        return value.strip()

    @field_validator("local_path")
    @classmethod
    def resolve_local_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class AssetCollector(Protocol):
    """Optional provider for official images found on a fetched page."""

    async def collect(
        self, page: object, directory: Path
    ) -> list[ResearchAsset]:
        """Download suitable public images and retain their provenance."""
        ...
