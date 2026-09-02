from __future__ import annotations

from pathlib import Path

import pytest

from localdeck.tools.workspace import WorkspaceTools
from localdeck.workspace import WorkspaceGuard, WorkspaceViolation


@pytest.fixture
def tools(tmp_path: Path) -> WorkspaceTools:
    return WorkspaceTools(WorkspaceGuard(tmp_path / "run"))


def test_write_and_read_file(tools: WorkspaceTools) -> None:
    tools.write_file("notes/topic.txt", "alpha\nbeta\ngamma")

    assert tools.read_file("notes/topic.txt") == "alpha\nbeta\ngamma"
    assert tools.read_file("notes/topic.txt", offset=1, length=1) == "beta"


def test_write_file_can_append(tools: WorkspaceTools) -> None:
    tools.write_file("notes.txt", "alpha")
    tools.write_file("notes.txt", "\nbeta", mode="append")

    assert tools.read_file("notes.txt") == "alpha\nbeta"


def test_edit_file_requires_exact_replacement_count(tools: WorkspaceTools) -> None:
    tools.write_file("slide.html", "old old")

    with pytest.raises(ValueError, match="expected 1"):
        tools.edit_file("slide.html", "old", "new")

    result = tools.edit_file("slide.html", "old", "new", expected_replacements=2)
    assert result["replacements"] == 2
    assert tools.read_file("slide.html") == "new new"


def test_list_directory_is_stable_and_typed(tools: WorkspaceTools) -> None:
    tools.create_directory("assets")
    tools.write_file("z.txt", "z")
    tools.write_file("a.txt", "a")

    assert tools.list_directory(".") == [
        "[DIR] assets",
        "[FILE] a.txt",
        "[FILE] z.txt",
    ]


def test_move_file_rejects_destination_escape(
    tools: WorkspaceTools, tmp_path: Path
) -> None:
    tools.write_file("inside.txt", "safe")

    with pytest.raises(WorkspaceViolation):
        tools.move_file("inside.txt", tmp_path / "outside.txt")


def test_move_file_creates_destination_parent(tools: WorkspaceTools) -> None:
    tools.write_file("inside.txt", "safe")

    tools.move_file("inside.txt", "archive/inside.txt")

    assert tools.read_file("archive/inside.txt") == "safe"
