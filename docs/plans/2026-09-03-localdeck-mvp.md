# LocalDeck MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Docker-free local Agent/MCP/HTML-to-PPTX pipeline that turns a text topic into an editable PowerPoint file through GLM-5.2.

**Architecture:** A Typer CLI creates an isolated run workspace, starts local stdio MCP servers, and runs Research and Design tool-calling agents. Playwright validates the generated HTML, a vendored DeepPresenter converter maps it to PptxGenJS elements, and Python validates the final PPTX before atomic publication.

**Tech Stack:** Python 3.11+, uv, Pydantic 2, OpenAI Python SDK, FastMCP/MCP, Typer, Playwright, python-pptx, pytest, Node.js 20+, PptxGenJS, Sharp.

---

### Task 1: Package skeleton and boundary models

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `localdeck/__init__.py`
- Create: `localdeck/config.py`
- Create: `localdeck/models.py`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_models.py`

**Step 1: Write failing settings tests**

```python
def test_settings_requires_api_key(monkeypatch):
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    with pytest.raises(SettingsError, match="ZAI_API_KEY"):
        Settings.from_env()
```

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_models.py -v`

Expected: collection fails because `localdeck.config` and `localdeck.models` do not exist.

**Step 3: Implement minimal settings and models**

Create typed Pydantic models for `GenerationRequest`, `RunManifest`, `GenerationResult`, `InspectionIssue`, and `InspectionReport`. Read the key only from `ZAI_API_KEY`; never include it in model representations.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/unit/test_config.py tests/unit/test_models.py -v`

Expected: all tests pass.

**Step 5: Commit**

```bash
git add pyproject.toml .gitignore .env.example localdeck tests
git commit -m "feat: add package settings and boundary models"
```

### Task 2: Workspace guard and file tools

**Files:**
- Create: `localdeck/workspace.py`
- Create: `localdeck/tools/__init__.py`
- Create: `localdeck/tools/workspace.py`
- Test: `tests/unit/test_workspace.py`
- Test: `tests/unit/test_workspace_tools.py`

**Step 1: Write failing path-containment tests**

```python
def test_guard_rejects_parent_escape(tmp_path):
    guard = WorkspaceGuard(tmp_path / "run")
    with pytest.raises(WorkspaceViolation):
        guard.resolve("../secret.txt")
```

Cover absolute escape, normal relative paths, nested creation, read/write, exact edit count, directory listing, and cross-boundary moves.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/test_workspace.py tests/unit/test_workspace_tools.py -v`

Expected: missing production modules.

**Step 3: Implement minimal guarded tools**

`WorkspaceGuard.resolve()` normalizes and resolves paths, then checks `candidate.is_relative_to(root)`. Tool methods call the guard before every read or mutation.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/unit/test_workspace.py tests/unit/test_workspace_tools.py -v`

Expected: all tests pass.

**Step 5: Commit**

```bash
git add localdeck/workspace.py localdeck/tools tests/unit
git commit -m "feat: add workspace-confined file tools"
```

### Task 3: Local MCP server and client

**Files:**
- Create: `localdeck/mcp/__init__.py`
- Create: `localdeck/mcp/workspace_server.py`
- Create: `localdeck/mcp/client.py`
- Test: `tests/integration/test_mcp_roundtrip.py`

**Step 1: Write failing stdio round-trip test**

The test launches `python -m localdeck.mcp.workspace_server`, lists tools, writes a file, reads it, and closes the session.

**Step 2: Run test and verify RED**

Run: `uv run pytest tests/integration/test_mcp_roundtrip.py -v`

Expected: server module is missing.

**Step 3: Implement FastMCP server and session manager**

Register the six guarded file functions. Pass `LOCALDECK_WORKSPACE` only to the subprocess. Ensure cleanup terminates the stdio session without orphan processes.

**Step 4: Run test and verify GREEN**

Run: `uv run pytest tests/integration/test_mcp_roundtrip.py -v`

Expected: the server lists tools and returns the written content.

**Step 5: Commit**

```bash
git add localdeck/mcp tests/integration/test_mcp_roundtrip.py
git commit -m "feat: run workspace tools through local MCP"
```

### Task 4: GLM adapter and generic Agent loop

**Files:**
- Create: `localdeck/llm/__init__.py`
- Create: `localdeck/llm/protocol.py`
- Create: `localdeck/llm/glm.py`
- Create: `localdeck/agents/__init__.py`
- Create: `localdeck/agents/base.py`
- Test: `tests/unit/test_glm.py`
- Test: `tests/unit/test_agent.py`

**Step 1: Write failing behavior tests**

Use a scripted fake model and a real in-process tool registry to prove:

- assistant tool calls are executed and appended as tool messages;
- invalid JSON becomes an error tool result;
- `finalize` ends the loop only after path validation;
- no-tool responses receive a continuation prompt;
- the maximum turn limit raises a typed error;
- retry classification excludes authentication errors.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/unit/test_glm.py tests/unit/test_agent.py -v`

