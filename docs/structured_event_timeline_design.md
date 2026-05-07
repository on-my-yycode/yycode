# Structured Event Timeline Design

## Goal

Improve the task execution experience so users can understand what the agent is doing while it works.

The target experience is closer to Cursor/Codex:

- show the current phase and active step
- show a readable timeline instead of raw tool logs
- show subagents as visible workers
- keep low-level commands, stdout, and diffs available behind expandable details
- preserve compatibility with the existing console renderer and streaming flow

This document proposes a backward-compatible extension of the current `StreamEvent` model.

## Current State

The project already has structured streaming events in `agent/streaming.py`.

Current `StreamEvent` fields:

```python
source: str
session_id: str
event_type: str
content: str = ""
role: Optional[str] = None
parent_session_id: Optional[str] = None
usage: Optional[dict[str, int]] = None
```

Current event types include:

- `thinking_start`
- `thinking_delta`
- `thinking_end`
- `tool_start`
- `tool_end`
- `tool_result`
- `usage`
- `context_compressed`
- `llm_waiting`
- `llm_timeout`
- `llm_retry`
- `llm_error`

This is already a good foundation. The gap is that `content` is mostly optimized for console logging, so the UI sees low-level messages like `bash: sed -n ...` instead of user-readable work steps.

## Compatibility Strategy

Keep the current fields and event types.

Add optional fields that richer UIs can consume. Old renderers can ignore them and continue using `event_type` plus `content`.

Proposed extended `StreamEvent`:

```python
@dataclass(frozen=True)
class StreamEvent:
    source: str
    session_id: str
    event_type: str
    content: str = ""
    role: Optional[str] = None
    parent_session_id: Optional[str] = None
    usage: Optional[dict[str, int]] = None

    title: Optional[str] = None
    detail: Optional[str] = None
    phase: Optional[str] = None
    status: Optional[str] = None
    tool_name: Optional[str] = None
    file_paths: Optional[list[str]] = None
    elapsed_ms: Optional[int] = None
    metadata: Optional[dict] = None
```

The JSON form remains straightforward:

```json
{
  "source": "main",
  "session_id": "abc",
  "event_type": "tool_start",
  "content": "read_file: agent/session.py",
  "title": "Read session code",
  "detail": "Reading agent/session.py",
  "phase": "exploring",
  "status": "running",
  "tool_name": "read_file",
  "file_paths": ["agent/session.py"],
  "metadata": {
    "path": "agent/session.py"
  }
}
```

## Event Semantics

Use the existing `event_type` values for compatibility, and optionally add higher-level event types over time.

Recommended semantic event types:

- `phase_changed`: current task phase changed
- `step_started`: a high-level timeline step started
- `step_finished`: a high-level timeline step finished
- `tool_start`: a tool started, enriched with title/detail
- `tool_end`: a tool completed, enriched with status and elapsed time
- `file_changed`: one or more workspace files changed
- `test_started`: verification started
- `test_finished`: verification completed
- `subagent_started`: a subagent started work
- `subagent_finished`: a subagent returned
- `approval_required`: user approval is needed
- `context_compressed`: context was compressed
- `llm_waiting`: model response is still pending
- `llm_error`: model request failed

The first implementation does not need every event type. It can enrich the existing events first.

## Phases

Suggested `phase` values:

- `planning`: understanding the request and aligning scope
- `exploring`: reading files, searching code, checking workspace state
- `designing`: deciding the implementation approach
- `implementing`: editing files or generating artifacts
- `verifying`: running tests, lint, typecheck, or manual validation
- `reviewing`: checking diffs, security, or risks
- `summarizing`: preparing the final response
- `waiting`: waiting for model, approval, or a long-running command
- `blocked`: stopped on approval denial, error, or missing information

These phases should be treated as display hints, not hard workflow state.

## Tool Display Mapping

`agent/runtime/tool_events.py` should produce both the existing compact `content` and richer display metadata.

Examples:

### read_file

Input:

```json
{"path": "agent/session.py", "start_line": 80, "end_line": 130}
```

Display:

```json
{
  "title": "Read file range",
  "detail": "agent/session.py lines 80-130",
  "phase": "exploring",
  "tool_name": "read_file",
  "file_paths": ["agent/session.py"]
}
```

### grep

Input:

```json
{"pattern": "tool_result", "path": "agent", "after_context": 3}
```

Display:

```json
{
  "title": "Search code",
  "detail": "Searching agent for tool_result",
  "phase": "exploring",
  "tool_name": "grep",
  "file_paths": ["agent"]
}
```

### apply_patch

Display:

```json
{
  "title": "Apply patch",
  "detail": "Editing agent/message_format.py",
  "phase": "implementing",
  "tool_name": "apply_patch",
  "file_paths": ["agent/message_format.py"]
}
```

