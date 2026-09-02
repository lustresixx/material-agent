from __future__ import annotations

from pathlib import Path

import pytest

from localdeck.mcp import quality_server
from localdeck.models import InspectionIssue, InspectionReport


async def test_failed_inspection_is_exposed_as_tool_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = InspectionReport(
        html_file=tmp_path / "slide.html",
        passed=False,
        width=1280,
        height=720,
        issues=[InspectionIssue(code="text_overflow", message="Text exceeds its box")],
    )

    class FailingInspector:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        async def __aenter__(self) -> FailingInspector:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def inspect(self, html_file: str, aspect_ratio: str) -> InspectionReport:
            return report

    monkeypatch.setenv("LOCALDECK_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(quality_server, "SlideInspector", FailingInspector)

    with pytest.raises(RuntimeError, match="text_overflow"):
        await quality_server.inspect_slide.fn("slide.html")
