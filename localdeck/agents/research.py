"""Research-stage specialization that produces a validated Markdown manuscript."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from localdeck.agents.base import Agent, ToolProvider
from localdeck.llm.protocol import LLMClient
from localdeck.models import GenerationRequest
from localdeck.workspace import WorkspaceGuard


class ResearchValidationError(ValueError):
    """Raised when the Research Agent finalizes an invalid manuscript."""


def _system_prompt() -> str:
    prompt_file = Path(__file__).parents[1] / "prompts" / "research.yaml"
    data = yaml.safe_load(prompt_file.read_text(encoding="utf-8"))
    return str(data["system"]).strip()


class ResearchAgent(Agent):
    """Generate and validate the content manuscript stage."""

    def __init__(
        self, llm: LLMClient, tools: ToolProvider, *, max_turns: int = 8
    ) -> None:
        super().__init__("Research", llm, tools, _system_prompt(), max_turns=max_turns)

    async def generate(self, request: GenerationRequest, workspace: Path) -> Path:
        """Run content generation and enforce file type and exact page count."""

        prompt = (
            f"主题: {request.topic}\n"
            f"页数: {request.slides}\n"
            f"语言: {request.language}\n"
            "请创建完整的分页演示文稿。"
        )
        outcome = await self.run(prompt)
        manuscript = WorkspaceGuard(workspace).resolve(outcome)
        if manuscript.suffix.lower() != ".md" or not manuscript.is_file():
            raise ResearchValidationError(
                f"Research outcome must be an existing Markdown file: {outcome}"
            )

        content = manuscript.read_text(encoding="utf-8")
        pages = [page for page in re.split(r"\n\s*---\s*\n", content) if page.strip()]
        if len(pages) != request.slides:
            raise ResearchValidationError(
                f"Research manuscript must contain exactly {request.slides} pages; "
                f"found {len(pages)}"
            )
        return manuscript