### verify

Display:

```json
{
  "title": "Run tests",
  "detail": "pytest tests/test_message_format.py",
  "phase": "verifying",
  "tool_name": "verify"
}
```

### bash

`bash` should be shown as a command only when no better semantic mapping exists.

For common inspection commands, map to intent:

- `sed -n '10,40p' file.py` -> `Read file range`
- `grep -n pattern file.py` -> `Search code`
- `pytest ...` -> `Run tests`
- `git status` -> `Check workspace state`

The raw command should remain available in `metadata.command`.

## UI Model

A Cursor/Codex-style UI can render events into three primary regions.

### Active Status

Shows the current phase and current work item:

```text
Exploring
Reading agent/session.py and message formatting code
```

This should update from `phase`, `title`, and `detail`.

### Timeline

Shows high-level chronological steps:

```text
Understanding request
Checked workspace state
Read provider message formatting
Edited agent/message_format.py
Ran regression tests
Ready with summary
```

Each item can be expandable. Expanded details can show:

- raw tool name
- raw command
- stdout/stderr
- diff preview
- elapsed time
- token usage

### Subagent Panel

Shows active subagents separately:

```text
explorer  running  Inspecting provider message flow
worker    done     Updated message formatting
tester    running  Running regression tests
```

This can be driven by `source="subagent"`, `role`, `parent_session_id`, and later `subagent_started/subagent_finished`.

## Approval Integration

Approval should remain a pluggable decision boundary, not a console-specific behavior.

The agent core should not know whether approval comes from terminal input, a Web UI button, silent auto-approval, or another future adapter.

### Current Shape

The current runtime is already close to the desired boundary:

```text
ToolExecutor
  -> ApprovalService.approve(...)
    -> build ApprovalRequest
    -> await approval_callback(request)
    -> approved: inject approved=True
    -> denied: raise ApprovalDenied
```

`ApprovalService` owns the approval rules and cache. The callback owns user interaction.

### Design Principles

- `ApprovalService` decides whether an action requires approval.
- `ApprovalRequest` is pure data and should remain serializable.
- `approval_callback` is the only abstraction that waits for a user decision.
- Console, Web, and silent mode are adapters behind the same callback contract.
- Approval events should appear in the timeline as visible blocked states.

### Console Adapter

Console mode can keep the existing synchronous interaction model:

```text
approval_callback = console_approval_callback
```

The callback prints the request, shows the diff preview, waits for `y/N`, and returns a boolean.

The structured event layer can still emit `approval_required` before waiting and `approval_resolved` after the user responds, but the terminal renderer can remain mostly unchanged in the first implementation.

### Web Adapter

Web mode needs a pending approval store because the event stream is usually one-way from backend to frontend, while the approval decision flows back from frontend to backend.

Recommended flow:

```text
ToolExecutor
  -> ApprovalService.approve(...)
    -> web_approval_callback(request)
      -> create approval_id
      -> store pending ApprovalRequest
      -> emit approval_required event
      -> wait for frontend decision
      <- frontend approve/deny
    <- bool
  -> approved: run tool
  -> denied: raise ApprovalDenied
```

Backend-to-frontend event:

```json
{
  "event_type": "approval_required",
  "title": "Approve file edit",
  "detail": "apply_patch wants to edit agent/message_format.py",
  "phase": "blocked",
  "status": "waiting_for_user",
  "tool_name": "apply_patch",
  "file_paths": ["agent/message_format.py"],
  "metadata": {
    "approval_id": "apr_123",
    "action": "edit_file",
    "reason": "apply_patch edits workspace files and requires user approval before writing.",
    "risk": "File edits can overwrite user work or introduce unintended code changes.",
    "diff_preview": "diff --git ..."
  }
}
```

Frontend-to-backend decision:

```json
{
  "type": "approval_decision",
  "approval_id": "apr_123",
  "approved": true
}
```

After the decision, emit:

```json
{
  "event_type": "approval_resolved",
  "title": "File edit approved",
  "phase": "implementing",
  "status": "approved",
  "tool_name": "apply_patch",
  "file_paths": ["agent/message_format.py"],
  "metadata": {
    "approval_id": "apr_123",
    "action": "edit_file"
  }
}
```

Denied approval should use `status="denied"` and `phase="blocked"`.

### Silent Mode

Silent mode can stay as a callback:

```text
approval_callback = auto_approval_callback
```

It may emit `approval_resolved` with `status="auto_approved"` for auditability, but it should not block.

### Required Web Components

A Web approval adapter needs:

- a pending approval store keyed by `approval_id`
- a way to emit `approval_required` into the session event stream
- an API or WebSocket message for resolving approvals
- a Future/Event per pending approval so the callback can await the decision
- timeout or cancellation behavior if the session ends while approval is pending

