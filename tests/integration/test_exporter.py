from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from pptx import Presentation

from localdeck.rendering.exporter import HTMLExporter
from localdeck.rendering.verifier import PPTXVerifier

FIXTURE = Path(__file__).parents[1] / "fixtures" / "slides" / "valid.html"


async def test_exporter_creates_editable_two_slide_pptx(tmp_path: Path) -> None:
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    html = FIXTURE.read_text(encoding="utf-8")
    (slides_dir / "slide_01.html").write_text(html, encoding="utf-8")
    (slides_dir / "slide_02.html").write_text(
        html.replace("LocalDeck", "第二页"), encoding="utf-8"
    )
    output = tmp_path / "deck.pptx"

    await HTMLExporter().export(slides_dir, output, "16:9")
    verification = PPTXVerifier().verify(output, expected_slides=2)

    presentation = Presentation(output)
    text_shapes = [
        shape
        for slide in presentation.slides
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False) and shape.text.strip()
    ]
    assert verification.slide_count == 2
    assert verification.text_shape_count >= 2
    assert text_shapes


async def test_exporter_does_not_replace_existing_output_on_failure(
    tmp_path: Path,
) -> None:
    slides_dir = tmp_path / "slides"
    slides_dir.mkdir()
    (slides_dir / "slide_01.html").write_text("<broken", encoding="utf-8")
    output = tmp_path / "deck.pptx"
    output.write_bytes(b"existing")

    with suppress(Exception):
        await HTMLExporter().export(slides_dir, output, "16:9")

    assert output.read_bytes() == b"existing"
