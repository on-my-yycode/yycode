"""Model-facing compaction for verbose tool outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.runtime.tool_events import file_paths_for_tool_call


MAX_MODEL_TOOL_OUTPUT_CHARS = 4_000
MAX_MODEL_DIFF_LINES = 80
MAX_MODEL_COMMAND_OUTPUT_CHARS = 3_000


@dataclass(frozen=True)
class ToolOutputView:
    """Separate output shown to users from output persisted into model messages."""

    display: str
    model: str
    context_policy: str = "full"


def build_tool_output_view(tool_name: str, raw_output: str, tc) -> ToolOutputView:
    """Return display and model-facing representations for one tool result."""
    display = raw_output or ""
    if tool_name == "git_diff":
        return ToolOutputView(
            display=display,
            model=_compact_diff_output(display, "git_diff"),
            context_policy="compact",
        )
    if tool_name in {"apply_patch", "write_file"}:
        return ToolOutputView(
            display=display,
            model=_compact_write_output(tool_name, display, tc),
            context_policy="compact",
        )
    if tool_name in {"bash", "verify"}:
        return _command_output_view(tool_name, display)
    if len(display) > MAX_MODEL_TOOL_OUTPUT_CHARS:
        return ToolOutputView(
            display=display,
            model=_truncate_with_notice(display, MAX_MODEL_TOOL_OUTPUT_CHARS),
            context_policy="compact",
        )
    return ToolOutputView(display=display, model=display)


def compact_preflight_output(output: str) -> str:
    """Return a compact preflight block for model context."""
    changed_files = _changed_files_from_workspace_state(output)
    diff_files = _changed_files_from_diff(output)
    files = _unique([*changed_files, *diff_files])
    lines = [
        "Code workflow guard blocked this write because workspace preflight had not been reviewed yet.",
        "",
        "Preflight summary:",
        f"- changed_files: {len(files)}" if files else "- changed_files: unknown",
    ]
    lines.extend(f"  - {path}" for path in files[:20])
    if len(files) > 20:
        lines.append(f"  ... {len(files) - 20} more file(s)")
    lines.extend(
        [
            "",
            "Review workspace_state/git_diff results, then retry the write with the smallest safe patch.",
            "Verbose preflight output was omitted from model context to avoid carrying large diffs forward.",
        ]
    )
    return "\n".join(lines)


def _command_output_view(tool_name: str, output: str) -> ToolOutputView:
    if _is_success_empty_command_output(output):
        return ToolOutputView(
            display=output,
            model=(
                "[Tool output omitted from model context; command completed successfully "
                "with empty stdout/stderr. Full result was shown in the UI.]"
            ),
            context_policy="marker",
        )
    if len(output) > MAX_MODEL_COMMAND_OUTPUT_CHARS:
        return ToolOutputView(
            display=output,
            model=_compact_command_output(tool_name, output),
            context_policy="compact",
        )
    return ToolOutputView(display=output, model=output)


def _compact_write_output(tool_name: str, output: str, tc) -> str:
    if output.startswith(("Error:", "approval_required:", "Code workflow guard blocked")):
        return _truncate_with_notice(output, MAX_MODEL_TOOL_OUTPUT_CHARS)
    paths = file_paths_for_tool_call(tc)
    diff = _extract_diff(output)
    stat = _extract_diff_stat(output)
    lines = [f"{tool_name} completed."]
    if paths:
        lines.append("files:")
        lines.extend(f"- {path}" for path in paths[:20])
        if len(paths) > 20:
            lines.append(f"- ... {len(paths) - 20} more file(s)")
    if stat:
        lines.extend(["", "diff_stat:", stat])
    if diff:
        lines.extend(["", _compact_diff_output(diff, "diff preview")])
    else:
        lines.extend(["", _truncate_with_notice(output, MAX_MODEL_TOOL_OUTPUT_CHARS)])
    return "\n".join(lines)


def _compact_diff_output(diff: str, label: str) -> str:
    if not diff.strip() or diff.strip() == "No diff.":
        return "No diff."
    files = _changed_files_from_diff(diff)
    added = removed = 0
    kept_lines: list[str] = []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
        if len(kept_lines) < MAX_MODEL_DIFF_LINES:
            kept_lines.append(line)
    lines = [
        f"{label} summary:",
        f"- files_changed: {len(files)}",
        f"- added_lines: {added}",
        f"- removed_lines: {removed}",
    ]
    if files:
        lines.append("- files:")
        lines.extend(f"  - {path}" for path in files[:20])
        if len(files) > 20:
            lines.append(f"  ... {len(files) - 20} more file(s)")
    lines.extend(["", f"first_{MAX_MODEL_DIFF_LINES}_diff_lines:", *kept_lines])
    if len(diff.splitlines()) > MAX_MODEL_DIFF_LINES:
        lines.append(
            f"... diff truncated for model context; full output was streamed to the UI "
            f"or can be requested again with git_diff."
        )
    return "\n".join(lines)


def _compact_command_output(tool_name: str, output: str) -> str:
    if len(output) <= MAX_MODEL_COMMAND_OUTPUT_CHARS:
        return output
    head = output[:1200].rstrip()
    tail = output[-1200:].lstrip()
    omitted = len(output) - len(head) - len(tail)
    return (
        f"{tool_name} output was truncated for model context.\n"
        f"original_chars: {len(output)}\n"
        f"omitted_chars: {max(omitted, 0)}\n\n"
        f"head:\n{head}\n\n"
        f"tail:\n{tail}"
    )


def _is_success_empty_command_output(output: str) -> bool:
    normalized = output.replace("\r\n", "\n")
    return (
        "status: success" in normalized
        and "exit_code: 0" in normalized
        and "stdout:\n(empty)" in normalized
        and "stderr:\n(empty)" in normalized
    )


def _truncate_with_notice(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return (
        text[:limit].rstrip()
        + f"\n... output truncated for model context from {len(text)} to {limit} chars"
    )


def _extract_diff(output: str) -> str:
    marker = "\ndiff:\n"
    if marker in output:
        return output.split(marker, 1)[1]
    if output.startswith("diff:\n"):
        return output[len("diff:\n") :]
    if output.startswith("diff --git ") or output.startswith("--- "):
        return output
    return ""


def _extract_diff_stat(output: str) -> str:
    marker = "\ndiff_stat:\n"
    if marker not in output:
        return ""
    tail = output.split(marker, 1)[1]
    if "\ndiff:\n" in tail:
        tail = tail.split("\ndiff:\n", 1)[0]
    return tail.strip()


def _changed_files_from_diff(diff: str) -> list[str]:
    paths: list[str] = []
    for line in diff.splitlines():
        path = None
        if line.startswith("diff --git "):
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


def _changed_files_from_workspace_state(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("branch:", "changed_files:", "status:")):
            continue
        if stripped[:2] in {"M ", "A ", "D ", "??"}:
            path = stripped[2:].strip()
            if path:
                paths.append(path)
    return paths


def _unique(items: list[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        if item and item not in values:
            values.append(item)
    return values
