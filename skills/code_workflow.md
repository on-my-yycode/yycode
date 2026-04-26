---
name: code_workflow
description: "Universal code development workflow for ANY project: confirm requirements with the user → save the confirmed plan as a document → coordinate subagents by role → implement → verify → evaluate against requirements. Follow this for ALL coding tasks."
---

# Code Workflow Skill

## Universal Workflow for Any Coding Task

Follow this exact process for ANY code development/modification task, in ANY project:

---

## Hard Gates

Do not skip these gates:

1. **Confirm requirements with the user before implementation.**
   - You may inspect workspace state and read relevant files first if needed to ask better questions.
   - Do not edit files or run implementation commands before the user confirms the requirements and approach.

2. **Save the confirmed plan as a document before implementation.**
   - After the user confirms, write the agreed plan to a markdown document.
   - Prefer `docs/` when it exists. Suggested path:
     `docs/confirmed_plan_<short_task_name>.md`
   - The document must include: user goal, confirmed requirements, scope, non-goals, affected files/areas, subagent assignments, implementation plan, verification plan, risks, and approval timestamp/context.

3. **Use subagents by role for non-trivial work.**
   - `explorer`: investigates code and evidence.
   - `architect`: designs the approach and tradeoffs.
   - `worker`: implements scoped changes.
   - `tester`: verifies behavior and test coverage.
   - `security`: reviews security-sensitive or risky changes.

4. **Task State is mandatory.**
   - Every user request must be represented with `todo`.
   - Keep exactly one item `in_progress` while work remains.
   - Do not finish until all todo items are completed.

---

## Phase 1: Requirements Analysis & Workspace Exploration

**Always start here - no exceptions!**

### 1.1 Understand User Requirements
- Carefully read and analyze the user's request
- Identify the core problem to solve
- Clarify ambiguous requirements
- Define clear success criteria
- Note all constraints and edge cases
- Prepare a concise confirmation proposal for the user

### 1.2 Check Workspace State
```
Call workspace_state()
→ Understand current branch and uncommitted changes
→ Confirm we're in the correct directory
→ Avoid overwriting user's existing work
```

### 1.3 Check Git Diff
```
Call git_diff()
→ See what the user has already changed
→ Understand current context
→ Do NOT overwrite or conflict with user changes
```

### 1.4 Explore the Codebase
- Use `list_files` to understand project structure
- Use `grep` to search for relevant code patterns
- Use `read_file` to examine key files
- Use `read_many_files` for multiple related files
- Prefer these built-in navigation tools over `bash` for normal code search and file reading
- Use `subagent` with `role="explorer"` for large/complex codebases
- Use `list_skills` + `load_skill` for project-specific or domain-specific guidance

### 1.5 Confirm Requirements With User
Before implementation, send the user a short confirmation message:

```text
I will implement the following confirmed scope:
- Goal: ...
- Requirements: ...
- Non-goals: ...
- Proposed approach: ...
- Verification: ...
- Subagent roles: ...

Please confirm before I proceed.
```

Rules:
- If the user has not confirmed, do not implement.
- If the user changes scope, update the confirmation and ask again.
- If the task is tiny and already fully specified, still provide a brief confirmation and wait.

---

## Phase 2: Confirmed Plan Document & Technical Planning

### 2.1 Create Task State
Every user request must be represented in Task State with the `todo` tool before the task can finish. For simple work, create a single item. For larger work, create a short, concrete plan:
```
Call todo(items=[
  {"id": "1", "text": "Analyze requirements and explore codebase", "status": "in_progress"},
  {"id": "2", "text": "Confirm requirements and save confirmed plan document", "status": "pending"},
  {"id": "3", "text": "Create technical design", "status": "pending"},
  {"id": "4", "text": "Implement the solution", "status": "pending"},
  {"id": "5", "text": "Run tests and verification", "status": "pending"},
  {"id": "6", "text": "Evaluate results against requirements", "status": "pending"}
], memory={
  "user_goal": "[one sentence goal]",
  "constraints": ["[important constraints]"],
  "next_steps": ["Analyze requirements and explore codebase"]
})
```

Task State rules:
- Keep exactly one item `in_progress` while work remains.
- Keep compact memory current: goal, constraints, inspected/modified files, decisions, test results, risks, and next steps.
- Do not provide a final answer until all items are `completed`.

### 2.2 Save Confirmed Plan Document
After the user confirms the requirement and approach, save the plan:

