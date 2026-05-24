# Agent Loop and opencode Comparison Notes

This note compares yycode's current agent loop with opencode's agent runtime from
the perspective of ReAct flow, system prompts, tool execution, planning, and
runtime constraints. It is intended as a discussion draft for future yycode
agent architecture work.

Sources:

- opencode repository: https://github.com/anomalyco/opencode
- opencode agents docs: https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/agents.mdx
- opencode server docs: https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/server.mdx
- opencode SDK docs: https://github.com/anomalyco/opencode/blob/dev/packages/web/src/content/docs/sdk.mdx
- yycode local implementation: `agent/session.py`, `agent/graph.py`, `agent/subagent.py`, `agent/nodes/task_guard_node.py`

## High-Level Conclusion

yycode is currently closer to a strong task-constrained ReAct agent. opencode is
closer to a multi-agent-profile coding runtime with explicit permissions,
typed tools, structured events, and server-first session orchestration.

yycode's strongest advantage is task closure. The mandatory Task State and todo
guard make it harder for the model to stop early or summarize before work is
done. This is valuable for yoyohub-style task execution where every run should
have a clear goal, state, result, and summary.

opencode's strongest advantage is runtime architecture. It separates behavior
across agent profiles, permissions, typed tool contracts, session APIs, and
event streams. This makes it better suited for multi-client IDE integration,
interrupt/replay, permission management, and long-running observable workflows.

The recommended direction is not to copy opencode wholesale. yycode should keep
the strong task execution loop for build-mode work, while adding lighter modes,
profile-based prompts, runtime permissions, and a richer event model.

## Agent Loop Shape

yycode's main loop is implemented with LangGraph:

```text
START -> llm
llm -> tools       if the model requested tool calls
llm -> task_guard  if the model did not request tools
tools -> llm       normally
tools -> END       if tool execution preserved a completed final answer
task_guard -> llm  if Task State is incomplete
task_guard -> END  if Task State is complete
```

This is a ReAct-style loop with an additional hard task guard. The model can
reason, call tools, observe results, and continue. When it tries to stop, the
runtime checks whether Task State is complete. If not, yycode injects an
ephemeral blocker message and forces another LLM turn.

Benefits:

- Strong closure for task execution.
- Clear invariant: no final answer while todo items are pending or in progress.
- Easy to reason about and debug.
- Useful for yoyohub, where task state and completion summaries matter.

Tradeoffs:

- Every request becomes a task, including simple chat, Q&A, or design discussion.
- The guard can introduce extra LLM turns and token cost.
- Behavior depends partly on model compliance with a large prompt contract.
- The same loop shape is used for different interaction types that may need
  different levels of ceremony.

opencode appears to organize execution around session/message/step lifecycle
events instead of a single mandatory todo guard. It has primary agents such as
`build` and `plan`, plus subagents such as `general`, `explore`, and `scout`.
Agent behavior is selected by profile and constrained by runtime permissions.

Benefits:

- Better fit for multiple clients such as TUI, IDE, SDK, and server API.
- Cleaner support for plan-only, build, and subagent workflows.
- More observable execution through structured events.
- Permissions and tool rules are not only prompt conventions.

Tradeoffs:

- More moving pieces.
- Harder to implement and reason about than yycode's current graph.
- Task closure may be weaker unless the chosen agent profile or runtime policy
  explicitly enforces it.

## System Prompt Philosophy

yycode currently uses a heavy default system prompt. It includes task state,
workflow, tools, editing rules, subagent boundaries, skills, safety, and final
answer rules in one place.

This gives yycode a simple mental model: one prompt defines the working style.
It is easy to inspect and edit. However, it also means the prompt carries too
many responsibilities:

- Planning policy.
- Task state contract.
- Tool usage preferences.
- Editing constraints.
- Safety rules.
- Subagent delegation policy.
- Final answer policy.

The larger and more universal the prompt becomes, the more fragile it is across
models. Some models follow detailed workflow contracts well; others may skip
steps, overuse tools, or produce premature summaries. This explains why behavior
can differ noticeably across GPT, Claude, DeepSeek, Qwen, and other providers.

opencode's design is more profile-oriented. It uses agent types and agent
configuration to split behavior by mode. For example:

- Build agent: full coding agent with broader tool access.
- Plan agent: read-only planning agent, with edit/bash actions gated by
  permission.
