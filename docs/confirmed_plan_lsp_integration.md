# Confirmed Plan: LSP Integration MVP

## User Goal

Implement a Python-first, read-only LSP integration MVP for yoyoagent so the agent can use semantic code navigation tools without coupling LSP internals to the main graph/runtime logic.

## Confirmed Requirements

- Add an independent LSP module under `agent/lsp/`.
- Add read-only LSP tools:
  - `lsp_document_symbols`
  - `lsp_workspace_symbols`
  - `lsp_definition`
  - `lsp_references`
  - `lsp_hover`
  - `lsp_diagnostics`
- Support Python language servers first:
  - Prefer `pyright-langserver` when available.
  - Fallback to `pylsp` when available.
  - Return clear `status: unavailable` output when neither exists.
- Keep LSP tools workspace-bound and read-only.
- Update prompts to tell agents to prefer LSP for semantic navigation and fallback to grep/read_file when unavailable.
- Add tests for registration, fallback, path safety, and JSON-RPC client behavior.

## Scope

- Implement minimal LSP JSON-RPC client.
- Implement LSP manager with lazy Python server detection/startup.
- Implement model-friendly formatting for symbols, locations, hover, and diagnostics.
- Add tests using fake/minimal LSP behavior where possible, without requiring a real language server installation.

## Non-goals

- No rename support.
- No codeAction support.
- No formatDocument support.
- No organizeImports support.
- No write-capable LSP operations.
- No TypeScript/JavaScript LSP support in this task.

## Affected Files / Areas

- `agent/lsp/`
- `tools/lsp_*.py`
- `agent/runtime/workspace_tools.py`
- `agent/session.py`
- Tests under `tests/`

## Subagent Assignments

No subagent is required for the first implementation pass. Verification can be handled directly with focused tests. If failures are broad or ambiguous, use a tester subagent for isolated diagnosis.

## Implementation Plan

1. Create `agent/lsp/types.py` with simple dataclasses and formatting helpers.
2. Create `agent/lsp/client.py` with a minimal async JSON-RPC/LSP client.
3. Create `agent/lsp/manager.py` with Python server detection, lazy startup, workspace path checks, and high-level read-only methods.
4. Create thin tool wrappers under `tools/`.
5. Register LSP tools as workspace-bound.
6. Update agent prompt guidance.
7. Add focused tests.
8. Run focused verification and fix issues.

## Verification Plan

- Run LSP-focused tests.
- Run tool registration/metadata tests.
- Run workspace-bound tests.
- Run broader tests if touched integration areas indicate risk.

## Risks

- Real language servers may not be installed; tools must degrade gracefully.
- LSP server lifecycle can leak processes if not cleaned up; MVP should include cleanup hooks and request timeouts.
- LSP uses zero-based line/character positions, while model-facing output may need clear formatting.
- Path safety must prevent workspace escape, including absolute paths and `..` traversal.

## Approval Context

User asked to start implementing LSP and then explicitly instructed to continue executing remaining Task State items. This is treated as confirmation to proceed with the above MVP scope.
