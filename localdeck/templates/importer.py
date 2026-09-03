"""Persist inspected PowerPoint templates as reusable local packages."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

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

    def import_template(self, source: Path, template_dir: Path) -> TemplatePackage:
        """Create a complete immutable-on-disk template package."""
        source_path = source.expanduser().resolve()
        inspection = self.inspector.inspect(source_path)
        root = template_dir.expanduser().resolve() / inspection.manifest.template_id
        root.mkdir(parents=True, exist_ok=False)
        assets = root / "assets"
        previews_dir = root / "previews"
        assets.mkdir()
        previews_dir.mkdir()

        package_source = root / "source.pptx"
        shutil.copy2(source_path, package_source)
        manifest = root / "template_manifest.json"
        theme = root / "theme.json"
        layouts = root / "layouts.json"
        components = root / "components.json"
        _write_json(manifest, inspection.manifest.model_dump(mode="json"))
        _write_json(theme, inspection.theme.model_dump(mode="json"))
        _write_json(
            layouts,
            [frame.model_dump(mode="json") for frame in inspection.layouts],
        )
        _write_json(
            components,
            [item.model_dump(mode="json") for item in inspection.components],
        )
        previews = self.preview_renderer.render(package_source, previews_dir)
        write_template_audit(inspection, previews, root / "template_audit.html")
        return TemplatePackage(
            root=root,
            manifest=manifest,
            theme=theme,
            layouts=layouts,
            components=components,
            source=package_source,
        )


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
