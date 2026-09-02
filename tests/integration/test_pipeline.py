from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pydantic import SecretStr

from localdeck.config import Settings
from localdeck.llm.protocol import AssistantResponse, ToolCall
from localdeck.models import GenerationRequest, RunManifest, RunStage
from localdeck.pipeline import LocalDeckPipeline
from tests.fixtures.scripted_run import ScriptedLLM


def tool_response(*calls: tuple[str, dict, str]) -> AssistantResponse:
    return AssistantResponse(
        tool_calls=[
            ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))
            for name, arguments, call_id in calls
        ]
    )


def valid_slide(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
html, body {{ margin:0; width:1280px; height:720px; overflow:hidden; }}
body {{ padding:72px; background:#f8fafc; font-family:Arial,sans-serif; }}
h1 {{ margin:0 0 40px; color:#0f172a; font-size:52px; }}
p {{ margin:0; width:1020px; color:#334155; font-size:30px; line-height:1.4; }}
</style></head><body><h1>{title}</h1><p>{body}</p></body></html>"""


async def test_pipeline_generates_complete_pptx_with_local_tools(
    tmp_path: Path,
) -> None:
    manuscript = "# AI 的现在\n\n核心能力\n\n---\n\n# AI 的未来\n\n发展方向"
    llm = ScriptedLLM(
        [
            tool_response(
                (
                    "write_file",
                    {"path": "manuscript.md", "content": manuscript},
                    "research-write",
                ),
                ("finalize", {"outcome": "manuscript.md"}, "research-final"),
            ),
            tool_response(
                (
                    "write_file",
                    {"path": "slides/global.css", "content": "body{}"},
                    "css",
                ),
                (
                    "write_file",
                    {
                        "path": "slides/slide_01.html",
                        "content": valid_slide(
                            "AI 的现在", "模型已成为通用信息处理平台。"
                        ),
                    },
                    "slide-1",
                ),
                (
                    "inspect_slide",
                    {"html_file": "slides/slide_01.html", "aspect_ratio": "16:9"},
                    "inspect-1",
                ),
                (
                    "write_file",
                    {
                        "path": "slides/slide_02.html",
                        "content": valid_slide(
                            "AI 的未来", "可靠性与可控性将决定落地速度。"
                        ),
                    },
                    "slide-2",
                ),
                (
                    "inspect_slide",
                    {"html_file": "slides/slide_02.html", "aspect_ratio": "16:9"},
                    "inspect-2",
                ),
                ("finalize", {"outcome": "slides"}, "design-final"),
            ),
        ]
    )
    settings = Settings(
        api_key=SecretStr("unused-test-key"), runs_dir=tmp_path / "runs"
    )
    output = tmp_path / "published.pptx"
    request = GenerationRequest(topic="AI 趋势", slides=2, output=output)

    result = await LocalDeckPipeline(settings, llm=llm).generate(request)

    assert result.output == output.resolve()
    assert result.output.is_file()
    assert len(Presentation(result.output).slides) == 2
    manifest = RunManifest.model_validate_json(
        result.manifest.read_text(encoding="utf-8")
    )
    assert all(manifest.stages[stage].status == "completed" for stage in RunStage)
    assert (result.workspace / "history" / "research.jsonl").is_file()
    assert (result.workspace / "history" / "design.jsonl").is_file()
