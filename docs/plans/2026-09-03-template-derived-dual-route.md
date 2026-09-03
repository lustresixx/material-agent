# Template-Derived Dual-Route Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Docker-free pipeline that accepts an outline JSON and editable PPTX template, expands the outline with authoritative public research, plans at most 30 slides, and produces comparable template-engine and HTML-agent PPTX outputs.

**Architecture:** Add a shared input, template-inspection, research, and slide-planning front half, then branch into a source-slide/component engine and a template-constrained HTML agent. Render and verify both final PPTX files, then publish an HTML report comparing corresponding slides, fidelity, editability, latency, model calls, and repair counts.

**Tech Stack:** Python 3.11, Pydantic 2, Typer, FastMCP/MCP streamable HTTP, OpenAI-compatible GLM Coding Plan, python-pptx plus OOXML helpers for source-deck editing, Playwright, Node.js, the original DeepPresenter v2 HTML2PPTX implementation, PowerPoint automation on Windows for PPTX rendering, pytest, Ruff, and Pyright.

---

## Execution Rules

- Use `@test-driven-development` for every production-code task.
- Execute in an isolated worktree rather than directly on `main`.
- Preserve the existing text-topic generation command throughout the migration.
- Commit after every task using the commit message shown in that task.
- Do not introduce a model-facing shell tool or unrestricted filesystem access.
- Never log `ZAI_API_KEY` or place it in a generated config file.
- Treat downloaded pages, search results, and templates as untrusted input.
- Use the approved design in
  `docs/plans/2026-09-03-template-derived-dual-route-design.md` as the product
  contract.

## External Interfaces Verified During Planning

Coding Plan exposes a remote streamable-HTTP search MCP at:

```text
https://open.bigmodel.cn/api/mcp/web_search_prime/mcp
```

It exposes a remote streamable-HTTP page-reader MCP at:

```text
https://open.bigmodel.cn/api/mcp/web_reader/mcp
```

Both use `Authorization: Bearer <ZAI_API_KEY>`. The search tool is
`webSearchPrime`; the reader tool is `webReader`. Keep these behind a provider
interface so they can be replaced without changing planning code.

## Milestone Order

Do not begin research orchestration until both rendering risks have passed:

1. Import, clone, edit, render, and reopen a representative template page.
2. Port the v2 HTML2PPTX converter and reproduce a gradient slide correctly.

If either spike fails, stop and record the blocker before implementing the
remaining agent workflow.

### Task 1: Add Outline Input Contracts And Normalization

**Files:**
- Create: `localdeck/inputs/__init__.py`
- Create: `localdeck/inputs/models.py`
- Create: `localdeck/inputs/normalizer.py`
- Create: `tests/unit/test_outline_input.py`

**Step 1: Write the failing model and normalization tests**

```python
from localdeck.inputs.models import OutlineDocument
from localdeck.inputs.normalizer import normalize_outline_payload


def test_normalizes_html_space_and_escaped_underscore() -> None:
    payload = {
        "title": "携手同济大学，共建数智化新生态",
        "chapters": [
            {
                "chapter\\_title": " 1. 华为公司介绍&#x20;",
                "sections": [" 1.1 华为经营情况 ", "1.2 华为教育业务介绍"],
            }
        ],
    }

    outline = OutlineDocument.model_validate(normalize_outline_payload(payload))

    assert outline.chapters[0].chapter_title == "1. 华为公司介绍"
    assert outline.chapters[0].sections[0] == "1.1 华为经营情况"


def test_rejects_empty_sections() -> None:
    payload = {
        "title": "标题",
        "chapters": [{"chapter_title": "第一章", "sections": []}],
    }

    with pytest.raises(ValueError, match="sections"):
        OutlineDocument.model_validate(payload)
```

**Step 2: Run the tests and verify failure**

Run:

```powershell
uv run pytest tests/unit/test_outline_input.py -v
```

Expected: collection fails because `localdeck.inputs` does not exist.

**Step 3: Implement the minimal contracts**

```python
class OutlineChapter(BaseModel):
    chapter_title: str = Field(min_length=1, max_length=200)
    sections: list[str] = Field(min_length=1, max_length=30)


class OutlineDocument(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    chapters: list[OutlineChapter] = Field(min_length=1, max_length=20)
```

`normalize_outline_payload()` must recursively decode HTML entities, convert a
literal `chapter\\_title` key to `chapter_title`, strip strings, and reject
non-object input without mutating the caller's object.

**Step 4: Run focused and static checks**

```powershell
uv run pytest tests/unit/test_outline_input.py -v
uv run ruff check localdeck/inputs tests/unit/test_outline_input.py
uv run pyright localdeck/inputs
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/inputs tests/unit/test_outline_input.py
git commit -m "feat: validate structured presentation outlines"
```

### Task 2: Add Template And Dual-Route Request Models

