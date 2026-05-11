# Changelog

All notable changes to this project will be documented in this file.

## [0.3.2] - 2026-05-11

### Features
- Add Python read-only LSP navigation tools with document/workspace symbols, definition, references, hover, diagnostics fallback, and timeline labeling for semantic navigation
- Add Message Token Manager support for analyzing context usage, manually compressing old tool outputs, and undoing the most recent manual compression
- Add TUI command/help improvements including `:help`, `:clear`, `?` help access, and command completion
- Add stronger session persistence recovery for corrupt session files, save failures, missing deletes, and corrupt list metadata

### Improvements
- Reduce TUI markdown rendering cost with cached item rendering, lightweight markdown while tasks are running, and full markdown/code highlighting after completion
- Improve workspace/workdir safety with additional absolute path, symlink escape, nested workspace, and apply_patch boundary coverage
- Filter noisy LSP symbols and ignore workspace-external LSP locations
- Refresh roadmap, usage, and project structure documentation to match the current implementation

### Tests
- Expand LSP, session store, workspace boundary, apply_patch safety, TUI runner, token manager, and subagent regression coverage

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
