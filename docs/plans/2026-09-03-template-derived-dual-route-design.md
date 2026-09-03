# Template-Derived Dual-Route Generation Design

## Status

Approved on 2026-09-03.

This design extends LocalDeck from a text-topic MVP into a Docker-free,
template-aware presentation generator. It accepts a structured outline, expands
the outline with public research, decides the final slide count, and produces two
presentations from the same content plan so their rendering approaches can be
compared fairly.

## Goals

- Accept a structured outline JSON instead of a single topic string.
- Import and inspect an editable PowerPoint template.
- Preserve recognizable template identity across newly generated slides.
- Use authoritative public sources to expand every requested section.
- Decide the final page count automatically, with a hard limit of 30 slides.
- Generate the same content through two visual routes:
  - Route B: template components and cloned source slides.
  - Route C: template-constrained free-form HTML/CSS.
- Publish two editable PPTX files and an HTML comparison report.
- Keep the complete workflow local on Windows without Docker.

## Product Context

The target material is a formal Huawei government-and-enterprise cooperation
deck. Typical recipients include government, university, and enterprise
stakeholders. The communication style must be restrained, professional,
technology-oriented, evidence-based, and suitable for executive discussion.

The default narrative should establish capability and credibility, connect those
capabilities to the customer's context, present relevant solutions and public
examples, and conclude with actionable cooperation opportunities. It must not
invent customer outcomes, internal information, unpublished partnerships, or
commitments.

## Inputs

### Outline JSON

The required input follows this shape:

```json
{
  "title": "携手同济大学，共建数智化新生态",
  "chapters": [
    {
      "chapter_title": "1. 华为公司介绍",
      "sections": [
        "1.1 华为经营情况",
        "1.2 华为教育业务介绍"
      ]
    }
  ]
}
```

The system must normalize HTML whitespace entities, escaped underscores, Unicode
punctuation, and surrounding whitespace before validation. Chapter and section
order and meaning are user-owned and must be preserved.

### PowerPoint Template

The required template input is an editable `.pptx` file. Existing narrative
text, example cases, and replaceable images are sample content. Brand furniture
such as logos, footers, confidentiality marks, recurring ornaments, page-number
styles, masters, and layouts must be preserved unless explicitly classified for
replacement.

### Deferred Customer Context

A future optional JSON document may contain the customer name, industry, region,
segment, stakeholder role, and topics of concern. It is outside the first
implementation milestone. Until it is added, the system infers the immediate
context from the deck title and outline.

## Non-Goals For The First Version

- Web UI.
- Customer-context JSON.
- Internal or confidential attachments.
- AI image generation.
- Video, animation, macro, or OLE authoring.
- Automatic SmartArt editing.
- Multi-user or cloud deployment.
- Online page editing.
- Automatic publication to external services.

Unsupported complex source objects should be preserved unchanged whenever
possible and marked `preserve_only` in the template inventory.

## Architecture

```text
Outline JSON + Template PPTX
            |
            v
Input validation and normalization
            |
            v
Template inspection and style extraction
            |
            v
Public research and source collection
            |
            v
Automatic pagination and slide_plan.json
            |
            v
Shared copy, facts, sources, and assets
            |
       +----+----+
       |         |
       v         v
Route B         Route C
Template engine HTML design agent
       |         |
       |         v
       |      High-fidelity HTML2PPTX
       |         |
       +----+----+
            |
            v
Final PPTX rendering and QA
            |
            v
Two PPTX files + comparison.html
```

The two routes must consume the same `slide_plan.json`, copy, evidence, images,
and source labels. This isolates visual generation as the experimental variable.

## Pipeline Stages

The observable pipeline becomes:

```text
INPUT
TEMPLATE_IMPORT
RESEARCH
PLAN
GENERATE_TEMPLATE
GENERATE_HTML
VERIFY_TEMPLATE
VERIFY_HTML
COMPARE
PUBLISH
```

Every stage must update the run manifest before and after execution. Failures must
retain all completed intermediate artifacts and must not overwrite a previously
published output.