This keeps approval decoupled from UI while still making it visible in the timeline.

## Backend Touch Points

### `agent/streaming.py`

Extend `StreamEvent` with optional fields and include them in `to_dict()`.

Keep the console renderer backward-compatible by continuing to use `event_type` and `content` as today.

### `agent/runtime/tool_events.py`

Add a function that returns structured display metadata:

```python
def format_tool_event_metadata(tool_call) -> dict:
    return {
        "title": "...",
        "detail": "...",
        "phase": "...",
        "tool_name": tool_call.name,
        "file_paths": [...],
        "metadata": {...},
    }
```

Keep the existing `format_tool_description()` for console compatibility.

### `agent/runtime/tool_executor.py`

When emitting `tool_start`, pass the enriched fields.

Track elapsed time and include `elapsed_ms` on `tool_end`.

When a write succeeds, emit `file_changed` in addition to the existing diff-oriented `tool_result`.

### `agent/nodes/tools_node.py`

When `todo` updates current work, optionally emit `phase_changed` or `step_started`.

This can be deferred until the tool timeline is working.

### `agent/subagent.py`

Emit `subagent_started` and `subagent_finished` around subagent runs.

Include:

- `role`
- task title or short task summary
- parent session id
- elapsed time
- final status

### `agent/llm_retry.py`

Keep `llm_waiting`, `llm_retry`, and `llm_error`, but enrich them:

- `phase="waiting"` for heartbeat events
- `phase="blocked"` for final error events
- `elapsed_ms` where available

## Rollout Plan

### Phase 1: Backward-Compatible Event Fields

- Add optional fields to `StreamEvent`.
- Update `to_dict()`.
- Add tests that old fields still serialize exactly enough for existing consumers.

Risk: low.

### Phase 2: Rich Tool Metadata

- Add display metadata for common tools.
- Enrich `tool_start` and `tool_end`.
- Keep console output unchanged or only lightly improved.

Risk: low to medium.

### Phase 3: Timeline-Friendly Events

- Emit `file_changed` for successful writes.
- Emit `test_started` / `test_finished` for verification.
- Emit `subagent_started` / `subagent_finished`.

Risk: medium, mostly around avoiding noisy duplicate events.

### Phase 4: UI Timeline

- Render active status and timeline from JSON events.
- Make low-level logs expandable.
- Add subagent panel.

Risk: depends on the UI surface, but backend event compatibility should already be stable.

## Non-Goals

- Do not change the provider message protocol.
- Do not change LangGraph routing.
- Do not change tool execution semantics.
- Do not require a web UI for the first backend event upgrade.
- Do not remove existing console output.

## Success Criteria

- Existing console mode still works.
- Existing stream consumers that read only `event_type` and `content` still work.
- New consumers can render a timeline without parsing raw shell commands.
- Users can tell what the agent is currently doing during long tasks.
- Subagent activity is visible as role-specific work, not hidden inside a single tool log.

## Implementation Summary

Initial backend support has been implemented with backward compatibility as the main constraint.

Implemented:

- `StreamEvent` now includes optional timeline fields: `title`, `detail`, `phase`, `status`, `tool_name`, `file_paths`, `elapsed_ms`, and `metadata`.
- `StreamEvent.to_dict()` serializes both old fields and new timeline fields.
- `ConsoleStreamRenderer` still supports the old event shape, but now uses `title/detail` for friendlier `tool_start` output when available.
- `agent/runtime/tool_events.py` now maps common tools to user-readable timeline metadata.
- `ToolExecutor` now emits enriched `tool_start` and `tool_end` events, including status and elapsed time.
- Successful workspace writes now emit `file_changed` in addition to the existing diff-oriented `tool_result`.
- `ApprovalService` now emits `approval_required` before waiting for a decision and `approval_resolved` after approval, denial, or cached approval.
- `SubagentRunner` now emits `subagent_started` and `subagent_finished` events with role, task detail, status, and elapsed time.
- Subagent runtime approvals now also emit approval timeline events.

Tests added or updated:

- `tests/test_streaming_events.py` covers serialization of timeline fields.
- `tests/test_tool_concurrency.py` covers enriched tool metadata, `file_changed`, and approval events.
- `tests/test_subagent.py` covers subagent lifecycle events.

Verified with:

```bash
pytest tests/test_streaming_events.py tests/test_tool_concurrency.py tests/test_subagent.py tests/test_message_format.py tests/test_anthropic_provider.py
python -m compileall agent
```

Not implemented yet:

- Web pending approval store and approval decision API/WebSocket.
- A dedicated Web timeline renderer.
- `phase_changed`, `step_started`, `step_finished`, `test_started`, and `test_finished` as first-class events.
- Rich timeline persistence for replay or audit.

