"""GLM client implemented through Zhipu's OpenAI-compatible endpoint."""

from __future__ import annotations

import asyncio
from typing import Any

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

from localdeck.config import Settings
from localdeck.llm.protocol import AssistantResponse, ToolCall


def should_retry(error: object) -> bool:
    """Return whether an API failure is transient and safe to retry."""

    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    status_code = getattr(error, "status_code", None)
    return status_code == 429 or (
        isinstance(status_code, int) and 500 <= status_code < 600
    )


class GLMClient:
    """Translate LocalDeck messages to GLM chat completions.

    An SDK client may be injected for deterministic tests. The default client unwraps
    the secret exactly once, at construction of the network boundary.
    """

    def __init__(self, settings: Settings, sdk_client: Any | None = None) -> None:
        self.settings = settings
        self._client = sdk_client or AsyncOpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=0,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AssistantResponse:
        """Request one tool-capable model turn with bounded transient retries."""

        for attempt in range(self.settings.max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.settings.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "extra_body": {"thinking": {"type": "enabled"}},
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                response = await self._client.chat.completions.create(**kwargs)
                return self._normalize(response)
            except Exception as error:
                if attempt >= self.settings.max_retries or not should_retry(error):
                    raise
                await asyncio.sleep(min(2**attempt, 8))

        raise RuntimeError("unreachable retry state")

    @staticmethod
    def _normalize(response: Any) -> AssistantResponse:
        """Extract only stable fields used by the rest of the application."""

        message = response.choices[0].message
        calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments,
            )
            for call in (message.tool_calls or [])
        ]
        usage = getattr(response, "usage", None)
        return AssistantResponse(
            content=message.content,
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
