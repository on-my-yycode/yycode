# Confirmed Plan: P0-P2 Reliability and UX Closure

## User Goal

Implement and close all current P0 through P2 follow-up items after the roadmap items 1-5 release.

## Scope

### P0: Release hygiene

- Run full verification baseline: `pytest` and `ruff check .`.
- Review and keep changes grouped by release area.

### P1: Reliability and safety closure

- Session persistence unwritable-directory fallback behavior and tests.
- Workspace/apply_patch/git path boundary tests and small fixes if needed.
- LSP close robustness: LSP shutdown failure must not prevent provider cleanup; avoid unnecessary broad failures.

### P2: UX and feature polish

- Help modal usability: scrollable help content and `?` shortcut.
- LSP diagnostics/output polish: bounded MVP only, no write-capable LSP actions.
- Message Token Manager MVP polish: undo/backup/config thresholds if small enough; otherwise implement the smallest safe undo/config surface and document remaining work.
- Documentation sync for usage, project structure, and roadmap status.

## Non-goals

- P3/P4 work: evals, subagent runtime unification, long-task summary memory, DAG scheduler.
- Write-capable LSP actions such as rename/codeAction/format.
- Large storage format redesign.
- Large model-generated summary compression system.

## Implementation Strategy

1. Save this plan.
2. Run full baseline verification and record failures.
3. Inspect current implementation for each P1/P2 item.
4. Implement the smallest safe changes for each item with focused tests.
5. Update docs.
6. Run focused tests and full verification again.

## Verification Plan

- `pytest`
- `ruff check .`
- Focused tests for changed areas, including session store, workspace tools, LSP tools, TUI command/help, Message Context Manager, and TUI state/runner.

## Risks

- Full verification may reveal unrelated pre-existing failures.
- P2 Message Token Manager undo/config may be too broad; keep to MVP and document remaining work.
- LSP diagnostics support varies by language server; avoid requiring real pyright/pylsp in tests.
