"""Build compact batch prompts from shared copy and template tokens."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from localdeck.planning.models import SlideSpec
from localdeck.templates.models import ThemeProfile


def build_messages(
    slides: tuple[SlideSpec, ...],
    theme: ThemeProfile,
    *,
    aspect_ratio: str,
    repair_issues: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, str]]:
    """Return an OpenAI-compatible prompt for one bounded slide batch."""
    prompt_file = Path(__file__).parents[2] / "prompts" / "template_html.yaml"
    system = str(
        yaml.safe_load(prompt_file.read_text(encoding="utf-8"))["system"]
    ).strip()
    payload = {
        "aspect_ratio": aspect_ratio,
        "theme": theme.model_dump(mode="json"),
        "slides": [slide.model_dump(mode="json") for slide in slides],
        "repair_issues": repair_issues or {},
        "response_schema": {
            "slides": [{"slide_id": "string", "html": "complete HTML string"}]
        },
    }
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        },
    ]
