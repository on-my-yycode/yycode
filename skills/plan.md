---
name: plan
description: "Use when the user types /plan or asks to clarify requirements, discuss options, or produce a concrete project-aware plan before implementation. This skill uses a planning-only subagent with lightweight read-only discovery and must not execute edits, verification, builds, or commands."
---

# Plan Skill

Use this skill when the user wants to discuss a solution before execution, especially when the
message starts with `/plan`.

## Goal

Produce a concrete, project-aware plan without implementing it.

The plan may inspect the workspace using read-only tools, but it must not modify files, run
verification, run shell commands, request approval, or perform implementation work.

## Allowed Actions

Use lightweight read-only discovery when it helps make the plan concrete:

- `workspace_state`
- `git_diff`
- `list_files`
- `grep`
- `read_file`
- `read_many_files`
- `git_show`
- `subagent` with `role="architect"` or `role="explorer"` only

Discovery budget:

- Prefer 3-6 read-only tool calls.
- Read only the files or snippets needed to understand the current design.
- Avoid large file dumps and unrelated project exploration.
- Reuse recent discovery from the conversation when repeating `/plan` on the same topic.

## Forbidden Actions

Do not call these while this skill is active:

- `apply_patch`
- `write_file`
- `edit_file`
- `bash`
- `verify`
- implementation-oriented `subagent role="worker"`
- approval-seeking or approval-dependent actions

If the user asks to execute after planning, stop planning and wait for explicit confirmation such
as "按这个执行", "开始修改", or "implement this".

## Required Subagent

Use a separate planning subagent for non-trivial `/plan` requests:

```text
subagent(
  role="architect",
  task="Clarify the user's requirements and produce a planning-only solution. Do not modify files, run commands, verify, or implement. Use the provided discovery summary and identify assumptions, options, recommended approach, risks, and questions.",
  context="[user goal + lightweight discovery summary + current constraints]"
)
```

Use `role="explorer"` only when the main uncertainty is where behavior lives in the codebase.
The explorer must remain read-only and return evidence, not implementation.

## Multi-Round `/plan`

Repeated `/plan` in the same conversation continues discussion of the latest plan by default.

When revising a prior plan:

- Treat the latest user feedback as the new steering input.
- Reuse the previous plan summary and only do more discovery if the user changes area or scope.
- Return a revised plan, not a complete rewrite unless the user asks for one.

## Output Format

Return a concise plan in Chinese unless the user asks otherwise:

```text
**方案草案**

目标：
- ...

当前理解：
- ...

推荐方案：
- ...

可选方案：
- ...

风险与边界：
- ...

待确认：
- ...
```

Keep the final response compact. Do not include hidden reasoning, raw tool dumps, or long
subagent transcripts. The main context should retain only the useful plan summary.
