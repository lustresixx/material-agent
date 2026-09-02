"""Command-line interface for the LocalDeck MVP."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.console import Console

from localdeck.config import Settings, SettingsError
from localdeck.models import GenerationRequest
from localdeck.pipeline import LocalDeckPipeline

app = typer.Typer(
    name="localdeck",
    help="Generate editable PowerPoint files locally without Docker.",
    no_args_is_help=True,
)
console = Console()


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


def main() -> None:
    """Console-script entrypoint."""

    app()


if __name__ == "__main__":
    main()