## Template Inspection

Template import must inspect every source slide rather than sampling a few
representative pages. It must preserve the source master-layout-slide hierarchy.

The import process performs the following work:

1. Import the complete source PPTX.
2. Inventory all masters, layouts, slides, placeholders, shapes, groups, images,
   charts, tables, notes, and inherited objects.
3. Render every source slide.
4. Extract fonts, colors, page geometry, spacing, backgrounds, borders, radii,
   and recurring brand elements.
5. Classify slide roles and layout families.
6. Identify replaceable text, image, table, chart, and metric slots.
7. Estimate content capacity for each slot and layout.
8. Extract authentic reusable assets and record their provenance.
9. Mark unsupported complex elements as `preserve_only`.
10. Produce a visual template audit.

The stored template package is:

```text
templates/<template-id>/
|-- source.pptx
|-- template_manifest.json
|-- theme.json
|-- layouts.json
|-- components.json
|-- assets/
|-- previews/
`-- template_audit.html
```

### Theme Model

`theme.json` stores page size, font families, typography scales, palette,
spacing, border, radius, background, source-label, and brand-furniture rules.
Extracted values remain authoritative; generated layouts may use only explicit
template values and defined derived variants.

### Layout Model

Every reusable source slide becomes a frame with:

- A stable layout ID.
- Its source slide number and inherited layout.
- A narrative role and layout family.
- A capacity profile.
- Stable source element IDs.
- Editable slots and their permitted actions.
- Preserve-only objects.

Supported initial roles are `cover`, `agenda`, `chapter`, `content`,
`comparison`, `timeline`, `data`, `case-study`, `solution`, `summary`, and
`closing`.

### Component Model

Reusable components include title regions, source regions, image frames, metric
blocks, text regions, timeline nodes, quote regions, table/chart frames, chapter
markers, and decorative furniture. Each component records geometry, style,
capacity, source slide, source elements, and allowed reuse policy.

Component reuse must not flatten a source deck into a screenshot-derived theme.
Whenever an existing source frame fits, the generator must clone and edit it in
place. Components are used only when no source frame can satisfy the slide plan.

## Research And Source Policy

The first version uses only authoritative public information. Sources are
prioritized as follows:

1. Huawei official sites, reports, and official news.
2. Customer, university, and government official sites.
3. Ministries, local governments, and recognized industry bodies.
4. Research institutions and primary papers.
5. Reliable media only when primary sources are unavailable.

Each section becomes an independent research task and may execute concurrently.
Research proceeds from broad background to specific claims, examples, and visual
assets.

Every retained claim stores its text, source title, URL, publisher, publication
date when available, access time, and confidence. Conflicting information uses
the newest applicable primary source. Unverifiable precision must be removed
rather than guessed.

Public images may be downloaded from authoritative official sources. Every image
must record its source URL, page URL, publisher, access time, dimensions, and
intended slide use. Low-resolution or visually unsuitable assets must be rejected.

Each section writes a research packet containing facts, conclusions, public
examples, visual opportunities, assets, and citations.

## Automatic Pagination

The final slide count has a hard limit of 30. The system must optimize for
information value rather than fill the limit.

The default structural budget is:

- One cover slide.
- One agenda slide.
- At most one chapter divider per chapter.
- One to three content slides per section.
- One final summary and cooperation-action slide.

Every section receives at least one content slide. Additional pages are allocated
according to content complexity, number of independent insights, available
evidence, case depth, visual opportunities, layout capacity, and deck rhythm.

If the proposed plan exceeds 30 slides, the planner must remove low-value
extensions, merge repeated points, reduce ordinary sections to one page, and
omit optional divider slides. It must never solve overflow by making text
unreadably small or by silently dropping a user section.

## Slide Plan

Planning produces `slide_plan.json` and continues automatically without an
approval pause. The plan is retained for auditing and comparison.

Every slide record includes:

- Index and stable ID.
- Chapter and section lineage.
- Narrative role.
- Audience-facing title.
- One core message.
- Structured content blocks.
- Evidence and source IDs.
- Required visual assets.
- Visual intent.
- Candidate layout families.
- Capacity requirements.
- Short source footer.

The system may add agenda, chapter divider, synthesis, conclusion, and
cooperation-action slides without changing chapter boundaries or inventing new
subject-matter chapters.

Visible slide content must not expose planning notes, research prompts, or
internal production instructions.

## Route B: Template Component Engine

Route B prioritizes fidelity and editability.

For each planned slide:

1. Match the narrative role, block count, text length, image count, image ratio,
   and data needs to available source frames.
2. Clone the best-fitting source slide when one exists.
3. Edit inherited slots by stable source element ID.
4. Preserve font family, size, weight, paragraph spacing, text insets,
   alignment, vertical anchor, crop, z-order, master, layout, and brand furniture.
5. Delete or replace only objects explicitly classified for that action.
6. If no source frame fits, compose a new layout from approved template
   components under the extracted theme and grid rules.
7. If content does not fit, shorten it, choose a larger layout, or split the
   slide. Do not silently shrink type.

New component-derived layouts may use only template fonts, palette values,
spacing rules, recurring ornaments, source regions, and approved components.
They must pass a template-consistency check before publication.

## Route C: Template-Constrained HTML Agent

Route C prioritizes visual freedom while remaining constrained by the template.

The design agent receives the current slide specifications, `theme.json`,
relevant source slide renders, component evidence, layout rules, page dimensions,
and an explicit supported-CSS contract.

The model generates two to four pages per batch. Local code writes the returned
files, validates them in one browser session, and sends only failed pages back
for repair. All pages share `global.css` and `theme.css`.

Route C must use the production-grade HTML2PPTX implementation from the original
v2 codebase or an equivalent extracted implementation. It must support or safely
rasterize gradients, opacity, shadows, per-side borders, SVG, tables, lists,
rich text, image clipping, and supported pseudo-elements. The current minimal
renderer is insufficient for comparison.

Conversion failures must trigger compatible HTML repair. The pipeline must never
publish an incorrect PPTX silently or declare success from the HTML render alone.

## Source Display

Slides containing external facts, data, cases, or images must show a short source
footer at the bottom of the slide. A typical footer is:

```text
来源：华为年度报告；同济大学官网，2026
```

The complete URL, title, publisher, publication date, and access time remain in
the run evidence and speaker notes where supported. Shortening the visible source
label must not remove the underlying provenance record.

## Quality Gates

### Content Gate

- Every requested section is represented.
- Chapter and section order is preserved.
- Every factual claim resolves to retained evidence.
- No unsupported internal claim, outcome, commitment, or exact number appears.
- Slide copy fits the chosen narrative role and capacity budget.

### Mechanical Layout Gate

- Correct page size.
- No page overflow.
- No clipped or unintended wrapped text.
- No unintended element overlap.
- No missing images.
- No unresolved placeholders.
- No empty inherited date, footer, or slide-number placeholders.
- No illegibly small text.
- No low-contrast text, including white text on a lost background.

### Final PPTX Gate

Both outputs must be rendered after export. Final PPTX renders, not intermediate
HTML renders, are authoritative. The gate checks slide count, editability,
placeholder state, asset presence, font resolution, image crop, layout integrity,
and visual conversion fidelity.

### Deck-Level Gate

- Stable brand treatment and source footer.
- Consistent typography and alignment.
- Appropriate density and pacing.
- No excessive repetition of a single layout silhouette.
- Coherent opening, chapter progression, synthesis, and conclusion.

## Comparison Report

The comparison output contains:

- Side-by-side renders for every corresponding slide.
- Template-style consistency observations.
- Content completeness.
- Editability observations.
- HTML-to-PPTX fidelity findings for Route C.
- Mechanical QA results.
- Total wall time and per-stage timing.
- Model request count and token usage.
- Repair count and failed-slide history.
- A concise recommendation for the supplied template and outline.

The report must not compare different content. Both routes use identical planned
copy, facts, assets, and source labels.

## CLI Surface

Template import:

```powershell
uv run localdeck template import .\template.pptx --name huawei-education
```

Template inspection:

```powershell
uv run localdeck template inspect huawei-education
```

Dual-route generation:

```powershell
uv run localdeck generate `
  --outline .\outline.json `
  --template huawei-education `
  --routes template,html `
  --max-slides 30 `
  --output-dir .\output
```

