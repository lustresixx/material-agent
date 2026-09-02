"""Provider-neutral, bounded tool-calling Agent loop."""

from __future__ import annotations

import json
from typing import Any, Protocol

from localdeck.llm.protocol import AssistantResponse, LLMClient, ToolCall
from localdeck.mcp.client import MCPTool, MCPToolResult


class AgentTurnLimitError(RuntimeError):
    """Raised when an agent does not finalize within its configured budget."""


class ToolProvider(Protocol):
    """Tool catalog and execution interface shared by MCP and test doubles."""

    async def list_tools(self) -> list[MCPTool]:
        """Return tools visible to the current Agent."""

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> MCPToolResult:
        """Execute a tool and return a normalized text result."""


class Agent:
    """Run a bounded assistant/tool conversation until ``finalize`` succeeds."""

    def __init__(
        self,
        name: str,
        llm: LLMClient,
        tools: ToolProvider,
        system_prompt: str,
        *,
        max_turns: int,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self.name = name
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.history: list[dict[str, Any]] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0

    async def run(self, prompt: str) -> str:
        """Execute the conversation and return the finalized outcome string."""

        catalog = await self.tools.list_tools()
        tool_specs = [tool.as_openai_tool() for tool in catalog]
        self.history = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ]

        for _turn in range(self.max_turns):
            response = await self.llm.complete(self.history, tool_specs)
            self.prompt_tokens += response.prompt_tokens
            self.completion_tokens += response.completion_tokens
            self.history.append(self._assistant_message(response))

            if not response.tool_calls:
                self.history.append(
                    {
                        "role": "user",
                        "content": (
                            "Continue the task by calling the available tools. "
                            "Call finalize only after the requested artifact exists."
                        ),
                    }
                )
                continue

            outcome = await self._execute_calls(response.tool_calls)
            if outcome is not None:
                return outcome

        raise AgentTurnLimitError(
            f"{self.name} did not finalize within {self.max_turns} turns"
        )

    @staticmethod
    def _assistant_message(response: AssistantResponse) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": response.content,
        }
        if response.tool_calls:
            message["tool_calls"] = [
                call.as_message_value() for call in response.tool_calls
            ]
        return message

    async def _execute_calls(self, calls: list[ToolCall]) -> str | None:
        outcome: str | None = None
        batch_failed = False
        for call in calls:
            result, arguments = await self._execute_call(call)
            batch_failed = batch_failed or result.is_error
            self.history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result.text,
                }
            )
            if call.name == "finalize" and not result.is_error:
                value = arguments.get("outcome") if arguments is not None else None
                if isinstance(value, str) and value.strip():
                    outcome = value.strip()
        return None if batch_failed else outcome

    async def _execute_call(
        self, call: ToolCall
    ) -> tuple[MCPToolResult, dict[str, Any] | None]:
        try:
            arguments = json.loads(call.arguments or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("arguments must decode to an object")
        except (json.JSONDecodeError, ValueError) as error:
            return (
                MCPToolResult(
                    text=f"Invalid JSON arguments for {call.name}: {error}",
                    is_error=True,
                ),
                None,
            )

        try:
            return await self.tools.call_tool(call.name, arguments), arguments
        except Exception as error:
            return (
                MCPToolResult(
                    text=f"Tool {call.name} failed: {error}",
                    is_error=True,
                ),
                arguments,
            )
