from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from localdeck.inputs.models import OutlineDocument
from localdeck.inputs.normalizer import normalize_outline_payload


def test_normalizes_html_space_and_escaped_chapter_title() -> None:
    payload = {
        "title": " 携手同济大学\uFF0C共建数智化新生态&#x20;",
        "chapters": [
            {
                "chapter\\_title": " 1. 华为公司介绍&#x20;",
                "sections": [
                    " 1.1 华为经营情况 ",
                    "1.2 华为教育业务介绍",
                ],
            }
        ],
    }

    outline = OutlineDocument.model_validate(normalize_outline_payload(payload))

    assert outline.title == "携手同济大学\uFF0C共建数智化新生态"
    assert outline.chapters[0].chapter_title == "1. 华为公司介绍"
    assert outline.chapters[0].sections == [
        "1.1 华为经营情况",
        "1.2 华为教育业务介绍",
    ]


def test_normalization_does_not_mutate_the_callers_payload() -> None:
    payload = {
        "title": " 标题 ",
        "chapters": [
            {"chapter_title": " 第一章 ", "sections": [" 第一节 "]}
        ],
    }
    original = deepcopy(payload)

    normalize_outline_payload(payload)

    assert payload == original


def test_rejects_empty_sections() -> None:
    payload = {
        "title": "标题",
        "chapters": [{"chapter_title": "第一章", "sections": []}],
    }

    with pytest.raises(ValidationError, match="sections"):
        OutlineDocument.model_validate(payload)


def test_rejects_non_object_payload() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        normalize_outline_payload(["not", "an", "object"])
