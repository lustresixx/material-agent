"""Completion tool that validates an Agent outcome inside its workspace."""

from __future__ import annotations

import os
from pathlib import Path

from fastmcp import FastMCP

from localdeck.workspace import WorkspaceGuard

mcp = FastMCP("LocalDeck Task")


def _guard() -> WorkspaceGuard:
    raw_workspace = os.getenv("LOCALDECK_WORKSPACE", "").strip()
    if not raw_workspace:
        raise RuntimeError("LOCALDECK_WORKSPACE is required")
    return WorkspaceGuard(Path(raw_workspace))


@mcp.tool()
def finalize(outcome: str) -> str:
    """Finish the current Agent stage after its output path exists."""

    target = _guard().resolve(outcome)
    if not target.exists():
        raise ValueError(f"Final outcome does not exist: {outcome}")
    return outcome


def main() -> None:
    """Run the task server over stdio."""

    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()

