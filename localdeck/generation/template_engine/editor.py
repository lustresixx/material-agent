"""Map canonical slide copy into editable source-template slots."""

from __future__ import annotations

from pathlib import Path

from localdeck.planning.models import ContentBlock, SlideSpec
from localdeck.templates.deck_backend import TemplateDeckBackend
from localdeck.templates.models import EditableSlot, EditPolicy, SlotType


class TemplateSlideEditor:
    """Replace all mutable sample content while preserving source styling."""

    def edit(
        self,
        backend: TemplateDeckBackend,
        *,
        slide_index: int,
        slide: SlideSpec,
        slots: tuple[EditableSlot, ...],
        assets: dict[str, Path],
    ) -> None:
        """Populate one cloned frame and remove every unused mutable shape."""
        title_slots = [slot for slot in slots if slot.slot_type == SlotType.TITLE]
        body_slots = [slot for slot in slots if slot.slot_type == SlotType.BODY]
        image_slots = [slot for slot in slots if slot.slot_type == SlotType.IMAGE]
        source_slots = [slot for slot in slots if slot.slot_type == SlotType.SOURCE]

        self._replace_first_text(backend, slide_index, title_slots, slide.title)
        self._replace_first_text(
            backend, slide_index, body_slots, _body_text(slide)
        )
        self._replace_first_text(
            backend, slide_index, source_slots, slide.source_footer or ""
        )

        asset = _first_asset(slide, assets)
        for index, slot in enumerate(image_slots):
            if index == 0 and asset is not None:
                backend.replace_image(slide_index, slot.source_shape_id, asset)
            else:
                backend.delete_shape(slide_index, slot.source_shape_id)

        handled = {
            *(slot.source_shape_id for slot in title_slots),
            *(slot.source_shape_id for slot in body_slots),
            *(slot.source_shape_id for slot in image_slots),
            *(slot.source_shape_id for slot in source_slots),
        }
        for slot in slots:
            if (
                slot.source_shape_id not in handled
                and slot.edit_policy != EditPolicy.PRESERVE_ONLY
            ):
                backend.delete_shape(slide_index, slot.source_shape_id)

    @staticmethod
    def _replace_first_text(
        backend: TemplateDeckBackend,
        slide_index: int,
        slots: list[EditableSlot],
        text: str,
    ) -> None:
        for index, slot in enumerate(slots):
            if index == 0 and text.strip():
                backend.replace_text(slide_index, slot.source_shape_id, text)
            else:
                backend.delete_shape(slide_index, slot.source_shape_id)


def _body_text(slide: SlideSpec) -> str:
    parts = [slide.core_message]
    for block in slide.content_blocks:
        parts.extend(_block_lines(block))
    return "\n".join(part for part in parts if part.strip())


def _block_lines(block: ContentBlock) -> list[str]:
    lines: list[str] = []
    if block.heading:
        lines.append(block.heading)
    if block.text:
        lines.append(block.text)
    lines.extend(f"• {item}" for item in block.items)
    return lines


def _first_asset(slide: SlideSpec, assets: dict[str, Path]) -> Path | None:
    return next(
        (assets[asset_id] for asset_id in slide.asset_ids if asset_id in assets),
        None,
    )
