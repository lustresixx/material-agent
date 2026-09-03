# Coding Plan Endpoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make GLM Coding Plan's OpenAI Chat Completion URL the LocalDeck default.

**Architecture:** Keep the current OpenAI-compatible client and environment override. Change only the default configuration contract and its documentation.

**Tech Stack:** Python 3.11+, Pydantic 2, pytest, Ruff, Pyright.

---

### Task 1: Replace the default endpoint

**Files:**
- Modify: `tests/unit/test_config.py`
- Modify: `localdeck/config.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/plans/2026-09-03-localdeck-design.md`

**Step 1: Write the failing test**

Change the settings-default assertion to require:

```python
assert settings.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
```

Add an assertion proving `LOCALDECK_BASE_URL` still overrides the default.

**Step 2: Run the test and verify RED**

Run:

```powershell
uv run python -m pytest tests/unit/test_config.py -v
```

Expected: the default assertion fails because the implementation still returns the
ordinary `/api/paas/v4/` endpoint.

**Step 3: Implement the minimal change**

Replace both default literals in `Settings` and `Settings.from_env()` with the Coding
Plan URL. Update the example environment file and documentation to match.

**Step 4: Verify GREEN and regression safety**

Run:

```powershell
uv run python -m pytest -m "not live" -q
uv run ruff format --check .
uv run ruff check .
uv run pyright localdeck
```

Expected: all commands pass.

**Step 5: Commit**

```powershell
git add localdeck/config.py tests/unit/test_config.py .env.example README.md docs
git commit -m "fix: default to GLM Coding Plan endpoint"
```

