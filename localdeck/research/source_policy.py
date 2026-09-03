"""Authoritative-source ranking, URL deduplication, and confidence rules."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from localdeck.research.models import PageEvidence, SearchHit

_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


class Confidence(StrEnum):
    """Evidence confidence that can be attached to a public claim."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourcePolicy:
    """Prefer primary official sources and constrain unsupported precision."""

    def __init__(self, customer_domains: set[str] | None = None) -> None:
        self.customer_domains = {
            domain.casefold().removeprefix("www.")
            for domain in (customer_domains or set())
        }

    def rank(self, hits: list[SearchHit]) -> list[SearchHit]:
        """Deduplicate and rank sources from official to secondary."""
        return sorted(deduplicate_hits(hits), key=self._rank_key)

    def confidence(
        self,
        hit: SearchHit,
        *,
        page: PageEvidence | None,
        precise: bool,
    ) -> Confidence:
        """Require fetched page evidence before approving precise claims."""
        if page is None:
            return Confidence.LOW if precise else Confidence.MEDIUM
        if self._domain_score(hit.url) <= 1 and len(page.text.strip()) >= 40:
            return Confidence.HIGH
        return Confidence.MEDIUM

    def _rank_key(self, hit: SearchHit) -> tuple[int, int, str]:
        dated = 0 if hit.published_at is not None else 1
        return self._domain_score(hit.url), dated, hit.title.casefold()

    def _domain_score(self, url: str) -> int:
        host = _host(url)
        if _matches_domain(host, "huawei.com"):
            return 0
        if any(_matches_domain(host, domain) for domain in self.customer_domains):
            return 0
        if host.endswith(".gov.cn") or host == "gov.cn":
            return 1
        if host.endswith(".edu.cn") or host == "edu.cn":
            return 1
        return 4


def canonicalize_url(url: str) -> str:
    """Normalize one HTTP URL for deterministic deduplication."""
    parts = urlsplit(url.strip())
    if parts.scheme.casefold() not in {"http", "https"} or not parts.netloc:
        raise ValueError("evidence URL must use HTTP or HTTPS")
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_PARAMETERS
        )
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.casefold(), parts.netloc.casefold(), path, query, "")
    )


def deduplicate_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """Keep the first result for each canonical public URL."""
    unique: dict[str, SearchHit] = {}
    for hit in hits:
        unique.setdefault(canonicalize_url(hit.url), hit)
    return list(unique.values())


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").casefold().removeprefix("www.")


def _matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")
