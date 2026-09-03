from __future__ import annotations

from pathlib import Path

from PIL import Image

from localdeck.comparison.models import RouteMetrics
from localdeck.comparison.report import write_comparison_report
from localdeck.planning.models import SlidePlan, SlideSpec
from localdeck.quality.deck import QualityIssue, QualityReport
from localdeck.templates.models import NarrativeRole


def test_writes_safe_side_by_side_report_with_stable_slide_ids(
    tmp_path: Path,
) -> None:
    plan = SlidePlan(
        max_slides=30,
        slides=tuple(
            SlideSpec(
                index=index,
                slide_id=f"section-01-0{index}-01",
                role=NarrativeRole.CONTENT,
                chapter_index=1,
                section_index=index,
                title=f"Page {index}",
                core_message="Core",
                visual_intent="comparison",
            )
            for index in range(1, 3)
        ),
    )
    template_previews = _previews(tmp_path / "template", "red")
    html_previews = _previews(tmp_path / "html", "blue")
    template_quality = QualityReport(passed=True)
    html_quality = QualityReport(
        passed=False,
        issues=(
            QualityIssue(
                code="possible-clipped-text",
                message="clipped",
                slide_index=2,
            ),
        ),
    )
    secret = "a70120-secret-must-not-leak"

    result = write_comparison_report(
        plan=plan,
        template_previews=template_previews,
        html_previews=html_previews,
        template_metrics=RouteMetrics(
            route="template", duration_seconds=1.2, model_calls=0, repairs=0
        ),
        html_metrics=RouteMetrics(
            route="html", duration_seconds=4.5, model_calls=2, repairs=1
        ),
        template_quality=template_quality,
        html_quality=html_quality,
        output=tmp_path / "comparison.html",
        excluded_values=(secret, "system prompt"),
    )

    source = result.read_text(encoding="utf-8")
    assert result.is_file()
    assert "section-01-01-01" in source
    assert "section-01-02-01" in source
    assert "Template route" in source
    assert "HTML route" in source
    assert "Recommended: template" in source
    assert "model calls: 2" in source
    assert secret not in source
    assert "system prompt" not in source


def _previews(directory: Path, color: str) -> list[Path]:
    directory.mkdir(parents=True)
    paths: list[Path] = []
    for index in range(1, 3):
        path = directory / f"slide_{index:02d}.png"
        Image.new("RGB", (320, 180), color).save(path)
        paths.append(path)
    return paths