**Files:**
- Create: `localdeck/templates/__init__.py`
- Create: `localdeck/templates/models.py`
- Modify: `localdeck/models.py`
- Test: `tests/unit/test_models.py`
- Create: `tests/unit/test_template_models.py`

**Step 1: Write failing request-model tests**

Add tests proving that:

- `TemplateGenerationRequest` resolves the outline, template, and output paths.
- `max_slides` accepts 1 through 30 and rejects 31.
- Routes contain one or both of `template` and `html` without duplicates.
- A template package cannot reference files outside its root.

Use this contract:

```python
class GenerationRoute(StrEnum):
    TEMPLATE = "template"
    HTML = "html"


class TemplateGenerationRequest(BaseModel):
    outline: Path
    template: str
    routes: tuple[GenerationRoute, ...] = (
        GenerationRoute.TEMPLATE,
        GenerationRoute.HTML,
    )
    max_slides: int = Field(default=30, ge=1, le=30)
    language: Literal["zh", "en"] = "zh"
    output_dir: Path
```

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_models.py tests/unit/test_template_models.py -v
```

Expected: imports or assertions fail for the missing models.

**Step 3: Implement the models**

Add immutable models for `TemplateManifest`, `ThemeProfile`, `LayoutFrame`,
`EditableSlot`, `ComponentSpec`, `CapacityProfile`, and `TemplatePackage`.
Represent source shape IDs as integers and source slide numbers as one-based
integers. Use explicit enums for narrative role, slot type, and edit policy.

**Step 4: Run the focused tests**

```powershell
uv run pytest tests/unit/test_models.py tests/unit/test_template_models.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/models.py localdeck/templates tests/unit/test_models.py tests/unit/test_template_models.py
git commit -m "feat: model template-aware generation requests"
```

### Task 3: Extend Configuration Without Exposing Credentials

**Files:**
- Modify: `localdeck/config.py`
- Modify: `tests/unit/test_config.py`

**Step 1: Write failing configuration tests**

Test defaults and environment overrides for:

```text
LOCALDECK_TEMPLATE_DIR
LOCALDECK_SEARCH_MCP_URL
LOCALDECK_READER_MCP_URL
LOCALDECK_RESEARCH_CONCURRENCY
LOCALDECK_HTML_BATCH_SIZE
LOCALDECK_MAX_REPAIRS
```

Also assert that `repr(settings)` and `settings.model_dump_json()` never contain
the raw API key.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_config.py -v
```

Expected: assertions fail for missing fields.

**Step 3: Add the settings**

Use these defaults:

```python
template_dir: Path = Path("templates").resolve()
search_mcp_url: str = "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"
reader_mcp_url: str = "https://open.bigmodel.cn/api/mcp/web_reader/mcp"
research_concurrency: int = Field(default=4, ge=1, le=12)
html_batch_size: int = Field(default=3, ge=1, le=4)
max_repairs: int = Field(default=2, ge=0, le=5)
```

The remote MCP clients unwrap `SecretStr` only when constructing the
authorization header. Do not persist that header.

**Step 4: Run tests and static checks**

```powershell
uv run pytest tests/unit/test_config.py -v
uv run ruff check localdeck/config.py tests/unit/test_config.py
uv run pyright localdeck/config.py
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/config.py tests/unit/test_config.py
git commit -m "feat: configure template and research services"
```

### Task 4: Add A Remote MCP Client For Coding Plan Research

**Files:**
- Create: `localdeck/mcp/remote.py`
- Create: `tests/unit/test_remote_mcp.py`

**Step 1: Write failing lifecycle and secret tests**

Use a fake `streamablehttp_client` and `ClientSession` to prove:

- Headers contain `Authorization: Bearer ...` only at connection time.
- The client lists and calls tools using the existing `MCPToolResult` contract.
- Errors close the exit stack.
- History records tool name and sanitized arguments, never headers.

**Step 2: Run the test and verify failure**

```powershell
uv run pytest tests/unit/test_remote_mcp.py -v
```

Expected: module import fails.

**Step 3: Implement `RemoteMCPClient`**

Use:

```python
from mcp.client.streamable_http import streamablehttp_client

reader, writer, _ = await stack.enter_async_context(
    streamablehttp_client(
        self.url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=self.timeout,
        sse_read_timeout=self.sse_read_timeout,
    )
)
session = await stack.enter_async_context(ClientSession(reader, writer))
await session.initialize()
```

Normalize results through `MCPToolResult`. Redact keys named `authorization`,
`api_key`, `token`, and `secret` recursively before history serialization.

**Step 4: Run tests and checks**

```powershell
uv run pytest tests/unit/test_remote_mcp.py -v
uv run ruff check localdeck/mcp/remote.py tests/unit/test_remote_mcp.py
uv run pyright localdeck/mcp/remote.py
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/mcp/remote.py tests/unit/test_remote_mcp.py
git commit -m "feat: connect Coding Plan research MCP servers"
```

