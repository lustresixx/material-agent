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
    assert settings.base_url == "https://open.bigmodel.cn/api/paas/v4/"
    assert settings.runs_dir == (tmp_path / "runs").resolve()
    assert secret not in repr(settings)
    assert secret not in settings.model_dump_json()
