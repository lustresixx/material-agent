from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from localdeck.inputs.models import OutlineDocument
from localdeck.research.coordinator import ResearchCoordinator
from localdeck.research.models import PageEvidence, SearchHit


class TrackingSearch:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls: list[str] = []

    async def search(
        self, query: str, *, domain: str | None = None
    ) -> list[SearchHit]:
        self.calls.append(query)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        number = len(self.calls)
        return [
            SearchHit(
                title=f"Source {number}",
                url=f"https://huawei.com/source-{number}",
                snippet="Public summary",
            )
        ]


class FakeReader:
    async def read(self, url: str) -> PageEvidence:
        return PageEvidence(
            url=url,
            title="Official source",
            text=(
                "This is a sufficiently detailed public evidence statement "
                "for a slide."
            ),
            accessed_at=datetime.now(UTC),
        )


async def test_researches_one_task_per_section_with_bounded_concurrency() -> None:
    outline = OutlineDocument(
        title="Partnership",
        chapters=[
            {"chapter_title": "One", "sections": ["A", "B", "C"]},
            {"chapter_title": "Two", "sections": ["D", "E"]},
        ],
    )
    search = TrackingSearch()

    packets = await ResearchCoordinator(
        search=search, reader=FakeReader(), concurrency=2
    ).research(outline)

    assert len(search.calls) == 5
    assert search.max_active == 2
    assert [(packet.chapter_index, packet.section_index) for packet in packets] == [
        (1, 1),
        (1, 2),
        (1, 3),
        (2, 1),
        (2, 2),
    ]
    assert all(claim.evidence_ids for packet in packets for claim in packet.claims)