### Task 5: Prove Source-Slide Cloning And In-Place Editing

**Files:**
- Create: `localdeck/templates/deck_backend.py`
- Create: `localdeck/templates/pptx_backend.py`
- Create: `localdeck/templates/relationships.py`
- Create: `tests/fixtures/build_template_deck.py`
- Create: `tests/integration/test_template_backend.py`
- Modify: `pyproject.toml`

**Step 1: Add the Windows PPTX fixture and failing spike test**

Build a two-slide fixture with:

- One theme and two layouts.
- A logo image inherited or repeated on both slides.
- A title placeholder and body placeholder.
- A cropped picture.
- A grouped decorative shape.
- A footer and slide-number placeholder.

The test must import the fixture, clone slide 2, replace title/body/image by
source shape ID, save a new deck, reopen it, and assert:

- The cloned slide uses the same layout.
- The new text is editable.
- The picture exists and retains its bounding box and crop.
- The logo and footer remain.
- The source theme part remains byte-for-byte identical.

**Step 2: Run the test and verify failure**

```powershell
uv run pytest tests/integration/test_template_backend.py -v
```

Expected: backend import fails.

**Step 3: Implement the narrow editing backend**

Define:

```python
class TemplateDeckBackend(Protocol):
    def inspect(self, source: Path) -> TemplateManifest: ...
    def create_from_map(self, source: Path, frame_map: FrameMap, output: Path) -> Path: ...
    def replace_text(self, slide_index: int, shape_id: int, text: str) -> None: ...
    def replace_image(self, slide_index: int, shape_id: int, image: Path) -> None: ...
    def save(self, output: Path) -> Path: ...
```

Implement only the common editable subset. Reuse the source deck's actual
layouts. Clone shape XML with relationship remapping for images and hyperlinks.
Replace pictures by inserting the new image at the inherited geometry, copying
crop values, moving the new XML element to the old z-order position, and removing
the old picture. Preserve unsupported source objects unchanged.

Add the Windows-only `pywin32` dependency only if the render task requires it;
the editing backend itself must not require PowerPoint automation.

**Step 4: Run the spike gate**

```powershell
uv run pytest tests/integration/test_template_backend.py -v
uv run ruff check localdeck/templates tests/integration/test_template_backend.py
uv run pyright localdeck/templates
```

Expected: all pass. If theme, media, grouping, or layout preservation fails,
stop and record the blocker rather than continuing.

**Step 5: Commit**

```powershell
git add pyproject.toml localdeck/templates tests/fixtures/build_template_deck.py tests/integration/test_template_backend.py
git commit -m "feat: clone and edit source presentation frames"
```

### Task 6: Port And Validate The Production HTML2PPTX Converter

**Files:**
- Replace: `localdeck/vendor/html2pptx/render_pptx.js`
- Create: `localdeck/vendor/html2pptx/html2pptx.js`
- Modify: `localdeck/vendor/html2pptx/package.json`
- Modify: `localdeck/rendering/exporter.py`
- Modify: `tests/integration/test_exporter.py`
- Create: `tests/fixtures/slides/gradient.html`
- Create: `tests/fixtures/slides/per_side_border.html`
- Create: `tests/fixtures/slides/rich_text.html`

**Step 1: Write the failing fidelity tests**

Add integration cases for:

- A dark gradient background with white title text.
- Semi-transparent panels.
- A colored left border distinct from the other borders.
- `<strong>` text inside a source bar.
- An SVG element.
- A rounded cropped image.

Each case exports PPTX, renders the final PPTX, and checks the rendered pixels or
object inventory rather than trusting the HTML screenshot.

**Step 2: Run and prove the current regression**

```powershell
uv run pytest tests/integration/test_exporter.py -v
```

Expected: the gradient and rich-style cases fail with the current 114-line
renderer.

**Step 3: Port the v2 implementation**

Adapt the MIT-licensed implementation from:

```text
../PPTAgent/deeppresenter/html2pptx/html2pptx.js
../PPTAgent/deeppresenter/html2pptx/html2pptx_cli.js
../PPTAgent/deeppresenter/html2pptx/package.json
```

Keep LocalDeck's fixed Python invocation, atomic temporary output, and verifier.
Remove assumptions about Docker, POSIX paths, package-global caches, and
DeepPresenter configuration. Preserve validation and soft-parser behavior, but
default to strict conversion for publication.

Add the original license notice and source commit information to
`localdeck/vendor/html2pptx/NOTICE.md`.

**Step 4: Run the fidelity gate**

```powershell
npm install --prefix localdeck/vendor/html2pptx
uv run pytest tests/integration/test_exporter.py -v
uv run ruff check localdeck/rendering tests/integration/test_exporter.py
uv run pyright localdeck/rendering
```

