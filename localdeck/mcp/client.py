"""Lifecycle-safe client for LocalDeck's local stdio MCP servers."""

from __future__ import annotations

import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field


class MCPTool(BaseModel):
    """Tool metadata in the OpenAI-compatible shape needed by an Agent."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)

    def as_openai_tool(self) -> dict[str, Any]:
        """Return the function-tool structure accepted by chat completions."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class MCPToolResult(BaseModel):
    """Normalized text result independent of the MCP SDK's content classes."""

    text: str
    is_error: bool = False


class LocalMCPClient:
    """Start one trusted Python MCP module and own its complete async lifecycle."""

    def __init__(self, server_module: str, workspace: Path) -> None:
        self.server_module = server_module
        self.workspace = workspace.resolve()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "LocalMCPClient":
        self.workspace.mkdir(parents=True, exist_ok=True)
        stack = AsyncExitStack()

        # Tool servers do not need the model credential. Explicit removal prevents a
        # future tool bug or diagnostic dump from exposing the user's API key.
        child_env = os.environ.copy()
        child_env.pop("ZAI_API_KEY", None)
        child_env["LOCALDECK_WORKSPACE"] = str(self.workspace)

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", self.server_module],
            env=child_env,
        )
        reader, writer = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(reader, writer))
        await session.initialize()
        self._stack = stack
        self._session = session
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCP client is not connected")
        return self._session

    async def list_tools(self) -> list[MCPTool]:
        """Fetch and normalize the server's current tool definitions."""

        response = await self._require_session().list_tools()
        return [
            MCPTool(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema,
            )
            for tool in response.tools
        ]

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> MCPToolResult:
        """Call one tool and combine its textual MCP content blocks."""

        response = await self._require_session().call_tool(name, arguments or {})
        texts = [
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ]
        return MCPToolResult(
            text="\n".join(texts),
            is_error=bool(response.isError),
        )

