# Changelog

All notable changes to this project will be documented in this file.

## [0.3.1] - 2026-05-08

### Features
- Add CLI session management shortcuts for listing, resuming, deleting, and running temporary sessions with `-s`, `-r <id>`, `-x <id>`, and `-t`
- Add a compact Transcript-style TUI timeline that groups consecutive tool calls into readable activity summaries while preserving tool targets, status, and duration details
- Add a Changed Files viewer in the TUI with `Ctrl+D`, per-file diff previews, added/removed line counts, and fold/unfold support
- Add lightweight Markdown rendering for TUI assistant output, including headings, lists, task items, quotes, fenced code blocks, and syntax highlighting for common languages

### Improvements
- Move approval prompts into the input area with clearer approve/deny copy, keyboard-first controls, and focused command/file change descriptions
- Improve file edit approval safety by blocking `apply_patch` and `write_file` calls that do not identify a target file and returning actionable correction guidance
- Improve patch path detection for unified diffs and Begin Patch style add/update/delete/move headers
- Prune internal todo tool-call artifacts from completed session history to keep follow-up conversations cleaner
- Display the active session id and restored message count in the TUI header for clearer resume status
- Update README and design documentation with a complete `docs/` directory reference that explains each document and diagram artifact

### Tests
- Expand coverage for apply_patch target validation, approval safety, subagent blocked edits, task guard behavior, tool concurrency, TUI runner/state behavior, and changed-file diff rendering

## [0.2.0] - 2026-04-23

### Features
- Add subagents system with explorer, architect, worker, and tester roles
- Implement skills management system with list_skills and load_skill tools
- Add streaming usage support
- Add tool_retry mechanism
- Add new tools: list_skills, load_skill, subagent

### Improvements
- Update agent providers (Anthropic and OpenAI)
- Enhance session management
- Improve todo management system
- Add comprehensive tests
- Add documentation

## [0.1.0] - 2026-04-22

### Features
- Initial commit of Yoyo Agent
- Core agent framework with graph-based execution
- Todo management system
- Retry mechanism for tools
- Support for OpenAI and Anthropic providers
- Basic examples and utilities
