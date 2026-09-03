from __future__ import annotations

from pathlib import Path

from localdeck.templates.importer import TemplateImporter
from tests.fixtures.build_template_deck import build_template_deck


class FakePreviewRenderer:
    def render(self, source: Path, output_dir: Path) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for index in (1, 2):
            path = output_dir / f"slide_{index:02d}.png"
            path.write_bytes(b"preview")
            paths.append(path)
        return paths


def test_importer_writes_complete_self_contained_template_package(
    tmp_path: Path,
) -> None:
    source, _ = build_template_deck(tmp_path / "fixture")
    importer = TemplateImporter(preview_renderer=FakePreviewRenderer())

    package = importer.import_template(source, tmp_path / "templates")

    expected = {
        "source.pptx",
        "template_manifest.json",
        "theme.json",
        "layouts.json",
        "components.json",
        "assets",
        "previews",
        "template_audit.html",
    }
    assert expected.issubset({path.name for path in package.root.iterdir()})
    assert len(list((package.root / "previews").glob("slide_*.png"))) == 2
    audit = (package.root / "template_audit.html").read_text(encoding="utf-8")
    assert "http://" not in audit
    assert "https://" not in audit
    assert "previews/slide_01.png" in audit
