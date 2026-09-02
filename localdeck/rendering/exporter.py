"""Extract rendered DOM geometry and publish an editable PPTX atomically."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Literal

from playwright.async_api import async_playwright

from localdeck.rendering.verifier import PPTXVerifier

LAYOUTS: dict[str, tuple[float, float, int, int]] = {
    "16:9": (13.333, 7.5, 1280, 720),
    "4:3": (10.0, 7.5, 960, 720),
}


class ExportError(RuntimeError):
    """Raised when HTML extraction or the trusted Node renderer fails."""


class HTMLExporter:
    """Convert a constrained HTML/CSS subset into editable PptxGenJS elements.

    Playwright owns browser interpretation of CSS. The Node renderer receives only a
    typed JSON-like document containing final geometry and styles, so it never loads
    untrusted remote pages or executes model-provided shell commands.
    """

    async def export(
        self,
        slides_dir: Path,
        output: Path,
        aspect_ratio: Literal["16:9", "4:3"] = "16:9",
    ) -> Path:
        """Export sorted slide HTML files and atomically replace ``output`` on success."""

        html_files = sorted(slides_dir.glob("slide_*.html"))
        if not html_files:
            raise ExportError(f"No slide HTML files found in {slides_dir}")
        for html_file in html_files:
            source = html_file.read_text(encoding="utf-8")
            if "<!doctype html" not in source.lower() or "<body" not in source.lower():
                raise ExportError(f"Slide is not a complete HTML document: {html_file}")

        node = shutil.which("node")
        if node is None:
            raise ExportError("Node.js is required but was not found on PATH")

        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        spec_file = output.parent / f".{output.stem}-{token}.json"
        temporary_output = output.parent / f".{output.stem}-{token}.pptx"
        try:
            specification = await self._extract(html_files, aspect_ratio)
            spec_file.write_text(
                json.dumps(specification, ensure_ascii=False), encoding="utf-8"
            )
            renderer = Path(__file__).parents[1] / "vendor" / "html2pptx" / "render_pptx.js"
            process = await asyncio.create_subprocess_exec(
                node,
                str(renderer),
                "--input",
                str(spec_file),
                "--output",
                str(temporary_output),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=120
                )
            except TimeoutError as error:
                process.kill()
                await process.wait()
                raise ExportError("Node PPTX renderer timed out") from error
            if process.returncode != 0:
                detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
                raise ExportError(f"Node PPTX renderer failed: {detail}")

            PPTXVerifier().verify(temporary_output, expected_slides=len(html_files))
            temporary_output.replace(output)
            return output
        finally:
            spec_file.unlink(missing_ok=True)
            temporary_output.unlink(missing_ok=True)

    async def _extract(
        self,
        html_files: list[Path],
        aspect_ratio: Literal["16:9", "4:3"],
    ) -> dict:
        """Use Chromium to convert CSS layout into a deterministic element model."""

        slide_width, slide_height, viewport_width, viewport_height = LAYOUTS[
            aspect_ratio
        ]
        slides: list[dict] = []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    viewport={"width": viewport_width, "height": viewport_height}
                )
                page = await context.new_page()
                for html_file in html_files:
                    await page.goto(html_file.resolve().as_uri(), wait_until="load")
                    slides.append(await page.evaluate(_DOM_EXTRACTOR))
                await context.close()
            finally:
                await browser.close()
        return {
            "layout": {"width": slide_width, "height": slide_height},
            "viewport": {"width": viewport_width, "height": viewport_height},
            "slides": slides,
        }


_DOM_EXTRACTOR = """
() => {
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
           Number(style.opacity) > 0 && rect.width > 0 && rect.height > 0;
  };
  const geometry = (element) => {
    const rect = element.getBoundingClientRect();
    return { x: rect.x, y: rect.y, w: rect.width, h: rect.height };
  };
  const styleValue = (element) => {
    const style = getComputedStyle(element);
    return {
      color: style.color,
      background: style.backgroundColor,
      borderColor: style.borderColor,
      borderWidth: parseFloat(style.borderWidth) || 0,
      borderRadius: parseFloat(style.borderRadius) || 0,
      fontFamily: style.fontFamily,
      fontSize: parseFloat(style.fontSize) || 18,
      fontWeight: style.fontWeight,
      fontStyle: style.fontStyle,
      textAlign: style.textAlign,
      lineHeight: parseFloat(style.lineHeight) || 1.2 * (parseFloat(style.fontSize) || 18),
      opacity: Number(style.opacity),
    };
  };

  const shapes = [...document.querySelectorAll('div,section,header,footer,aside')]
    .filter(visible)
    .filter((element) => {
      const style = getComputedStyle(element);
      return style.backgroundColor !== 'rgba(0, 0, 0, 0)' ||
             parseFloat(style.borderWidth) > 0;
    })
    .map((element) => ({ ...geometry(element), style: styleValue(element) }));

  const textSelector = 'h1,h2,h3,h4,h5,h6,p,li,span';
  const texts = [...document.querySelectorAll(textSelector)]
    .filter(visible)
    .filter((element) => !element.querySelector(textSelector))
    .map((element) => ({
      ...geometry(element),
      text: element.innerText.trim(),
      kind: element.tagName.toLowerCase(),
      style: styleValue(element),
    }))
    .filter((element) => element.text.length > 0);

  const images = [...document.images]
    .filter(visible)
    .filter((image) => image.complete && image.naturalWidth > 0)
    .map((image) => ({ ...geometry(image), src: image.src }));

  return {
    background: getComputedStyle(document.body).backgroundColor,
    shapes,
    texts,
    images,
  };
}
"""

