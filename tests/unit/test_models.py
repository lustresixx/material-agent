from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from localdeck.models import (
    GenerationRequest,
    GenerationRoute,
    RunManifest,
    RunStage,
    TemplateGenerationRequest,
)


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
    with pytest.raises(ValidationError, match=r"\.pptx"):
        GenerationRequest(topic="topic", slides=3, output=tmp_path / "x.pdf")


def test_manifest_records_stage_artifact(tmp_path: Path) -> None:
    manifest = RunManifest(run_id="run-1", workspace=tmp_path)

    manifest.complete_stage(RunStage.RESEARCH, tmp_path / "manuscript.md")

    assert manifest.stages[RunStage.RESEARCH].status == "completed"
    assert manifest.stages[RunStage.RESEARCH].artifact == tmp_path / "manuscript.md"


def test_template_generation_request_resolves_paths(tmp_path: Path) -> None:
    request = TemplateGenerationRequest(
        outline=tmp_path / "outline.json",
        template=str(tmp_path / "brand.pptx"),
        output_dir=tmp_path / "output",
    )

    assert request.outline == (tmp_path / "outline.json").resolve()
    assert request.template == str((tmp_path / "brand.pptx").resolve())
    assert request.output_dir == (tmp_path / "output").resolve()
    assert request.routes == (
        GenerationRoute.TEMPLATE,
        GenerationRoute.HTML,
    )


@pytest.mark.parametrize("max_slides", [1, 30])
def test_template_generation_request_accepts_slide_limit(
    max_slides: int, tmp_path: Path
) -> None:
    request = TemplateGenerationRequest(
        outline=tmp_path / "outline.json",
        template=str(tmp_path / "brand.pptx"),
        output_dir=tmp_path / "output",
        max_slides=max_slides,
    )

    assert request.max_slides == max_slides


def test_template_generation_request_rejects_more_than_30_slides(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="max_slides"):
        TemplateGenerationRequest(
            outline=tmp_path / "outline.json",
            template=str(tmp_path / "brand.pptx"),
            output_dir=tmp_path / "output",
            max_slides=31,
        )


@pytest.mark.parametrize(
    "routes",
    [(), (GenerationRoute.HTML, GenerationRoute.HTML)],
)
def test_template_generation_request_rejects_invalid_routes(
    routes: tuple[GenerationRoute, ...], tmp_path: Path
) -> None:
    with pytest.raises(ValidationError, match="routes"):
        TemplateGenerationRequest(
            outline=tmp_path / "outline.json",
            template=str(tmp_path / "brand.pptx"),
            output_dir=tmp_path / "output",
            routes=routes,
        )
