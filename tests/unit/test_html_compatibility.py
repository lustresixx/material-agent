from __future__ import annotations

from localdeck.generation.html_agent.compatibility import inspect_html


def test_accepts_complete_local_only_slide() -> None:
    report = inspect_html(
        """<!doctype html><html><head>
        <link rel="stylesheet" href="theme.css">
        </head><body><h1>标题</h1><img src="asset.png"></body></html>"""
    )

    assert report.passed
    assert report.issues == ()


def test_rejects_scripts_remote_resources_and_network_fonts() -> None:
    report = inspect_html(
        """<!doctype html><html><head>
        <script src="https://example.com/app.js"></script>
        <style>@font-face { src: url(https://example.com/font.woff2); }</style>
        </head><body><img src="//example.com/image.png"></body></html>"""
    )

    assert not report.passed
    assert {issue.code for issue in report.issues} == {
        "script-not-allowed",
        "remote-resource",
        "network-font-not-allowed",
    }

