"""Self-contained HTML audit generation for imported template packages."""

from __future__ import annotations

from html import escape
from pathlib import Path

from localdeck.templates.models import TemplateInspection


def write_template_audit(
    inspection: TemplateInspection, previews: list[Path], output: Path
) -> Path:
    """Write an offline audit showing every classified source frame."""
    cards = []
    for frame, preview in zip(inspection.layouts, previews, strict=True):
        cards.append(
            "<article>"
            f'<img src="previews/{escape(preview.name)}" alt="Slide '
            f'{frame.source_slide_number}">'
            f"<h2>{escape(frame.layout_id)}</h2>"
            f"<p>Role: {escape(frame.role.value)} · Family: "
            f"{escape(frame.family)} · Confidence: "
            f"{frame.classification_confidence:.2f}</p>"
            f"<p>Editable slots: {len(frame.editable_slots)} · Preserve-only: "
            f"{len(frame.preserve_shape_ids)}</p>"
            "</article>"
        )
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Template audit</title>
<style>body{font:16px system-ui;margin:32px;background:#f3f5f8;color:#17233d}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px}
article{background:white;padding:18px;border-radius:12px;box-shadow:0 4px 18px #0002}
img{width:100%;display:block;border:1px solid #ccd3df}h2{font-size:18px}</style>
</head><body><h1>Template audit</h1><main>""" + "".join(cards) + (
        "</main></body></html>"
    )
    output.write_text(html, encoding="utf-8")
    return output
