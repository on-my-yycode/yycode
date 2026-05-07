# Confirmed Plan: Changelog Update

## User goal
Update the project changelog to reflect the recent feature updates currently present in the workspace.

## Confirmed requirements
- Review the existing changelog files.
- Summarize the recent feature and improvement work visible in the current workspace changes.
- Update the changelog files in English and Chinese.
- Keep changes scoped to changelog documentation and this confirmed plan document.

## Scope
- Add a new unreleased section to:
  - `changes/CHANGELOG.md`
  - `changes/CHANGELOG_en.md`
  - `changes/CHANGELOG_zh.md`
- Capture TUI timeline, changed-files view, approval UX, markdown rendering, file approval safety, todo history pruning, documentation, and test coverage updates.

## Non-goals
- Do not modify runtime behavior or feature code.
- Do not rewrite existing changelog history.
- Do not resolve unrelated uncommitted workspace changes.

## Affected files or areas
- `changes/CHANGELOG.md`
- `changes/CHANGELOG_en.md`
- `changes/CHANGELOG_zh.md`
- `docs/confirmed_plan_changelog_update.md`

## Subagent assignments
No subagents are needed. This is a small documentation-only update based on direct workspace inspection.

## Implementation plan
1. Insert an `Unreleased` section at the top of the English changelog files.
2. Insert a `未发布` section at the top of the Chinese changelog file.
3. Group entries into features, improvements, and tests/documentation where appropriate.
4. Review the resulting diff for accuracy and scope.

## Verification plan
- Inspect the resulting git diff for the changed changelog files and plan document.
- Confirm no functional code was modified by this task.

## Risks
- The workspace has many existing uncommitted changes from prior work. This task must avoid overwriting them.
- The changelog is based on currently visible workspace changes rather than a tagged release diff.

## Confirmation note
The user requested continuing execution of the remaining task-state items after the proposed changelog update scope was presented. This plan records the scope being implemented before documentation edits.
