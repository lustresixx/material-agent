"""Lifecycle-safe client for authenticated remote Streamable HTTP MCP servers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from types import TracebackType
from typing import Any

import httpx
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
        max_retries: int = 3,
    ) -> None:
        self.url = url
        self._token = token
        self.timeout = timeout
        self.sse_read_timeout = sse_read_timeout
        self.max_retries = max_retries
        self.history: list[dict[str, Any]] = []

    async def __aenter__(self) -> RemoteMCPClient:
        """Keep the wrapper lightweight; each operation owns its connection."""

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Connections are already closed by individual operations."""

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[ClientSession]:
        """Open one initialized transport/session per remote operation."""

        # Coding Plan Streamable HTTP responses close their SSE stream after a
        # result. Reusing the SDK session triggers a closed-memory-stream race,
        # so isolate every operation at the protocol lifecycle boundary.
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
            session = await stack.enter_async_context(
                ClientSession(reader, writer)
            )
            await session.initialize()
            yield session
        finally:
            await stack.aclose()

    async def _run_with_retries(
        self, operation: Callable[[ClientSession], Awaitable[Any]]
    ) -> Any:
        """Retry only transient transport failures with a fresh MCP session."""

        for attempt in range(self.max_retries + 1):
            try:
                async with self._connect() as session:
                    return await operation(session)
            except Exception as error:
                if attempt >= self.max_retries or not _is_transient(error):
                    raise
                await asyncio.sleep(min(0.5 * 2**attempt, 4))
        raise RuntimeError("unreachable MCP retry state")

    async def list_tools(self) -> list[MCPTool]:
        """Fetch remote tool definitions in the shared agent-tool shape."""
        async def fetch(session: ClientSession) -> list[MCPTool]:
            response = await session.list_tools()
            return [
                MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema,
                )
                for tool in response.tools
            ]

        return await self._run_with_retries(fetch)

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> MCPToolResult:
        """Call a remote tool and retain only sanitized audit history."""
        call_arguments = arguments or {}
        response = await self._run_with_retries(
            lambda session: session.call_tool(name, call_arguments)
        )
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


def _is_transient(error: BaseException) -> bool:
    """Return whether an error or nested error group is transport-transient."""

    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(_is_transient(nested) for nested in error.exceptions)
    return False
