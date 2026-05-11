# Confirmed Plan: Clean Baseline and Roadmap Refresh

## User Goal

From the latest roadmap todo list, discard items 5, 6, and 8, and implement items 1, 2, 3, 4, and 7. Then update todo and roadmap documentation accordingly.

## Included Items

1. Fix full pytest failure caused by locale-dependent safety test.
2. Clean up full `ruff check .` issues.
3. Update the roadmap tail / recommended next steps to current state.
4. Add user-visible session persistence warning for memory-only fallback.
7. Improve LSP diagnostics / output quality within read-only MVP bounds.

## Explicitly Discarded Items

5. Manual `:help` modal verification / micro-polish.
6. New TUI commands such as `:messages`, `:plan`, `:diff`.
8. Message Token Manager multi-step history/config enhancements.

## Non-goals

- LSP write actions.
- Full LSP diagnostics implementation if it requires broad protocol lifecycle changes.
- Message Token Manager multi-step backup/config work.
- P3/P4 roadmap items such as evals, long-task memory, subagent runtime unification, or DAG.

## Verification Plan

- `pytest`
- `ruff check .`
- Focused tests for safety, session warning, LSP output, and docs if changed.
