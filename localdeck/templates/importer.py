"""Persist inspected PowerPoint templates as reusable local packages."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from localdeck.rendering.pptx_preview import PPTXPreviewRenderer
from localdeck.templates.audit import write_template_audit
from localdeck.templates.inspector import TemplateInspector
from localdeck.templates.models import TemplatePackage


class TemplateImporter:
    """Inspect, preview, and persist one editable source template."""

    def __init__(
        self,
        *,
        preview_renderer: PPTXPreviewRenderer,
        inspector: TemplateInspector | None = None,
    ) -> None:
        self.preview_renderer = preview_renderer
        self.inspector = inspector or TemplateInspector()

    def import_template(
        self,
        source: Path,
        template_dir: Path,
        *,
        template_id: str | None = None,
        replace: bool = False,
    ) -> TemplatePackage:
        """Create a complete immutable-on-disk template package."""
        source_path = source.expanduser().resolve()
        inspection = self.inspector.inspect(source_path)
        package_id = _validate_template_id(
            template_id or inspection.manifest.template_id
        )
        inspection = inspection.model_copy(
            update={
                "manifest": inspection.manifest.model_copy(
                    update={"template_id": package_id}
                )
            }
        )
        parent = template_dir.expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        target = parent / package_id
        if target.exists() and not replace:
            raise FileExistsError(
                f"Template '{package_id}' already exists; use --replace to overwrite it"
            )
        with TemporaryDirectory(prefix=f".{package_id}-", dir=parent) as stage_name:
            stage = Path(stage_name)
            self._build_package(source_path, inspection, stage)
            _publish_directory(stage, target, replace=replace)
        return _package_at(target)

    def _build_package(self, source: Path, inspection: object, root: Path) -> None:
        """Build and validate all artifacts inside an unpublished directory."""
        from localdeck.templates.models import TemplateInspection

        typed_inspection = TemplateInspection.model_validate(inspection)
        assets = root / "assets"
        previews_dir = root / "previews"
        assets.mkdir()
        previews_dir.mkdir()

        package_source = root / "source.pptx"
        shutil.copy2(source, package_source)
        manifest = root / "template_manifest.json"
        theme = root / "theme.json"
        layouts = root / "layouts.json"
        components = root / "components.json"
        _write_json(manifest, typed_inspection.manifest.model_dump(mode="json"))
        _write_json(theme, typed_inspection.theme.model_dump(mode="json"))
        _write_json(
            layouts,
            [frame.model_dump(mode="json") for frame in typed_inspection.layouts],
        )
        _write_json(
            components,
            [item.model_dump(mode="json") for item in typed_inspection.components],
        )
        previews = self.preview_renderer.render(package_source, previews_dir)
        write_template_audit(
            typed_inspection, previews, root / "template_audit.html"
        )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_template_id(value: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or Path(normalized).name != normalized
        or "/" in normalized
        or "\\" in normalized
    ):
        raise ValueError("template name must be a single safe directory name")
    return normalized


def _publish_directory(stage: Path, target: Path, *, replace: bool) -> None:
    if not target.exists():
        stage.replace(target)
        return
    if not replace:
        raise FileExistsError(
            f"Template '{target.name}' already exists; use --replace to overwrite it"
        )
    backup = target.parent / f".{target.name}-backup-{uuid.uuid4().hex}"
    target.replace(backup)
    try:
        stage.replace(target)
    except BaseException:
        backup.replace(target)
        raise
    shutil.rmtree(backup)


def _package_at(root: Path) -> TemplatePackage:
    return TemplatePackage(
        root=root,
        manifest=root / "template_manifest.json",
        theme=root / "theme.json",
        layouts=root / "layouts.json",
        components=root / "components.json",
        source=root / "source.pptx",
    )
