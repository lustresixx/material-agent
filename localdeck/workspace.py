"""Path confinement primitives for model-accessible filesystem operations."""

from __future__ import annotations

from os import PathLike
from pathlib import Path


class WorkspaceViolation(ValueError):
    """Raised when a requested path resolves outside the active run workspace."""


class WorkspaceGuard:
    """Resolve paths while enforcing a single-directory security boundary.

    ``Path.resolve(strict=False)`` resolves existing symbolic links and normalizes
    ``..`` components. Checking the normalized result, rather than the user-provided
    text, prevents lexical paths and symlinks from escaping the workspace.
    """

    def __init__(self, root: str | PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, requested: str | PathLike[str]) -> Path:
        """Return a normalized in-workspace path or raise ``WorkspaceViolation``."""

        raw = Path(requested).expanduser()
        candidate = (raw if raw.is_absolute() else self.root / raw).resolve(
            strict=False
        )
        if not candidate.is_relative_to(self.root):
            raise WorkspaceViolation(
                f"Path is outside workspace {self.root}: {requested}"
            )
        return candidate

