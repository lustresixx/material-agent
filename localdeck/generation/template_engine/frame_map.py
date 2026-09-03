"""Persistence helpers for auditable template frame maps."""

from __future__ import annotations

import json
from pathlib import Path

from localdeck.generation.template_engine.matcher import FrameMatchMap


def write_frame_map(frame_map: FrameMatchMap, output: Path) -> Path:
    """Write the deterministic matching decision as stable UTF-8 JSON."""
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            frame_map.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return destination
