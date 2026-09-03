"""Pluggable PPTX-to-PNG preview rendering for final visual QA."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol


class PPTXPreviewUnavailable(RuntimeError):
    """Raised when no supported local PPTX renderer can be used."""


class PPTXPreviewRenderer(Protocol):
    """Backend contract consumed by quality and comparison stages."""

    def render(self, source: Path, output_dir: Path) -> list[Path]:
        """Render all slides to consecutive PNG files."""
        ...


DispatchFactory = Callable[[str], Any]


class PowerPointPreviewRenderer:
    """Render slides through an isolated Microsoft PowerPoint COM instance."""

    def __init__(self, dispatch_factory: DispatchFactory) -> None:
        self._dispatch_factory = dispatch_factory

    def render(self, source: Path, output_dir: Path) -> list[Path]:
        """Export a PPTX to PNG and close only resources created here."""
        source_path = source.expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"PPTX does not exist: {source_path}")
        destination = output_dir.expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)

        application: Any | None = None
        presentation: Any | None = None
        try:
            try:
                application = self._dispatch_factory("PowerPoint.Application")
            except Exception as error:
                raise PPTXPreviewUnavailable(
                    f"Microsoft PowerPoint automation is unavailable: {error}"
                ) from error
            assert application is not None
            # Some PowerPoint builds reject hiding the application object itself.
            # WithWindow=False below still prevents a presentation window, so keep
            # the preferred setting as a best effort for compatible installations.
            with suppress(Exception):
                application.Visible = False
            presentation = application.Presentations.Open(
                FileName=str(source_path),
                ReadOnly=True,
                Untitled=False,
                WithWindow=False,
            )
            assert presentation is not None
            with TemporaryDirectory(
                prefix=".powerpoint-preview-", dir=destination
            ) as staging_name:
                staging = Path(staging_name)
                for index in range(1, int(presentation.Slides.Count) + 1):
                    presentation.Slides(index).Export(
                        str(staging / f"slide_{index:02d}.png"), "PNG"
                    )
                exported = sorted(
                    (
                        path
                        for path in staging.iterdir()
                        if path.is_file() and path.suffix.casefold() == ".png"
                    ),
                    key=_slide_sort_key,
                )
                if not exported:
                    raise PPTXPreviewUnavailable(
                        "PowerPoint completed without producing slide PNG files"
                    )
                paths: list[Path] = []
                for index, image in enumerate(exported, start=1):
                    target = destination / f"slide_{index:02d}.png"
                    image.replace(target)
                    paths.append(target)
                return paths
        finally:
            if presentation is not None:
                with suppress(Exception):
                    presentation.Close()
            if application is not None:
                with suppress(Exception):
                    application.Quit()


def select_pptx_preview_renderer(
    *,
    platform_name: str | None = None,
    dispatch_factory: DispatchFactory | None = None,
) -> PPTXPreviewRenderer:
    """Select the supported renderer for the current local platform."""
    platform_value = platform_name or sys.platform
    if platform_value == "win32":
        return PowerPointPreviewRenderer(dispatch_factory or _dispatch_powerpoint)
    raise PPTXPreviewUnavailable(
        f"No PPTX preview renderer is available for platform: {platform_value}"
    )


def _dispatch_powerpoint(program_id: str) -> Any:
    try:
        from win32com.client import DispatchEx
    except ImportError as error:
        raise PPTXPreviewUnavailable(
            "pywin32 is required for Microsoft PowerPoint preview rendering"
        ) from error
    return DispatchEx(program_id)


def _slide_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"(\d+)", path.stem)
    return (int(match.group(1)) if match else sys.maxsize, path.name.casefold())
