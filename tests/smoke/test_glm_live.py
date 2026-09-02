from __future__ import annotations

import os

import pytest

from localdeck.config import Settings
from localdeck.llm.glm import GLMClient


@pytest.mark.live
async def test_glm_returns_a_structured_tool_call() -> None:
    """Exercise the real provider only when a developer explicitly opts in."""

    if os.getenv("LOCALDECK_RUN_LIVE_TESTS") != "1":
        pytest.skip("set LOCALDECK_RUN_LIVE_TESTS=1 to call the real GLM API")

    client = GLMClient(Settings.from_env())
    response = await client.complete(
        [
            {
                "role": "system",
                "content": (
                    "Call the finalize tool exactly once. Do not answer in text."
                ),
            },
            {"role": "user", "content": "Finalize with outcome smoke-ok."},
        ],
        [
            {
                "type": "function",
                "function": {
                    "name": "finalize",
                    "description": "Finish the smoke test.",
                    "parameters": {
                        "type": "object",
                        "properties": {"outcome": {"type": "string"}},
                        "required": ["outcome"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
    )

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "finalize"
