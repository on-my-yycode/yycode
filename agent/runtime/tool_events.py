"""Formatting helpers for tool stream events."""

import re


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


def format_tool_event_metadata(tc) -> dict:
    """Return timeline-friendly metadata for a tool call."""
    tool_name = tc.name
    args = tc.args or {}
    metadata = {"args": args}

    if tool_name == "read_file":
        path = args.get("path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        if start_line or end_line:
            detail = f"{path} lines {start_line or 1}-{end_line or 'end'}"
            title = "Read file range"
        else:
            detail = path
            title = "Read file"
        return {
            "title": title,
            "detail": detail,
            "phase": "exploring",
            "tool_name": tool_name,
            "file_paths": [path] if path else None,
            "metadata": metadata,
        }

    if tool_name == "read_many_files":
        paths = args.get("paths") or []
        return {
            "title": "Read files",
            "detail": ", ".join(paths[:3]) + ("..." if len(paths) > 3 else ""),
            "phase": "exploring",
            "tool_name": tool_name,
            "file_paths": paths,
            "metadata": metadata,
        }

    if tool_name == "grep":
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        return {
            "title": "Search code",
            "detail": f"Searching {path} for {pattern}",
            "phase": "exploring",
            "tool_name": tool_name,
            "file_paths": [path],
            "metadata": metadata,
        }

    if tool_name in {"list_files", "git_show", "workspace_state", "git_diff"}:
        return {
            "title": _title_for_readonly_tool(tool_name),
            "detail": _detail_for_path_args(args),
            "phase": "exploring",
            "tool_name": tool_name,
            "file_paths": _file_paths_from_args(args),
            "metadata": metadata,
        }

    if tool_name.startswith("lsp_"):
        return {
            "title": _title_for_lsp_tool(tool_name),
            "detail": _detail_for_lsp_args(args),
            "phase": "semantic_navigation",
            "tool_name": tool_name,
            "file_paths": _file_paths_from_args(args),
            "metadata": metadata,
        }

    if tool_name in {"apply_patch", "write_file", "edit_file"}:
        return {
            "title": _title_for_write_tool(tool_name),
            "detail": _detail_for_path_args(args),
            "phase": "implementing",
            "tool_name": tool_name,
            "file_paths": _file_paths_from_args(args),
            "metadata": metadata,
        }

    if tool_name == "verify":
        target = args.get("target") or args.get("command") or args.get("kind", "")
        return {
            "title": "Run verification",
            "detail": str(target),
            "phase": "verifying",
            "tool_name": tool_name,
            "metadata": metadata,
        }

    if tool_name == "todo":
        items = args.get("items") or []
        active = next((item for item in items if item.get("status") == "in_progress"), None)
        return {
            "title": "Update task plan",
            "detail": active.get("text", "") if active else f"{len(items)} item(s)",
            "phase": "planning",
            "tool_name": tool_name,
            "metadata": metadata,
        }

    if tool_name == "subagent":
        role = args.get("role", "subagent")
        task = args.get("task", "")
        return {
            "title": f"Start {role} subagent",
            "detail": task,
            "phase": "implementing" if role == "worker" else "exploring",
            "tool_name": tool_name,
            "metadata": metadata,
        }

    if tool_name == "bash":
        command = args.get("command", "")
        return {
            "title": _title_for_bash(command),
            "detail": command,
            "phase": _phase_for_bash(command),
            "tool_name": tool_name,
            "metadata": {"command": command, "args": args},
        }

    return {
        "title": f"Run {tool_name}",
        "detail": format_tool_description(tc),
        "tool_name": tool_name,
        "metadata": metadata,
    }


def file_paths_for_tool_call(tc) -> list[str]:
    """Return workspace paths referenced by a tool call when obvious."""
    return _file_paths_from_args(tc.args or {}) or []


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


def _title_for_readonly_tool(tool_name: str) -> str:
    return {
        "list_files": "List files",
        "git_show": "Read file from git",
        "workspace_state": "Check workspace state",
        "git_diff": "Review git diff",
    }.get(tool_name, f"Run {tool_name}")


def _title_for_lsp_tool(tool_name: str) -> str:
    return {
        "lsp_document_symbols": "LSP document symbols",
        "lsp_workspace_symbols": "LSP workspace symbols",
        "lsp_definition": "LSP definition",
        "lsp_references": "LSP references",
        "lsp_hover": "LSP hover",
        "lsp_diagnostics": "LSP diagnostics",
    }.get(tool_name, f"LSP {tool_name.removeprefix('lsp_').replace('_', ' ')}")


def _detail_for_lsp_args(args: dict) -> str:
    path = args.get("path")
    query = args.get("query")
    line = args.get("line")
    character = args.get("character")
    parts: list[str] = []
    if path:
        parts.append(str(path))
    if query:
        parts.append(f"query={query}")
    if line is not None and character is not None:
        parts.append(f"position={line}:{character}")
    return " · ".join(parts)


def _title_for_write_tool(tool_name: str) -> str:
    return {
        "apply_patch": "Apply patch",
        "write_file": "Create file",
        "edit_file": "Edit file",
    }.get(tool_name, f"Run {tool_name}")


def _detail_for_path_args(args: dict) -> str:
    paths = _file_paths_from_args(args)
    if paths:
        return ", ".join(paths)
    command = args.get("command")
    return str(command or "")


def _file_paths_from_args(args: dict) -> list[str]:
    paths = args.get("paths")
    if isinstance(paths, list):
        return [str(path) for path in paths]
    path = args.get("path")
    if path:
        return [str(path)]
    patch = args.get("patch")
    if patch:
        return _paths_from_unified_diff(str(patch))
    return []


def _title_for_bash(command: str) -> str:
    if _is_drawio_command(command):
        if "--version" in command:
            return "Check draw.io CLI"
        if " -x " in f" {command} " or " --export " in f" {command} ":
            return "Export draw.io diagram"
        return "Run draw.io command"
    if command.startswith(("pytest", "ruff", "mypy")):
        return "Run verification"
    if command.startswith("git status"):
        return "Check workspace state"
    if command.startswith("git diff"):
        return "Review git diff"
    if command.startswith(("sed ", "grep ", "rg ")):
        return "Inspect workspace"
    return "Run command"


def _phase_for_bash(command: str) -> str:
    if _is_drawio_command(command):
        return "verifying" if "--version" in command else "implementing"
    if command.startswith(("pytest", "ruff", "mypy")):
        return "verifying"
    return "exploring"


def _is_drawio_command(command: str) -> bool:
    return any(token in command for token in ("draw.io", "drawio"))


def _paths_from_unified_diff(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        path = None
        begin_patch_match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)$", line)
        if begin_patch_match:
            path = begin_patch_match.group(1).strip()
        elif line.startswith("*** Move to: "):
            path = line[len("*** Move to: "):].strip()
        elif line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if match:
                path = match.group(2)
        elif line.startswith("+++ "):
            raw = line[4:].split("\t", 1)[0].strip()
            if raw != "/dev/null":
                path = raw[2:] if raw.startswith("b/") else raw
        if path and path not in paths:
            paths.append(path)
    return paths