Expected: all cases pass and the final gradient slide has a dark background with
visible white text. If not, stop before research work.

**Step 5: Commit**

```powershell
git add localdeck/vendor/html2pptx localdeck/rendering/exporter.py tests/fixtures/slides tests/integration/test_exporter.py
git commit -m "feat: port high-fidelity html to pptx conversion"
```

### Task 7: Render Final PPTX Files On Windows

**Files:**
- Create: `localdeck/rendering/pptx_preview.py`
- Create: `tests/unit/test_pptx_preview.py`
- Create: `tests/integration/test_pptx_preview_windows.py`
- Modify: `pyproject.toml`

**Step 1: Write failing renderer-selection tests**

Define a `PPTXPreviewRenderer` protocol and assert:

- Windows selects PowerPoint automation when PowerPoint is available.
- A missing renderer raises a clear `PPTXPreviewUnavailable` error.
- Rendering returns consecutive `slide_01.png` paths.
- Temporary PowerPoint processes and files are closed on failure.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_pptx_preview.py -v
```

Expected: module import fails.

**Step 3: Implement the Windows renderer**

Use a platform-specific optional dependency:

```toml
"pywin32>=308; sys_platform == 'win32'"
```

Open PowerPoint with `Visible = False`, call `Export` to PNG, close the
presentation in `finally`, and quit only the automation instance created by
LocalDeck. Do not close user-owned PowerPoint windows.

Keep a backend protocol so LibreOffice or another headless renderer can be added
later without changing QA code.

**Step 4: Run unit and Windows integration tests**

```powershell
uv run pytest tests/unit/test_pptx_preview.py -v
uv run pytest tests/integration/test_pptx_preview_windows.py -v
```

Expected: unit tests always pass; the integration test passes when PowerPoint is
installed and otherwise skips with an explicit reason.

**Step 5: Commit**

```powershell
git add pyproject.toml localdeck/rendering/pptx_preview.py tests/unit/test_pptx_preview.py tests/integration/test_pptx_preview_windows.py
git commit -m "feat: render final pptx slides on Windows"
```

### Task 8: Inspect Templates And Produce A Reusable Package

**Files:**
- Create: `localdeck/templates/inspector.py`
- Create: `localdeck/templates/theme.py`
- Create: `localdeck/templates/classifier.py`
- Create: `localdeck/templates/importer.py`
- Create: `localdeck/templates/audit.py`
- Create: `tests/unit/test_template_inspector.py`
- Create: `tests/integration/test_template_import.py`

**Step 1: Write failing inspection tests**

Assert that importing the fixture produces:

```text
source.pptx
template_manifest.json
theme.json
layouts.json
components.json
assets/
previews/
template_audit.html
```

Assert that every source slide has an inventory entry, stable source shape IDs,
a role, family, capacity, editable slots, and preserve-only objects.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_template_inspector.py tests/integration/test_template_import.py -v
```

Expected: missing importer and inspector failures.

**Step 3: Implement deterministic extraction first**

Extract page size, master/layout identity, placeholder metadata, text geometry,
font runs, paragraph properties, fill/line values, picture geometry and crop,
group membership, z-order, and recurring objects. Classify a recurring element
as brand furniture only when its source identity or normalized geometry/style is
present across the required threshold of slides.

Use heuristics plus one structured GLM call to label roles and families from the
extracted slide text and geometry summary. Persist confidence and allow
`unknown`; do not force a misleading classification.

**Step 4: Run tests and inspect the audit**

```powershell
uv run pytest tests/unit/test_template_inspector.py tests/integration/test_template_import.py -v
```

Expected: all pass and the audit opens without remote assets.

**Step 5: Commit**

```powershell
git add localdeck/templates tests/unit/test_template_inspector.py tests/integration/test_template_import.py
git commit -m "feat: import and classify presentation templates"
```

### Task 9: Add Template CLI Commands

**Files:**
- Modify: `localdeck/cli.py`
- Modify: `tests/integration/test_cli.py`

**Step 1: Write failing CLI tests**

Test:

```text
localdeck template import TEMPLATE --name NAME
localdeck template inspect NAME
```

Assert duplicate names require `--replace`, encrypted or unreadable templates
fail without partial publication, and `inspect` prints the absolute audit path.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/integration/test_cli.py -v
```

Expected: commands are unknown.

**Step 3: Register a `template` Typer sub-application**

```python
template_app = typer.Typer(help="Import and inspect reusable PPTX templates.")
app.add_typer(template_app, name="template")
```

Make import atomic by building in a sibling temporary directory and replacing
the target template directory only after all artifacts validate.

**Step 4: Run the CLI tests**

```powershell
uv run pytest tests/integration/test_cli.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/cli.py tests/integration/test_cli.py
git commit -m "feat: add template import and inspection commands"
```

### Task 10: Implement Research Evidence And Source Policy

**Files:**
- Create: `localdeck/research/__init__.py`
- Create: `localdeck/research/models.py`
- Create: `localdeck/research/source_policy.py`
- Create: `localdeck/research/providers.py`
- Create: `tests/unit/test_source_policy.py`
- Create: `tests/unit/test_research_providers.py`

**Step 1: Write failing policy tests**

Cover:

- Huawei, customer, university, and government official domains rank highest.
- Duplicate canonical URLs collapse into one source.
- A missing publication date remains `None`, not an invented date.
- Search snippets alone cannot support a high-confidence precise claim.
- URLs with non-HTTP schemes are rejected.
- Credentials and query headers never enter evidence files.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_source_policy.py tests/unit/test_research_providers.py -v
```

