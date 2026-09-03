from __future__ import annotations

from pathlib import Path

from localdeck.templates.inspector import TemplateInspector
from localdeck.templates.models import EditPolicy, NarrativeRole, SlotType
from tests.fixtures.build_template_deck import build_template_deck


def test_inspector_inventories_every_slide_and_stable_shape(tmp_path: Path) -> None:
    source, _ = build_template_deck(tmp_path)

    inspection = TemplateInspector().inspect(source)

    assert inspection.manifest.slide_count == 2
    assert len(inspection.layouts) == 2
    assert inspection.layouts[0].role == NarrativeRole.COVER
    assert all(frame.family for frame in inspection.layouts)
    assert all(frame.source_shape_ids for frame in inspection.layouts)
    assert all(frame.capacity.max_characters >= 0 for frame in inspection.layouts)
    assert any(frame.editable_slots for frame in inspection.layouts)

    content = inspection.layouts[1]
    assert any(slot.slot_type == SlotType.TITLE for slot in content.editable_slots)
    assert any(slot.slot_type == SlotType.BODY for slot in content.editable_slots)
    assert any(slot.slot_type == SlotType.IMAGE for slot in content.editable_slots)
    assert content.preserve_shape_ids
    assert all(
        slot.edit_policy != EditPolicy.PRESERVE_ONLY
        for slot in content.editable_slots
    )


def test_inspector_extracts_template_theme(tmp_path: Path) -> None:
    source, _ = build_template_deck(tmp_path)

    theme = TemplateInspector().inspect(source).theme

    assert theme.page_width == 13.333
    assert theme.page_height == 7.5
    assert theme.font_families
    assert theme.palette
    assert theme.spacing
