"""Command-line interface for the LocalDeck MVP."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console

from localdeck.config import Settings, SettingsError
from localdeck.models import GenerationRequest
from localdeck.pipeline import LocalDeckPipeline
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
    topic: Annotated[str, typer.Argument(help="Presentation topic or brief")],
    slides: Annotated[int, typer.Option("--slides", "-n")] = 6,
    language: Annotated[Literal["zh", "en"], typer.Option("--language")] = "zh",
    aspect_ratio: Annotated[
        Literal["16:9", "4:3"], typer.Option("--aspect-ratio")
    ] = "16:9",
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("output.pptx"),
) -> None:
    """Generate an editable PPTX from a text-only topic."""

    try:
        settings = Settings.from_env()
        request = GenerationRequest(
            topic=topic,
            slides=slides,
            language=language,
            aspect_ratio=aspect_ratio,
            output=output,
        )
        result = asyncio.run(LocalDeckPipeline(settings).generate(request))
    except (SettingsError, ValueError) as error:
        console.print(f"[bold red]Configuration error:[/bold red] {error}")
        raise typer.Exit(2) from error
    except Exception as error:
        console.print(f"[bold red]Generation failed:[/bold red] {error}")
        raise typer.Exit(1) from error

    console.print("[bold green]Generated[/bold green]")
    typer.echo(f"Output: {result.output.resolve()}")
    typer.echo(f"Workspace: {result.workspace.resolve()}")


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
