"""Coding Plan MCP adapters normalized behind provider-neutral contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from localdeck.mcp.client import MCPToolResult
from localdeck.research.models import PageEvidence, SearchHit


class RemoteToolClient(Protocol):
    """Minimal remote MCP behavior required by research providers."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> MCPToolResult:
        """Call one normalized MCP tool."""
        ...


class SearchProvider(Protocol):
    """Provider-neutral public search interface."""

    async def search(
        self, query: str, *, domain: str | None = None
    ) -> list[SearchHit]:
        """Return normalized public search hits."""
        ...


class PageReader(Protocol):
    """Provider-neutral public page reader interface."""

    async def read(self, url: str) -> PageEvidence:
        """Return fetched page evidence."""
        ...


class CodingPlanSearchProvider:
    """Normalize Coding Plan's ``webSearchPrime`` MCP response."""

    def __init__(self, client: RemoteToolClient) -> None:
        self.client = client

    async def search(
        self, query: str, *, domain: str | None = None
    ) -> list[SearchHit]:
        arguments = {"search_query": query}
        if domain:
            arguments["search_domain_filter"] = domain
        result = await self.client.call_tool("web_search_prime", arguments)
        _raise_tool_error(result)
        payload = _parse_object(result.text)
        raw_hits = _result_list(payload)
        return [
            SearchHit(
                title=str(item.get("title") or item.get("name") or "Untitled"),
                url=str(item.get("url") or item.get("link") or ""),
                snippet=str(
                    item.get("snippet")
                    or item.get("description")
                    or item.get("content")
                    or ""
                ),
                publisher=_optional_string(item.get("publisher")),
                published_at=item.get("published_at") or item.get("date"),
            )
            for item in raw_hits
        ]


class CodingPlanPageReader:
    """Normalize Coding Plan's ``webReader`` MCP response."""

    def __init__(self, client: RemoteToolClient) -> None:
        self.client = client

    async def read(self, url: str) -> PageEvidence:
        result = await self.client.call_tool("webReader", {"url": url})
        _raise_tool_error(result)
        payload = _parse_object(result.text)
        if not isinstance(payload, Mapping):
            raise ValueError("webReader returned an invalid object")
        data = payload.get("data", payload)
        if not isinstance(data, Mapping):
            raise ValueError("webReader returned an invalid object")
        return PageEvidence(
            url=str(data.get("url") or url),
            title=str(data.get("title") or "Untitled page"),
            text=str(data.get("text") or data.get("content") or ""),
            publisher=_optional_string(data.get("publisher")),
            published_at=data.get("published_at") or data.get("date"),
        )


def _parse_object(text: str) -> Mapping[str, Any] | list[Any]:
    payload = json.loads(text)
    if not isinstance(payload, (Mapping, list)):
        raise ValueError("research MCP returned invalid JSON")
    return payload


def _result_list(payload: Mapping[str, Any] | list[Any]) -> list[Mapping[str, Any]]:
    raw: Any = payload
    if isinstance(payload, Mapping):
        raw = (
            payload.get("results")
            or payload.get("search_results")
            or payload.get("data")
            or []
        )
        if isinstance(raw, Mapping):
            raw = raw.get("results") or raw.get("items") or []
    if not isinstance(raw, list):
        raise ValueError("web_search_prime returned an invalid result list")
    return [item for item in raw if isinstance(item, Mapping)]


def _optional_string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _raise_tool_error(result: MCPToolResult) -> None:
    if result.is_error:
        raise RuntimeError(f"research MCP tool failed: {result.text}")
