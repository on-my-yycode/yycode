---
name: code_workflow
description: "Universal code development workflow for ANY project: understand requirements → explore codebase → plan → implement → verify → evaluate against requirements. Follow this for ALL coding tasks."
---

# Code Workflow Skill

## Universal Workflow for Any Coding Task

Follow this exact process for ANY code development/modification task, in ANY project:

---

## Phase 1: Requirements Analysis & Workspace Exploration

**Always start here - no exceptions!**

### 1.1 Understand User Requirements
- Carefully read and analyze the user's request
- Identify the core problem to solve
- Clarify any ambiguous requirements (ask user if needed!)
- Define clear success criteria
- Note all constraints and edge cases

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
- Use `subagent` with `role="explorer"` for large/complex codebases
- Use `list_skills` + `load_skill` for project-specific or domain-specific guidance

---

## Phase 2: Technical Planning

### 2.1 Create Task State
Every user request must be represented in Task State with the `todo` tool before the task can finish. For simple work, create a single item. For larger work, create a short, concrete plan:
```
Call todo(items=[
  {"id": "1", "text": "Analyze requirements and explore codebase", "status": "in_progress"},
  {"id": "2", "text": "Create technical design", "status": "pending"},
  {"id": "3", "text": "Implement the solution", "status": "pending"},
  {"id": "4", "text": "Run tests and verification", "status": "pending"},
  {"id": "5", "text": "Evaluate results against requirements", "status": "pending"}
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

### 2.2 (Optional) Use Architect Subagent
For complex features or when design guidance is needed:
```
Call subagent(
  role="architect",
  task="Design the technical solution for: [describe requirements in detail]",
  context="[provide relevant files, existing code, and constraints]"
)
```

### 2.3 Refine & Update Todo
```
Call todo(items=[... update statuses and add detailed implementation steps ...])
```

---

## Phase 3: Implementation

### 3.1 Choose the Right Tools
- **`apply_patch`**: Preferred for ALL existing-file edits. Patch only the minimal changed block; never pass the whole file for a small edit.
- **`write_file`**: Only for brand new files or generated artifacts
- **`edit_file`**: Avoid for normal code edits; use apply_patch instead
- **`bash`**: For running necessary commands (use carefully, avoid destructive operations)

### 3.2 (Optional) Use Worker Subagent
For well-defined implementation tasks:
```
Call subagent(
  role="worker",
  task="Implement [specific feature/fix in detail]",
  context="[provide design, relevant files, and requirements]"
)
```

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
For comprehensive testing:
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
For security-sensitive changes:
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
3. (Optional) subagent(explorer) → Deep codebase exploration
4. todo → Create clear plan
5. (Optional) subagent(architect) → Technical design
6. apply_patch/write_file/edit_file → Implement changes
7. todo → Track progress
8. verify → Test and verify
9. (Optional) subagent(tester/security) → Deep testing or security review
10. git_diff → Review all changes
11. Evaluate against requirements → Check completeness and quality
12. Provide summary to user → Final report
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
