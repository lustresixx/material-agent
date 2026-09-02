from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import localdeck.cli as cli_module
from localdeck.models import GenerationResult


def test_cli_generate_reports_output(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "deck.pptx"

    class FakePipeline:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def generate(self, request) -> GenerationResult:
            output.write_bytes(b"fake")
            workspace = tmp_path / "run"
            workspace.mkdir()
            manuscript = workspace / "manuscript.md"
            manuscript.write_text("# test", encoding="utf-8")
            slides = workspace / "slides"
            slides.mkdir()
            manifest = workspace / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            return GenerationResult(
                output=output,
                workspace=workspace,
                manuscript=manuscript,
                slides_dir=slides,
                manifest=manifest,
            )

    monkeypatch.setattr(cli_module, "LocalDeckPipeline", FakePipeline)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.app,
        ["generate", "测试主题", "--slides", "2", "--output", str(output)],
        env={"ZAI_API_KEY": "test-only-key"},
    )

    assert result.exit_code == 0, result.output
    assert "Generated" in result.output
    assert str(output.resolve()) in result.output
