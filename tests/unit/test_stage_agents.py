from __future__ import annotations

import json
from pathlib import Path

import pytest

from localdeck.agents.design import DesignAgent, DesignValidationError
from localdeck.agents.research import ResearchAgent, ResearchValidationError
from localdeck.llm.protocol import AssistantResponse, ToolCall
from localdeck.models import GenerationRequest
from tests.fixtures.scripted_run import ScriptedLLM, StageTools


def tool_response(*calls: tuple[str, dict, str]) -> AssistantResponse:
    return AssistantResponse(
        tool_calls=[
            ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))
            for name, arguments, call_id in calls
        ]
    )


async def test_research_agent_requires_exact_markdown_page_count(
    tmp_path: Path,
) -> None:
    request = GenerationRequest(
        topic="AI 发展",
        slides=2,
        output=tmp_path / "output.pptx",
    )
    llm = ScriptedLLM(
        [
            tool_response(
                (
                    "write_file",
                    {
                        "path": "manuscript.md",
                        "content": "# 第一页\n\n内容\n\n---\n\n# 第二页\n\n内容",
                    },
                    "write",
                ),
                ("finalize", {"outcome": "manuscript.md"}, "final"),
            )
        ]
    )
    agent = ResearchAgent(llm, StageTools(tmp_path), max_turns=3)

    manuscript = await agent.generate(request, tmp_path)

    assert manuscript == tmp_path / "manuscript.md"
    assert len(manuscript.read_text(encoding="utf-8").split("\n---\n")) == 2


async def test_research_agent_rejects_wrong_page_count(tmp_path: Path) -> None:
    request = GenerationRequest(topic="AI", slides=2, output=tmp_path / "out.pptx")
    llm = ScriptedLLM(
        [
            tool_response(
                ("write_file", {"path": "manuscript.md", "content": "# Only"}, "w"),
                ("finalize", {"outcome": "manuscript.md"}, "f"),
            )
        ]
    )

    with pytest.raises(ResearchValidationError, match="2 pages"):
        await ResearchAgent(llm, StageTools(tmp_path), max_turns=2).generate(
            request, tmp_path
        )


async def test_design_agent_requires_inspection_for_every_slide(tmp_path: Path) -> None:
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text("# One\n\n---\n\n# Two", encoding="utf-8")
    html = "<html><body style='width:1280px;height:720px'></body></html>"
    llm = ScriptedLLM(
        [
            tool_response(
                ("write_file", {"path": "slides/global.css", "content": "body{}"}, "c"),
                ("write_file", {"path": "slides/slide_01.html", "content": html}, "w1"),
                ("inspect_slide", {"html_file": "slides/slide_01.html"}, "i1"),
                ("write_file", {"path": "slides/slide_02.html", "content": html}, "w2"),
                ("inspect_slide", {"html_file": "slides/slide_02.html"}, "i2"),
                ("finalize", {"outcome": "slides"}, "f"),
            )
        ]
    )
    tools = StageTools(tmp_path)

    slides_dir = await DesignAgent(llm, tools, max_turns=3).generate(
        manuscript, expected_slides=2, aspect_ratio="16:9", workspace=tmp_path
    )

    assert slides_dir == tmp_path / "slides"
    assert tools.calls.count("inspect_slide") == 2


async def test_design_agent_rejects_missing_inspection(tmp_path: Path) -> None:
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text("# One", encoding="utf-8")
    html = "<html><body></body></html>"
    llm = ScriptedLLM(
        [
            tool_response(
                ("write_file", {"path": "slides/global.css", "content": "body{}"}, "c"),
                ("write_file", {"path": "slides/slide_01.html", "content": html}, "w"),
                ("finalize", {"outcome": "slides"}, "f"),
            )
        ]
    )

    with pytest.raises(DesignValidationError, match="inspection"):
        await DesignAgent(llm, StageTools(tmp_path), max_turns=2).generate(
            manuscript, expected_slides=1, aspect_ratio="16:9", workspace=tmp_path
        )
