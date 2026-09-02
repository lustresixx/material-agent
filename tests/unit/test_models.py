from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from localdeck.models import GenerationRequest, RunManifest, RunStage


def test_generation_request_normalizes_output(tmp_path: Path) -> None:
    request = GenerationRequest(
        topic="  人工智能的发展  ",
        slides=6,
        language="zh",
        aspect_ratio="16:9",
        output=tmp_path / "deck.pptx",
    )

    assert request.topic == "人工智能的发展"
    assert request.output == (tmp_path / "deck.pptx").resolve()


@pytest.mark.parametrize("slides", [0, 31])
def test_generation_request_rejects_invalid_slide_count(
    slides: int, tmp_path: Path
) -> None:
    with pytest.raises(ValidationError):
        GenerationRequest(topic="topic", slides=slides, output=tmp_path / "x.pptx")


def test_generation_request_requires_pptx_output(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match=".pptx"):
        GenerationRequest(topic="topic", slides=3, output=tmp_path / "x.pdf")


def test_manifest_records_stage_artifact(tmp_path: Path) -> None:
    manifest = RunManifest(run_id="run-1", workspace=tmp_path)

    manifest.complete_stage(RunStage.RESEARCH, tmp_path / "manuscript.md")

    assert manifest.stages[RunStage.RESEARCH].status == "completed"
    assert manifest.stages[RunStage.RESEARCH].artifact == tmp_path / "manuscript.md"
