"""Browser-backed slide inspection without Docker, PDF, or LibreOffice."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Literal

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from localdeck.models import InspectionIssue, InspectionReport
from localdeck.workspace import WorkspaceGuard

SLIDE_SIZES: dict[str, tuple[int, int]] = {
    "16:9": (1280, 720),
    "4:3": (960, 720),
}


class SlideInspector:
    """Load local slide HTML, measure DOM geometry, and persist evidence."""

    def __init__(self, workspace: Path) -> None:
        self.guard = WorkspaceGuard(workspace)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "SlideInspector":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None

    async def inspect(
        self,
        html_file: str | Path,
        aspect_ratio: Literal["16:9", "4:3"] = "16:9",
    ) -> InspectionReport:
        """Inspect one page and write a JSON receipt plus a PNG screenshot."""

        if self._browser is None:
            raise RuntimeError("SlideInspector must be used as an async context manager")
        html_path = self.guard.resolve(html_file)
        if html_path.suffix.lower() != ".html" or not html_path.is_file():
            raise ValueError(f"Slide HTML does not exist: {html_path}")

        width, height = SLIDE_SIZES[aspect_ratio]
        self._context = await self._browser.new_context(
            viewport={"width": width, "height": height}, device_scale_factor=1
        )
        page = await self._context.new_page()
        runtime_errors: list[InspectionIssue] = []
        page.on(
            "pageerror",
            lambda error: runtime_errors.append(
                InspectionIssue(code="page_error", message=str(error))
            ),
        )
        page.on(
            "console",
            lambda message: (
                runtime_errors.append(
                    InspectionIssue(code="console_error", message=message.text)
                )
                if message.type == "error"
                else None
            ),
        )

        await page.goto(html_path.as_uri(), wait_until="load")
        await page.wait_for_timeout(50)
        measurements = await page.evaluate(
            """
            ([expectedWidth, expectedHeight]) => {
              const bodyRect = document.body.getBoundingClientRect();
              const selector = (element) => {
                if (element.id) return `#${element.id}`;
                const classes = [...element.classList].slice(0, 2).join('.');
                return element.tagName.toLowerCase() + (classes ? `.${classes}` : '');
              };
              const bounds = [];
              const textOverflow = [];
              const missingImages = [];

              for (const element of document.body.querySelectorAll('*')) {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                if (style.display === 'none' || style.visibility === 'hidden' ||
                    rect.width === 0 || rect.height === 0) continue;

                if (rect.left < -1 || rect.top < -1 ||
                    rect.right > expectedWidth + 1 || rect.bottom > expectedHeight + 1) {
                  bounds.push(selector(element));
                }

                const ownText = [...element.childNodes]
                  .filter((node) => node.nodeType === Node.TEXT_NODE)
                  .map((node) => node.textContent || '')
                  .join('').trim();
                if (ownText && (element.scrollWidth > element.clientWidth + 1 ||
                                element.scrollHeight > element.clientHeight + 1)) {
                  textOverflow.push(selector(element));
                }

                if (element instanceof HTMLImageElement &&
                    (!element.complete || element.naturalWidth === 0)) {
                  missingImages.push(selector(element));
                }
              }

              return {
                bodyWidth: Math.round(bodyRect.width),
                bodyHeight: Math.round(bodyRect.height),
                pageOverflow: document.documentElement.scrollWidth > expectedWidth + 1 ||
                              document.documentElement.scrollHeight > expectedHeight + 1,
                bounds,
                textOverflow,
                missingImages,
              };
            }
            """,
            [width, height],
        )

        issues = runtime_errors + self._measurement_issues(measurements, width, height)
        inspections_dir = self.guard.resolve("inspections")
        inspections_dir.mkdir(parents=True, exist_ok=True)
        screenshot = inspections_dir / f"{html_path.stem}.png"
        await page.screenshot(path=str(screenshot), full_page=False)

        report = InspectionReport(
            html_file=html_path,
            passed=not any(issue.severity == "error" for issue in issues),
            width=measurements["bodyWidth"],
            height=measurements["bodyHeight"],
            issues=issues,
            screenshot=screenshot,
        )
        report_path = inspections_dir / f"{html_path.stem}.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        await page.close()
        await self._context.close()
        self._context = None
        return report

    @staticmethod
    def _measurement_issues(
        measurements: dict, expected_width: int, expected_height: int
    ) -> list[InspectionIssue]:
        """Convert raw DOM measurements into stable, model-readable issue codes."""

        issues: list[InspectionIssue] = []
        actual = (measurements["bodyWidth"], measurements["bodyHeight"])
        if actual != (expected_width, expected_height):
            issues.append(
                InspectionIssue(
                    code="page_size",
                    message=(
                        f"Body is {actual[0]}x{actual[1]}; expected "
                        f"{expected_width}x{expected_height}."
                    ),
                )
            )
        if measurements["pageOverflow"]:
            issues.append(
                InspectionIssue(
                    code="page_overflow", message="Document exceeds the slide viewport."
                )
            )
        for selector in measurements["bounds"]:
            issues.append(
                InspectionIssue(
                    code="element_out_of_bounds",
                    message="Visible element extends beyond the slide.",
                    selector=selector,
                )
            )
        for selector in measurements["textOverflow"]:
            issues.append(
                InspectionIssue(
                    code="text_overflow",
                    message="Text is clipped by its container.",
                    selector=selector,
                )
            )
        for selector in measurements["missingImages"]:
            issues.append(
                InspectionIssue(
                    code="missing_image",
                    message="Image failed to load.",
                    selector=selector,
                )
            )
        return issues

