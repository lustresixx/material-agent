from __future__ import annotations

from pathlib import Path

from localdeck.inputs.models import OutlineDocument
from localdeck.research.assets import ResearchAsset
from localdeck.research.coordinator import ResearchCoordinator
from localdeck.research.models import PageEvidence, SearchHit


class SearchWithTwoResults:
    async def search(
        self, query: str, *, domain: str | None = None
    ) -> list[SearchHit]:
        return [
            SearchHit(
                title="Good", url="https://huawei.com/good", snippet="Good summary"
            ),
            SearchHit(
                title="Broken",
                url="https://huawei.com/broken",
                snippet="Broken summary",
            ),
        ]


class PartlyFailingReader:
    async def read(self, url: str) -> PageEvidence:
        if url.endswith("broken"):
            raise RuntimeError("page unavailable")
        return PageEvidence(
            url=url,
            title="Good official page",
            text="Verified public information with enough detail to support the claim.",
        )


class FakeAssetCollector:
    async def collect(self, page: PageEvidence, directory: Path) -> list[ResearchAsset]:
        local_path = directory / "official.png"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"image")
        return [
            ResearchAsset(
                asset_id="asset-1",
                width=1200,
                height=800,
                source_page=page.url,
                direct_url="https://huawei.com/media/official.png",
                local_path=local_path,
            )
        ]


async def test_research_pipeline_writes_complete_packet_tree(tmp_path: Path) -> None:
    outline = OutlineDocument(
        title="Partnership",
        chapters=[{"chapter_title": "Chapter", "sections": ["Section"]}],
    )
    coordinator = ResearchCoordinator(
        search=SearchWithTwoResults(),
        reader=PartlyFailingReader(),
        concurrency=2,
        asset_collector=FakeAssetCollector(),
    )

    packets = await coordinator.research(outline, output_dir=tmp_path / "research")

    packet = packets[0]
    assert packet.claims[0].evidence_ids
    assert packet.failed_pages[0].url.endswith("broken")
    assert packet.evidence
    assert packet.assets[0].width == 1200
    assert packet.assets[0].height == 800
    assert packet.assets[0].source_page == "https://huawei.com/good"
    assert packet.assets[0].direct_url.startswith("https://")
    assert packet.assets[0].local_path.is_file()
    section_dir = tmp_path / "research" / "chapter_01" / "section_01"
    assert {
        "research.json",
        "sources.json",
        "assets.json",
        "summary.txt",
    }.issubset({path.name for path in section_dir.iterdir()})
