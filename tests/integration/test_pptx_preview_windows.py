from __future__ import annotations

import sys
from pathlib import Path

import pytest

from localdeck.rendering.pptx_preview import (
    PPTXPreviewUnavailable,
    select_pptx_preview_renderer,
)
from tests.fixtures.build_template_deck import build_template_deck


@pytest.mark.skipif(
    sys.platform != "win32", reason="PowerPoint automation is Windows-only"
)
def test_powerpoint_renders_real_pptx_to_png(tmp_path: Path) -> None:
    source, _ = build_template_deck(tmp_path / "fixture")
    try:
        renderer = select_pptx_preview_renderer()
        paths = renderer.render(source, tmp_path / "previews")
    except PPTXPreviewUnavailable as error:
        pytest.skip(str(error))

    assert [path.name for path in paths] == ["slide_01.png", "slide_02.png"]
    assert all(path.stat().st_size > 0 for path in paths)
