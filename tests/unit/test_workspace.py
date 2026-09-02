from __future__ import annotations

from pathlib import Path

import pytest

from localdeck.workspace import WorkspaceGuard, WorkspaceViolation


def test_guard_resolves_relative_path_inside_workspace(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path / "run")

    resolved = guard.resolve("slides/slide_01.html")

    assert resolved == (tmp_path / "run" / "slides" / "slide_01.html").resolve()
    assert guard.root.is_dir()


def test_guard_rejects_parent_escape(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path / "run")

    with pytest.raises(WorkspaceViolation, match="outside workspace"):
        guard.resolve("../secret.txt")


def test_guard_rejects_absolute_path_outside_workspace(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path / "run")

    with pytest.raises(WorkspaceViolation, match="outside workspace"):
        guard.resolve(tmp_path / "secret.txt")


def test_guard_accepts_absolute_path_inside_workspace(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path / "run")
    target = guard.root / "manuscript.md"

    assert guard.resolve(target) == target.resolve()
