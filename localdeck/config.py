"""Runtime configuration loaded from an intentionally small environment surface."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class SettingsError(RuntimeError):
    """Raised when required LocalDeck configuration is unavailable or invalid."""


class Settings(BaseModel):
    """Immutable runtime settings.

    The API key is represented as :class:`SecretStr`, which prevents accidental
    disclosure through ``repr`` and Pydantic serialization. Callers should unwrap it
    only at the network boundary.
    """

    model_config = ConfigDict(frozen=True)

    api_key: SecretStr = Field(repr=False)
    model: str = "glm-5.2"
    base_url: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    runs_dir: Path = Field(default_factory=lambda: Path("runs").resolve())
    template_dir: Path = Field(default_factory=lambda: Path("templates").resolve())
    search_mcp_url: str = (
        "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp"
    )
    reader_mcp_url: str = "https://open.bigmodel.cn/api/mcp/web_reader/mcp"
    research_concurrency: int = Field(default=4, ge=1, le=12)
    html_batch_size: int = Field(default=3, ge=1, le=4)
    max_repairs: int = Field(default=2, ge=0, le=5)
    request_timeout_seconds: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)
    research_max_turns: int = Field(default=8, ge=1, le=50)
    design_max_turns: int = Field(default=20, ge=1, le=100)

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables without loading secret files."""

        api_key = os.getenv("ZAI_API_KEY", "").strip()
        if not api_key:
            raise SettingsError(
                "ZAI_API_KEY is required. Set it in the current shell environment."
            )

        return cls(
            api_key=SecretStr(api_key),
            model=os.getenv("LOCALDECK_MODEL", "glm-5.2").strip() or "glm-5.2",
            base_url=os.getenv(
                "LOCALDECK_BASE_URL",
                "https://open.bigmodel.cn/api/coding/paas/v4",
            ).strip(),
            runs_dir=Path(os.getenv("LOCALDECK_RUNS_DIR", "runs"))
            .expanduser()
            .resolve(),
            template_dir=Path(os.getenv("LOCALDECK_TEMPLATE_DIR", "templates"))
            .expanduser()
            .resolve(),
            search_mcp_url=os.getenv(
                "LOCALDECK_SEARCH_MCP_URL",
                "https://open.bigmodel.cn/api/mcp/web_search_prime/mcp",
            ).strip(),
            reader_mcp_url=os.getenv(
                "LOCALDECK_READER_MCP_URL",
                "https://open.bigmodel.cn/api/mcp/web_reader/mcp",
            ).strip(),
            research_concurrency=int(
                os.getenv("LOCALDECK_RESEARCH_CONCURRENCY", "4")
            ),
            html_batch_size=int(os.getenv("LOCALDECK_HTML_BATCH_SIZE", "3")),
            max_repairs=int(os.getenv("LOCALDECK_MAX_REPAIRS", "2")),
        )
