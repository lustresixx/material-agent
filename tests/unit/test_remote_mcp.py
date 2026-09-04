from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ConnectError
from mcp.types import TextContent
from pydantic import SecretStr

import localdeck.mcp.remote as remote_module
from localdeck.mcp.remote import RemoteMCPClient


class FakeSession:
    """Small async session double matching the MCP methods used by the client."""

    fail_initialize = False
    exited = False
    instances = 0

    def __init__(self, reader: object, writer: object) -> None:
        type(self).instances += 1
        self.reader = reader
        self.writer = writer

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        type(self).exited = True

    async def initialize(self) -> None:
        if self.fail_initialize:
            raise RuntimeError("initialization failed")

    async def list_tools(self) -> SimpleNamespace:
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="webSearchPrime",
                    description="Search authoritative public pages",
                    inputSchema={"type": "object"},
                )
            ]
        )

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> SimpleNamespace:
        return SimpleNamespace(
            content=[TextContent(type="text", text=f"{name}:ok")],
            isError=False,
        )


class ConcurrentFakeSession(FakeSession):
    """Expose whether concurrent requests use isolated sessions."""

    active_calls = 0
    max_active_calls = 0
    completed_calls = 0

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> SimpleNamespace:
        type(self).active_calls += 1
        type(self).max_active_calls = max(
            type(self).max_active_calls, type(self).active_calls
        )
        try:
            await asyncio.sleep(0)
            return await super().call_tool(name, arguments)
        finally:
            type(self).active_calls -= 1
            type(self).completed_calls += 1


@pytest.mark.asyncio
async def test_remote_client_connects_lists_calls_and_redacts_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    @asynccontextmanager
    async def fake_streamablehttp_client(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        sse_read_timeout: float,
    ) -> AsyncIterator[tuple[object, object, object]]:
        captured.update(
            url=url,
            headers=headers,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
        )
        yield object(), object(), object()

    monkeypatch.setattr(
        remote_module, "streamablehttp_client", fake_streamablehttp_client
    )
    monkeypatch.setattr(remote_module, "ClientSession", FakeSession)
    token = "coding-plan-secret"
    FakeSession.instances = 0
    client = RemoteMCPClient(
        "https://search.example/mcp",
        SecretStr(token),
        timeout=12,
        sse_read_timeout=34,
    )

    async with client:
        tools = await client.list_tools()
        result = await client.call_tool(
            "webSearchPrime",
            {
                "query": "Huawei annual report",
                "api_key": token,
                "nested": {"Authorization": f"Bearer {token}"},
            },
        )

    assert captured["headers"] == {"Authorization": f"Bearer {token}"}
    assert not hasattr(client, "headers")
    assert tools[0].name == "webSearchPrime"
    assert result.text == "webSearchPrime:ok"
    assert result.is_error is False
    assert FakeSession.instances == 2
    assert client.history[0]["arguments"] == {
        "query": "Huawei annual report",
        "api_key": "[REDACTED]",
        "nested": {"Authorization": "[REDACTED]"},
    }
    assert token not in repr(client.history)


@pytest.mark.asyncio
async def test_remote_client_closes_transport_when_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport_exited = False

    @asynccontextmanager
    async def fake_streamablehttp_client(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        sse_read_timeout: float,
    ) -> AsyncIterator[tuple[object, object, object]]:
        nonlocal transport_exited
        yield object(), object(), object()
        transport_exited = True

    FakeSession.fail_initialize = True
    FakeSession.exited = False
    FakeSession.instances = 0
    monkeypatch.setattr(
        remote_module, "streamablehttp_client", fake_streamablehttp_client
    )
    monkeypatch.setattr(remote_module, "ClientSession", FakeSession)
    client = RemoteMCPClient(
        "https://search.example/mcp",
        SecretStr("coding-plan-secret"),
    )

    with pytest.raises(RuntimeError, match="initialization failed"):
        await client.list_tools()

    assert FakeSession.exited is True
    assert transport_exited is True
    FakeSession.fail_initialize = False


@pytest.mark.asyncio
async def test_remote_client_isolates_concurrent_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent requests must not share one Streamable HTTP session."""

    @asynccontextmanager
    async def fake_streamablehttp_client(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        sse_read_timeout: float,
    ) -> AsyncIterator[tuple[object, object, object]]:
        yield object(), object(), object()

    monkeypatch.setattr(
        remote_module, "streamablehttp_client", fake_streamablehttp_client
    )
    monkeypatch.setattr(remote_module, "ClientSession", ConcurrentFakeSession)
    ConcurrentFakeSession.max_active_calls = 0
    ConcurrentFakeSession.completed_calls = 0
    ConcurrentFakeSession.instances = 0
    client = RemoteMCPClient(
        "https://search.example/mcp", SecretStr("coding-plan-secret")
    )

    async with client:
        await asyncio.gather(
            client.call_tool("webSearchPrime", {"query": "first"}),
            client.call_tool("webSearchPrime", {"query": "second"}),
        )

    assert ConcurrentFakeSession.instances == 2
    assert ConcurrentFakeSession.completed_calls == 2


@pytest.mark.asyncio
async def test_remote_client_reconnects_after_transient_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proxy connection failure should reopen the operation session once."""

    attempts = 0

    @asynccontextmanager
    async def flaky_streamablehttp_client(
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
        sse_read_timeout: float,
    ) -> AsyncIterator[tuple[object, object, object]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ExceptionGroup(
                "transport failed", [ConnectError("proxy unavailable")]
            )
        yield object(), object(), object()

    FakeSession.fail_initialize = False
    monkeypatch.setattr(
        remote_module, "streamablehttp_client", flaky_streamablehttp_client
    )
    monkeypatch.setattr(remote_module, "ClientSession", FakeSession)
    client = RemoteMCPClient(
        "https://search.example/mcp",
        SecretStr("coding-plan-secret"),
        max_retries=1,
    )

    tools = await client.list_tools()

    assert tools[0].name == "webSearchPrime"
    assert attempts == 2