```
Call write_file(
  path="docs/confirmed_plan_<short_task_name>.md",
  content="[confirmed plan markdown]"
)
```

The document must include:

- Title
- User goal
- Confirmed requirements
- Scope
- Non-goals
- Affected files or areas
- Subagent assignments
- Implementation plan
- Verification plan
- Security/risk considerations
- Confirmation note, including the fact that the user confirmed the plan

If `docs/` does not exist, either create it or use a clearly named root-level markdown file such as `confirmed_plan_<short_task_name>.md`.

### 2.3 Use Architect Subagent
For non-trivial features or when design guidance is needed:
```
Call subagent(
  role="architect",
  task="Design the technical solution for: [describe requirements in detail]",
  context="[provide relevant files, existing code, and constraints]"
)
```

### 2.4 Refine & Update Todo
```
Call todo(items=[... update statuses and add detailed implementation steps ...])
```

---

## Phase 2.5: Subagent Coordination

For non-trivial tasks, assign focused subagent work before or during implementation:

### Explorer
Use for evidence and codebase understanding:

```
Call subagent(
  role="explorer",
  task="Investigate the relevant code paths, files, existing behavior, and constraints for: [confirmed task]",
  context="[user-confirmed plan, workspace findings]"
)
```

### Architect
Use for design:

```
Call subagent(
  role="architect",
  task="Design a minimal, safe technical approach for: [confirmed task]",
  context="[explorer findings, confirmed plan]"
)
```

### Worker
Use for implementation:

```
Call subagent(
  role="worker",
  task="Implement only the scoped changes from the confirmed plan.",
  context="[confirmed plan document path, architect design, relevant files]"
)
```

### Tester
Use for verification:

```
Call subagent(
  role="tester",
  task="Verify the implementation against the confirmed requirements and report test coverage, failures, and residual risks.",
  context="[confirmed plan, changed files, worker summary]"
)
```

### Security
Use when changes affect inputs, auth, permissions, file access, shell commands, networking, secrets, or dependency behavior:

```
Call subagent(
  role="security",
  task="Review the implementation for security risks and concrete mitigations.",
  context="[confirmed plan, changed files, diff summary]"
)
```

Rules:
- Subagents must receive focused, bounded tasks.
- Do not ask subagents to make broad unrelated changes.
- Prefer a single `worker` for implementation by default.
- Only use multiple `worker` subagents when the implementation spans many files and the write scope can be split cleanly.
- Never assign multiple `worker` subagents to edit the same file.
- When using multiple `worker` subagents, give each one an explicit file ownership boundary and a disjoint write set.
- Integrate subagent results yourself and update Task State memory.
- For simple one-file tasks, subagents may be skipped only after the user-confirmed plan document is saved.

---

## Phase 3: Implementation

Implementation may start only after:
- The user has confirmed the requirements and approach.
- The confirmed plan document has been saved.
- Task State reflects the confirmed plan.

### 3.1 Choose the Right Tools
- **`apply_patch`**: Preferred for ALL existing-file edits. Patch only the minimal changed block; never pass the whole file for a small edit.
- **`write_file`**: Only for brand new files or generated artifacts
- **`edit_file`**: Avoid for normal code edits; use apply_patch instead
- **`bash`**: For running necessary commands (use carefully, avoid destructive operations)
- Use `bash` only when built-in tools cannot express the needed inspection or command

### 3.2 Use Worker Subagent When Appropriate
For well-defined implementation tasks:
```
Call subagent(
  role="worker",
  task="Implement [specific feature/fix in detail]",
  context="[provide design, relevant files, and requirements]"
)
```

Worker assignment rules:
- Default to one `worker` for the whole implementation whenever possible.
- Split implementation across multiple `worker` subagents only when there are many files and the work can be partitioned safely.
- Do not let multiple `worker` subagents operate on the same file.
- If you split work, state each worker's owned files or modules clearly in the task context.

### 3.3 Track Progress
Update todo items as you complete each part:
```
Call todo(items=[... update statuses, mark items as completed/in_progress ...])
```
Also update `memory` with inspected files, modified files, decisions, test results, open risks, and next steps.

---

## Phase 4: Verification & Testing

**DO NOT SKIP THIS STEP - ALWAYS VERIFY YOUR CHANGES!**

### 4.1 Run Tests
```
Call verify(kind="tests", target="specific_test_file.py")
→ Start narrow with specific tests related to your changes
→ Then run broader test suites if everything passes
```

