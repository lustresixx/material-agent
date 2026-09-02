"""Small JSON persistence helpers for reproducible run diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def write_json(path: Path, value: Any) -> None:
    """Atomically write JSON-serializable data with readable UTF-8 formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, records: Iterable[Any]) -> None:
    """Write one JSON object per line without leaking process environment values."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, default=str) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