Expected: imports fail.

**Step 3: Implement provider-neutral contracts**

```python
class SearchProvider(Protocol):
    async def search(self, query: str, *, domain: str | None = None) -> list[SearchHit]: ...


class PageReader(Protocol):
    async def read(self, url: str) -> PageEvidence: ...
```

Implement Coding Plan adapters by calling `webSearchPrime` and `webReader`
through `RemoteMCPClient`. Normalize all remote responses into local Pydantic
models before saving them.

**Step 4: Run tests and checks**

```powershell
uv run pytest tests/unit/test_source_policy.py tests/unit/test_research_providers.py -v
uv run ruff check localdeck/research tests/unit/test_source_policy.py tests/unit/test_research_providers.py
uv run pyright localdeck/research
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/research tests/unit/test_source_policy.py tests/unit/test_research_providers.py
git commit -m "feat: add authoritative public research providers"
```

### Task 11: Build Concurrent Per-Section Research Packets

**Files:**
- Create: `localdeck/research/coordinator.py`
- Create: `localdeck/research/assets.py`
- Create: `localdeck/prompts/research_section.yaml`
- Create: `tests/unit/test_research_coordinator.py`
- Create: `tests/integration/test_research_pipeline.py`

**Step 1: Write failing coordinator tests**

Use fake search and reader providers to assert:

- One task is created per section.
- At most `research_concurrency` tasks execute simultaneously.
- Results are returned in original chapter/section order.
- Each retained claim has at least one evidence ID.
- Failed pages are recorded and do not erase successful evidence.
- Official images include dimensions, source page, direct URL, and local path.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_research_coordinator.py tests/integration/test_research_pipeline.py -v
```

Expected: coordinator imports fail.

**Step 3: Implement the coordinator**

Use `asyncio.Semaphore` and deterministic result ordering. For each section,
perform broad search, official-domain narrowing, full-page reads, claim
extraction, evidence validation, and optional official-image download. Write:

```text
research/chapter_XX/section_YY/research.json
research/chapter_XX/section_YY/sources.json
research/chapter_XX/section_YY/assets.json
research/chapter_XX/section_YY/summary.txt
```

Model-generated claims without retained evidence must be dropped before the
packet is accepted.

**Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_research_coordinator.py tests/integration/test_research_pipeline.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/research localdeck/prompts/research_section.yaml tests/unit/test_research_coordinator.py tests/integration/test_research_pipeline.py
git commit -m "feat: research outline sections concurrently"
```

### Task 12: Plan Slides And Enforce The 30-Slide Budget

**Files:**
- Create: `localdeck/planning/__init__.py`
- Create: `localdeck/planning/models.py`
- Create: `localdeck/planning/pagination.py`
- Create: `localdeck/planning/planner.py`
- Create: `localdeck/prompts/slide_plan.yaml`
- Create: `tests/unit/test_pagination.py`
- Create: `tests/unit/test_slide_planner.py`

**Step 1: Write failing deterministic pagination tests**

Cover the approved sample outline and assert:

- Cover, agenda, chapter dividers, section content, and closing are ordered.
- Every section receives at least one content slide.
- A normal section receives one or two slides.
- A complex section may receive three slides.
- Total slides never exceed `max_slides`.
- Optional chapter dividers are removed before a required section is dropped.
- No section title is renamed or reordered.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_pagination.py tests/unit/test_slide_planner.py -v
```

Expected: imports fail.

**Step 3: Implement planning in two layers**

The deterministic paginator allocates mandatory pages and a remaining budget.
One structured GLM call proposes slide records within that budget. A validator
then checks lineage, sources, capacity, page count, and user-owned ordering.

Use this essential model:

```python
class SlideSpec(BaseModel):
    index: int
    slide_id: str
    role: NarrativeRole
    chapter_index: int | None
    section_index: int | None
    title: str
    core_message: str
    content_blocks: list[ContentBlock]
    evidence_ids: list[str]
    asset_ids: list[str]
    visual_intent: str
    preferred_layouts: list[str]
    source_footer: str | None
