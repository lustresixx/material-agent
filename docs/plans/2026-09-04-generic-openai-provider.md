# Generic OpenAI Provider Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow LocalDeck to use any OpenAI Chat Completions-compatible endpoint, including local servers with an empty API key, while preserving GLM Coding Plan and providing explicit research fallbacks.

**Architecture:** Extend immutable settings with provider and research-mode policies, then apply CLI overrides after environment loading. Keep one OpenAI SDK adapter but conditionally add GLM-only request fields. Route template research through MCP, one batched LLM expansion, or outline-only packets according to the resolved policy.

**Tech Stack:** Python 3.11+, Pydantic 2, Typer, OpenAI Python SDK, pytest, pytest-asyncio, Ruff, Pyright

---

### Task 1: Resolve generic model configuration

**Files:**
- Modify: `tests/unit/test_config.py`
- Modify: `localdeck/config.py`

**Step 1: Write failing configuration tests**

Add focused tests for:

```python
def test_settings_allows_explicit_empty_openai_key(...):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    settings = Settings.from_env()
    assert settings.api_key.get_secret_value() == ""

def test_openai_environment_takes_precedence_over_legacy_environment(...):
    ...

def test_settings_detects_provider_from_final_base_url(...):
    ...

def test_cli_overrides_can_explicitly_clear_api_key(...):
    settings = Settings.from_env().with_overrides(api_key="")
    assert settings.api_key.get_secret_value() == ""
```

Also cover blank Base URL/model rejection and separate MCP key resolution.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/test_config.py -q`

Expected: FAIL because provider/research enums and `with_overrides` do not exist, and empty model keys are currently rejected.

**Step 3: Implement minimal settings behavior**

Add string enums and resolution helpers:

```python
class ProviderMode(StrEnum):
    OPENAI = "openai"
    CODING_PLAN = "coding-plan"


class ResearchMode(StrEnum):
    AUTO = "auto"
    MCP = "mcp"
    LLM = "llm"
    OFF = "off"
```

Make `api_key` default to `SecretStr("")`, add a separate `mcp_api_key`, resolve generic variables before legacy variables while preserving explicitly empty keys, and expose:

```python
def with_overrides(
    self,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    provider: ProviderMode | None = None,
    research_mode: ResearchMode | None = None,
) -> Settings:
    ...
```

Provider auto-detection runs after the final Base URL is known.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/unit/test_config.py -q`

Expected: PASS.

**Step 5: Commit**

```powershell
git add tests/unit/test_config.py localdeck/config.py
git commit -m "feat: add generic provider settings"
```

### Task 2: Make the model client provider-neutral

**Files:**
- Modify: `tests/unit/test_glm.py`
- Modify: `localdeck/llm/glm.py`

**Step 1: Write failing client tests**

Test these observable request boundaries:

```python
@pytest.mark.asyncio
async def test_generic_provider_omits_vendor_extra_body():
    ...
    assert "extra_body" not in sdk.chat.completions.kwargs

@pytest.mark.asyncio
async def test_coding_plan_provider_enables_thinking():
    ...
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}

def test_empty_key_uses_non_secret_sdk_placeholder(monkeypatch):
    ...
    assert captured["api_key"] == "not-required"
```

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/test_glm.py -q`

Expected: FAIL because all requests currently include `extra_body` and the SDK receives an empty key.

**Step 3: Implement minimal adapter changes**

Rename the implementation to `OpenAICompatibleClient`, retain `GLMClient` as an alias, use the placeholder only at SDK construction, and conditionally add the GLM field:

```python
if self.settings.provider is ProviderMode.CODING_PLAN:
    kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
```

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/unit/test_glm.py -q`

Expected: PASS.

**Step 5: Commit**

```powershell
git add tests/unit/test_glm.py localdeck/llm/glm.py
git commit -m "feat: generalize OpenAI-compatible client"
```

### Task 3: Add LLM and outline-only research packets

**Files:**
- Create: `tests/unit/test_llm_research.py`
- Create: `localdeck/research/llm.py`
- Modify: `localdeck/research/models.py`

**Step 1: Write failing research tests**

Create a fake `LLMClient` and verify:

```python
@pytest.mark.asyncio
async def test_llm_research_expands_all_sections_in_one_completion(...):
    packets = await LLMResearchProvider(fake).research(outline, output_dir)
    assert fake.calls == 1
    assert packets[0].claims[0].evidence_ids == ()

@pytest.mark.asyncio
async def test_llm_research_falls_back_per_missing_section(...):
    ...
    assert packets[1].claims[0].text == packets[1].section_title

def test_outline_research_uses_section_titles(...):
    ...
```

Include fenced JSON parsing and malformed response coverage.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/test_llm_research.py -q`

Expected: collection/import FAIL because `localdeck.research.llm` does not exist.

**Step 3: Implement batched expansion**

Implement:

```python
class LLMResearchProvider:
    async def research(
        self, outline: OutlineDocument, output_dir: Path
    ) -> list[ResearchPacket]:
        ...


def outline_packets(outline: OutlineDocument) -> list[ResearchPacket]:
    ...
```

Use one no-tools completion, parse a strict positional JSON payload, retain valid section results, and fall back to section titles. Persist the sanitized packets under the normal research directory. Relax `ResearchClaim.evidence_ids` to permit an empty tuple for explicitly ungrounded LLM output.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/unit/test_llm_research.py -q`

