from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from localdeck.templates.models import (
    CapacityProfile,
    ComponentSpec,
    EditableSlot,
    EditPolicy,
    LayoutFrame,
    NarrativeRole,
    SlotType,
    TemplateManifest,
    TemplatePackage,
    ThemeProfile,
)


def test_template_package_accepts_files_inside_root(tmp_path: Path) -> None:
    package = TemplatePackage(
        root=tmp_path,
        manifest=tmp_path / "template_manifest.json",
        theme=tmp_path / "theme.json",
        layouts=tmp_path / "layouts.json",
        components=tmp_path / "components.json",
        source=tmp_path / "source.pptx",
    )

    assert package.root == tmp_path.resolve()
    assert package.source == (tmp_path / "source.pptx").resolve()


def test_template_package_rejects_file_outside_root(tmp_path: Path) -> None:
    package_root = tmp_path / "package"

    with pytest.raises(ValidationError, match="outside template package root"):
        TemplatePackage(
            root=package_root,
            manifest=package_root / "template_manifest.json",
            theme=package_root / "theme.json",
            layouts=package_root / "layouts.json",
            components=tmp_path / "outside.json",
            source=package_root / "source.pptx",
        )


def test_template_inventory_models_are_immutable() -> None:
    capacity = CapacityProfile(max_characters=240, max_items=5, max_images=1)
    slot = EditableSlot(
        source_shape_id=7,
        name="body",
        slot_type=SlotType.BODY,
        edit_policy=EditPolicy.REPLACE_TEXT,
        capacity=capacity,
    )
    layout = LayoutFrame(
        layout_id="content-1",
        source_slide_number=3,
        role=NarrativeRole.CONTENT,
        family="title-body-image",
        capacity=capacity,
        editable_slots=(slot,),
    )
    component = ComponentSpec(
        component_id="body-card",
        source_slide_number=3,
        source_shape_ids=(7,),
        slot_type=SlotType.BODY,
        edit_policy=EditPolicy.REPLACE_TEXT,
        capacity=capacity,
    )
    manifest = TemplateManifest(
        template_id="huawei-blue",
        name="Huawei Blue",
        source_file="source.pptx",
        slide_count=12,
    )
    theme = ThemeProfile(
        page_width=13.333,
        page_height=7.5,
        font_families=("Microsoft YaHei",),
        palette=("#0A59F7", "#FFFFFF"),
        spacing=(0.08, 0.16, 0.24),
    )

    assert layout.source_slide_number == 3
    assert component.source_shape_ids == (7,)
    assert manifest.slide_count == 12
    assert theme.palette[0] == "#0A59F7"

    with pytest.raises(ValidationError, match="frozen"):
        layout.family = "changed"
