from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from localdeck.config import Settings
from localdeck.llm.glm import GLMClient, should_retry


class FakeCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def fake_response() -> SimpleNamespace:
    call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="write_file", arguments='{"path":"x"}'),
    )
    message = SimpleNamespace(content=None, tool_calls=[call])
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=12, completion_tokens=7)
    return SimpleNamespace(choices=[choice], usage=usage)


async def test_glm_client_normalizes_openai_tool_call(tmp_path) -> None:
    completions = FakeCompletions(fake_response())
    sdk = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    settings = Settings(api_key=SecretStr("secret"), runs_dir=tmp_path)
    client = GLMClient(settings, sdk_client=sdk)

    response = await client.complete(
        [{"role": "user", "content": "create"}],
        [{"type": "function", "function": {"name": "write_file"}}],
    )

    assert response.tool_calls[0].name == "write_file"
    assert response.prompt_tokens == 12
    assert completions.kwargs["model"] == "glm-5.2"
    assert completions.kwargs["tool_choice"] == "auto"


def test_retry_classification_uses_status_code() -> None:
    transient = SimpleNamespace(status_code=429)
    server_error = SimpleNamespace(status_code=503)
    auth_error = SimpleNamespace(status_code=401)

    assert should_retry(transient)
    assert should_retry(server_error)
    assert not should_retry(auth_error)
