"""Generate a portable local HTML comparison for both visual routes."""

from __future__ import annotations

import shutil
from html import escape
from pathlib import Path

from localdeck.comparison.models import RouteMetrics
from localdeck.planning.models import SlidePlan
from localdeck.quality.deck import QualityReport


def write_comparison_report(
    *,
    plan: SlidePlan,
    template_previews: list[Path],
    html_previews: list[Path],
    template_metrics: RouteMetrics,
    html_metrics: RouteMetrics,
    template_quality: QualityReport,
    html_quality: QualityReport,
    output: Path,
    excluded_values: tuple[str, ...] = (),
) -> Path:
    """Copy preview assets and write a sanitized side-by-side report."""
    if len(template_previews) != len(plan.slides):
        raise ValueError("template preview count differs from slide plan")
    if len(html_previews) != len(plan.slides):
        raise ValueError("HTML preview count differs from slide plan")
    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    assets_dir = destination.parent / "comparison_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    template_assets = _copy_previews(template_previews, assets_dir, "template")
    html_assets = _copy_previews(html_previews, assets_dir, "html")
    recommendation = _recommend(
        template_metrics,
        html_metrics,
        template_quality,
        html_quality,
    )
    cards = "".join(
        _slide_card(
            slide.slide_id,
            slide.index,
            slide.title,
            template_assets[slide.index - 1],
            html_assets[slide.index - 1],
            template_quality,
            html_quality,
        )
        for slide in plan.slides
    )
    css = (Path(__file__).with_name("report.css")).read_text(encoding="utf-8")
    source = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LocalDeck route comparison</title><style>{css}</style></head>
<body><header><h1>LocalDeck route comparison</h1>
<p class="recommendation">Recommended: {escape(recommendation)}</p>
<div class="summary">{_metrics(template_metrics, template_quality)}
{_metrics(html_metrics, html_quality)}</div></header>
<main>{cards}</main></body></html>"""
    for value in excluded_values:
        if value:
            source = source.replace(value, "[REDACTED]")
    destination.write_text(source, encoding="utf-8")
    return destination


def _copy_previews(
    previews: list[Path], assets_dir: Path, route: str
) -> list[Path]:
    copied: list[Path] = []
    for index, preview in enumerate(previews, start=1):
        target = assets_dir / f"{route}_{index:02d}.png"
        shutil.copy2(preview, target)
        copied.append(target)
    return copied


def _recommend(
    template: RouteMetrics,
    html: RouteMetrics,
    template_quality: QualityReport,
    html_quality: QualityReport,
) -> str:
    def score(
        metrics: RouteMetrics, quality: QualityReport
    ) -> tuple[int, int, int, float]:
        return (
            0 if quality.passed else 1,
            len(quality.issues),
            metrics.repairs + len(metrics.fallback_slides),
            metrics.duration_seconds,
        )

    return (
        "template"
        if score(template, template_quality) <= score(html, html_quality)
        else "html"
    )


def _metrics(metrics: RouteMetrics, quality: QualityReport) -> str:
    status = "passed" if quality.passed else f"{len(quality.issues)} issue(s)"
    label = "Template route" if metrics.route == "template" else "HTML route"
    return (
        f'<section class="metric"><h2>{label}</h2><p>quality: {status}<br>'
        f"duration: {metrics.duration_seconds:.2f}s · model calls: "
        f"{metrics.model_calls} · repairs: {metrics.repairs}</p></section>"
    )


def _slide_card(
    slide_id: str,
    index: int,
    title: str,
    template_preview: Path,
    html_preview: Path,
    template_quality: QualityReport,
    html_quality: QualityReport,
) -> str:
    template_issues = _slide_issues(template_quality, index)
    html_issues = _slide_issues(html_quality, index)
    template_image = escape(template_preview.name)
    html_image = escape(html_preview.name)
    return f"""<article class="slide" data-slide-id="{escape(slide_id)}">
<h2>{index:02d} · {escape(title)}</h2><div class="pair">
<figure><img src="comparison_assets/{template_image}"
alt="Template route slide {index}">
<figcaption>Template route{template_issues}</figcaption></figure>
<figure><img src="comparison_assets/{html_image}"
alt="HTML route slide {index}">
<figcaption>HTML route{html_issues}</figcaption></figure>
</div></article>"""


def _slide_issues(report: QualityReport, index: int) -> str:
    codes = [issue.code for issue in report.issues if issue.slide_index == index]
    return (
        f'<span class="issues"> · {escape(", ".join(codes))}</span>'
        if codes
        else ""
    )
