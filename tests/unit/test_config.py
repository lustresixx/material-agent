from __future__ import annotations

from pathlib import Path

import pytest

from localdeck.config import Settings, SettingsError


def test_settings_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZAI_API_KEY", raising=False)

    with pytest.raises(SettingsError, match="ZAI_API_KEY"):
        Settings.from_env()


def test_settings_read_safe_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = "test-secret-value"
    monkeypatch.setenv("ZAI_API_KEY", secret)
    monkeypatch.setenv("LOCALDECK_RUNS_DIR", str(tmp_path / "runs"))

    settings = Settings.from_env()

    assert settings.api_key.get_secret_value() == secret
    assert settings.model == "glm-5.2"
    assert settings.base_url == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert settings.runs_dir == (tmp_path / "runs").resolve()
    assert settings.template_dir == Path("templates").resolve()
    assert (
        settings.search_mcp_url
        == "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"
    )
    assert settings.reader_mcp_url == "https://open.bigmodel.cn/api/mcp/web_reader/mcp"
    assert settings.research_concurrency == 4
    assert settings.html_batch_size == 3
    assert settings.max_repairs == 2
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()


def test_settings_allow_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    custom_url = "https://example.test/openai/v1"
    monkeypatch.setenv("ZAI_API_KEY", "test-secret-value")
    monkeypatch.setenv("LOCALDECK_BASE_URL", custom_url)

    assert Settings.from_env().base_url == custom_url


def test_settings_allow_template_and_research_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ZAI_API_KEY", "test-secret-value")
    monkeypatch.setenv("LOCALDECK_TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("LOCALDECK_SEARCH_MCP_URL", "https://search.example/mcp")
    monkeypatch.setenv("LOCALDECK_READER_MCP_URL", "https://reader.example/mcp")
    monkeypatch.setenv("LOCALDECK_RESEARCH_CONCURRENCY", "8")
    monkeypatch.setenv("LOCALDECK_HTML_BATCH_SIZE", "4")
    monkeypatch.setenv("LOCALDECK_MAX_REPAIRS", "5")

    settings = Settings.from_env()

    assert settings.template_dir == (tmp_path / "templates").resolve()
    assert settings.search_mcp_url == "https://search.example/mcp"
    assert settings.reader_mcp_url == "https://reader.example/mcp"
    assert settings.research_concurrency == 8
    assert settings.html_batch_size == 4
    assert settings.max_repairs == 5
