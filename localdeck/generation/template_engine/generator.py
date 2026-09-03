"""Editable source-template presentation generation route."""

from __future__ import annotations

from pathlib import Path

from localdeck.generation.template_engine.components import (
    finalize_template_furniture,
    select_derived_frame,
)
from localdeck.generation.template_engine.editor import TemplateSlideEditor
from localdeck.generation.template_engine.matcher import (
    FrameMatchDecision,
    FrameMatchMap,
    ReuseMode,
)
from localdeck.planning.copywriter import SharedCopy
from localdeck.planning.models import SlideSpec
from localdeck.templates.deck_backend import FrameMap
from localdeck.templates.models import LayoutFrame, TemplateInspection
from localdeck.templates.pptx_backend import PptxTemplateBackend


class TemplateRouteGenerator:
    """Generate an editable deck exclusively from imported template material."""

    def __init__(self, backend: PptxTemplateBackend | None = None) -> None:
        self._backend = backend or PptxTemplateBackend()
        self._editor = TemplateSlideEditor()

    def generate(
        self,
        *,
        source: Path,
        inspection: TemplateInspection,
        shared_copy: SharedCopy,
        frame_map: FrameMatchMap,
        output: Path,
        assets: dict[str, Path] | None = None,
    ) -> Path:
        """Clone, populate, and finalize all planned slides in order."""
        plan = shared_copy.plan
        if len(frame_map.decisions) != len(plan.slides):
            raise ValueError("frame map and slide plan lengths differ")
        selected_frames = tuple(
            self._resolve_frame(slide, decision, inspection.layouts)
            for slide, decision in zip(
                plan.slides, frame_map.decisions, strict=True
            )
        )
        for slide, decision in zip(
            plan.slides, frame_map.decisions, strict=True
        ):
            if slide.slide_id != decision.slide_id:
                raise ValueError("frame map order does not match slide plan")

        destination = self._backend.create_from_map(
            source,
            FrameMap(
                source_slide_numbers=tuple(
                    frame.source_slide_number for frame in selected_frames
                )
            ),
            output,
        )
        asset_map = assets or {}
        for index, (slide, frame) in enumerate(
            zip(plan.slides, selected_frames, strict=True)
        ):
            self._editor.edit(
                self._backend,
                slide_index=index,
                slide=slide,
                slots=frame.editable_slots,
                assets=asset_map,
            )
        destination = self._backend.save(destination)
        finalize_template_furniture(
            destination, tuple(slide.source_footer for slide in plan.slides)
        )
        return destination

    @staticmethod
    def _resolve_frame(
        slide: SlideSpec,
        decision: FrameMatchDecision,
        frames: tuple[LayoutFrame, ...],
    ) -> LayoutFrame:
        if decision.reuse_mode == ReuseMode.DERIVED_LAYOUT:
            return select_derived_frame(slide, frames)
        selected = next(
            (
                frame
                for frame in frames
                if frame.source_slide_number == decision.source_slide_number
            ),
            None,
        )
        if selected is None:
            raise ValueError(
                f"source frame not found: {decision.source_slide_number}"
            )
        return selected
