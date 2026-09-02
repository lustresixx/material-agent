"""Design-stage specialization that enforces inspected, consecutive HTML slides."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml

from localdeck.agents.base import Agent, ToolProvider
from localdeck.llm.protocol import LLMClient
from localdeck.models import InspectionReport
from localdeck.workspace import WorkspaceGuard


class DesignValidationError(ValueError):
    """Raised when finalized slide HTML lacks required files or inspection evidence."""


def _system_prompt() -> str:
    prompt_file = Path(__file__).parents[1] / "prompts" / "design.yaml"
    data = yaml.safe_load(prompt_file.read_text(encoding="utf-8"))
    return str(data["system"]).strip()


class DesignAgent(Agent):
    """Generate slide HTML and verify completion independently of model claims."""

    def __init__(
        self, llm: LLMClient, tools: ToolProvider, *, max_turns: int = 20
    ) -> None:
        super().__init__("Design", llm, tools, _system_prompt(), max_turns=max_turns)

    async def generate(
        self,
        manuscript: Path,
        *,
        expected_slides: int,
        aspect_ratio: Literal["16:9", "4:3"],
        workspace: Path,
    ) -> Path:
        """Run visual generation and require a passing receipt for every slide."""

        prompt = (
            f"文稿路径: {manuscript}\n"
            f"幻灯片页数: {expected_slides}\n"
            f"页面比例: {aspect_ratio}\n"
            "请逐页生成、检查并修正 HTML。"
        )
        outcome = await self.run(prompt)
        guard = WorkspaceGuard(workspace)
        slides_dir = guard.resolve(outcome)
        if not slides_dir.is_dir():
            raise DesignValidationError(
                f"Design outcome must be an existing directory: {outcome}"
            )
        if not (slides_dir / "global.css").is_file():
            raise DesignValidationError("slides/global.css is missing")

        html_files = sorted(slides_dir.glob("slide_*.html"))
        expected_names = [
            f"slide_{index:02d}.html" for index in range(1, expected_slides + 1)
        ]
        actual_names = [path.name for path in html_files]
        if actual_names != expected_names:
            raise DesignValidationError(
                f"Expected consecutive slides {expected_names}; found {actual_names}"
            )

        inspections = guard.resolve("inspections")
        for html_file in html_files:
            report_file = inspections / f"{html_file.stem}.json"
            if not report_file.is_file():
                raise DesignValidationError(
                    f"Missing passing inspection for {html_file.name}"
                )
            report = InspectionReport.model_validate_json(
                report_file.read_text(encoding="utf-8")
            )
            if not report.passed:
                raise DesignValidationError(
                    f"Latest inspection failed for {html_file.name}"
                )
        return slides_dir
