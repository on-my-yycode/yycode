"""No-key web search tool.

The default provider uses DuckDuckGo's HTML endpoint as a best-effort,
keyless search backend. This tool intentionally returns search results only;
full page fetching/extraction should be implemented as a separate tool.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser

MAX_RESULTS = 10
MAX_OUTPUT_CHARS = 20_000
DEFAULT_TIMEOUT_SECONDS = 15
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
DUCKDUCKGO_LITE_URL = "https://lite.duckduckgo.com/lite/"
USER_AGENT = "yoyoagent-web-search/0.1 (+https://github.com/yoyofx/yoyoagent)"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""


class DuckDuckGoHTMLParser(HTMLParser):
    """Small parser for DuckDuckGo HTML search results."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._current: dict[str, str] | None = None
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        classes = set(attr.get("class", "").split())

        if tag == "a" and ("result__a" in classes or "result-link" in classes):
            self._finish_result()
            self._current = {"title": "", "url": _clean_duckduckgo_url(attr.get("href", "")), "snippet": ""}
            self._capture = "title"
            self._parts = []
            return

        if self._current is not None and (
            "result__snippet" in classes or "result-snippet" in classes
        ):
            self._capture = "snippet"
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None or self._capture is None:
            return
        if self._capture == "title" and tag == "a":
            self._current["title"] = _normalize_space(" ".join(self._parts))
            self._capture = None
            self._parts = []
        elif self._capture == "snippet":
            self._current["snippet"] = _normalize_space(" ".join(self._parts))
            self._capture = None
            self._parts = []

    def close(self) -> None:
        super().close()
        self._finish_result()

    def _finish_result(self) -> None:
        if not self._current:
            return
        title = self._current.get("title", "").strip()
        url = self._current.get("url", "").strip()
        if title and url:
            self.results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=self._current.get("snippet", "").strip(),
                )
            )
        self._current = None
        self._capture = None
        self._parts = []


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _clean_duckduckgo_url(url: str) -> str:
    url = unescape(url).strip()
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return url


def _fetch_url(url: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _parse_duckduckgo_html(html: str, max_results: int) -> list[SearchResult]:
    parser = DuckDuckGoHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.results[:max_results]


def _search_duckduckgo(query: str, max_results: int, timeout: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query})
    html = _fetch_url(f"{DUCKDUCKGO_HTML_URL}?{params}", timeout=timeout)
    results = _parse_duckduckgo_html(html, max_results)
    if results:
        return results
    lite_html = _fetch_url(f"{DUCKDUCKGO_LITE_URL}?{params}", timeout=timeout)
    return _parse_duckduckgo_html(lite_html, max_results)


def _search_searxng(
    query: str,
    max_results: int,
    timeout: int,
    searxng_base_url: str | None,
) -> list[SearchResult]:
    if not searxng_base_url:
        raise ValueError("searxng_base_url is required when provider='searxng'")
    base_url = searxng_base_url.rstrip("/")
    params = urllib.parse.urlencode({"q": query, "format": "json"})
    payload = _fetch_url(f"{base_url}/search?{params}", timeout=timeout)
    data = json.loads(payload)
    results = []
    for item in data.get("results", [])[:max_results]:
        title = _normalize_space(str(item.get("title", "")))
        url = str(item.get("url", "")).strip()
        snippet = _normalize_space(str(item.get("content", item.get("snippet", ""))))
        if title and url:
            results.append(SearchResult(title=title, url=url, snippet=snippet))
    return results


def _format_results(provider: str, query: str, results: list[SearchResult]) -> str:
    if not results:
        return f"No results found for {query!r} via {provider}."

    lines = [f"web_search provider={provider} query={query!r} results={len(results)}"]
    for index, result in enumerate(results, start=1):
        lines.append(f"\n{index}. {result.title}")
        lines.append(f"   URL: {result.url}")
        if result.snippet:
            lines.append(f"   Snippet: {result.snippet}")
    return "\n".join(lines)[:MAX_OUTPUT_CHARS]


def web_search(
    query: str,
    max_results: int = 5,
    provider: str = "auto",
    searxng_base_url: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Search the web using a no-key provider when possible."""
    try:
        query = query.strip()
        if not query:
            return "Error: query is required"

        max_results = max(1, min(int(max_results), MAX_RESULTS))
        timeout = max(1, min(int(timeout_seconds), DEFAULT_TIMEOUT_SECONDS))
        provider = (provider or "auto").strip().lower()

        if provider == "auto":
            provider = "searxng" if searxng_base_url else "duckduckgo"

        if provider in {"duckduckgo", "ddg"}:
            provider_name = "duckduckgo"
            results = _search_duckduckgo(query, max_results, timeout)
        elif provider == "searxng":
            provider_name = "searxng"
            results = _search_searxng(query, max_results, timeout, searxng_base_url)
        else:
            return "Error: provider must be one of auto, duckduckgo, ddg, searxng"

        return _format_results(provider_name, query, results)
    except urllib.error.URLError as exc:
        return f"Error: network request failed: {exc}"
    except TimeoutError:
        return "Error: network request timed out"
    except json.JSONDecodeError as exc:
        return f"Error: invalid provider response JSON: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


web_search_tool = {
    "name": "web_search",
    "description": (
        "Search online resources using keyless providers when possible. "
        "Default is DuckDuckGo HTML/Lite best-effort search; optional SearXNG requires a base URL."
    ),
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 20,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
            "max_results": {
                "type": "integer",
                "description": f"Maximum number of results, capped at {MAX_RESULTS}. Defaults to 5.",
            },
            "provider": {
                "type": "string",
                "description": "Search provider: auto, duckduckgo, ddg, or searxng. Defaults to auto.",
            },
            "searxng_base_url": {
                "type": "string",
                "description": "Optional SearXNG instance base URL used when provider is searxng or auto.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": f"Network timeout in seconds, capped at {DEFAULT_TIMEOUT_SECONDS}.",
            },
        },
        "required": ["query"],
    },
}
