"""End-to-end orchestration for Docker-free presentation generation."""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from localdeck.agents.design import DesignAgent
from localdeck.agents.research import ResearchAgent
from localdeck.comparison.models import RouteMetrics
from localdeck.comparison.report import write_comparison_report
from localdeck.config import Settings
from localdeck.generation.html_agent.generator import (
    HtmlRouteGenerator,
    HtmlRouteResult,
)
from localdeck.generation.template_engine.frame_map import write_frame_map
from localdeck.generation.template_engine.generator import TemplateRouteGenerator
from localdeck.generation.template_engine.matcher import match_plan
from localdeck.inputs.models import OutlineDocument
from localdeck.inputs.normalizer import normalize_outline_payload
from localdeck.llm.glm import GLMClient
from localdeck.llm.protocol import LLMClient
from localdeck.logging import StageTimer, write_json, write_jsonl
from localdeck.mcp.client import FilteredTools, LocalToolHub
from localdeck.mcp.remote import RemoteMCPClient
from localdeck.models import (
    GenerationRequest,
    GenerationResult,
    GenerationRoute,
    RunManifest,
    RunStage,
    StageRecord,
    TemplateGenerationRequest,
    TemplateGenerationResult,
    TemplateRouteRecord,
    TemplateRunManifest,
    TemplateRunStage,
)
from localdeck.planning.copywriter import SharedCopy, prepare_shared_copy
from localdeck.planning.planner import SlidePlanner
from localdeck.quality.content import inspect_content
from localdeck.quality.deck import FinalDeckQualityGate, QualityReport
from localdeck.rendering.exporter import HTMLExporter
from localdeck.rendering.pptx_preview import (
    PPTXPreviewRenderer,
    select_pptx_preview_renderer,
)
from localdeck.rendering.verifier import PPTXVerifier
from localdeck.research.coordinator import ResearchCoordinator
from localdeck.research.models import ResearchPacket
from localdeck.research.providers import (
    CodingPlanPageReader,
    CodingPlanSearchProvider,
    PageReader,
    SearchProvider,
)
from localdeck.templates.inspector import TemplateInspector
from localdeck.templates.models import TemplateInspection

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


