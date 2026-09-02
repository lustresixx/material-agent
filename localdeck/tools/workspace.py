"""Small, workspace-confined filesystem toolset used by both agents."""

from __future__ import annotations

import shutil
from os import PathLike
from typing import Literal

from localdeck.workspace import WorkspaceGuard


class WorkspaceTools:
    """Implement the six file operations that the MVP exposes to the model.

    This class intentionally has no shell/process operation. Keeping the tool layer
    narrow makes path confinement auditable and prevents prompt content from becoming
    executable host commands.
    """

    def __init__(self, guard: WorkspaceGuard) -> None:
        self.guard = guard

    def read_file(
        self,
        path: str | PathLike[str],
        offset: int = 0,
        length: int | None = None,
    ) -> str:
        """Read UTF-8 text, optionally returning a line range."""

        target = self.guard.resolve(path)
        text = target.read_text(encoding="utf-8")
        if offset == 0 and length is None:
            return text

        lines = text.splitlines()
        selected = lines[offset:] if length is None else lines[offset : offset + length]
        return "\n".join(selected)

    def write_file(
        self,
        path: str | PathLike[str],
        content: str,
        mode: Literal["overwrite", "append"] = "overwrite",
    ) -> dict[str, int | str]:
        """Write UTF-8 text and create missing parent directories."""

        target = self.guard.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_mode = "a" if mode == "append" else "w"
        with target.open(file_mode, encoding="utf-8", newline="") as stream:
            stream.write(content)
        return {"path": str(target), "characters": len(content), "mode": mode}

    def edit_file(
        self,
        file_path: str | PathLike[str],
        old_string: str,
        new_string: str,
        expected_replacements: int = 1,
    ) -> dict[str, int | str]:
        """Replace an exact number of occurrences to avoid broad accidental edits."""

        if expected_replacements < 1:
            raise ValueError("expected_replacements must be at least 1")
        target = self.guard.resolve(file_path)
        text = target.read_text(encoding="utf-8")
        actual = text.count(old_string)
        if actual != expected_replacements:
            raise ValueError(
                f"Replacement count mismatch: expected {expected_replacements}, "
                f"found {actual}"
            )
        target.write_text(text.replace(old_string, new_string), encoding="utf-8")
        return {"path": str(target), "replacements": actual}

    def move_file(
        self, source: str | PathLike[str], destination: str | PathLike[str]
    ) -> dict[str, str]:
        """Move a file or directory between two guarded locations."""

        source_path = self.guard.resolve(source)
        destination_path = self.guard.resolve(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        return {"source": str(source_path), "destination": str(destination_path)}

    def create_directory(self, path: str | PathLike[str]) -> dict[str, str]:
        """Create a guarded directory and any missing parents."""

        target = self.guard.resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return {"path": str(target)}

    def list_directory(self, path: str | PathLike[str] = ".") -> list[str]:
        """List directories first, then files, with deterministic sorting."""

        target = self.guard.resolve(path)
        entries = sorted(
            target.iterdir(), key=lambda item: (not item.is_dir(), item.name)
        )
        return [
            f"[{'DIR' if entry.is_dir() else 'FILE'}] {entry.name}" for entry in entries
        ]
