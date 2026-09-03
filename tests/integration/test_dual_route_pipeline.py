from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import SecretStr

from localdeck.config import Settings
from localdeck.llm.protocol import AssistantResponse
from localdeck.models import GenerationRoute, TemplateGenerationRequest
from localdeck.pipeline import TemplateDeckPipeline
from localdeck.research.models import PageEvidence, SearchHit
from tests.fixtures.build_template_deck import build_template_deck
from tests.fixtures.scripted_run import ScriptedLLM


async def test_dual_route_pipeline_publishes_shared_plan_and_telemetry(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    pipeline = TemplateDeckPipeline(
        _settings(tmp_path),
        llm=ScriptedLLM(
            [AssistantResponse(content="invalid"), AssistantResponse(content="invalid")]
        ),
        search=_Search(),
        reader=_Reader(),
        preview_renderer=_PreviewRenderer(),
    )

    result = await pipeline.generate(request)

    assert result.template_output is not None and result.template_output.is_file()
    assert result.html_output is not None and result.html_output.is_file()
    assert result.comparison is not None and result.comparison.is_file()
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["stage_order"] == [
        "input",
        "template",
        "research",
        "plan",
        "template-route",
        "html-route",
        "quality",
        "comparison",
        "publish",
    ]
    assert manifest["routes"]["template"]["plan_digest"] == manifest["plan_digest"]
    assert manifest["routes"]["html"]["plan_digest"] == manifest["plan_digest"]
    assert all(value >= 0 for value in manifest["timings"].values())
    assert (result.workspace / "planning" / "slide-plan.json").is_file()
    assert (result.workspace / "planning" / "frame-map.json").is_file()
    assert list((result.workspace / "research").rglob("research.json"))
    assert not list(request.output_dir.glob(".*.tmp"))


async def test_one_route_failure_does_not_discard_the_other(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    pipeline = TemplateDeckPipeline(
        _settings(tmp_path),
        llm=ScriptedLLM([]),
        search=_Search(),
        reader=_Reader(),
        preview_renderer=_PreviewRenderer(),
        html_generator=_FailingHtmlGenerator(),
    )

    result = await pipeline.generate(request)

    assert result.template_output is not None and result.template_output.is_file()
    assert result.html_output is None
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["routes"]["template"]["status"] == "completed"
    assert manifest["routes"]["html"]["status"] == "failed"
    assert "synthetic HTML failure" in manifest["routes"]["html"]["error"]


async def test_fails_when_no_selected_route_can_be_published(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path).model_copy(
        update={"routes": (GenerationRoute.HTML,)}
    )
    pipeline = TemplateDeckPipeline(
        _settings(tmp_path),
        llm=ScriptedLLM([]),
        search=_Search(),
        reader=_Reader(),
        preview_renderer=_PreviewRenderer(),
        html_generator=_FailingHtmlGenerator(),
    )

    with pytest.raises(RuntimeError, match="No selected route passed"):
        await pipeline.generate(request)


def _request(tmp_path: Path) -> TemplateGenerationRequest:
    source, _ = build_template_deck(tmp_path / "fixture")
    outline = tmp_path / "outline.json"
    outline.write_text(
        json.dumps(
            {
                "title": "携手同济大学,共建数智化新生态",
                "chapters": [
                    {"chapter_title": "华为公司介绍", "sections": ["经营情况"]}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return TemplateGenerationRequest(
        outline=outline,
        template=str(source),
        routes=(GenerationRoute.TEMPLATE, GenerationRoute.HTML),
        max_slides=4,
        output_dir=tmp_path / "published",
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key=SecretStr("test-only"),
        runs_dir=tmp_path / "runs",
        template_dir=tmp_path / "templates",
        html_batch_size=3,
        max_repairs=0,
    )


class _Search:
    async def search(
        self, query: str, *, domain: str | None = None
    ) -> list[SearchHit]:
        del query, domain
        return [
            SearchHit(
                title="Official",
                url="https://www.huawei.com/example",
                snippet="Official information",
            )
        ]


class _Reader:
    async def read(self, url: str) -> PageEvidence:
        return PageEvidence(
            url=url,
            title="Huawei official publication",
            text="Huawei continues to invest in research and industry collaboration.",
        )


class _PreviewRenderer:
    def render(self, source: Path, output_dir: Path) -> list[Path]:
        from pptx import Presentation

        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for index in range(1, len(Presentation(source).slides) + 1):
            path = output_dir / f"slide_{index:02d}.png"
            Image.new("RGB", (320, 180), (30, 90, 160)).save(path)
            paths.append(path)
        return paths


class _FailingHtmlGenerator:
    async def generate(self, **kwargs: object) -> object:
        del kwargs
        raise RuntimeError("synthetic HTML failure")
