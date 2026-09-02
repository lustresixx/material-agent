from __future__ import annotations

from pathlib import Path

from localdeck.quality import SlideInspector

FIXTURES = Path(__file__).parents[1] / "fixtures" / "slides"


async def test_valid_slide_passes_and_writes_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    slides = workspace / "slides"
    slides.mkdir(parents=True)
    html_file = slides / "slide_01.html"
    html_file.write_text(
        (FIXTURES / "valid.html").read_text(encoding="utf-8"), encoding="utf-8"
    )

    async with SlideInspector(workspace) as inspector:
        report = await inspector.inspect(html_file, "16:9")

    assert report.passed
    assert report.width == 1280
    assert report.height == 720
    assert report.screenshot is not None and report.screenshot.is_file()
    assert (workspace / "inspections" / "slide_01.json").is_file()


async def test_text_overflow_is_reported(tmp_path: Path) -> None:
    workspace = tmp_path / "run"
    slides = workspace / "slides"
    slides.mkdir(parents=True)
    html_file = slides / "slide_01.html"
    html_file.write_text(
        (FIXTURES / "overflow.html").read_text(encoding="utf-8"), encoding="utf-8"
    )

    async with SlideInspector(workspace) as inspector:
        report = await inspector.inspect(html_file, "16:9")

    assert not report.passed
    assert "text_overflow" in {issue.code for issue in report.issues}