## TUI Timeline C Plan: Lightweight Tree Blocks

This section records the current preferred TUI timeline direction.

The goal is to make each timeline item feel structured and scannable without using heavy boxes. The UI should preserve the fast Codex-like flow, but group related events into small phase blocks so users can understand hierarchy at a glance.

### Design Principles

- Use light tree structure instead of bordered cards or drawbox containers.
- Group contiguous related events into phase blocks.
- Keep task state short in the timeline; full task detail belongs in the `Ctrl+T` Task Plan panel.
- Keep low-level details visible, but subordinate to human-readable titles.
- Preserve complete diff content, and append a compact changed-files summary.
- Show running state with a small spinner or animated marker so the current step is obvious.
- Avoid keeping historical task plan blocks pinned at the top of the timeline, because users can scroll with `Tab` and the status bar already carries compressed state.

### Target Visual Prototype

```text
● Task State
  0/1 done · current
  了解当前项目结构和输入框相关实现，形成可讨论的最新方案
  Ctrl+T full plan

◇ Exploration
  explored 1 file · inspected git
  tokens 2.5k · input 2.4k · output 59

  ├─ Inspect workspace
  │  Check workspace state
  │  running ◑
  ├─ List files
  │  .
  │  21ms
  └─ Inspect workspace
     Check workspace state
     36ms

◇ Search
  1 search · inspected files
  tokens 3.7k · input 3.6k · output 124

  ├─ Search code
  │  Input|TextArea|key_up|up|history|prompt|submit|MainInput
  │  agent tests
  │  running ◓
  └─ Inspect files
     agent/tui/app.py, agent/tui/state.py
     tests/test_main_input.py, tests/test_tui_state.py
     16ms
```

### Phase Blocks

Recommended block titles:

- `Task State`: compact todo/task-memory summary.
- `Exploration`: file reads, directory listing, workspace state, git inspection.
- `Search`: grep, ripgrep, symbol lookup, code search.
- `Edit`: apply patch, write file, file update operations.
- `Verification`: tests, lint, typecheck, compile, manual validation commands.
- `Approval`: pending or resolved user approval.
- `Model`: waiting, retry, timeout, or model-side status.

Phase title markers:

- `●` for the primary current state, especially `Task State`.
- `◇` for regular grouped activity blocks.
- `├─` and `└─` for child operations.
- `│` for child details.

### Task State Rendering

The timeline should not render full task memory or full todo dumps.

Preferred compact shape:

```text
● Task State
  1/2 done · current
  结合现状给出方案
  Ctrl+T full plan
```

Full details remain available in `Ctrl+T`, including:

- goal
- checklist
- constraints
- files inspected
- decisions
- risks
- next steps

After normal task completion, todo tool calls and todo tool messages should be pruned from provider history to reduce context pollution. If the task stops unexpectedly, the last task state may remain available as recovery context.

### Tool Operation Rendering

Each operation should prefer a human title, then compact detail.

Example:

```text
├─ Search code
│  key_up|history|prompt
│  agent tests
│  34ms
```

Running example:

```text
└─ Run tests
   pytest tests/test_tui_state.py -q
   running ◓
```

The renderer should derive these titles in the TUI layer where possible, using existing structured event fields first and existing content parsing only as a fallback.

### Usage Rendering

Token usage should be a subordinate line inside the nearest relevant block instead of a standalone timeline item when possible.

Preferred shape:

```text
tokens 3.7k · input 3.6k · output 124
```

If no nearby block can own the usage event, it can remain as a compact standalone line.

### Diff Rendering

Diff output must keep the complete content.

After the full diff, append a changed-files summary:

```text
files changed
  agent/tui/renderers.py  +42 -11
  tests/test_tui_state.py +18 -4
```

This keeps review accurate while giving users a quick scan target.

### Implementation Notes

The first implementation should stay mostly in `agent/tui/renderers.py`.

Suggested approach:

- Keep `StreamEvent` and TUI state schemas unchanged unless a missing field becomes unavoidable.
- Update `_render_timeline_blocks(state)` to group contiguous events into phase blocks.
- Reuse `_activity_summary`, `_render_tool_activity`, `_tool_activity_line`, `_render_task_state_summary`, `_task_spinner`, and diff summary helpers where possible.
- Add a small phase classifier for known tool names and event types.
- Update `tests/test_tui_state.py` expectations from flat action summaries to tree-like grouped blocks.

Verification target:

```bash
pytest tests/test_tui_state.py tests/test_tui_approval.py tests/test_tui_runner.py tests/test_streaming_events.py tests/test_task_guard.py tests/test_task_state.py tests/test_tool_concurrency.py -q
```