```

Write the accepted plan to `slide_plan.json` and continue automatically.

**Step 4: Run tests and checks**

```powershell
uv run pytest tests/unit/test_pagination.py tests/unit/test_slide_planner.py -v
uv run ruff check localdeck/planning tests/unit/test_pagination.py tests/unit/test_slide_planner.py
uv run pyright localdeck/planning
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/planning localdeck/prompts/slide_plan.yaml tests/unit/test_pagination.py tests/unit/test_slide_planner.py
git commit -m "feat: plan evidence-backed slides within a fixed budget"
```

### Task 13: Generate Shared Audience-Facing Copy And Source Footers

**Files:**
- Create: `localdeck/planning/copywriter.py`
- Create: `localdeck/planning/sources.py`
- Create: `localdeck/prompts/slide_copy.yaml`
- Create: `tests/unit/test_slide_copy.py`

**Step 1: Write failing copy tests**

Assert:

- Both routes receive byte-identical structured copy.
- Every visible title and content block is audience-facing.
- Internal notes and planning language are rejected.
- A precise number requires an evidence ID.
- Source footers are short enough for the template source region.
- Complete source metadata remains available for notes and run evidence.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_slide_copy.py -v
```

Expected: module import fails.

**Step 3: Implement one structured copywriting pass**

Generate all copy in one call when it fits the context window; otherwise batch by
chapter. Reject unsupported claims and repair only the rejected records. Do not
allow either visual route to rewrite facts independently.

**Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_slide_copy.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/planning/copywriter.py localdeck/planning/sources.py localdeck/prompts/slide_copy.yaml tests/unit/test_slide_copy.py
git commit -m "feat: prepare shared slide copy and citations"
```

### Task 14: Match Route B Slides To Source Frames

**Files:**
- Create: `localdeck/generation/__init__.py`
- Create: `localdeck/generation/template_engine/__init__.py`
- Create: `localdeck/generation/template_engine/matcher.py`
- Create: `localdeck/generation/template_engine/frame_map.py`
- Create: `tests/unit/test_layout_matcher.py`

**Step 1: Write failing matcher tests**

Assert that matching considers narrative role, text capacity, content-block count,
image count and ratio, data needs, and adjacent-slide silhouette. A frame that
cannot fit must never outrank one that can. Every output slide must receive a
source frame or an explicit `derived-layout` decision.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_layout_matcher.py -v
```

Expected: import fails.

**Step 3: Implement deterministic scoring**

Use a transparent weighted score and return the score breakdown. Do not use a
model for the final match. Persist `template_frame_map.json` with source slide,
narrative role, reuse mode, edit targets, and reasons for omitted source slides.

**Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_layout_matcher.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/generation tests/unit/test_layout_matcher.py
git commit -m "feat: map planned slides to template frames"
```

### Task 15: Generate Route B From Cloned Frames And Components

**Files:**
- Create: `localdeck/generation/template_engine/editor.py`
- Create: `localdeck/generation/template_engine/components.py`
- Create: `localdeck/generation/template_engine/generator.py`
- Create: `tests/integration/test_template_route.py`

**Step 1: Write the failing route test**

Generate a small deck from the fixture and a three-slide plan containing one
cloned cover, one cloned content page, and one derived layout. Assert source
theme preservation, editable text, preserved logo/footer, correct source labels,
no sample content, and no empty structural placeholders.

**Step 2: Run the test and verify failure**

```powershell
uv run pytest tests/integration/test_template_route.py -v
```

Expected: generator import fails.

**Step 3: Implement the generator**

For cloned frames, modify only frame-map edit targets. For derived layouts, reuse
the source layout and approved components; do not invent fonts, colors, radii, or
decorative motifs. Resolve overflow by shortening copy, selecting another frame,
or splitting the plan record. Never silently shrink template text.

**Step 4: Run the route test**

```powershell
uv run pytest tests/integration/test_template_route.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/generation/template_engine tests/integration/test_template_route.py
git commit -m "feat: generate decks from template frames and components"
```

### Task 16: Generate Route C In Batches Under Template Constraints

**Files:**
- Create: `localdeck/generation/html_agent/__init__.py`
- Create: `localdeck/generation/html_agent/compatibility.py`
- Create: `localdeck/generation/html_agent/prompt_builder.py`
- Create: `localdeck/generation/html_agent/generator.py`
- Create: `localdeck/prompts/template_html.yaml`
- Create: `tests/unit/test_html_compatibility.py`
- Create: `tests/integration/test_html_route.py`

**Step 1: Write failing compatibility and batching tests**

Assert:

- Two to four planned slides are sent per batch.
- Generated pages use shared `global.css` and `theme.css`.
- Fonts, palette, source region, and brand rules come from `theme.json`.
- Unsupported remote scripts, fonts, and resources are rejected.
- Only failed slides enter a repair request.
- A page exceeding `max_repairs` falls back to a safe approved HTML layout.
- Final PPTX is rendered and inspected rather than accepted from HTML alone.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_html_compatibility.py tests/integration/test_html_route.py -v
```

