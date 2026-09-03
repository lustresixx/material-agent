from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import localdeck.cli as cli_module
from localdeck.models import GenerationResult
from tests.fixtures.build_template_deck import build_template_deck


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


class FakePreviewRenderer:
    def render(self, source: Path, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for index in (1, 2):
            path = output_dir / f"slide_{index:02d}.png"
            path.write_bytes(b"preview")
            paths.append(path)
        return paths


def test_cli_imports_and_inspects_named_template(monkeypatch, tmp_path: Path) -> None:
    source, _ = build_template_deck(tmp_path / "fixture")
    template_dir = tmp_path / "templates"
    monkeypatch.setattr(
        cli_module, "select_pptx_preview_renderer", lambda: FakePreviewRenderer()
    )
    runner = CliRunner()

    imported = runner.invoke(
        cli_module.app,
        ["template", "import", str(source), "--name", "huawei-blue"],
        env={"LOCALDECK_TEMPLATE_DIR": str(template_dir)},
    )
    inspected = runner.invoke(
        cli_module.app,
        ["template", "inspect", "huawei-blue"],
        env={"LOCALDECK_TEMPLATE_DIR": str(template_dir)},
    )

    audit = template_dir / "huawei-blue" / "template_audit.html"
    assert imported.exit_code == 0, imported.output
    assert inspected.exit_code == 0, inspected.output
    assert str(audit.resolve()) in inspected.output


def test_cli_duplicate_template_requires_replace(monkeypatch, tmp_path: Path) -> None:
    source, _ = build_template_deck(tmp_path / "fixture")
    template_dir = tmp_path / "templates"
    monkeypatch.setattr(
        cli_module, "select_pptx_preview_renderer", lambda: FakePreviewRenderer()
    )
    runner = CliRunner()
    arguments = ["template", "import", str(source), "--name", "brand"]

    first = runner.invoke(
        cli_module.app,
        arguments,
        env={"LOCALDECK_TEMPLATE_DIR": str(template_dir)},
    )
    duplicate = runner.invoke(
        cli_module.app,
        arguments,
        env={"LOCALDECK_TEMPLATE_DIR": str(template_dir)},
    )
    replaced = runner.invoke(
        cli_module.app,
        [*arguments, "--replace"],
        env={"LOCALDECK_TEMPLATE_DIR": str(template_dir)},
    )

    assert first.exit_code == 0
    assert duplicate.exit_code == 1
    assert "--replace" in duplicate.output
    assert replaced.exit_code == 0, replaced.output


def test_cli_unreadable_template_leaves_no_partial_package(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "invalid.pptx"
    source.write_bytes(b"not a presentation")
    template_dir = tmp_path / "templates"
    monkeypatch.setattr(
        cli_module, "select_pptx_preview_renderer", lambda: FakePreviewRenderer()
    )

    result = CliRunner().invoke(
        cli_module.app,
        ["template", "import", str(source), "--name", "broken"],
        env={"LOCALDECK_TEMPLATE_DIR": str(template_dir)},
    )

    assert result.exit_code == 1
    assert not (template_dir / "broken").exists()
