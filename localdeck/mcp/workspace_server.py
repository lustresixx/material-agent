"""FastMCP stdio server exposing only workspace-confined file operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

from localdeck.tools.workspace import WorkspaceTools
from localdeck.workspace import WorkspaceGuard

mcp = FastMCP("LocalDeck Workspace")


def _tools() -> WorkspaceTools:
    """Build the tool facade from the workspace injected by the parent process."""

    raw_workspace = os.getenv("LOCALDECK_WORKSPACE", "").strip()
    if not raw_workspace:
        raise RuntimeError("LOCALDECK_WORKSPACE is required")
    return WorkspaceTools(WorkspaceGuard(Path(raw_workspace)))


@mcp.tool()
def read_file(path: str, offset: int = 0, length: int | None = None) -> str:
    """Read a UTF-8 text file inside the active run workspace."""

    return _tools().read_file(path, offset=offset, length=length)


@mcp.tool()
def write_file(
    path: str,
    content: str,
    mode: Literal["overwrite", "append"] = "overwrite",
) -> dict[str, int | str]:
    """Write or append UTF-8 text inside the active run workspace."""

    return _tools().write_file(path, content, mode)


@mcp.tool()
def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    expected_replacements: int = 1,
) -> dict[str, int | str]:
    """Replace an exact number of text occurrences in a workspace file."""

    return _tools().edit_file(
        file_path,
        old_string,
        new_string,
        expected_replacements=expected_replacements,
    )


@mcp.tool()
def move_file(source: str, destination: str) -> dict[str, str]:
    """Move or rename a file or directory inside the workspace."""

    return _tools().move_file(source, destination)


@mcp.tool()
def create_directory(path: str) -> dict[str, str]:
    """Create a directory and missing parents inside the workspace."""

    return _tools().create_directory(path)


@mcp.tool()
def list_directory(path: str = ".") -> list[str]:
    """List a workspace directory with stable file/directory markers."""

    return _tools().list_directory(path)


def main() -> None:
    """Run the server on stdio; stdout is reserved for MCP frames."""

    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
