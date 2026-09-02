"""Language-model adapters with a provider-independent internal protocol."""

from localdeck.llm.glm import GLMClient
from localdeck.llm.protocol import AssistantResponse, LLMClient, ToolCall

__all__ = ["AssistantResponse", "GLMClient", "LLMClient", "ToolCall"]