### 4.2 (Optional) Use Tester Subagent
For non-trivial changes, use tester subagent:
```
Call subagent(
  role="tester",
  task="Thoroughly test the implementation, including edge cases",
  context="[provide changes made and requirements]"
)
```

### 4.3 Additional Verification (if project is configured)
- `verify(kind="lint")` - Code style and lint checks
- `verify(kind="typecheck")` - Type checking
- `verify(kind="all")` - Full verification suite

### 4.4 (Optional) Security Review
For security-sensitive or risk-bearing changes:
```
Call subagent(
  role="security",
  task="Review the code for potential security issues",
  context="[provide changes made]"
)
```

---

## Phase 5: Result Evaluation (Critical Final Step)

**ALWAYS COMPLETE THIS STEP BEFORE FINISHING!**

### 5.1 Review Your Changes
- Use `git_diff()` to see exactly what was modified
- Verify all changes are necessary and relevant to the requirements
- Ensure no unintended changes were made
- Check that the code follows project conventions

### 5.2 Evaluate Against Requirements
Go through EACH requirement and verify:

1. **Functional Completeness**
   - ✓ Does it implement ALL requested features?
   - ✓ Are all edge cases handled properly?
   - ✓ Does it handle errors gracefully?
   - ✓ Is the functionality correct?

2. **Code Quality**
   - ✓ Is the code clean and maintainable?
   - ✓ Are there appropriate comments/documentation?
   - ✓ Does it follow project coding conventions?
   - ✓ Is the implementation efficient?

3. **Verification Status**
   - ✓ Do ALL tests pass?
   - ✓ Are there no lint or type errors?
   - ✓ Was the solution verified thoroughly?

4. **User Experience**
   - ✓ Is the solution intuitive to use?
   - ✓ Does it solve the user's actual problem?
   - ✓ Is the solution robust?

### 5.3 Provide Summary Report
Before the final answer, call `todo` with every item marked `completed`. Only then give the user a clear, concise summary:
- What was implemented/changed
- What verification was performed
- Any remaining concerns, tradeoffs, or follow-up considerations
- How to use the new feature/fix (if applicable)

---

## Summary: Full Universal Workflow Loop

```
1. workspace_state/git_diff → Understand current workspace state
2. list_files/grep/read_file/read_many_files → Explore and understand codebase
3. subagent(explorer) when useful → Deep codebase exploration
4. Confirm requirements and approach with the user → Mandatory gate
5. todo → Create/align Task State
6. write_file → Save confirmed plan document
7. subagent(architect) → Technical design for non-trivial work
8. subagent(worker) or apply_patch/write_file → Implement scoped changes
9. todo → Track progress and decisions
10. verify + subagent(tester) → Test and verify
11. subagent(security) when relevant → Security review
12. git_diff → Review all changes
13. Evaluate against confirmed requirements → Check completeness and quality
14. todo completed → Final report
```

---

## Complete Tool Reference

| Tool | Purpose | Best Used For |
|------|---------|---------------|
| `workspace_state` | Check git status and current branch | Always start here |
| `git_diff` | View current changes in workspace | Before and after making changes |
| `list_files` | List directory contents | Understanding project structure |
| `grep` | Search code for patterns | Finding functions, classes, references |
| `read_file` | Read a single file | Examining specific code |
| `read_many_files` | Read multiple files at once | Understanding related code |
| `git_show` | Show git history for a file | Understanding why code changed |
| `apply_patch` | Safely apply a minimal diff | PREFERRED for existing-file edits |
| `write_file` | Write content to a file | New files or generated artifacts |
| `edit_file` | Blocked fallback | Avoid; use apply_patch |
| `bash` | Run shell commands | Setup, scripts, or project-specific commands |
| `verify` | Run tests, lint, or type checks | Verification (critical!) |
| `todo` | Track and manage tasks | Multi-step projects |
| `list_skills` | See available skills | Finding project-specific guidance |
| `load_skill` | Load a specific skill | Using specialized guidance |
| `subagent(explorer)` | Explore codebase | Large/complex projects |
| `subagent(architect)` | Create technical design | Complex features |
| `subagent(worker)` | Implement features | Well-defined implementation tasks |
| `subagent(tester)` | Test thoroughly | Comprehensive testing |
| `subagent(security)` | Security review | Security-sensitive code |