Expected: imports fail.

**Step 3: Implement batch generation**

Use a structured model response containing page name and complete HTML. Local
code performs all writes. Feed the model only the current batch, shared theme,
relevant layout summaries, and required assets. Record request count, prompt and
completion tokens, wall time, and repair count.

**Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_html_compatibility.py tests/integration/test_html_route.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/generation/html_agent localdeck/prompts/template_html.yaml tests/unit/test_html_compatibility.py tests/integration/test_html_route.py
git commit -m "feat: generate template-constrained html slides in batches"
```

### Task 17: Add Final-PPTX Quality Gates

**Files:**
- Create: `localdeck/quality/content.py`
- Create: `localdeck/quality/pptx.py`
- Create: `localdeck/quality/deck.py`
- Modify: `localdeck/rendering/verifier.py`
- Create: `tests/unit/test_content_quality.py`
- Create: `tests/integration/test_final_pptx_quality.py`

**Step 1: Write failing quality tests**

Create failing fixtures for:

- White text on a lost white background.
- Clipped final-PPTX text.
- Empty inherited placeholders.
- Missing logo and source footer.
- A missing section.
- A 31-slide deck.
- Repeated use of one layout silhouette across the entire deck.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/unit/test_content_quality.py tests/integration/test_final_pptx_quality.py -v
```

Expected: missing quality modules or undetected failures.

**Step 3: Implement three gates**

- Content gate validates section coverage, evidence, order, and source footer.
- PPTX gate validates OOXML placeholders, editability, required assets, and final
  rendered geometry/contrast.
- Deck gate validates consistent typography, brand furniture, density, and
  layout repetition.

Final PPTX renders are authoritative. HTML screenshots can assist diagnosis but
cannot satisfy the publication gate.

**Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_content_quality.py tests/integration/test_final_pptx_quality.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/quality localdeck/rendering/verifier.py tests/unit/test_content_quality.py tests/integration/test_final_pptx_quality.py
git commit -m "feat: verify final presentation content and visuals"
```

### Task 18: Build The Side-By-Side Comparison Report

**Files:**
- Create: `localdeck/comparison/__init__.py`
- Create: `localdeck/comparison/models.py`
- Create: `localdeck/comparison/report.py`
- Create: `localdeck/comparison/report.css`
- Create: `tests/unit/test_comparison_report.py`

**Step 1: Write the failing report test**

Assert the generated standalone HTML contains corresponding B/C images for every
slide, route labels, QA findings, wall time, per-stage time, model call count,
token usage, repair count, editability notes, and a recommendation. Assert no API
key, authorization header, or full hidden prompt appears.

**Step 2: Run the test and verify failure**

```powershell
uv run pytest tests/unit/test_comparison_report.py -v
```

Expected: import fails.

**Step 3: Implement a local standalone report**

Embed only local relative image paths and static CSS. Pair slides by stable
`slide_id`, not by filename alone. Clearly mark a route that failed without
discarding the successful route's evidence.

**Step 4: Run tests**

```powershell
uv run pytest tests/unit/test_comparison_report.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/comparison tests/unit/test_comparison_report.py
git commit -m "feat: compare template and html generation routes"
```

### Task 19: Orchestrate The Dual-Route Pipeline

**Files:**
- Modify: `localdeck/models.py`
- Modify: `localdeck/pipeline.py`
- Modify: `localdeck/logging.py`
- Create: `tests/integration/test_dual_route_pipeline.py`

**Step 1: Write the failing end-to-end orchestration test**

Use fake LLM and research providers plus the template fixture. Assert the stage
order, manifest transitions, shared plan identity, independent route failure,
per-stage telemetry, atomic publication, and retained artifacts.

**Step 2: Run the test and verify failure**

```powershell
uv run pytest tests/integration/test_dual_route_pipeline.py -v
```

Expected: the existing pipeline cannot accept a template request.

**Step 3: Add a separate template-aware pipeline class**

Keep `LocalDeckPipeline` working for the old topic command. Add
`TemplateDeckPipeline` with explicit stage methods rather than one deeply nested
method. Use one run workspace and write timings after every stage. Publish each
route only after its own final gate; publish `comparison.html` after both route
records reach a terminal state.

**Step 4: Run old and new pipeline tests**

```powershell
uv run pytest tests/integration/test_pipeline.py tests/integration/test_dual_route_pipeline.py -v
```

Expected: both pass.

**Step 5: Commit**

```powershell
git add localdeck/models.py localdeck/pipeline.py localdeck/logging.py tests/integration/test_dual_route_pipeline.py
git commit -m "feat: orchestrate dual-route template generation"
```

### Task 20: Extend `generate` Without Breaking Topic Mode

**Files:**
- Modify: `localdeck/cli.py`
- Modify: `tests/integration/test_cli.py`

**Step 1: Write failing CLI compatibility tests**

Cover both forms:

```powershell
uv run localdeck generate "topic" --slides 2 --output demo.pptx
```

```powershell
uv run localdeck generate `
  --outline outline.json `
  --template huawei-education `
  --routes template,html `
  --max-slides 30 `
  --output-dir output
```

