from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from localdeck.rendering.pptx_preview import (
    PowerPointPreviewRenderer,
    PPTXPreviewUnavailable,
    select_pptx_preview_renderer,
)


class FakePresentation:
    def __init__(self, *, fail_export: bool = False) -> None:
        self.fail_export = fail_export
        self.closed = False
        self.Slides = FakeSlides(self)

    def Close(self) -> None:
        self.closed = True


class FakeSlide:
    def __init__(self, presentation: FakePresentation, number: int) -> None:
        self.presentation = presentation
        self.number = number

    def Export(self, output_file: str, image_format: str) -> None:
        if self.presentation.fail_export:
            raise RuntimeError("export failed")
        assert image_format == "PNG"
        Path(output_file).write_bytes(f"slide-{self.number}".encode())


class FakeSlides:
    Count = 2

    def __init__(self, presentation: FakePresentation) -> None:
        self.presentation = presentation

    def __call__(self, number: int) -> FakeSlide:
        return FakeSlide(self.presentation, number)


class FakePresentations:
    def __init__(self, presentation: FakePresentation) -> None:
        self.presentation = presentation

    def Open(self, *args: Any, **kwargs: Any) -> FakePresentation:
        return self.presentation


class FakeApplication:
    def __init__(self, presentation: FakePresentation) -> None:
        self.Presentations = FakePresentations(presentation)
        self.Visible: bool | None = None
        self.quit_called = False

    def Quit(self) -> None:
        self.quit_called = True


def test_windows_selects_powerpoint_renderer() -> None:
    renderer = select_pptx_preview_renderer(
        platform_name="win32",
        dispatch_factory=lambda _: FakeApplication(FakePresentation()),
    )

    assert isinstance(renderer, PowerPointPreviewRenderer)


def test_missing_preview_backend_has_clear_error() -> None:
    with pytest.raises(PPTXPreviewUnavailable, match="No PPTX preview renderer"):
        select_pptx_preview_renderer(platform_name="linux")


def test_powerpoint_renderer_returns_consecutive_png_paths(tmp_path: Path) -> None:
    presentation = FakePresentation()
    application = FakeApplication(presentation)
    renderer = PowerPointPreviewRenderer(lambda _: application)
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"fixture")

    paths = renderer.render(source, tmp_path / "previews")

    assert [path.name for path in paths] == ["slide_01.png", "slide_02.png"]
    assert all(path.is_file() for path in paths)
    assert presentation.closed is True
    assert application.quit_called is True
    assert application.Visible is False


def test_powerpoint_renderer_closes_owned_resources_on_failure(tmp_path: Path) -> None:
    presentation = FakePresentation(fail_export=True)
    application = FakeApplication(presentation)
    renderer = PowerPointPreviewRenderer(lambda _: application)
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"fixture")

    with pytest.raises(RuntimeError, match="export failed"):
        renderer.render(source, tmp_path / "previews")

    assert presentation.closed is True
    assert application.quit_called is True
