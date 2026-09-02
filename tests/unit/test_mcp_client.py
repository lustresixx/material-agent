from __future__ import annotations

from pathlib import Path

import pytest

from localdeck.mcp import client as client_module
from localdeck.mcp.client import LocalToolHub, MCPTool


async def test_tool_hub_closes_started_servers_when_enter_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exited: list[str] = []

    class DuplicateToolClient:
        def __init__(self, server_module: str, workspace: Path) -> None:
            self.server_module = server_module

        async def __aenter__(self) -> DuplicateToolClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            exited.append(self.server_module)

        async def list_tools(self) -> list[MCPTool]:
            return [MCPTool(name="duplicate")]

    monkeypatch.setattr(client_module, "LocalMCPClient", DuplicateToolClient)
    hub = LocalToolHub(tmp_path, ("first", "second"))

    with pytest.raises(ValueError, match="Duplicate MCP tool"):
        await hub.__aenter__()

    assert exited == ["second", "first"]
