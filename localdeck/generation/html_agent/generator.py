"""Batched template-constrained HTML generation with bounded repair."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from localdeck.generation.html_agent.compatibility import inspect_html
from localdeck.generation.html_agent.prompt_builder import build_messages
from localdeck.llm.protocol import LLMClient
from localdeck.planning.copywriter import SharedCopy
from localdeck.planning.models import SlideSpec
from localdeck.rendering.exporter import HTMLExporter
from localdeck.templates.models import ThemeProfile


class HtmlRouteResult(BaseModel):
    """Artifacts and bounded generation telemetry for the HTML route."""

    model_config = ConfigDict(frozen=True)

    pptx: Path
    slides_dir: Path
    model_calls: int
    repairs: int
    fallback_slides: tuple[str, ...] = ()


class HtmlRouteGenerator:
    """Generate small batches and repair only slides that fail static checks."""

    def __init__(
        self,
        llm: LLMClient,
        *,
        exporter: HTMLExporter | None = None,
        batch_size: int = 3,
        max_repairs: int = 2,
    ) -> None:
        if not 2 <= batch_size <= 4:
            raise ValueError("HTML batch size must be between 2 and 4")
        if max_repairs < 0:
            raise ValueError("max_repairs cannot be negative")
        self._llm = llm
        self._exporter = exporter or HTMLExporter()
        self._batch_size = batch_size
        self._max_repairs = max_repairs

    async def generate(
        self,
        *,
        shared_copy: SharedCopy,
        theme: ThemeProfile,
        workspace: Path,
        output: Path,
        aspect_ratio: Literal["16:9", "4:3"],
    ) -> HtmlRouteResult:
        """Generate validated HTML pages, then export one editable PPTX."""
        slides_dir = workspace.expanduser().resolve() / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        _write_css(slides_dir, theme, aspect_ratio)

        model_calls = 0
        repairs = 0
        fallbacks: list[str] = []
        slides = shared_copy.plan.slides
        for start in range(0, len(slides), self._batch_size):
            batch = slides[start : start + self._batch_size]
            generated, issues = await self._request(batch, theme, aspect_ratio, None)
            model_calls += 1
            pending = tuple(slide for slide in batch if slide.slide_id in issues)
            attempt = 0
            while pending and attempt < self._max_repairs:
                repair_issues = {
                    slide.slide_id: issues[slide.slide_id] for slide in pending
                }
                repaired, issues = await self._request(
                    pending, theme, aspect_ratio, repair_issues
                )
                generated.update(repaired)
                model_calls += 1
                repairs += 1
                attempt += 1
                pending = tuple(
                    slide for slide in pending if slide.slide_id in issues
                )
            for slide in pending:
                generated[slide.slide_id] = _fallback_html(slide)
                fallbacks.append(slide.slide_id)
            for slide in batch:
                source = generated.get(slide.slide_id) or _fallback_html(slide)
                if slide.slide_id not in generated:
                    fallbacks.append(slide.slide_id)
                destination = slides_dir / f"slide_{slide.index:02d}.html"
                destination.write_text(source, encoding="utf-8")

        pptx = await self._exporter.export(slides_dir, output, aspect_ratio)
        return HtmlRouteResult(
            pptx=pptx,
            slides_dir=slides_dir,
            model_calls=model_calls,
            repairs=repairs,
            fallback_slides=tuple(dict.fromkeys(fallbacks)),
        )

    async def _request(
        self,
        slides: tuple[SlideSpec, ...],
        theme: ThemeProfile,
        aspect_ratio: str,
        repair_issues: dict[str, tuple[str, ...]] | None,
    ) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
        response = await self._llm.complete(
            build_messages(
                slides,
                theme,
                aspect_ratio=aspect_ratio,
                repair_issues=repair_issues,
            ),
            [],
        )
        expected = {slide.slide_id for slide in slides}
        try:
            candidates = _parse_response(response.content or "")
        except (json.JSONDecodeError, ValueError, TypeError):
            return {}, {
                slide_id: ("Response is not valid schema-compliant JSON",)
                for slide_id in expected
            }

        generated: dict[str, str] = {}
        issues: dict[str, tuple[str, ...]] = {}
        for slide_id in expected:
            source = candidates.get(slide_id)
            if source is None:
                issues[slide_id] = ("Requested slide is missing from response",)
                continue
            report = inspect_html(source)
            if report.passed:
                generated[slide_id] = source
            else:
                issues[slide_id] = tuple(issue.message for issue in report.issues)
        return generated, issues


def _parse_response(content: str) -> dict[str, str]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", stripped)
    payload = json.loads(stripped)
    if not isinstance(payload, dict) or not isinstance(payload.get("slides"), list):
        raise ValueError("response must contain a slides array")
    result: dict[str, str] = {}
    for item in payload["slides"]:
        if not isinstance(item, dict):
            raise ValueError("slide response item must be an object")
        slide_id = item.get("slide_id")
        source = item.get("html")
        if not isinstance(slide_id, str) or not isinstance(source, str):
            raise ValueError("slide response requires string slide_id and html")
        if slide_id in result:
            raise ValueError("slide response contains duplicate slide_id")
        result[slide_id] = source
    return result


def _write_css(
    slides_dir: Path, theme: ThemeProfile, aspect_ratio: str
) -> None:
    width = 1280 if aspect_ratio == "16:9" else 960
    height = 720
    font_stack = ", ".join(f'"{font}"' for font in theme.font_families)
    palette = list(theme.palette)
    while len(palette) < 3:
        palette.append(palette[-1])
    global_css = f"""* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; width: {width}px; height: {height}px; overflow: hidden;
}}
body {{
  position: relative; font-family: var(--font-family);
  background: var(--color-bg); color: var(--color-text); padding: 64px 72px;
}}
h1 {{ margin: 0 0 28px; font-size: 46px; line-height: 1.15; }}
p, li {{ font-size: 24px; line-height: 1.42; }}
footer {{
  position: absolute; left: 72px; right: 72px; bottom: 26px;
  font-size: 12px; color: var(--color-muted);
}}
"""
    theme_css = f""":root {{
  --font-family: {font_stack}, sans-serif;
  --color-accent: {palette[0]};
  --color-text: {palette[1]};
  --color-bg: {palette[2]};
  --color-muted: {palette[1]};
  --space-1: {theme.spacing[0]}in;
  --space-2: {theme.spacing[min(1, len(theme.spacing) - 1)]}in;
  --space-3: {theme.spacing[min(2, len(theme.spacing) - 1)]}in;
}}
"""
    (slides_dir / "global.css").write_text(global_css, encoding="utf-8")
    (slides_dir / "theme.css").write_text(theme_css, encoding="utf-8")


def _fallback_html(slide: SlideSpec) -> str:
    bullets = "".join(
        f"<li>{html.escape(item)}</li>"
        for block in slide.content_blocks
        for item in block.items
    )
    footer = (
        f"<footer>{html.escape(slide.source_footer)}</footer>"
        if slide.source_footer
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<link rel="stylesheet" href="global.css"><link rel="stylesheet" href="theme.css">
</head><body><main><h1>{html.escape(slide.title)}</h1>
<p>{html.escape(slide.core_message)}</p><ul>{bullets}</ul></main>{footer}</body></html>"""
