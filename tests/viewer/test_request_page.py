from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


PAGE = Path(__file__).parents[2] / "viewer" / "request" / "index.html"


class ElementIds(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        element_id = dict(attrs).get("id")
        if element_id:
            self.ids.add(element_id)


def test_request_page_has_all_controls_referenced_by_its_script():
    html = PAGE.read_text(encoding="utf-8")
    parser = ElementIds()
    parser.feed(html)
    referenced = set(re.findall(r'\\$\\(["\\']([^"\\']+)["\\']\\)', html))
    assert referenced <= parser.ids
    assert {
        "api-endpoint",
        "api-token",
        "confirm-submit",
        "submit-product",
        "submit-status",
    } <= parser.ids


def test_request_page_keeps_submission_explicit_and_token_ephemeral():
    html = PAGE.read_text(encoding="utf-8")
    assert "Submit to Foundry" in html
    assert 'credentials:"omit"' in html
    assert 'cache:"no-store"' in html
    assert 'window.addEventListener("pagehide"' in html
    assert "localStorage" not in html
    assert "sessionStorage" not in html


def test_request_page_javascript_parses_with_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed; browser script syntax check unavailable")
    html = PAGE.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    assert len(scripts) == 1
    result = subprocess.run(
        [node, "--check"],
        input=scripts[0],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