- Subagents: focused agents for exploration, search, or general subtasks.

The important architectural difference is that opencode does not rely on one
monolithic prompt to enforce all behavior. It combines:

- Prompt instructions.
- Agent profile configuration.
- Tool schemas.
- Runtime permissions.
- Event lifecycle.
- Session APIs.

For yycode, the useful lesson is to move from one universal prompt to profile
composition:

- Common base identity.
- Mode-specific behavior.
- Tool-specific rules.
- Permission-specific constraints.
- Output style rules.

## ReAct and Tool Execution

yycode's ReAct behavior is straightforward:

1. Convert message history to provider format.
2. Send messages, tools, and system prompt to the provider.
3. Receive assistant text and tool calls.
4. Execute tool calls.
5. Append tool messages.
6. Repeat until no tool call remains.
7. Check Task State before ending.

Subagents use a similar manual loop with a bounded max-turn count. They have
isolated history, cannot call `todo`, and cannot delegate to other subagents.
This is a good boundary because the parent agent owns planning and integration.

Areas where yycode can improve:

- Tool argument validation should become more explicit and model-facing.
- Tool failures should provide structured correction hints to the model.
- Tool output truncation should be standardized per tool.
- Tool lifecycle events should include stable IDs for run, step, call, and
  result.
- Runtime permission decisions should be first-class instead of mostly prompt
  driven.

opencode's tool design is more runtime-driven. Tools have schemas, execution
contexts, metadata, permission prompts, and structured failure behavior. Invalid
arguments can be converted into model-readable errors that ask the model to fix
the input. This reduces ambiguity and makes the loop more resilient across
models.

## Planning and Task State

yycode's mandatory todo model is strong for execution tasks:

- Every user request is represented in Task State.
- Exactly one item should be in progress while work remains.
- Final answer is blocked until all items are completed.
- Task summary memory can be produced after completion.

This is a good fit for:

- yoyohub task execution.
- Long-running implementation tasks.
- Agent work that needs progress tracking.
- Cases where the UI should show task state and completion status.

However, it is too heavy for:

- Casual questions.
- Architecture discussion.
- "Look at this and tell me what you think."
- Short commands.
- Debugging conversations where no file changes are intended.

opencode's split between plan/build agents suggests a better yycode direction:

- `chat` mode: answer or discuss without mandatory todo.
- `plan` mode: inspect and design, read-only by default.
- `build` mode: perform implementation with Task State enforced.
- `review` mode: inspect changes and report findings first.
- `subagent` mode: isolated bounded work delegated by a parent.

The key point: Task State should remain strong, but it should be attached to
execution-oriented modes instead of every interaction.

### Todo State, Client Events, and Model Context

yycode should separate three related but different concepts:

1. Runtime task state.
2. Client/UI events.
3. Model-visible context messages.

The todo tool should primarily update runtime task state. TUI, ACP, yoyohub, and
future IDE clients can render that state directly through structured snapshots
or events. This does not require periodically inserting the full todo list back
into the model context.

Recommended direction:

- Keep `TodoManager` or a future task-state service as the source of truth.
- Continue emitting TUI/ACP/yoyohub plan updates from task-state changes.
- Stop periodically injecting the full todo list into model-visible context.
- Keep `task_guard` as the final completion gate.
- Inject short model-visible reminders only at important moments:
  - the model tries to finish before Task State exists;
  - todo items are still pending or in progress at finish time;
  - code changed but verification is still required;
  - the model repeats the same incomplete todo state without real progress;
  - the user adds new instructions that need reconciliation.

In other words:

```text
todo tool call
  -> runtime task state update
  -> client event / plan update for UI
  -> no automatic model-context injection
```

Only guard or anomaly cases should produce model-visible ephemeral messages:

```text
task_guard / workflow_guard detects blocker
  -> short ephemeral HumanMessage
  -> next LLM turn sees the blocker
```

This keeps the UI observable without polluting the model context. It also makes
the distinction clear for ACP: ACP plan/status updates are client events, not
messages that should be replayed into the LLM prompt.

## Subagents

yycode already has a useful subagent model:

- `explorer`
- `architect`
- `worker`
- `tester`
- `security`

The boundaries are sensible:

