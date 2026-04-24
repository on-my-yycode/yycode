---
name: code_workflow
description: "Complete code modification workflow: understand code → safe edit → verify → iterate. Follow this process for all non-trivial code changes."
---

# Code Workflow Skill

## Mandatory Workflow for Code Changes

Follow this exact process for all non-trivial code tasks:

---

## Phase 1: Understand the Code & Workspace

**Always start here before writing any code!**

### 1.1 Check Workspace State
```
Call workspace_state()
→ Understand current branch and uncommitted changes
```

### 1.2 Check Git Diff (if needed)
```
Call git_diff()
→ See what the user has already changed
→ Don't overwrite user's work!
```

### 1.3 Explore the Codebase
- Use `grep` to find relevant code
- Use `read_file` to examine key files
- Use `list_skills` + `load_skill` if there are relevant skills
- Consider using `subagent` with `role="explorer"` for large codebases

---

## Phase 2: Plan the Work (for multi-step tasks)

For anything beyond a single simple edit:
```
Call todo(items=[
  {"id": "1", "text": "Understand code and requirements", "status": "in_progress"},
  {"id": "2", "text": "Make code changes", "status": "pending"},
  {"id": "3", "text": "Run tests/verification", "status": "pending"}
])
```
Update todo items as you progress.

---

## Phase 3: Make Changes Safely

### Prefer apply_patch!
Use `apply_patch` as the primary way to edit code:
- It's safer (atomic, validates before applying)
- Works for multi-file changes
- Provides clear diff summary

### When to use other tools:
- `write_file`: Only for brand new files or complete rewrites
- `edit_file`: Only for small, exact replacements

---

## Phase 4: Verify! (Critical Step)

**Always verify after making changes!**

```
Call verify(kind="tests", target="relevant_test_file.py")
→ Start narrow, then broader if needed
```

Then optionally:
- `verify(kind="lint")` - if configured
- `verify(kind="typecheck")` - if configured
- `verify(kind="all")` - for final check

---

## Phase 5: Iterate if Needed

If verification fails:
1. Read and understand the failure output
2. Make necessary fixes
3. Re-verify
4. Repeat until passing

---

## Summary: The Complete Loop

```
1. workspace_state/git_diff → Understand current state
2. grep/read_file → Understand code
3. todo → Plan (if multi-step)
4. apply_patch → Make changes
5. verify → Validate
6. Iterate → Fix if needed
```
