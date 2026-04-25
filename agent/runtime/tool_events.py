"""Formatting helpers for tool stream events."""


MAX_TOOL_RESULT_PREVIEW_CHARS = 12_000


def format_tool_description(tc) -> str:
    """Format a tool call for display."""
    tool_name = tc.name
    args = tc.args or {}
    if tool_name == "bash":
        cmd = args.get("command", "")
        cmd_preview = cmd[:40] + "..." if len(cmd) > 40 else cmd
        return f"{tool_name}: {cmd_preview}"
    if tool_name in {"read_file", "write_file", "edit_file"}:
        path = args.get("path", "")
        return f"{tool_name}: {path}"
    if tool_name == "todo":
        items = args.get("items", [])
        return f"{tool_name}: {len(items)} item(s)"
    if tool_name == "subagent":
        role = args.get("role", "")
        task = args.get("task", "")
        if role and task:
            task_preview = task[:30] + "..." if len(task) > 30 else task
            return f"{tool_name} @{role}: {task_preview}"
        return tool_name
    return tool_name


def diff_preview_from_output(output: str) -> str:
    """Extract a bounded diff preview from a tool output string."""
    marker = "\ndiff:\n"
    if marker in output:
        preview = output.split(marker, 1)[1]
    elif output.startswith("diff:\n"):
        preview = output[len("diff:\n") :]
    else:
        preview = output
    if len(preview) > MAX_TOOL_RESULT_PREVIEW_CHARS:
        return preview[:MAX_TOOL_RESULT_PREVIEW_CHARS] + (
            f"\n... diff preview truncated to {MAX_TOOL_RESULT_PREVIEW_CHARS} chars"
        )
    return preview


def tool_output_indicates_successful_write(output: str) -> bool:
    """Return whether a workspace write output looks successful."""
    return not output.startswith(
        (
            "Error:",
            "approval_required:",
            "Code workflow guard blocked",
        )
    )
