"""Minimal language-model contracts consumed by the Agent loop."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """One OpenAI-compatible function request emitted by a model."""

    id: str
    name: str
    arguments: str

    def as_message_value(self) -> dict[str, Any]:
        """Serialize the call for inclusion in an assistant history message."""

        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


class AssistantResponse(BaseModel):
    """Provider-neutral subset of a chat-completion response."""

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    """Structural interface that makes Agent behavior independently testable."""

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantResponse:
        """Return one assistant turn for the supplied conversation and tools."""

        ...
