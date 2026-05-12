# Confirmed Plan: Web Search Tool

## User goal

Implement a `web_search` tool for searching online resources, prioritizing providers that do not require third-party platform API keys.

## Confirmed requirements

- Add a read-only tool that can be auto-registered by the existing `tools` package.
- Default provider should work without API keys.
- Prefer a lightweight MVP that does not add new dependencies if practical.
- Provide clear error handling for network failures, parsing changes, and unavailable providers.
- Add tests for schema/registration, provider parsing, and graceful error behavior.
- Update related documentation with usage, limitations, and future provider options.

## Scope

- Add `tools/web_search.py`.
- Add focused tests under `tests/`.
- Update relevant docs.

## Non-goals

- Do not implement full web page fetching or article extraction in this task.
- Do not rely on SerpAPI, Tavily, Brave Search, Bing, Google Custom Search, or other key-required APIs as the default.
- Do not introduce browser automation such as Playwright/Selenium for the MVP.
- Do not bypass CAPTCHAs, paywalls, robots restrictions, or target site anti-abuse protections.

## Affected areas

- `tools/` auto-registered tool definitions and handlers.
- Tool metadata tests.
- Usage/project documentation.

## Subagent assignments

No subagent is required for this implementation because the design was already discussed and the code change is small and localized.

## Implementation plan

1. Implement `web_search` as a read-only, concurrency-safe tool.
2. Use DuckDuckGo HTML/Lite as the default no-key provider via Python standard library HTTP and HTML parsing.
3. Optionally support SearXNG when a caller supplies a `searxng_base_url` or provider-specific configuration.
4. Return compact, source-attributed results with title, URL, snippet, and provider metadata.
5. Cap result counts and output length.
6. Return explicit `Error:` strings for invalid provider/config/network conditions.

## Verification plan

- Run focused tests for `web_search` parsing/error behavior.
- Run tool metadata tests to confirm auto-registration and execution metadata.
- Run lint on changed Python files.

## Risks

- Direct DuckDuckGo HTML scraping is best-effort and may break if markup changes or if the environment is rate-limited.
- Runtime network access may be unavailable in some environments.
- Public SearXNG instances can be unstable; SearXNG should not be the only default provider.

## Approval context

User confirmed implementation after previous `/plan` discussion with: `可以实现方案吧`.