Expected: modules are missing.

**Step 3: Implement protocol-first model adapter**

Define an `LLMClient` protocol so the Agent loop never imports the concrete OpenAI client. `GLMClient` converts internal messages to OpenAI-compatible dictionaries and retries only transient errors.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/unit/test_glm.py tests/unit/test_agent.py -v`

Expected: all tests pass without a network call.

**Step 5: Commit**

```bash
git add localdeck/llm localdeck/agents tests/unit
git commit -m "feat: add GLM tool-calling agent loop"
```

### Task 5: Research and Design agents

**Files:**
- Create: `localdeck/prompts/research.yaml`
- Create: `localdeck/prompts/design.yaml`
- Create: `localdeck/agents/research.py`
- Create: `localdeck/agents/design.py`
- Test: `tests/unit/test_stage_agents.py`
- Create: `tests/fixtures/scripted_run.py`

**Step 1: Write failing stage tests**

Script tool-call responses that create `manuscript.md`, `global.css`, two HTML slides, run inspection, and finalize. Assert exact phase outputs and that every slide was inspected before Design completes.

**Step 2: Run test and verify RED**

Run: `uv run pytest tests/unit/test_stage_agents.py -v`

Expected: stage agents are missing.

**Step 3: Implement stage-specific prompts and completion rules**

Research exposes file tools plus `finalize`. Design exposes file tools, `inspect_slide`, and `finalize`; its result validator requires all expected slide files and successful inspection receipts.

**Step 4: Run test and verify GREEN**

Run: `uv run pytest tests/unit/test_stage_agents.py -v`

Expected: all stage tests pass.

**Step 5: Commit**

```bash
git add localdeck/agents localdeck/prompts tests
git commit -m "feat: add manuscript and HTML design stages"
```

### Task 6: Playwright quality inspection

**Files:**
- Create: `localdeck/quality.py`
- Create: `localdeck/mcp/quality_server.py`
- Test: `tests/integration/test_quality.py`
- Create: `tests/fixtures/slides/valid.html`
- Create: `tests/fixtures/slides/overflow.html`

**Step 1: Write failing browser tests**

Assert a valid 1280×720 page passes and an overflowing text box returns `text_overflow` with a screenshot path.

**Step 2: Run test and verify RED**

Run: `uv run pytest tests/integration/test_quality.py -v`

Expected: inspector module is missing.

**Step 3: Implement one-browser inspector**

Launch Chromium lazily, collect DOM measurements through `page.evaluate`, capture console/page errors, write JSON and PNG artifacts, and close the browser during server shutdown.

**Step 4: Run test and verify GREEN**

Run: `uv run pytest tests/integration/test_quality.py -v`

Expected: valid page passes; overflow page fails for the expected code.

**Step 5: Commit**

```bash
git add localdeck/quality.py localdeck/mcp/quality_server.py tests
git commit -m "feat: inspect slide HTML with local Playwright"
```

### Task 7: HTML-to-PPTX exporter and verifier

**Files:**
- Create: `localdeck/vendor/html2pptx/NOTICE.md`
- Vendor: `localdeck/vendor/html2pptx/html2pptx.js`
- Vendor: `localdeck/vendor/html2pptx/html2pptx_cli.js`
- Create: `localdeck/vendor/html2pptx/package.json`
- Create: `localdeck/rendering/__init__.py`
- Create: `localdeck/rendering/exporter.py`
- Create: `localdeck/rendering/verifier.py`
- Test: `tests/integration/test_exporter.py`

**Step 1: Write failing export test**

Export two fixture HTML files to a temporary PPTX. Reopen with `python-pptx`, assert two slides, and assert at least one editable text shape exists.

**Step 2: Run test and verify RED**

Run: `uv run pytest tests/integration/test_exporter.py -v`

Expected: exporter is missing.

**Step 3: Vendor converter and implement fixed subprocess boundary**

Use argument arrays only, capture stdout/stderr, enforce timeout, export to a temporary PPTX, verify it, then atomically replace the target.

**Step 4: Install Node dependencies and verify GREEN**

Run: `npm install --prefix localdeck/vendor/html2pptx`

Run: `uv run pytest tests/integration/test_exporter.py -v`

Expected: generated PPTX opens and contains two editable slides.

**Step 5: Commit**

```bash
git add localdeck/vendor localdeck/rendering tests/integration/test_exporter.py
git commit -m "feat: export validated HTML to editable PPTX"
```

### Task 8: Pipeline and CLI

**Files:**
- Create: `localdeck/pipeline.py`
- Create: `localdeck/cli.py`
- Create: `localdeck/__main__.py`
- Test: `tests/integration/test_pipeline.py`
- Test: `tests/integration/test_cli.py`

**Step 1: Write failing end-to-end tests**

Use the scripted fake LLM to generate a two-slide presentation. Assert workspace artifacts, manifest state, PPTX output, and CLI exit code.

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/integration/test_pipeline.py tests/integration/test_cli.py -v`

