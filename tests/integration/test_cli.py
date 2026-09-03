from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import localdeck.cli as cli_module
from localdeck.models import GenerationResult, TemplateGenerationResult
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


def test_cli_generate_dispatches_imported_template_mode(
    monkeypatch, tmp_path: Path
) -> None:
    template_dir = tmp_path / "templates"
    package = template_dir / "huawei-education"
    package.mkdir(parents=True)
    (package / "source.pptx").write_bytes(b"fixture")
    outline = tmp_path / "outline.json"
    outline.write_text('{"title":"T","chapters":[]}', encoding="utf-8")
    output_dir = tmp_path / "output"
    captured: dict[str, object] = {}

    class FakeTemplatePipeline:
        def __init__(self, settings) -> None:
            self.settings = settings

        async def generate(self, request) -> TemplateGenerationResult:
            captured["request"] = request
            workspace = tmp_path / "template-run"
            workspace.mkdir()
            plan = workspace / "slide-plan.json"
            plan.write_text("{}", encoding="utf-8")
            manifest = workspace / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            output_dir.mkdir()
            template_output = output_dir / "template-route.pptx"
            template_output.write_bytes(b"template")
            html_output = output_dir / "html-route.pptx"
            html_output.write_bytes(b"html")
            comparison = output_dir / "comparison.html"
            comparison.write_text("report", encoding="utf-8")
            return TemplateGenerationResult(
                output_dir=output_dir,
                workspace=workspace,
                manifest=manifest,
                plan=plan,
                template_output=template_output,
                html_output=html_output,
                comparison=comparison,
            )

    monkeypatch.setattr(cli_module, "TemplateDeckPipeline", FakeTemplatePipeline)
    result = CliRunner().invoke(
        cli_module.app,
        [
            "generate",
            "--outline",
            str(outline),
            "--template",
            "huawei-education",
            "--routes",
            "template,html",
            "--max-slides",
            "30",
            "--output-dir",
            str(output_dir),
        ],
        env={
            "ZAI_API_KEY": "test-only-key",
            "LOCALDECK_TEMPLATE_DIR": str(template_dir),
        },
    )

    assert result.exit_code == 0, result.output
    assert "template-route.pptx" in result.output
    assert "html-route.pptx" in result.output
    assert "comparison.html" in result.output
    request = captured["request"]
    assert request.template == str((package / "source.pptx").resolve())


def test_cli_generate_requires_exactly_one_input_mode(tmp_path: Path) -> None:
    outline = tmp_path / "outline.json"
    outline.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    both = runner.invoke(
        cli_module.app,
        ["generate", "topic", "--outline", str(outline), "--template", "brand"],
        env={"ZAI_API_KEY": "test-only-key"},
    )
    neither = runner.invoke(
        cli_module.app,
        ["generate"],
        env={"ZAI_API_KEY": "test-only-key"},
    )

    assert both.exit_code == 2
    assert "exactly one" in both.output
    assert neither.exit_code == 2
    assert "exactly one" in neither.output


def test_cli_template_mode_requires_imported_template(tmp_path: Path) -> None:
    outline = tmp_path / "outline.json"
    outline.write_text("{}", encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.app,
        ["generate", "--outline", str(outline), "--template", "missing"],
        env={
            "ZAI_API_KEY": "test-only-key",
            "LOCALDECK_TEMPLATE_DIR": str(tmp_path / "templates"),
        },
    )

    assert result.exit_code == 2
    assert "imported template" in result.output
