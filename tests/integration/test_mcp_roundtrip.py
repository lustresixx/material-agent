from __future__ import annotations

from pathlib import Path

from localdeck.mcp.client import LocalMCPClient


async def test_workspace_server_round_trip(tmp_path: Path) -> None:
    workspace = tmp_path / "run"

    async with LocalMCPClient(
        server_module="localdeck.mcp.workspace_server",
        workspace=workspace,
    ) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools}
        assert names == {
            "create_directory",
            "edit_file",
            "list_directory",
            "move_file",
            "read_file",
            "write_file",
        }

        written = await client.call_tool(
            "write_file", {"path": "notes/topic.txt", "content": "hello MCP"}
        )
        assert not written.is_error

        read = await client.call_tool("read_file", {"path": "notes/topic.txt"})
        assert not read.is_error
        assert read.text == "hello MCP"


async def test_workspace_server_rejects_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "run"

    async with LocalMCPClient(
        server_module="localdeck.mcp.workspace_server",
        workspace=workspace,
    ) as client:
        result = await client.call_tool(
            "write_file", {"path": "../outside.txt", "content": "blocked"}
        )

    assert result.is_error
    assert "outside workspace" in result.text
    assert not (tmp_path / "outside.txt").exists()
