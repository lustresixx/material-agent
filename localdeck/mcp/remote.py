"""Lifecycle-safe client for authenticated remote Streamable HTTP MCP servers."""

from __future__ import annotations

from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent
from pydantic import SecretStr

from localdeck.mcp.client import MCPTool, MCPToolResult

_SENSITIVE_KEYS = frozenset({"authorization", "api_key", "token", "secret"})


class RemoteMCPClient:
    """Connect to one authenticated Coding Plan research MCP endpoint."""

    def __init__(
        self,
        url: str,
        token: SecretStr,
        *,
        timeout: float = 30,
        sse_read_timeout: float = 300,
    ) -> None:
        self.url = url
        self._token = token
        self.timeout = timeout
        self.sse_read_timeout = sse_read_timeout
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self.history: list[dict[str, Any]] = []

    async def __aenter__(self) -> RemoteMCPClient:
        stack = AsyncExitStack()
        try:
            reader, writer, _ = await stack.enter_async_context(
                streamablehttp_client(
                    self.url,
                    headers={
                        "Authorization": (
                            f"Bearer {self._token.get_secret_value()}"
                        )
                    },
                    timeout=self.timeout,
                    sse_read_timeout=self.sse_read_timeout,
                )
            )
            session = await stack.enter_async_context(ClientSession(reader, writer))
            await session.initialize()
        except BaseException:
            await stack.aclose()
            raise
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
            raise RuntimeError("Remote MCP client is not connected")
        return self._session

    async def list_tools(self) -> list[MCPTool]:
        """Fetch remote tool definitions in the shared agent-tool shape."""
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
        """Call a remote tool and retain only sanitized audit history."""
        call_arguments = arguments or {}
        response = await self._require_session().call_tool(name, call_arguments)
        texts = [
            block.text for block in response.content if isinstance(block, TextContent)
        ]
        result = MCPToolResult(
            text="\n".join(texts),
            is_error=bool(response.isError),
        )
        self.history.append(
            {
                "tool": name,
                "arguments": _redact(call_arguments),
                "result": result.model_dump(),
            }
        )
        return result


def _redact(value: Any) -> Any:
    """Recursively redact known credential fields before serialization."""
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if isinstance(key, str) and key.casefold() in _SENSITIVE_KEYS
                else _redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value