Expected: pipeline and CLI are missing.

**Step 3: Implement orchestration**

Create a run workspace, persist the request, start tool services, execute Research then Design, export, verify, publish, update the manifest after each state, and always close external resources.

**Step 4: Run tests and verify GREEN**

Run: `uv run pytest tests/integration/test_pipeline.py tests/integration/test_cli.py -v`

Expected: both end-to-end tests pass.

**Step 5: Commit**

```bash
git add localdeck tests/integration pyproject.toml
git commit -m "feat: expose the complete localdeck pipeline"
```

### Task 9: Documentation and Archify call chain

**Files:**
- Create: `README.md`
- Create: `docs/call-chain.json`
- Generate: `docs/call-chain.html`

**Step 1: Write operational README**

Document prerequisites, installation, environment variables, CLI examples, outputs, architecture limits, security constraints, and troubleshooting without including a real key.

**Step 2: Author Archify workflow specification**

Use stable IDs and Chinese labels for the main Research → Design → Inspect → Export path, with retry and failure branches.

**Step 3: Validate and deliver**

Run showcase validation until it reports all checks with zero warnings. Deliver the frozen HTML and run browser visual-check.

**Step 4: Commit**

```bash
git add README.md docs
git commit -m "docs: explain local workflow and add call-chain viewer"
```

### Task 10: Final verification and optional GLM smoke test

**Files:**
- Create: `tests/smoke/test_glm_live.py`
- Modify: `README.md`

**Step 1: Add opt-in live test**

Skip unless both `ZAI_API_KEY` and `LOCALDECK_RUN_LIVE_TESTS=1` are set. Ask GLM-5.2 to call a harmless test tool and assert the returned tool name.

**Step 2: Run complete offline suite**

Run: `uv run pytest -m "not live" -v`

Expected: all offline unit and integration tests pass.

**Step 3: Run quality gates**

Run: `uv run ruff check .`

Run: `uv run pyright localdeck`

Expected: no lint or type errors.

**Step 4: Run the live smoke test once**

Inject the user-provided key only into this process. Do not write or print it.

Run: `uv run pytest tests/smoke/test_glm_live.py -m live -v`

Expected: GLM returns the requested tool call, or the result is reported as an external credential/quota limitation without weakening offline verification.

**Step 5: Scan tracked files and run artifacts for secret leakage**

Search for the exact secret value without printing matching content. Expected: zero matches.

**Step 6: Commit**

```bash
git add tests/smoke README.md
git commit -m "test: add opt-in GLM integration coverage"
```
