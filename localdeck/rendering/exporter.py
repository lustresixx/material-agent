"""Publish complete HTML slides as editable PPTX files atomically."""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Literal

from localdeck.rendering.verifier import PPTXVerifier


class ExportError(RuntimeError):
    """Raised when HTML validation or the trusted Node converter fails."""


class HTMLExporter:
    """Convert constrained HTML/CSS using the high-fidelity v2 converter."""

    async def export(
        self,
        slides_dir: Path,
        output: Path,
        aspect_ratio: Literal["16:9", "4:3"] = "16:9",
    ) -> Path:
        """Convert ordered HTML pages and atomically publish ``output``."""
        html_files = sorted(slides_dir.glob("slide_*.html"))
        if not html_files:
            raise ExportError(f"No slide HTML files found in {slides_dir}")
        for html_file in html_files:
            source = html_file.read_text(encoding="utf-8")
            if "<!doctype html" not in source.lower() or "<body" not in source.lower():
                raise ExportError(f"Slide is not a complete HTML document: {html_file}")

        node = _resolve_node()
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.parent / f".{output.stem}-{uuid.uuid4().hex}.pptx"
        converter = (
            Path(__file__).parents[1]
            / "vendor"
            / "html2pptx"
            / "html2pptx_cli.js"
        )
        command = [str(node), str(converter)]
        for html_file in html_files:
            command.extend(("--html", str(html_file.resolve())))
        command.extend(
            (
                "--output",
                str(temporary_output),
                "--layout",
                aspect_ratio,
                "--author",
                "LocalDeck",
                "--company",
                "LocalDeck",
            )
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=300
                )
            except TimeoutError as error:
                process.kill()
                await process.wait()
                raise ExportError("Node PPTX converter timed out") from error
            if process.returncode != 0:
                detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
                raise ExportError(f"Node PPTX converter failed: {detail}")

            PPTXVerifier().verify(temporary_output, expected_slides=len(html_files))
            temporary_output.replace(output)
            return output
        finally:
            temporary_output.unlink(missing_ok=True)


def _resolve_node() -> Path:
    """Prefer an explicitly provisioned runtime, then the user's PATH."""
    for environment_name in ("LOCALDECK_NODE_PATH", "RUNTIME_NODE"):
        configured = os.getenv(environment_name, "").strip()
        if configured:
            node = Path(configured).expanduser().resolve()
            if node.is_file():
                return node
            raise ExportError(f"Configured Node.js executable not found: {node}")
    discovered = shutil.which("node")
    if discovered is None:
        raise ExportError("Node.js is required but was not found on PATH")
    return Path(discovered).resolve()
