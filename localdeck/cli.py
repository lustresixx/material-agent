"""Command-line interface for the LocalDeck MVP."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console

from localdeck.config import Settings, SettingsError
from localdeck.models import (
    GenerationRequest,
    GenerationRoute,
    TemplateGenerationRequest,
)
from localdeck.pipeline import LocalDeckPipeline, TemplateDeckPipeline
from localdeck.rendering.pptx_preview import select_pptx_preview_renderer
from localdeck.templates.importer import TemplateImporter

app = typer.Typer(
    name="localdeck",
    help="Generate editable PowerPoint files locally without Docker.",
    no_args_is_help=True,
)
console = Console()
template_app = typer.Typer(help="Import and inspect reusable PPTX templates.")
app.add_typer(template_app, name="template")


@app.callback()
def root() -> None:
    """LocalDeck command group."""


@app.command()
def generate(
    topic: Annotated[
        str | None, typer.Argument(help="Presentation topic or brief")
    ] = None,
    slides: Annotated[int, typer.Option("--slides", "-n")] = 6,
    language: Annotated[Literal["zh", "en"], typer.Option("--language")] = "zh",
    aspect_ratio: Annotated[
        Literal["16:9", "4:3"], typer.Option("--aspect-ratio")
    ] = "16:9",
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("output.pptx"),
    outline: Annotated[Path | None, typer.Option("--outline")] = None,
    template: Annotated[str | None, typer.Option("--template")] = None,
    routes: Annotated[str, typer.Option("--routes")] = "template,html",
    max_slides: Annotated[int, typer.Option("--max-slides")] = 30,
    output_dir: Annotated[Path, typer.Option("--output-dir")] = Path("output"),
) -> None:
    """Generate from either a text topic or a structured outline and template."""

    try:
        settings = Settings.from_env()
        if (topic is None) == (outline is None):
            raise ValueError("select exactly one input mode: topic or --outline")
        if outline is not None:
            source = _resolve_imported_template(template)
            request = TemplateGenerationRequest(
                outline=outline,
                template=str(source),
                routes=_parse_routes(routes),
                max_slides=max_slides,
                language=language,
                output_dir=output_dir,
            )
            template_result = asyncio.run(
                TemplateDeckPipeline(settings).generate(request)
            )
            console.print("[bold green]Generated[/bold green]")
            if template_result.template_output is not None:
                typer.echo(
                    f"Template PPTX: {template_result.template_output.resolve()}"
                )
            if template_result.html_output is not None:
                typer.echo(f"HTML PPTX: {template_result.html_output.resolve()}")
            if template_result.comparison is not None:
                typer.echo(f"Comparison: {template_result.comparison.resolve()}")
            typer.echo(f"Workspace: {template_result.workspace.resolve()}")
            return
        assert topic is not None
        topic_request = GenerationRequest(
            topic=topic,
            slides=slides,
            language=language,
            aspect_ratio=aspect_ratio,
            output=output,
        )
        result = asyncio.run(LocalDeckPipeline(settings).generate(topic_request))
    except (SettingsError, ValueError) as error:
        console.print(f"[bold red]Configuration error:[/bold red] {error}")
        raise typer.Exit(2) from error
    except Exception as error:
        console.print(f"[bold red]Generation failed:[/bold red] {error}")
        raise typer.Exit(1) from error

    console.print("[bold green]Generated[/bold green]")
    typer.echo(f"Output: {result.output.resolve()}")
    typer.echo(f"Workspace: {result.workspace.resolve()}")


def _parse_routes(value: str) -> tuple[GenerationRoute, ...]:
    names = tuple(part.strip().casefold() for part in value.split(",") if part.strip())
    if not names:
        raise ValueError("--routes must contain template, html, or both")
    try:
        result = tuple(GenerationRoute(name) for name in names)
    except ValueError as error:
        raise ValueError("--routes must contain only template and html") from error
    if len(result) != len(set(result)):
        raise ValueError("--routes cannot contain duplicates")
    return result


def _resolve_imported_template(name: str | None) -> Path:
    if name is None or not name.strip():
        raise ValueError("--template is required with --outline")
    normalized = name.strip()
    if Path(normalized).name != normalized or normalized in {".", ".."}:
        raise ValueError("--template must name an imported template")
    source = (_template_dir() / normalized / "source.pptx").resolve()
    if not source.is_file():
        raise ValueError(
            f"imported template not found: {normalized}; run localdeck template import"
        )
    return source


@template_app.command("import")
def import_template_command(
    source: Annotated[Path, typer.Argument(help="Editable source PPTX")],
    name: Annotated[str, typer.Option("--name")] ,
    replace: Annotated[bool, typer.Option("--replace")] = False,
) -> None:
    """Import and inspect a reusable editable PowerPoint template."""
    try:
        package = TemplateImporter(
            preview_renderer=select_pptx_preview_renderer()
        ).import_template(
            source,
            _template_dir(),
            template_id=name,
            replace=replace,
        )
    except Exception as error:
        console.print(f"[bold red]Template import failed:[/bold red] {error}")
        raise typer.Exit(1) from error
    console.print("[bold green]Template imported[/bold green]")
    typer.echo(f"Package: {package.root}")
    typer.echo(f"Audit: {(package.root / 'template_audit.html').resolve()}")


@template_app.command("inspect")
def inspect_template_command(
    name: Annotated[str, typer.Argument(help="Imported template name")],
) -> None:
    """Print the offline audit path for one imported template."""
    audit = (_template_dir() / name / "template_audit.html").resolve()
    if not audit.is_file():
        console.print(f"[bold red]Template not found:[/bold red] {name}")
        raise typer.Exit(1)
    typer.echo(f"Audit: {audit}")


def _template_dir() -> Path:
    return Path(os.getenv("LOCALDECK_TEMPLATE_DIR", "templates")).expanduser().resolve()


def main() -> None:
    """Console-script entrypoint."""

    app()


if __name__ == "__main__":
    main()
