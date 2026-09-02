from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from localdeck.agents.base import Agent, AgentTurnLimitError
from localdeck.llm.protocol import AssistantResponse, ToolCall
from localdeck.mcp.client import MCPTool, MCPToolResult


class ScriptedLLM:
    def __init__(self, responses: Iterable[AssistantResponse]) -> None:
        self.responses = iter(responses)
        self.requests: list[list[dict]] = []

    async def complete(
        self, messages: list[dict], tools: list[dict]
    ) -> AssistantResponse:
        self.requests.append([dict(message) for message in messages])
        return next(self.responses)


class RecordingTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[MCPTool]:
        schema = {"type": "object", "properties": {}}
        return [
            MCPTool(name="write_file", input_schema=schema),
            MCPTool(name="finalize", input_schema=schema),
        ]

    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        self.calls.append((name, arguments))
        if name == "finalize":
            return MCPToolResult(text=arguments["outcome"])
        return MCPToolResult(text="written")


def response_with_call(name: str, arguments: str, call_id: str) -> AssistantResponse:
    return AssistantResponse(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)]
    )


async def test_agent_executes_tools_until_finalize() -> None:
    llm = ScriptedLLM(
        [
            response_with_call(
                "write_file",
                json.dumps({"path": "manuscript.md", "content": "# Topic"}),
                "call-1",
            ),
            response_with_call(
                "finalize", json.dumps({"outcome": "manuscript.md"}), "call-2"
            ),
        ]
    )
    tools = RecordingTools()
    agent = Agent("Research", llm, tools, "system", max_turns=4)

    outcome = await agent.run("create a manuscript")

    assert outcome == "manuscript.md"
    assert [name for name, _ in tools.calls] == ["write_file", "finalize"]
    assert llm.requests[1][-1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "written",
    }


async def test_agent_returns_invalid_json_as_tool_error() -> None:
    llm = ScriptedLLM(
        [
            response_with_call("write_file", "{broken", "bad-call"),
            response_with_call(
                "finalize", json.dumps({"outcome": "result.md"}), "final-call"
            ),
        ]
    )
    tools = RecordingTools()
    agent = Agent("Research", llm, tools, "system", max_turns=3)

    assert await agent.run("create") == "result.md"
    assert tools.calls == [("finalize", {"outcome": "result.md"})]
    assert "Invalid JSON arguments" in llm.requests[1][-1]["content"]


async def test_agent_prompts_model_to_continue_when_no_tool_is_called() -> None:
    llm = ScriptedLLM(
        [
            AssistantResponse(content="I will prepare it."),
            response_with_call(
                "finalize", json.dumps({"outcome": "result.md"}), "final-call"
            ),
        ]
    )
    agent = Agent("Research", llm, RecordingTools(), "system", max_turns=3)

    assert await agent.run("create") == "result.md"
    assert llm.requests[1][-1]["role"] == "user"
    assert "tool" in llm.requests[1][-1]["content"].lower()


async def test_agent_stops_at_turn_limit() -> None:
    llm = ScriptedLLM(
        [AssistantResponse(content="not done"), AssistantResponse(content="still not done")]
    )
    agent = Agent("Research", llm, RecordingTools(), "system", max_turns=2)

    with pytest.raises(AgentTurnLimitError, match="Research"):
        await agent.run("create")


async def test_agent_ignores_finalize_when_same_batch_contains_tool_error() -> None:
    llm = ScriptedLLM(
        [
            AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id="bad-write",
                        name="write_file",
                        arguments="{broken",
                    ),
                    ToolCall(
                        id="early-finalize",
                        name="finalize",
                        arguments=json.dumps({"outcome": "result.md"}),
                    ),
                ]
            ),
            response_with_call(
                "finalize", json.dumps({"outcome": "result.md"}), "valid-finalize"
            ),
        ]
    )
    agent = Agent("Research", llm, RecordingTools(), "system", max_turns=2)

    assert await agent.run("create") == "result.md"
    assert len(llm.requests) == 2
    assert "Invalid JSON arguments" in llm.requests[1][-2]["content"]