Expected: PASS.

**Step 5: Commit**

```powershell
git add tests/unit/test_llm_research.py localdeck/research/llm.py localdeck/research/models.py
git commit -m "feat: add local LLM research fallback"
```

### Task 4: Select the research route in the template pipeline

**Files:**
- Modify: `tests/integration/test_dual_route_pipeline.py`
- Modify: `localdeck/pipeline.py`

**Step 1: Write failing route-selection tests**

Cover:

```python
@pytest.mark.asyncio
async def test_auto_research_uses_llm_without_mcp_credentials(...):
    ...

@pytest.mark.asyncio
async def test_off_research_does_not_call_model_or_mcp(...):
    ...

@pytest.mark.asyncio
async def test_mcp_research_requires_complete_configuration(...):
    with pytest.raises(SettingsError, match="MCP"):
        ...
```

Keep injected search/reader providers as the highest-priority deterministic test path.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/integration/test_dual_route_pipeline.py -q`

Expected: FAIL because the pipeline always creates remote MCP clients when providers are not injected.

**Step 3: Implement route selection**

Resolve `auto` to MCP only when both URLs and a non-empty MCP key exist. Pass the model client to `LLMResearchProvider`, use `outline_packets` for `off`, and validate forced MCP mode before opening network clients. Write MCP tool history only for the MCP branch.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/integration/test_dual_route_pipeline.py -q`

Expected: PASS.

**Step 5: Commit**

```powershell
git add tests/integration/test_dual_route_pipeline.py localdeck/pipeline.py
git commit -m "feat: route template research by capability"
```

### Task 5: Expose CLI overrides

**Files:**
- Modify: `tests/integration/test_cli.py`
- Modify: `localdeck/cli.py`

**Step 1: Write failing CLI tests**

Invoke Typer with `--base-url`, `--api-key`, `--model`, `--provider`, and
`--research-mode`; capture the settings received by a fake pipeline. Assert CLI values override conflicting environment variables and an explicitly empty API key remains empty.

**Step 2: Run tests to verify RED**

Run: `uv run pytest tests/integration/test_cli.py -q`

Expected: FAIL with unknown options.

**Step 3: Add CLI options**

Add optional arguments to `generate`, call `Settings.from_env().with_overrides(...)`, and keep the options common to both input modes. Use enum-backed Typer options so invalid values receive normal CLI validation.

**Step 4: Run tests to verify GREEN**

Run: `uv run pytest tests/integration/test_cli.py -q`

Expected: PASS.

**Step 5: Commit**

```powershell
git add tests/integration/test_cli.py localdeck/cli.py
git commit -m "feat: expose provider options in CLI"
```

### Task 6: Document generic and Coding Plan usage

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/call-chain.html`

**Step 1: Write a failing documentation assertion**

Add or extend the lightweight documentation test to assert the README includes `OPENAI_BASE_URL`, empty-key local usage, research modes, and the CLI precedence rule. Assert the call-chain page names the MCP/LLM/off research split.

**Step 2: Run the documentation test to verify RED**

Run the specific existing documentation test module discovered with `rg -n "README|call-chain" tests`.

Expected: FAIL because the new configuration is undocumented.

**Step 3: Update documentation**

Document:

- generic environment-variable setup;
- one-command CLI override example;
- GLM Coding Plan compatibility example;
- `auto`, `mcp`, `llm`, and `off` semantics;
- tool-calling requirement for the topic route;
- credential separation and CLI history warning.

Update the existing HTML call-chain diagram in place to include the research selector and its three execution branches.

**Step 4: Run documentation tests to verify GREEN**

Run the same focused test command.

Expected: PASS.

**Step 5: Commit**

```powershell
git add .env.example README.md docs/call-chain.html tests
git commit -m "docs: explain generic provider configuration"
```

### Task 7: Full regression and local no-key smoke test

**Files:**
- Modify only if a failing test reveals a defect; add the failing regression test first.

**Step 1: Run static checks**

Run:

```powershell
uv run ruff check .
uv run pyright
```

Expected: both pass.

**Step 2: Run the offline suite**

Run: `uv run pytest -m "not live" -q`

Expected: all offline tests pass.

**Step 3: Run a no-key protocol smoke test**

Start a temporary local HTTP handler that accepts `/v1/chat/completions`, records the Authorization header and returns a minimal OpenAI-compatible response. Invoke `OpenAICompatibleClient` with an empty Key and verify the request reaches the server without a configuration exception.

Expected: the handler receives exactly one request and the client normalizes the response.

**Step 4: Scan for credential leakage**

Run searches for the previously supplied credential prefix and common real-secret patterns across tracked files and Git diff.

Expected: no matches.

**Step 5: Commit any verification-only fixes**

```powershell
git add <tested-files>
git commit -m "fix: close generic provider release gaps"
```

Skip this commit when verification requires no changes.

### Task 8: Publish

**Files:** none.

**Step 1: Confirm repository state**

Run: `git status --short; git log --oneline -8`

Expected: clean worktree and the design, plan, feature, documentation, and any fix commits are present.

**Step 2: Push the current branch**

Run: `git push origin main`

Expected: remote `main` advances successfully.

**Step 3: Report exact usage**

Provide both PowerShell environment-variable and CLI examples, explain when to choose each research mode, state the test/static-check results, and link the design and implementation plan files.
