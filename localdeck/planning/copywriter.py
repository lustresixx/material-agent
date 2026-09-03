"""Prepare one immutable audience-facing copy payload for both visual routes."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from localdeck.planning.models import SlidePlan, SlideSpec
from localdeck.planning.sources import shorten_source_footer
from localdeck.research.models import EvidenceRecord

_INTERNAL_MARKERS = (
    "todo:",
    "internal note",
    "planning note",
    "choose a layout",
    "此页需要",
    "这里放",
)
_PRECISE_NUMBER = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:%|billion|million|亿元|万元|万|亿)", re.IGNORECASE
)


class SharedCopy(BaseModel):
    """Canonical copy and complete evidence registry shared byte-for-byte."""

    model_config = ConfigDict(frozen=True)

    plan: SlidePlan
    evidence: dict[str, EvidenceRecord]

    def for_route(self, route: Literal["template", "html"]) -> bytes:
        """Return canonical bytes; the route name cannot alter the payload."""
        del route
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def prepare_shared_copy(
    plan: SlidePlan,
    evidence: list[EvidenceRecord],
    *,
    footer_limit: int = 72,
) -> SharedCopy:
    """Validate audience copy, citations, and compact visible source labels."""
    evidence_map = {record.evidence_id: record for record in evidence}
    slides: list[SlideSpec] = []
    for slide in plan.slides:
        visible = "\n".join(
            filter(
                None,
                (
                    slide.title,
                    slide.core_message,
                    *(block.text for block in slide.content_blocks),
                    *(
                        item
                        for block in slide.content_blocks
                        for item in block.items
                    ),
                ),
            )
        )
        lowered = visible.casefold()
        if any(marker in lowered for marker in _INTERNAL_MARKERS):
            raise ValueError(
                f"slide {slide.slide_id} contains non-audience-facing language"
            )
        if _PRECISE_NUMBER.search(visible) and not slide.evidence_ids:
            raise ValueError(
                f"slide {slide.slide_id} has a precise number without evidence"
            )
        missing = [
            evidence_id
            for evidence_id in slide.evidence_ids
            if evidence_id not in evidence_map
        ]
        if missing:
            raise ValueError(
                f"slide {slide.slide_id} references unknown evidence IDs: {missing}"
            )
        slides.append(
            slide.model_copy(
                update={
                    "source_footer": shorten_source_footer(
                        slide.source_footer, footer_limit
                    )
                }
            )
        )
    return SharedCopy(
        plan=plan.model_copy(update={"slides": tuple(slides)}),
        evidence=evidence_map,
    )
