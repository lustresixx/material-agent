from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from localdeck.research.models import PageEvidence, SearchHit
from localdeck.research.source_policy import (
    Confidence,
    SourcePolicy,
    canonicalize_url,
    deduplicate_hits,
)


def test_official_domains_rank_above_media() -> None:
    policy = SourcePolicy(customer_domains={"tongji.edu.cn"})
    hits = [
        SearchHit(title="Media", url="https://example.com/report", snippet="x"),
        SearchHit(title="Huawei", url="https://huawei.com/cn/news", snippet="x"),
        SearchHit(title="Tongji", url="https://www.tongji.edu.cn/news", snippet="x"),
        SearchHit(title="Ministry", url="https://www.moe.gov.cn/news", snippet="x"),
    ]

    ranked = policy.rank(hits)

    assert {hit.title for hit in ranked[:3]} == {"Huawei", "Tongji", "Ministry"}
    assert ranked[-1].title == "Media"


def test_duplicate_canonical_urls_collapse() -> None:
    hits = [
        SearchHit(
            title="A",
            url="HTTPS://Huawei.com/report/?utm_source=test&id=3#top",
            snippet="first",
        ),
        SearchHit(
            title="B", url="https://huawei.com/report?id=3", snippet="second"
        ),
    ]

    assert canonicalize_url(hits[0].url) == "https://huawei.com/report?id=3"
    assert len(deduplicate_hits(hits)) == 1


def test_missing_publication_date_remains_none() -> None:
    evidence = PageEvidence(
        url="https://huawei.com/report", title="Report", text="Evidence"
    )

    assert evidence.published_at is None


def test_search_snippet_cannot_support_precise_high_confidence_claim() -> None:
    policy = SourcePolicy()
    hit = SearchHit(
        title="Snippet",
        url="https://huawei.com/report",
        snippet="Revenue was 123.45 billion in 2025.",
        published_at=date(2026, 1, 1),
    )

    assert policy.confidence(hit, page=None, precise=True) == Confidence.LOW


@pytest.mark.parametrize("url", ["file:///secret", "ftp://example.com/a"])
def test_non_http_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match="HTTP"):
        SearchHit(title="bad", url=url, snippet="x")
