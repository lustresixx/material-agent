"""FastMCP wrapper for the local Playwright slide inspector."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

from localdeck.quality import SlideInspector

mcp = FastMCP("LocalDeck Quality")


def _workspace() -> Path:
    raw_workspace = os.getenv("LOCALDECK_WORKSPACE", "").strip()
    if not raw_workspace:
        raise RuntimeError("LOCALDECK_WORKSPACE is required")
    return Path(raw_workspace)


@mcp.tool()
async def inspect_slide(
    html_file: str,
    aspect_ratio: Literal["16:9", "4:3"] = "16:9",
) -> dict:
    """Inspect one local HTML slide and return its persisted quality report."""

    async with SlideInspector(_workspace()) as inspector:
        report = await inspector.inspect(html_file, aspect_ratio)
    return report.model_dump(mode="json")


def main() -> None:
    """Run the quality server over stdio."""

    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
