from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from localdeck.llm.protocol import AssistantResponse
from localdeck.mcp.client import MCPTool, MCPToolResult
from localdeck.models import InspectionReport
from localdeck.tools.workspace import WorkspaceTools
from localdeck.workspace import WorkspaceGuard


class ScriptedLLM:
    """Deterministic model double that still exercises the real Agent loop."""

    def __init__(self, responses: Iterable[AssistantResponse]) -> None:
        self.responses = iter(responses)
        self.requests: list[list[dict]] = []

    async def complete(self, messages: list[dict], tools: list[dict]) -> AssistantResponse:
        self.requests.append([dict(message) for message in messages])
        return next(self.responses)


class StageTools:
    """Real guarded file tools plus deterministic quality/finalize test tools."""

    def __init__(self, workspace: Path, *, inspection_passes: bool = True) -> None:
        self.workspace = workspace
        self.files = WorkspaceTools(WorkspaceGuard(workspace))
        self.inspection_passes = inspection_passes
        self.calls: list[str] = []

    async def list_tools(self) -> list[MCPTool]:
        schema = {"type": "object", "properties": {}}
        return [
            MCPTool(name=name, input_schema=schema)
            for name in ["read_file", "write_file", "inspect_slide", "finalize"]
        ]

    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        self.calls.append(name)
        try:
            if name == "write_file":
                result = self.files.write_file(**arguments)
                return MCPToolResult(text=json.dumps(result))
            if name == "read_file":
                return MCPToolResult(text=self.files.read_file(**arguments))
            if name == "inspect_slide":
                html_file = self.files.guard.resolve(arguments["html_file"])
                report = InspectionReport(
                    html_file=html_file,
                    passed=self.inspection_passes,
                    width=1280,
                    height=720,
                )
                report_path = self.workspace / "inspections" / f"{html_file.stem}.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
                return MCPToolResult(
                    text=report.model_dump_json(), is_error=not report.passed
                )
            if name == "finalize":
                outcome = self.files.guard.resolve(arguments["outcome"])
                if not outcome.exists():
                    return MCPToolResult(text="Outcome does not exist", is_error=True)
                return MCPToolResult(text=arguments["outcome"])
        except Exception as error:
            return MCPToolResult(text=str(error), is_error=True)
        return MCPToolResult(text=f"Unknown tool: {name}", is_error=True)

