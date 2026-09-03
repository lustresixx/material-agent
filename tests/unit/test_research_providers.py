from __future__ import annotations

import json
from typing import Any

from localdeck.mcp.client import MCPToolResult
from localdeck.research.providers import CodingPlanPageReader, CodingPlanSearchProvider


class FakeRemoteClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> MCPToolResult:
        self.calls.append((name, arguments))
        return MCPToolResult(text=json.dumps(self.responses[name]))


async def test_coding_plan_search_normalizes_remote_results() -> None:
    client = FakeRemoteClient(
        {
            "webSearchPrime": {
                "results": [
                    {
                        "title": "Huawei report",
                        "link": "https://huawei.com/report",
                        "description": "Annual results",
                    }
                ]
            }
        }
    )

    hits = await CodingPlanSearchProvider(client).search(
        "Huawei annual report", domain="huawei.com"
    )

    assert hits[0].url == "https://huawei.com/report"
    assert hits[0].published_at is None
    assert client.calls == [
        (
            "webSearchPrime",
            {"query": "Huawei annual report", "domain": "huawei.com"},
        )
    ]


async def test_coding_plan_reader_strips_credentials_from_evidence() -> None:
    client = FakeRemoteClient(
        {
            "webReader": {
                "title": "Official page",
                "url": "https://huawei.com/page",
                "content": "Public evidence",
                "authorization": "Bearer secret-token",
                "headers": {"api_key": "secret-token"},
            }
        }
    )

    evidence = await CodingPlanPageReader(client).read("https://huawei.com/page")
    serialized = evidence.model_dump_json()

    assert evidence.text == "Public evidence"
    assert "secret-token" not in serialized
    assert "authorization" not in serialized.casefold()
    assert "api_key" not in serialized.casefold()