The final output directory contains:

```text
output/
|-- presentation-template.pptx
|-- presentation-html.pptx
`-- comparison.html
```

## Module Boundaries

```text
localdeck/
|-- inputs/        # Outline schema and normalization
|-- templates/     # Import, inspection, classification, themes, components
|-- research/      # Search, source policy, retrieval, and asset resolution
|-- planning/      # Content plan, pagination, and slide specification
|-- generation/
|   |-- template_engine/ # Route B
|   `-- html_agent/      # Route C
|-- quality/       # Content, layout, PPTX, visual, and deck checks
`-- comparison/    # Metrics and comparison report
```

Existing Agent, MCP, workspace, logging, and manifest primitives should be reused
where their contracts remain appropriate. New code must not expose an arbitrary
shell or unrestricted host filesystem access to a model.

## Error Handling

- Invalid input fails before research or model calls.
- Encrypted or unreadable templates fail with a specific import error.
- Unsupported source objects are preserved and reported rather than discarded.
- Search and download errors retain the affected query and URL.
- Unverifiable claims are removed from the plan.
- A layout mismatch triggers another source frame, component layout, or split.
- A Route C compatibility failure triggers HTML repair.
- A page that fails two repair attempts falls back to a safe approved layout.
- A route may fail independently without deleting the other route's artifacts.
- Publication is atomic and occurs only after final-route verification.

## Security And Privacy

- API credentials remain in the parent process environment and secret wrappers.
- Model-facing tools remain workspace-confined.
- Downloaded content is treated as untrusted data.
- Template files and extracted assets remain local.
- The model receives only the source material required for the current stage.
- Network access is limited to the research and asset retrieval modules.
- Every external request is logged without credentials.

## Testing Strategy

Tests cover input normalization, malformed outlines, page-budget enforcement,
template master/layout preservation, placeholder identification, grouped shapes,
missing fonts, 4:3 and 16:9 templates, unsupported objects, source ranking,
conflicting evidence, image failures, layout matching, content overflow, source
footers, Route C CSS compatibility, final PPTX rendering, editability, and atomic
publication.

The first end-to-end acceptance fixture uses the approved Huawei/Tongji outline
and one representative editable template.

## Acceptance Criteria

1. The complete workflow runs locally on Windows without Docker.
2. The system accepts the approved outline JSON and an editable PPTX template.
3. All chapters and sections appear in their original order and meaning.
4. The generated plan contains no more than 30 slides.
5. Every section has at least one content slide.
6. Functional pages may be added without inventing new subject chapters.
7. Public claims and assets are traceable to authoritative sources.
8. Applicable slides show a short bottom source label.
9. Route B and Route C consume the same `slide_plan.json` and shared assets.
10. Route B clones source frames where possible and creates template-derived
    layouts only when necessary.
11. Route C follows extracted typography, palette, spacing, and brand rules.
12. Both outputs are editable PPTX files that open successfully.
13. Required logos, footers, confidentiality marks, and brand furniture remain.
14. Final renders contain no clipping, unintended overlap, unresolved
    placeholders, missing assets, or lost-background text.
15. Route C does not reproduce the current gradient-loss and white-on-white bug.
16. The comparison report contains corresponding renders, QA findings, timings,
    model request counts, token usage, and repair counts.
17. A failed stage cannot overwrite an earlier successful published output.

## Delivery Strategy

Implementation should proceed through narrow vertical slices. The first slice
must prove source-slide import, duplication, in-place text/image editing, theme
preservation, Windows rendering, and high-fidelity HTML conversion before adding
research or orchestration complexity. This keeps the two highest-risk rendering
paths testable before expensive agent behavior is introduced.
