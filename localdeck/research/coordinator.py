"""Bounded concurrent research for ordered outline sections."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from localdeck.inputs.models import OutlineDocument
from localdeck.research.assets import AssetCollector, ResearchAsset
from localdeck.research.models import (
    EvidenceRecord,
    FailedPage,
    PageEvidence,
    ResearchClaim,
    ResearchPacket,
)
from localdeck.research.providers import PageReader, SearchProvider
from localdeck.research.source_policy import SourcePolicy


@dataclass(frozen=True, slots=True)
class _SectionJob:
    chapter_index: int
    section_index: int
    chapter_title: str
    section_title: str


class ResearchCoordinator:
    """Research every section concurrently while retaining deterministic order."""

    def __init__(
        self,
        *,
        search: SearchProvider,
        reader: PageReader,
        concurrency: int,
        source_policy: SourcePolicy | None = None,
        asset_collector: AssetCollector | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("research concurrency must be positive")
        self.search = search
        self.reader = reader
        self.concurrency = concurrency
        self.source_policy = source_policy or SourcePolicy()
        self.asset_collector = asset_collector

    async def research(
        self, outline: OutlineDocument, output_dir: Path | None = None
    ) -> list[ResearchPacket]:
        """Run one bounded task per section and return original outline order."""
        jobs = [
            _SectionJob(
                chapter_index=chapter_index,
                section_index=section_index,
                chapter_title=chapter.chapter_title,
                section_title=section,
            )
            for chapter_index, chapter in enumerate(outline.chapters, start=1)
            for section_index, section in enumerate(chapter.sections, start=1)
        ]
        semaphore = asyncio.Semaphore(self.concurrency)
        root = output_dir.expanduser().resolve() if output_dir is not None else None

        async def run(job: _SectionJob) -> ResearchPacket:
            async with semaphore:
                return await self._research_section(outline.title, job, root)

        return list(await asyncio.gather(*(run(job) for job in jobs)))

    async def _research_section(
        self, deck_title: str, job: _SectionJob, root: Path | None
    ) -> ResearchPacket:
        hits = self.source_policy.rank(
            await self.search.search(
                f"{deck_title} {job.chapter_title} {job.section_title}"
            )
        )
        evidence: list[EvidenceRecord] = []
        failed: list[FailedPage] = []
        assets: list[ResearchAsset] = []
        section_dir = (
            root
            / f"chapter_{job.chapter_index:02d}"
            / f"section_{job.section_index:02d}"
            if root is not None
            else None
        )
        for hit in hits[:4]:
            try:
                page = await self.reader.read(hit.url)
            except Exception as error:
                failed.append(FailedPage(url=hit.url, error=str(error)))
                continue
            evidence_id = (
                f"evidence-{job.chapter_index:02d}-{job.section_index:02d}-"
                f"{len(evidence) + 1:02d}"
            )
            evidence.append(EvidenceRecord(evidence_id=evidence_id, page=page))
            if self.asset_collector is not None and section_dir is not None:
                assets.extend(
                    await self.asset_collector.collect(page, section_dir / "media")
                )

        claims = tuple(
            ResearchClaim(
                claim_id=(
                    f"claim-{job.chapter_index:02d}-{job.section_index:02d}-"
                    f"{index:02d}"
                ),
                text=_claim_text(record.page),
                evidence_ids=(record.evidence_id,),
            )
            for index, record in enumerate(evidence, start=1)
            if _claim_text(record.page)
        )
        packet = ResearchPacket(
            chapter_index=job.chapter_index,
            section_index=job.section_index,
            chapter_title=job.chapter_title,
            section_title=job.section_title,
            claims=claims,
            evidence=tuple(evidence),
            failed_pages=tuple(failed),
            assets=tuple(assets),
        )
        if section_dir is not None:
            _write_packet(section_dir, packet)
        return packet


def _claim_text(page: PageEvidence) -> str:
    normalized = " ".join(page.text.split())
    parts = re.split(r"(?<=[。\uFF01\uFF1F.!?])\s*", normalized, maxsplit=1)
    return parts[0][:500].strip()


def _write_packet(directory: Path, packet: ResearchPacket) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _write_json(directory / "research.json", packet.model_dump(mode="json"))
    _write_json(
        directory / "sources.json",
        [item.model_dump(mode="json") for item in packet.evidence],
    )
    _write_json(
        directory / "assets.json",
        [item.model_dump(mode="json") for item in packet.assets],
    )
    summary = "\n".join(claim.text for claim in packet.claims)
    (directory / "summary.txt").write_text(summary, encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
