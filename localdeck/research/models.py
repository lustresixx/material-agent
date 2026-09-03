"""Validated local models for public search results and page evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PublicEvidenceModel(BaseModel):
    """Reject unknown remote fields so credentials cannot be persisted."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class SearchHit(PublicEvidenceModel):
    """One unverified result returned by a public search provider."""

    title: str = Field(min_length=1)
    url: str
    snippet: str = ""
    publisher: str | None = None
    published_at: date | None = None

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        """Keep local-file and executable schemes out of research artifacts."""
        normalized = value.strip()
        parts = urlsplit(normalized)
        if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
            raise ValueError("evidence URL must use HTTP or HTTPS")
        return normalized


class PageEvidence(PublicEvidenceModel):
    """Fetched page content that may support claims in the presentation."""

    url: str
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    publisher: str | None = None
    published_at: date | None = None
    accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("url")
    @classmethod
    def require_http_url(cls, value: str) -> str:
        """Apply the same safe URL boundary used by search results."""
        return SearchHit.require_http_url(value)