class TemplateDeckPipeline:
    """Run research and both template-aware visual routes in one workspace."""

    def __init__(
        self,
        settings: Settings,
        *,
        llm: LLMClient | None = None,
        search: SearchProvider | None = None,
        reader: PageReader | None = None,
        preview_renderer: PPTXPreviewRenderer | None = None,
        html_generator: Any | None = None,
    ) -> None:
        self.settings = settings
        self.llm = llm or GLMClient(settings)
        self.search = search
        self.reader = reader
        self.preview_renderer = preview_renderer or select_pptx_preview_renderer()
        self.html_generator = html_generator

    async def generate(
        self, request: TemplateGenerationRequest
    ) -> TemplateGenerationResult:
        """Execute every stage, retaining diagnostics and independent failures."""
        workspace = self._create_workspace()
        manifest_path = workspace / "manifest.json"
        manifest = TemplateRunManifest(run_id=workspace.name, workspace=workspace)
        write_json(workspace / "request.json", request.model_dump(mode="json"))
        self._save(manifest_path, manifest)

        outline = self._timed(
            manifest,
            TemplateRunStage.INPUT,
            lambda: self._load_outline(request.outline),
            manifest_path,
        )
        inspection = self._timed(
            manifest,
            TemplateRunStage.TEMPLATE,
            lambda: TemplateInspector().inspect(Path(request.template)),
            manifest_path,
        )
        packets = await self._research_stage(
            outline, workspace, manifest, manifest_path
        )
        shared_copy = self._timed(
            manifest,
            TemplateRunStage.PLAN,
            lambda: self._plan(
                outline, packets, request.max_slides, workspace, manifest
            ),
            manifest_path,
        )

        generated: dict[GenerationRoute, Path] = {}
        html_result: HtmlRouteResult | None = None
        if GenerationRoute.TEMPLATE in request.routes:
            try:
                generated[GenerationRoute.TEMPLATE] = self._template_route(
                    Path(request.template),
                    inspection,
                    shared_copy,
                    packets,
                    workspace,
                    manifest,
                    manifest_path,
                )
            except Exception as error:
                self._fail_route(
                    manifest,
                    GenerationRoute.TEMPLATE,
                    TemplateRunStage.TEMPLATE_ROUTE,
                    error,
                    manifest_path,
                )
        else:
            self._skip_route(
                manifest,
                GenerationRoute.TEMPLATE,
                TemplateRunStage.TEMPLATE_ROUTE,
                manifest_path,
            )

        if GenerationRoute.HTML in request.routes:
            try:
                html_result = await self._html_route(
                    shared_copy,
                    inspection,
                    workspace,
                    manifest,
                    manifest_path,
                )
                generated[GenerationRoute.HTML] = html_result.pptx
            except Exception as error:
                self._fail_route(
                    manifest,
                    GenerationRoute.HTML,
                    TemplateRunStage.HTML_ROUTE,
                    error,
                    manifest_path,
                )
        else:
            self._skip_route(
                manifest,
                GenerationRoute.HTML,
                TemplateRunStage.HTML_ROUTE,
                manifest_path,
            )

        qualities, previews = self._quality_stage(
            outline,
            shared_copy,
            generated,
            workspace,
            manifest,
            manifest_path,
        )
        comparison = self._comparison_stage(
            shared_copy,
            qualities,
            previews,
            html_result,
            workspace,
            manifest,
            manifest_path,
        )
        published = self._publish_stage(
            request,
            generated,
            qualities,
            comparison,
            workspace,
            manifest,
            manifest_path,
        )
        return TemplateGenerationResult(
            output_dir=request.output_dir,
            workspace=workspace,
            manifest=manifest_path,
            plan=workspace / "planning" / "slide-plan.json",
            template_output=published.get(GenerationRoute.TEMPLATE),
            html_output=published.get(GenerationRoute.HTML),
            comparison=(request.output_dir / "comparison.html")
            if comparison is not None
            else None,
        )

    def _create_workspace(self) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.settings.runs_dir / f"{timestamp}-{uuid.uuid4().hex[:8]}"
        path.mkdir(parents=True, exist_ok=False)
        return path.resolve()

    @staticmethod
    def _load_outline(path: Path) -> OutlineDocument:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return OutlineDocument.model_validate(normalize_outline_payload(payload))

    async def _research_stage(
        self,
        outline: OutlineDocument,
        workspace: Path,
        manifest: TemplateRunManifest,
        manifest_path: Path,
    ) -> list[ResearchPacket]:
        stage = TemplateRunStage.RESEARCH
        self._start(manifest, stage, manifest_path)
        with StageTimer() as timer:
            try:
                if self.search is not None and self.reader is not None:
                    packets = await ResearchCoordinator(
                        search=self.search,
                        reader=self.reader,
                        concurrency=self.settings.research_concurrency,
                    ).research(outline, workspace / "research")
                else:
                    packets = await self._remote_research(outline, workspace)
            except Exception as error:
                self._finish_failed(manifest, stage, error, timer, manifest_path)
                raise
        self._finish_completed(
            manifest, stage, workspace / "research", timer, manifest_path
        )
        return packets

    async def _remote_research(
        self, outline: OutlineDocument, workspace: Path
    ) -> list[ResearchPacket]:
        token = self.settings.api_key
        async with (
            RemoteMCPClient(self.settings.search_mcp_url, token) as search_client,
            RemoteMCPClient(self.settings.reader_mcp_url, token) as reader_client,
        ):
            coordinator = ResearchCoordinator(
                search=CodingPlanSearchProvider(search_client),
                reader=CodingPlanPageReader(reader_client),
                concurrency=self.settings.research_concurrency,
            )
            packets = await coordinator.research(outline, workspace / "research")
            write_jsonl(
                workspace / "history" / "research-tools.jsonl",
                [*search_client.history, *reader_client.history],
            )
            return packets

    @staticmethod
    def _plan(
        outline: OutlineDocument,
        packets: list[ResearchPacket],
        max_slides: int,
        workspace: Path,
        manifest: TemplateRunManifest,
    ) -> SharedCopy:
        planning_dir = workspace / "planning"
        plan = SlidePlanner().plan(
            outline,
            packets,
            max_slides=max_slides,
            output=planning_dir / "slide-plan.json",
        )
        evidence = [record for packet in packets for record in packet.evidence]
        shared = prepare_shared_copy(plan, evidence)
        canonical = shared.for_route("template")
        manifest.plan_digest = hashlib.sha256(canonical).hexdigest()
        write_json(planning_dir / "shared-copy.json", shared.model_dump(mode="json"))
        return shared

    def _template_route(
        self,
        source: Path,
        inspection: TemplateInspection,
        shared_copy: SharedCopy,
        packets: list[ResearchPacket],
        workspace: Path,
        manifest: TemplateRunManifest,
        manifest_path: Path,
    ) -> Path:
        stage = TemplateRunStage.TEMPLATE_ROUTE
        route = GenerationRoute.TEMPLATE
        self._start(manifest, stage, manifest_path)
        manifest.routes[route] = TemplateRouteRecord(
            status="running", plan_digest=manifest.plan_digest
        )
        with StageTimer() as timer:
            frame_map = match_plan(shared_copy.plan, list(inspection.layouts))
            write_frame_map(frame_map, workspace / "planning" / "frame-map.json")
            assets = {
                asset.asset_id: asset.local_path
                for packet in packets
                for asset in packet.assets
            }
            result = TemplateRouteGenerator().generate(
                source=source,
                inspection=inspection,
                shared_copy=shared_copy,
                frame_map=frame_map,
                output=workspace / "routes" / "template.pptx",
                assets=assets,
            )
        manifest.routes[route] = manifest.routes[route].model_copy(
            update={"duration_seconds": timer.elapsed, "artifact": result}
        )
        self._finish_completed(manifest, stage, result, timer, manifest_path)
        return result

    async def _html_route(
        self,
        shared_copy: SharedCopy,
        inspection: TemplateInspection,
        workspace: Path,
        manifest: TemplateRunManifest,
        manifest_path: Path,
    ) -> HtmlRouteResult:
        stage = TemplateRunStage.HTML_ROUTE
        route = GenerationRoute.HTML
        self._start(manifest, stage, manifest_path)
        manifest.routes[route] = TemplateRouteRecord(
            status="running", plan_digest=manifest.plan_digest
        )
        generator = self.html_generator or HtmlRouteGenerator(
            self.llm,
            batch_size=self.settings.html_batch_size,
            max_repairs=self.settings.max_repairs,
        )
        with StageTimer() as timer:
            result = await generator.generate(
                shared_copy=shared_copy,
                theme=inspection.theme,
                workspace=workspace / "routes" / "html",
                output=workspace / "routes" / "html.pptx",
                aspect_ratio="16:9"
                if inspection.theme.page_width / inspection.theme.page_height > 1.5
                else "4:3",
            )
        typed = HtmlRouteResult.model_validate(result)
        manifest.routes[route] = manifest.routes[route].model_copy(
            update={
                "duration_seconds": timer.elapsed,
                "artifact": typed.pptx,
                "model_calls": typed.model_calls,
                "repairs": typed.repairs,
                "fallback_slides": typed.fallback_slides,
            }
        )
        self._finish_completed(manifest, stage, typed.pptx, timer, manifest_path)
        return typed

    def _quality_stage(
        self,
        outline: OutlineDocument,
        shared_copy: SharedCopy,
        generated: dict[GenerationRoute, Path],
        workspace: Path,
        manifest: TemplateRunManifest,
        manifest_path: Path,
    ) -> tuple[dict[GenerationRoute, QualityReport], dict[GenerationRoute, list[Path]]]:
        stage = TemplateRunStage.QUALITY
        self._start(manifest, stage, manifest_path)
        qualities: dict[GenerationRoute, QualityReport] = {}
        previews: dict[GenerationRoute, list[Path]] = {}
        with StageTimer() as timer:
            content_report = inspect_content(outline, shared_copy.plan)
            write_json(
                workspace / "quality" / "content.json",
                content_report.model_dump(mode="json"),
            )
            if not content_report.passed:
                error = RuntimeError("content quality gate failed")
                self._finish_failed(manifest, stage, error, timer, manifest_path)
                raise error
            for route, path in tuple(generated.items()):
                route_previews = workspace / "quality" / route.value / "previews"
                report = FinalDeckQualityGate().inspect(
                    path,
                    plan=shared_copy.plan,
                    required_brand_names=("brand-logo", "brand-footer")
                    if route == GenerationRoute.TEMPLATE
                    else (),
                    preview_renderer=self.preview_renderer,
                    previews_dir=route_previews,
                )
                qualities[route] = report
                previews[route] = sorted(route_previews.glob("slide_*.png"))
                write_json(
                    workspace / "quality" / route.value / "report.json",
                    report.model_dump(mode="json"),
                )
                record = manifest.routes[route].model_copy(
                    update={
                        "quality_issues": tuple(
                            issue.code for issue in report.issues
                        )
                    }
                )
                if report.passed:
                    record = record.model_copy(update={"status": "completed"})
                else:
                    record = record.model_copy(
                        update={
                            "status": "failed",
                            "error": "final PPTX quality gate failed",
                        }
                    )
                    generated.pop(route)
                manifest.routes[route] = record
        self._finish_completed(
            manifest, stage, workspace / "quality", timer, manifest_path
        )
        return qualities, previews

    def _comparison_stage(
        self,
        shared_copy: SharedCopy,
        qualities: dict[GenerationRoute, QualityReport],
        previews: dict[GenerationRoute, list[Path]],
        html_result: HtmlRouteResult | None,
        workspace: Path,
        manifest: TemplateRunManifest,
        manifest_path: Path,
    ) -> Path | None:
        stage = TemplateRunStage.COMPARISON
        self._start(manifest, stage, manifest_path)
        with StageTimer() as timer:
            if not all(route in qualities for route in GenerationRoute):
                self._finish_skipped(manifest, stage, timer, manifest_path)
                return None
            template_record = manifest.routes[GenerationRoute.TEMPLATE]
            html_record = manifest.routes[GenerationRoute.HTML]
            result = write_comparison_report(
                plan=shared_copy.plan,
                template_previews=previews[GenerationRoute.TEMPLATE],
                html_previews=previews[GenerationRoute.HTML],
                template_metrics=RouteMetrics(
                    route="template",
                    duration_seconds=template_record.duration_seconds,
                    model_calls=template_record.model_calls,
                    repairs=template_record.repairs,
                    fallback_slides=template_record.fallback_slides,
                ),
                html_metrics=RouteMetrics(
                    route="html",
                    duration_seconds=html_record.duration_seconds,
                    model_calls=html_record.model_calls,
                    repairs=html_record.repairs,
                    fallback_slides=(
                        html_result.fallback_slides if html_result else ()
                    ),
                ),
                template_quality=qualities[GenerationRoute.TEMPLATE],
                html_quality=qualities[GenerationRoute.HTML],
                output=workspace / "comparison" / "comparison.html",
            )
        self._finish_completed(manifest, stage, result, timer, manifest_path)
        return result

    def _publish_stage(
        self,
        request: TemplateGenerationRequest,
        generated: dict[GenerationRoute, Path],
        qualities: dict[GenerationRoute, QualityReport],
        comparison: Path | None,
        workspace: Path,
        manifest: TemplateRunManifest,
        manifest_path: Path,
    ) -> dict[GenerationRoute, Path]:
        stage = TemplateRunStage.PUBLISH
        self._start(manifest, stage, manifest_path)
        published: dict[GenerationRoute, Path] = {}
        request.output_dir.mkdir(parents=True, exist_ok=True)
        with StageTimer() as timer:
            for route, source in generated.items():
                if not qualities[route].passed:
                    continue
                target = request.output_dir / f"{route.value}-route.pptx"
                self._publish_file(source, target)
                published[route] = target
                manifest.routes[route] = manifest.routes[route].model_copy(
                    update={"artifact": target}
                )
            if comparison is not None:
                self._publish_file(comparison, request.output_dir / "comparison.html")
                self._publish_directory(
                    workspace / "comparison" / "comparison_assets",
                    request.output_dir / "comparison_assets",
                )
        if not published:
            error = RuntimeError("No selected route passed the final quality gate")
            self._finish_failed(manifest, stage, error, timer, manifest_path)
            raise error
        self._finish_completed(
            manifest, stage, request.output_dir, timer, manifest_path
        )
        return published

    def _timed(
        self,
        manifest: TemplateRunManifest,
        stage: TemplateRunStage,
        operation: Any,
        manifest_path: Path,
    ) -> Any:
        self._start(manifest, stage, manifest_path)
        with StageTimer() as timer:
            try:
                result = operation()
            except Exception as error:
                self._finish_failed(manifest, stage, error, timer, manifest_path)
                raise
        artifact = result if isinstance(result, Path) else None
        self._finish_completed(manifest, stage, artifact, timer, manifest_path)
        return result

    @staticmethod
    def _start(
        manifest: TemplateRunManifest,
        stage: TemplateRunStage,
        path: Path,
    ) -> None:
        manifest.stage_order.append(stage.value)
        manifest.stages[stage.value] = StageRecord(status="running")
        TemplateDeckPipeline._save(path, manifest)

    @staticmethod
    def _finish_completed(
        manifest: TemplateRunManifest,
        stage: TemplateRunStage,
        artifact: Path | None,
        timer: StageTimer,
        path: Path,
    ) -> None:
        manifest.timings[stage.value] = timer.elapsed
        manifest.stages[stage.value] = StageRecord(
            status="completed", artifact=artifact
        )
        TemplateDeckPipeline._save(path, manifest)

    @staticmethod
    def _finish_failed(
        manifest: TemplateRunManifest,
        stage: TemplateRunStage,
        error: Exception,
        timer: StageTimer,
        path: Path,
    ) -> None:
        manifest.timings[stage.value] = timer.elapsed
        manifest.stages[stage.value] = StageRecord(status="failed", error=str(error))
        TemplateDeckPipeline._save(path, manifest)

    @staticmethod
    def _finish_skipped(
        manifest: TemplateRunManifest,
        stage: TemplateRunStage,
        timer: StageTimer,
        path: Path,
    ) -> None:
        manifest.timings[stage.value] = timer.elapsed
        manifest.stages[stage.value] = StageRecord(status="completed")
        TemplateDeckPipeline._save(path, manifest)

    @staticmethod
    def _fail_route(
        manifest: TemplateRunManifest,
        route: GenerationRoute,
        stage: TemplateRunStage,
        error: Exception,
        path: Path,
    ) -> None:
        current = manifest.routes[route]
        manifest.routes[route] = current.model_copy(
            update={"status": "failed", "error": str(error)}
        )
        manifest.stages[stage.value] = StageRecord(status="failed", error=str(error))
        manifest.timings.setdefault(stage.value, current.duration_seconds)
        TemplateDeckPipeline._save(path, manifest)

    @staticmethod
    def _skip_route(
        manifest: TemplateRunManifest,
        route: GenerationRoute,
        stage: TemplateRunStage,
        path: Path,
    ) -> None:
        manifest.stage_order.append(stage.value)
        manifest.routes[route] = TemplateRouteRecord(status="skipped")
        manifest.stages[stage.value] = StageRecord(status="completed")
        manifest.timings[stage.value] = 0
        TemplateDeckPipeline._save(path, manifest)

    @staticmethod
    def _save(path: Path, manifest: TemplateRunManifest) -> None:
        write_json(path, manifest.model_dump(mode="json"))

    @staticmethod
    def _publish_file(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}-{uuid.uuid4().hex}.tmp"
        try:
            shutil.copy2(source, temporary)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _publish_directory(source: Path, target: Path) -> None:
        temporary = target.parent / f".{target.name}-{uuid.uuid4().hex}.tmp"
        backup = target.parent / f".{target.name}-{uuid.uuid4().hex}.backup"
        shutil.copytree(source, temporary)
        try:
            if target.exists():
                target.replace(backup)
            temporary.replace(target)
            if backup.exists():
                shutil.rmtree(backup)
        except BaseException:
            if backup.exists() and not target.exists():
                backup.replace(target)
            raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
