# Confirmed Plan: Roadmap Items 1-5 Release

## Approval Context

The user requested `/code_workflow` and asked to bundle the previously recommended roadmap next steps 1-5 into a single version and begin execution. After scope clarification, the user instructed to continue executing the remaining Task State items, which is treated as confirmation of this plan.

## User Goal

Deliver one bounded release that closes the next five roadmap follow-ups:

1. Current status / release scope calibration.
2. Workspace / workdir boundary test closure.
3. Session persistence resilience test closure.
4. LSP MVP cleanup and status calibration.
5. Message Token Manager calibration and focused test coverage.

## Confirmed Requirements

### 1. Status and roadmap calibration

- Update roadmap/documentation to reflect current implemented features.
- Mark LSP and Message Token Manager work according to actual current implementation.
- Record remaining follow-ups clearly.

### 2. Workspace / workdir boundary tests

- Add focused tests for workspace-bound path safety and direct tool behavior.
- Cover absolute paths, `..` escape, symlink escape, and nested workspace behavior where practical.
- Keep implementation changes minimal unless tests reveal bugs.

### 3. Session persistence resilience

- Add or improve tests for corrupted session files, workspace isolation, clear/reset persistence semantics, and boundary behavior.
- Keep storage format stable unless a bug requires a small fix.

### 4. LSP MVP cleanup

- Ensure LSP tools remain read-only and workspace-bound.
- Add lifecycle cleanup so LSP managers can be shut down from session close.
- Keep diagnostics behavior explicit as MVP unsupported/empty unless a small safe improvement is obvious.
- Do not add write-capable LSP actions.

### 5. Message Token Manager calibration

- Verify exact/estimated context reporting and compression suggestion behavior.
- Add focused tests for manual old-tool-output compression and TUI header/manager consistency where practical.
- Keep this bounded to calibration/tests and small correctness fixes.

## Non-goals

- TypeScript / JavaScript LSP support.
- LSP rename, codeAction, organize imports, or formatting.
- Full LSP diagnostics publish/pull implementation.
- Message Token Manager undo, backup history, configurable thresholds, or model-generated summaries.
- Large session storage format redesign.
- Full DAG scheduler implementation.
- Full evals suite implementation.

## Affected Areas

- `docs/code_agent_roadmap.md`
- `docs/usage.md` if user-facing behavior changed
- `agent/session.py`
- `agent/lsp/`
- `tools/lsp_*.py`
- `agent/message_context_manager.py`
- `agent/tui/` message context surfaces if needed
- `tests/test_workspace_tools.py`
- `tests/test_session_store.py`
- `tests/test_lsp_tools.py`
- `tests/test_message_context_manager.py`
- TUI tests as needed

## Subagent Assignments

- `explorer`: Identify exact current implementation/test gaps for items 2-5.
- `worker`: Implement scoped fixes and tests.
- `security`: Review workspace/session path safety changes.
- `tester`: Run focused and broader verification.

## Implementation Plan

1. Explore current code and tests for workspace, session persistence, LSP, and message context.
2. Add missing focused tests first where possible.
3. Implement small fixes uncovered by tests.
4. Add LSP cleanup hook to session close if not already present.
5. Update roadmap/status documentation.
6. Run focused tests and lint.
7. Run broader relevant tests if focused checks pass.

## Verification Plan

Focused checks:

```text
pytest tests/test_workspace_tools.py
pytest tests/test_session_store.py
pytest tests/test_lsp_tools.py
pytest tests/test_message_context_manager.py
pytest tests/test_tui_runner.py
pytest tests/test_tui_state.py
ruff check affected files
```

If time and scope allow:

```text
pytest
ruff check .
```

## Risks

- Scope is broad; keep changes bounded to tests, small bug fixes, lifecycle cleanup, and docs.
- LSP availability differs by machine; tests should use fake server/unavailable fallback rather than requiring pyright/pylsp.
- Symlink handling differs by filesystem; tests should assert intended safety behavior without relying on platform-specific permissions.
- Session persistence may involve sensitive data; avoid expanding persisted content.