Assert exactly one input mode is selected and template mode requires an imported
template.

**Step 2: Run the tests and verify failure**

```powershell
uv run pytest tests/integration/test_cli.py -v
```

Expected: new options are unknown.

**Step 3: Implement mode dispatch**

Make the positional topic optional. If `--outline` is present, validate the
template options and call `TemplateDeckPipeline`; otherwise preserve the current
topic behavior and defaults. Print absolute output and workspace paths.

**Step 4: Run CLI and regression tests**

```powershell
uv run pytest tests/integration/test_cli.py tests/integration/test_pipeline.py tests/integration/test_dual_route_pipeline.py -v
```

Expected: all pass.

**Step 5: Commit**

```powershell
git add localdeck/cli.py tests/integration/test_cli.py
git commit -m "feat: expose template-aware generation in the cli"
```

### Task 21: Run The Approved Huawei/Tongji Acceptance Scenario

**Files:**
- Create: `examples/huawei-tongji-outline.json`
- Create: `tests/acceptance/test_huawei_tongji.py`
- Modify: `README.md`

**Step 1: Add the approved outline fixture**

Use the exact four chapters and seven sections approved in the design. Do not
include private facts or credentials.

**Step 2: Add the acceptance test**

The test requires a user-supplied editable template path through
`LOCALDECK_ACCEPTANCE_TEMPLATE`. It must skip clearly when absent. When present,
assert all 17 design acceptance criteria, including at most 30 slides, section
coverage, source footers, two editable outputs, brand preservation, final-render
quality, and comparison metrics.

**Step 3: Run the offline suite first**

```powershell
uv run pytest -m "not live" -v
uv run ruff check .
uv run pyright localdeck
```

Expected: all pass.

**Step 4: Run the live acceptance test explicitly**

```powershell
$env:LOCALDECK_RUN_LIVE_TESTS="1"
$env:LOCALDECK_ACCEPTANCE_TEMPLATE="C:\absolute\path\to\template.pptx"
uv run pytest tests/acceptance/test_huawei_tongji.py -v
```

Expected: two PPTX files and `comparison.html` pass all gates. Never commit the
template, generated customer deck, downloaded assets, or credentials.

**Step 5: Document installation, import, generation, artifacts, limits, and costs**

Update the README with:

- PowerPoint rendering prerequisite on Windows.
- Coding Plan search/reader MCP use and quota behavior.
- Template import examples.
- The outline schema.
- Route B/C output names.
- Source and privacy behavior.
- Known unsupported PowerPoint objects.
- How to rerun only a failed route.

**Step 6: Commit**

```powershell
git add README.md examples/huawei-tongji-outline.json tests/acceptance/test_huawei_tongji.py
git commit -m "docs: add template generation acceptance workflow"
```

### Task 22: Final Regression And Release Audit

**Files:**
- Modify only files required to fix failures discovered by this audit.

**Step 1: Verify repository state**

```powershell
git status --short
git log --oneline -25
```

Expected: only intentional changes and one commit per completed task.

**Step 2: Run all offline validation**

```powershell
uv run pytest -m "not live"
uv run ruff check .
uv run pyright localdeck
```

Expected: all pass.

**Step 3: Re-run the current two-slide topic command**

```powershell
uv run localdeck generate "用两页介绍人工智能的发展" --slides 2 --language zh --aspect-ratio 16:9 --output .tmp/regression-topic.pptx
```

Expected: the legacy path remains functional and benefits from the upgraded
HTML2PPTX converter.

**Step 4: Re-run live template acceptance**

Use the user-supplied template and approved Huawei/Tongji outline. Inspect every
final slide from both routes at full size, then inspect the contact sheet for
deck-level consistency. Fix any clipping, overlap, missing brand object, source
error, placeholder, or conversion mismatch before release.

**Step 5: Commit audit fixes**

```powershell
git add <only-the-files-fixed-by-the-audit>
git commit -m "fix: close template generation release gaps"
```

Skip the commit if no files changed.

## Completion Definition

The milestone is complete only when:

- The offline test, Ruff, and Pyright suites pass.
- Both rendering-risk spikes have passed on Windows.
- The approved outline and a real editable template produce both route outputs.
- Both final PPTX files pass final-render and editability gates.
- Every requested section appears in order.
- The deck has no more than 30 slides.
- External claims and images remain traceable and display short bottom sources.
- The comparison report contains corresponding slides and real telemetry.
- The legacy text-topic command still works.
- No secret, private template, downloaded asset, or generated customer deck is
  committed.