- Isolated conversation history.
- Parent owns planning.
- Subagent cannot use todo.
- Subagent cannot delegate further.
- Output is summarized back to the parent.

opencode's subagent model is more configurable and user-facing. Agents can be
defined as primary agents or subagents, and subagents can be invoked explicitly
with mention-like syntax.

Potential yycode improvements:

- Make subagent definitions configurable rather than hard-coded only.
- Allow project-local custom agents.
- Add per-agent tool permissions.
- Add per-agent model and max-turn settings.
- Preserve subagent run events as first-class timeline entries.

## Permissions and Safety

yycode currently relies on a combination of prompt rules and runtime approval
callbacks. This is useful, but it is not yet a complete permission system.

opencode has a stronger permission model:

- Allow, deny, or ask rules.
- Pattern-based matching.
- Pending permission requests.
- User replies such as once, always, or reject.
- Permission events that clients can observe.

For yycode, a permission engine would help both TUI and ACP/IDE integrations.
The agent should not merely be told "avoid dangerous commands"; the runtime
should decide whether a tool call is allowed, denied, or requires approval.

Suggested permission dimensions:

- Tool name.
- File path.
- Command pattern.
- Network access.
- Write operation.
- Destructive operation.
- Workspace boundary.
- Agent mode.
- Agent role.

## Event Model and IDE Readiness

opencode's server-first architecture is a major difference. The TUI is one
client of a broader session server. This model naturally supports SDKs, external
clients, permission UIs, session events, and IDE integration.

yycode already has streaming events, ACP support, and TUI output, but the event
model should become more explicit before building a larger IDE experience.

Recommended event primitives:

- `run_started`
- `run_finished`
- `step_started`
- `step_finished`
- `text_delta`
- `reasoning_delta` when supported by provider
- `tool_call_started`
- `tool_call_delta`
- `tool_call_finished`
- `tool_result`
- `tool_error`
- `permission_requested`
- `permission_resolved`
- `task_state_changed`
- `context_compacted`
- `summary_saved`

Each event should carry stable IDs where possible:

- session id
- run id
- message id
- step id
- tool call id
- parent run id for subagents

This would let TUI, ACP, yoyohub, and a future IDE consume the same runtime
facts instead of each layer inferring behavior from text.

## Recommended yycode Direction

The best path is evolutionary:

1. Keep the current strong build loop.
2. Add agent modes.
3. Split the prompt into reusable profile fragments.
4. Add a runtime permission engine.
5. Standardize tool schema validation and model-facing tool errors.
6. Promote events to a first-class run model.
7. Make subagents configurable.

## Suggested Milestones

### Milestone 1: Agent Modes

Add a small mode layer above the current session:

- `chat`: no mandatory todo.
- `plan`: read-only, no writes by default.
- `build`: current Task State guard remains enabled.
- `review`: code-review style output, findings first.

This would immediately reduce unnecessary todo overhead while preserving the
current reliable execution behavior for real tasks.

### Milestone 2: Prompt Profiles

Move the default prompt into composable pieces:

- base identity
- workflow contract
- task-state contract
- editing rules
- safety rules
- subagent rules
- final-answer rules
- mode-specific rules

Then each agent mode can assemble the prompt it needs.

### Milestone 3: Permission Engine

Introduce runtime permission decisions:

```text
tool call -> permission policy -> allow | ask | deny -> execute or return error
```

This should apply consistently across TUI, ACP, yoyohub, and future IDE clients.

### Milestone 4: Structured Run Events

Create a stable event schema for all agent runs. The TUI and ACP should render
from this event stream rather than relying on provider-specific text behavior.

### Milestone 5: Configurable Agents

Support project or user configuration for agents:

- name
- description
- mode
- prompt additions
- allowed tools
- denied tools
- model
- temperature
- max turns

This would bring yycode closer to opencode's flexibility while keeping yycode's
task-state discipline where it matters.

## Product-Level Implication

For yoyohub, the merge manager and task manager should probably connect to the
same future run/event/task model:

- build-mode runs produce task state and artifacts;
- plan-mode runs produce proposals;
- review-mode runs produce findings;
- permission events are surfaced to the user;
- subagent runs are visible as nested timeline entries;
- final summaries are generated from structured run state, not scraped from
  assistant text.

This keeps yycode suitable for both interactive coding and managed agent task
execution.
