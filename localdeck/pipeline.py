"""End-to-end orchestration for Docker-free presentation generation."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path

from localdeck.agents.design import DesignAgent
from localdeck.agents.research import ResearchAgent
from localdeck.config import Settings
from localdeck.llm.glm import GLMClient
from localdeck.llm.protocol import LLMClient
from localdeck.logging import write_json, write_jsonl
from localdeck.mcp.client import FilteredTools, LocalToolHub
from localdeck.models import (
    GenerationRequest,
    GenerationResult,
    RunManifest,
    RunStage,
)
from localdeck.rendering.exporter import HTMLExporter
from localdeck.rendering.verifier import PPTXVerifier

RESEARCH_TOOLS = {
    "read_file",
    "write_file",
    "edit_file",
    "move_file",
    "create_directory",
    "list_directory",
    "finalize",
}
DESIGN_TOOLS = RESEARCH_TOOLS | {"inspect_slide"}


class LocalDeckPipeline:
    """Coordinate Agents, local tools, inspection, export, and publication."""

    def __init__(self, settings: Settings, *, llm: LLMClient | None = None) -> None:
        self.settings = settings
        self.llm = llm or GLMClient(settings)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Generate one presentation while preserving every diagnostic artifact."""

        workspace = self._create_workspace()
        manifest_path = workspace / "manifest.json"
        manifest = RunManifest(run_id=workspace.name, workspace=workspace)
        write_json(workspace / "request.json", request.model_dump(mode="json"))
        self._save_manifest(manifest_path, manifest)

        manuscript: Path | None = None
        slides_dir: Path | None = None
        current_stage = RunStage.RESEARCH
        try:
            async with LocalToolHub(workspace) as hub:
                manifest.start_stage(RunStage.RESEARCH)
                self._save_manifest(manifest_path, manifest)
                research = ResearchAgent(
                    self.llm,
                    FilteredTools(hub, RESEARCH_TOOLS),
                    max_turns=self.settings.research_max_turns,
                )
                manuscript = await research.generate(request, workspace)
                write_jsonl(workspace / "history" / "research.jsonl", research.history)
                manifest.complete_stage(RunStage.RESEARCH, manuscript)
                self._save_manifest(manifest_path, manifest)

                current_stage = RunStage.DESIGN
                manifest.start_stage(RunStage.DESIGN)
                self._save_manifest(manifest_path, manifest)
                design = DesignAgent(
                    self.llm,
                    FilteredTools(hub, DESIGN_TOOLS),
                    max_turns=self.settings.design_max_turns,
                )
                slides_dir = await design.generate(
                    manuscript,
                    expected_slides=request.slides,
                    aspect_ratio=request.aspect_ratio,
                    workspace=workspace,
                )
                write_jsonl(workspace / "history" / "design.jsonl", design.history)
                write_jsonl(workspace / "history" / "tools.jsonl", hub.history)
                manifest.complete_stage(RunStage.DESIGN, slides_dir)
                self._save_manifest(manifest_path, manifest)

            current_stage = RunStage.EXPORT
            manifest.start_stage(RunStage.EXPORT)
            self._save_manifest(manifest_path, manifest)
            workspace_pptx = workspace / "output.pptx"
            await HTMLExporter().export(
                slides_dir, workspace_pptx, request.aspect_ratio
            )
            manifest.complete_stage(RunStage.EXPORT, workspace_pptx)
            self._save_manifest(manifest_path, manifest)

            current_stage = RunStage.VERIFY
            manifest.start_stage(RunStage.VERIFY)
            self._save_manifest(manifest_path, manifest)
            PPTXVerifier().verify(workspace_pptx, expected_slides=request.slides)
            self._publish(workspace_pptx, request.output)
            manifest.complete_stage(RunStage.VERIFY, request.output)
            self._save_manifest(manifest_path, manifest)
        except Exception as error:
            manifest.fail_stage(current_stage, str(error))
            self._save_manifest(manifest_path, manifest)
            raise

        assert manuscript is not None and slides_dir is not None
        return GenerationResult(
            output=request.output,
            workspace=workspace,
            manuscript=manuscript,
            slides_dir=slides_dir,
            manifest=manifest_path,
        )

    def _create_workspace(self) -> Path:
        """Create a sortable, collision-resistant run directory."""

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        workspace = self.settings.runs_dir / f"{timestamp}-{uuid.uuid4().hex[:8]}"
        workspace.mkdir(parents=True, exist_ok=False)
        return workspace.resolve()

    @staticmethod
    def _save_manifest(path: Path, manifest: RunManifest) -> None:
        write_json(path, manifest.model_dump(mode="json"))

    @staticmethod
    def _publish(source: Path, output: Path) -> None:
        """Copy to a sibling temporary file before atomically replacing output."""

        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}-{uuid.uuid4().hex}.pptx")
        try:
            shutil.copy2(source, temporary)
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
