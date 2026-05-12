"""Tests for the web_search tool."""

import urllib.error

from tools import TOOL_HANDLERS, TOOLS
from tools import web_search as web_search_module


DUCKDUCKGO_HTML = """
<html>
  <body>
    <div class="result">
      <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs&amp;rut=abc">
        Example Docs
      </a>
      <a class="result__snippet"> Example snippet with   spacing. </a>
    </div>
    <div class="result">
      <a class="result__a" href="https://example.org/plain">Plain Result</a>
    </div>
  </body>
</html>
"""

DUCKDUCKGO_LITE_HTML = """
<html>
  <body>
    <tr>
      <td>
        <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpython.org%2F&amp;rut=abc" class='result-link'>
          Welcome to Python.org
        </a>
      </td>
    </tr>
    <tr>
      <td class='result-snippet'>
        Python is a versatile language.
      </td>
    </tr>
  </body>
</html>
"""


def test_web_search_tool_is_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert "web_search" in tool_names
    assert TOOL_HANDLERS["web_search"] is web_search_module.web_search


def test_parse_duckduckgo_html_results():
    results = web_search_module._parse_duckduckgo_html(DUCKDUCKGO_HTML, max_results=5)

    assert len(results) == 2
    assert results[0].title == "Example Docs"
    assert results[0].url == "https://example.com/docs"
    assert results[0].snippet == "Example snippet with spacing."
    assert results[1].title == "Plain Result"
    assert results[1].url == "https://example.org/plain"


def test_parse_duckduckgo_lite_results():
    results = web_search_module._parse_duckduckgo_html(DUCKDUCKGO_LITE_HTML, max_results=5)

    assert len(results) == 1
    assert results[0].title == "Welcome to Python.org"
    assert results[0].url == "https://python.org/"
    assert results[0].snippet == "Python is a versatile language."


def test_web_search_duckduckgo_falls_back_to_lite_when_html_has_no_results(monkeypatch):
    calls = []

    def fake_fetch(url: str, *, timeout: int) -> str:
        calls.append(url)
        if "html.duckduckgo.com" in url:
            return "<html><body>No web results</body></html>"
        return DUCKDUCKGO_LITE_HTML

    monkeypatch.setattr(web_search_module, "_fetch_url", fake_fetch)

    output = web_search_module.web_search("python", max_results=1)

    assert len(calls) == 2
    assert "html.duckduckgo.com" in calls[0]
    assert "lite.duckduckgo.com" in calls[1]
    assert "Welcome to Python.org" in output


def test_web_search_duckduckgo_uses_fetcher(monkeypatch):
    def fake_fetch(url: str, *, timeout: int) -> str:
        assert "html.duckduckgo.com" in url
        assert "q=yoyoagent" in url
        assert timeout == 3
        return DUCKDUCKGO_HTML

    monkeypatch.setattr(web_search_module, "_fetch_url", fake_fetch)

    output = web_search_module.web_search("yoyoagent", max_results=1, timeout_seconds=3)

    assert "provider=duckduckgo" in output
    assert "results=1" in output
    assert "Example Docs" in output
    assert "https://example.com/docs" in output
    assert "Plain Result" not in output


def test_web_search_requires_query():
    assert web_search_module.web_search("   ").startswith("Error: query is required")


def test_web_search_reports_unknown_provider():
    output = web_search_module.web_search("python", provider="unknown")

    assert output == "Error: provider must be one of auto, duckduckgo, ddg, searxng"


def test_web_search_reports_missing_searxng_base_url():
    output = web_search_module.web_search("python", provider="searxng")

    assert output == "Error: searxng_base_url is required when provider='searxng'"


def test_web_search_reports_network_error(monkeypatch):
    def fake_fetch(url: str, *, timeout: int) -> str:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(web_search_module, "_fetch_url", fake_fetch)

    output = web_search_module.web_search("python")

    assert output.startswith("Error: network request failed:")
    assert "offline" in output


def test_web_search_searxng_json(monkeypatch):
    def fake_fetch(url: str, *, timeout: int) -> str:
        assert url == "https://searx.example/search?q=python&format=json"
        return '{"results": [{"title": "Python", "url": "https://python.org", "content": "Language"}]}'

    monkeypatch.setattr(web_search_module, "_fetch_url", fake_fetch)

    output = web_search_module.web_search(
        "python",
        provider="searxng",
        searxng_base_url="https://searx.example/",
    )

    assert "provider=searxng" in output
    assert "Python" in output
    assert "https://python.org" in output
    assert "Language" in output
