"""Formatting helpers for TUI widgets."""

from __future__ import annotations

import time

from .state import MAX_TIMELINE_ITEMS, PendingApproval, SubagentStatus, TimelineItem, TuiState


import re


PROGRESS_TRACK_WIDTH = 18
PROGRESS_PULSE_WIDTH = 6
PROGRESS_COLORS = (
    "#3b82f6",
    "#06b6d4",
    "#22d3ee",
    "#8b5cf6",
    "#c084fc",
    "#f472b6",
    "#fb7185",
    "#f97316",
    "#facc15",
)


def _safe_text(value: object, limit: int | None = None) -> str:
    """Return dynamic content escaped for Textual/Rich markup."""
    text = str(value)
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text.replace("[", r"\[")


def _safe_repr(value: object, limit: int = 160) -> str:
    """Return a bounded repr escaped for Textual/Rich markup."""
    text = repr(value).replace("\n", "\\n")
    if len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text.replace("[", r"\[")


def _format_duration(ms: int) -> str:
    """Format milliseconds to human readable duration."""
    if ms <= 0:
        return "0s"
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m{secs}s"


def _format_tokens(num: int) -> str:
    """Format token count with k/m units."""
    if num < 1000:
        return f"{num}"
    if num < 1_000_000:
        return _format_compact_number(num / 1000, "k")
    return _format_compact_number(num / 1_000_000, "m")


def _format_compact_number(value: float, suffix: str) -> str:
    """Format a compact number and trim a trailing .0."""
    formatted = f"{value:.1f}"
    if formatted.endswith(".0"):
        formatted = formatted[:-2]
    return f"{formatted}{suffix}"


def _usage_total(usage: dict[str, int] | None) -> int:
    """Return the total token count for a usage payload."""
    return int((usage or {}).get("total_tokens", 0) or 0)


def _render_progress_pulse(frame: int) -> str:
    """Render a compact colorful progress pulse."""
    scan_width = min(PROGRESS_PULSE_WIDTH, PROGRESS_TRACK_WIDTH)
    travel = max(1, PROGRESS_TRACK_WIDTH - scan_width)
    cycle = travel * 2
    normalized = frame % cycle
    position = normalized if normalized <= travel else cycle - normalized
    cells = [f"[#2b3038]·[/]" for _ in range(PROGRESS_TRACK_WIDTH)]
    color_offset = frame % len(PROGRESS_COLORS)
    for index in range(scan_width):
        cell = position + index
        color = PROGRESS_COLORS[(color_offset + index) % len(PROGRESS_COLORS)]
        style = "bold " if index >= scan_width - 2 else ""
        cells[cell] = f"[{style}{color}]━[/]"
    return "".join(cells)


def colorize_diff_for_tui(diff: str) -> str:
    """Return a diff with Rich markup colors for TUI display."""
    lines = []
    in_diff = False
    for line in diff.splitlines():
        # 检测 diff 开始
        if not in_diff and (line.startswith("diff --git") or line.startswith("--- ") or line.startswith("@@")):
            in_diff = True

        if in_diff:
            if line.startswith("@@"):
                lines.append(f"[bold cyan]{_safe_text(line)}[/]")
            elif line.startswith("diff --git") or line.startswith("index "):
                lines.append(f"[dim]{_safe_text(line)}[/]")
            elif line.startswith("+++") or line.startswith("---"):
                lines.append(f"[dim]{_safe_text(line)}[/]")
            elif line.startswith("+"):
                lines.append(f"[bold green]{_safe_text(line)}[/]")
            elif line.startswith("-"):
                lines.append(f"[bold red]{_safe_text(line)}[/]")
            else:
                lines.append(_safe_text(line))
        else:
            # diff 之前的普通文本
            lines.append(_safe_text(line))
    if diff.endswith("\n"):
        return "\n".join(lines) + "\n"
    return "\n".join(lines)


def _visible_len(text: str) -> int:
    """Return visible character count, stripping Rich markup tags."""
    return len(re.sub(r"(?<!\\)\[/?[^]]*\]", "", text))


def _plain_truncate(text: str, limit: int) -> str:
    """Truncate plain text to a visible character limit."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return "." * limit
    return text[: limit - 3] + "..."


def _pad_line(left: str, right: str, width: int, border: str) -> str:
    """Build one bordered line: left content, pad to width, right border."""
    visible = _visible_len(left + right)
    return f"{left}{right}{' ' * max(0, width - visible)}{border}"


def _two_column_line(left: str, right: str, left_width: int, right_width: int) -> str:
    """Build a simple two-column line without box borders."""
    left_visible = _visible_len(left)
    left_pad = " " * max(1, left_width - left_visible)
    return f"{left}{left_pad}  {right}"


def _join_status_parts(parts: list[str]) -> str:
    """Join status bar parts with a consistent compact separator."""
    return "  ".join(part for part in parts if part)


def _parts_visible_len(parts: list[str]) -> int:
    """Return visible length for status parts including separators."""
    if not parts:
        return 0
    return sum(_visible_len(part) for part in parts) + (len(parts) - 1) * 2


def render_brand_text(state: TuiState | None = None, width: int = 100) -> str:
    """Render the compact app brand block."""
    W = max(72, min(width, 180))
    brand_line = (
        "[bold #c9a6ff]YOYOAGENT[/] "
        "[#7f8794]code assistant[/] "
        "[#3f4652]" + ("─" * max(4, W - 29)) + "[/]"
    )
    if state is None:
        return brand_line
    workspace_text = _safe_text(state.workspace_path if state.workspace_path else "(not set)", max(12, W - 6))
    return "\n".join(
        [
            brand_line,
            f"[#7f8794]Dir[/] [#cfd3dc]{workspace_text}[/]",
        ]
    )


def render_status_bar_text(
    state: TuiState,
    width: int = 100,
    *,
    progress_frame: int = 0,
) -> str:
    """Render session and task status for the input-adjacent status bar."""
    W = max(72, min(width, 180))

    model_text = _safe_text(state.model_name if state.session_id else "(initializing)", 24)
    usage = {}
    if state.active_task and state.active_task.get("is_running"):
        usage = state.active_task.get("usage", {}) or {}
    if _usage_total(usage) <= 0 and getattr(state, "last_task", None):
        usage = state.last_task.get("usage", {}) or {}
    if _usage_total(usage) <= 0:
        usage = state.latest_usage or {}
    total = usage.get("total_tokens", 0)
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    window_size = int(getattr(state, "context_window_tokens", 0) or 0)
    used_context = int((state.latest_usage or {}).get("total_tokens", 0) or 0)
    if window_size > 0:
        percentage = min(int((used_context / window_size) * 100), 100)
        context_info = f"{_format_tokens(used_context)}/{_format_tokens(window_size)} {percentage}%"
    else:
        context_info = f"{_format_tokens(used_context)}/- 0%"

    status_text = "[#8fd6a3]⏺ Ready[/]"
    elapsed_label = "Last run"
    elapsed_text = "0s"
    if getattr(state, "last_task", None) and state.last_task.get("elapsed_ms") is not None:
        elapsed_text = _format_duration(int(state.last_task["elapsed_ms"]))
    goal_text = ""
    if state.active_task and state.active_task['is_running']:
        task = state.active_task
        elapsed_ms = 0
        if task.get('start_time_ms'):
            elapsed_ms = int(time.time() * 1000) - int(task['start_time_ms'])
        status_text = "[#d7ba7d]⏺ Task running[/]"
        status_text = f"{status_text}  {_render_progress_pulse(progress_frame)}"
        elapsed_label = "Elapsed"
        elapsed_text = _format_duration(elapsed_ms)
        goal_text = _safe_text(task.get("intent") or "", max(12, W - 9))

    model_part = f"[#7f8794]Model[/] [#cfd3dc]{model_text}[/]"
    context_part = f"[#7f8794]Context[/] [#cfd3dc]{context_info}[/]"
    status_part = f"[#7f8794]Status[/] {status_text}"
    elapsed_part = f"[#7f8794]{elapsed_label}[/] [#cfd3dc]{elapsed_text}[/]"
    tokens_part = (
        f"[#7f8794]Tokens[/] [#cfd3dc]{_format_tokens(total)}[/] "
        f"[#7f8794](input[/] [#cfd3dc]{_format_tokens(input_tokens)}[/][#7f8794], "
        f"output[/] [#cfd3dc]{_format_tokens(output_tokens)}[/][#7f8794])[/]"
    )
    todo_items = getattr(state.todo_manager, "todo_items", []) if state.todo_manager else []
    todo_reserve = 28 if todo_items else 8

    parts = [status_part, elapsed_part, tokens_part]
    for optional in (context_part, model_part):
        if _parts_visible_len([optional, *parts]) + 2 + todo_reserve <= W:
            parts.insert(0, optional)

    todo_width = max(8, W - _parts_visible_len(parts) - 2)
    todo_summary = _render_todo_header_summary(state.todo_manager, todo_width)
    if not todo_summary:
        todo_summary = "[#7f8794]Todo[/] [#cfd3dc]-[/]"
    parts.insert(1 if parts and parts[0] == status_part else len(parts), todo_summary)

    while _parts_visible_len(parts) > W and len(parts) > 3:
        for candidate in (context_part, model_part, elapsed_part):
            if candidate in parts:
                parts.remove(candidate)
                break
        todo_index = parts.index(todo_summary)
        todo_width = max(8, W - _parts_visible_len([part for part in parts if part != todo_summary]) - 2)
        todo_summary = _render_todo_header_summary(state.todo_manager, todo_width) or "[#7f8794]Todo[/] [#cfd3dc]-[/]"
        parts[todo_index] = todo_summary

    if goal_text:
        goal_width = max(8, W - _parts_visible_len(parts) - 8)
        goal_part = f"[#7f8794]Goal[/] [#cfd3dc]{_safe_text(goal_text, goal_width)}[/]"
        if _parts_visible_len([*parts, goal_part]) <= W:
            parts.append(goal_part)
    return _join_status_parts(parts)


def render_status_text(state: TuiState, width: int = 100) -> str:
    """Render the legacy combined brand/status block."""
    return "\n".join(
        [
            render_brand_text(state, width),
            render_status_bar_text(state, width),
        ]
    )


def _render_todo_header_summary(todo_manager, width: int) -> str:
    """Render a one-line todo progress summary for the header."""
    width = max(8, width)
    if not todo_manager:
        return ""
    items = getattr(todo_manager, "todo_items", []) or []
    if not items:
        if getattr(todo_manager, "task_completed", False):
            return "[#7f8794]Todo[/] [#8fd6a3]completed[/]"
        if getattr(todo_manager, "task_state_started", False):
            return "[#7f8794]Todo[/] [#8fd6a3]completed[/]"
        return "[#7f8794]Todo[/] [#cfd3dc]-[/]"

    total = len(items)
    completed = len([item for item in items if item.get("status") == "completed"])
    active = next((item for item in items if item.get("status") == "in_progress"), None)
    pending = next((item for item in items if item.get("status") != "completed"), None)
    current = active or pending
    current_text = ""
    if current:
        current_text = str(current.get("text") or current.get("id") or "")

    prefix = f"Todo {completed}/{total}"
    if current_text:
        status = "doing" if active else "next"
        fixed_len = len(prefix) + len(status) + 3
        remaining = max(0, width - fixed_len)
        clipped = _plain_truncate(current_text, remaining)
        if clipped:
            return f"[#7f8794]{prefix}[/] [#d7ba7d]{status}:[/] [#cfd3dc]{_safe_text(clipped)}[/]"
        return f"[#7f8794]{prefix}[/] [#d7ba7d]{status}[/]"
    return f"[#7f8794]{prefix}[/] [#8fd6a3]done[/]"


def render_timeline_lines(
    state: TuiState,
    limit: int = MAX_TIMELINE_ITEMS,
    *,
    offset_from_end: int = 0,
    max_lines: int | None = None,
    header_mode: str = "history",
) -> str:
    """Render the main activity transcript."""
    if header_mode == "main":
        return render_main_timeline_lines(state, limit=limit, max_lines=max_lines)

    rendered_items = _render_timeline_blocks(state)

    if rendered_items:
        total = len(rendered_items)
        page_size = max(1, min(limit, total))
        end = max(0, total - max(0, offset_from_end))
        start = max(0, end - page_size)

        if max_lines is not None:
            body_budget = max(4, max_lines - 2)
            start = end
            used_lines = 0
            while start > 0:
                candidate = rendered_items[start - 1]
                candidate_lines = candidate.count("\n") + 1
                separator_lines = 2 if used_lines else 0
                if used_lines and used_lines + separator_lines + candidate_lines > body_budget:
                    break
                if not used_lines and candidate_lines > body_budget:
                    start -= 1
                    break
                used_lines += separator_lines + candidate_lines
                start -= 1

        visible = rendered_items[start:end]
        if not visible:
            visible = rendered_items[:1]
            start = 0
            end = 1

        header = _timeline_window_header(start, end, total, mode=header_mode)
        return "\n\n".join([header, *visible])
    if not state.session_id:
        return (
            "[#d7ba7d]Starting yoyoagent[/]\n"
            "\n"
            "[#7f8794]The workspace is loading and the session is being prepared.[/]"
        )
    return (
        "[#8fd6a3]Ready[/]\n"
        "\n"
        "[#7f8794]Ask yoyoagent to inspect code, make a change, run verification, or explain a result.[/]\n"
        "[#7f8794]Ctrl+T opens task plan. Ctrl+Enter sends. Ctrl+Q quits.[/]"
    )


def render_main_timeline_lines(
    state: TuiState,
    limit: int = MAX_TIMELINE_ITEMS,
    max_lines: int | None = None,
) -> str:
    """Render ALL activity for the main UI (unlimited, scrollable)."""
    rendered_items = _render_timeline_blocks(state)

    sections = []

    if not rendered_items:
        sections.append(
            "[#8fd6a3]Ready[/]\n"
            "\n"
            "[#7f8794]Ask yoyoagent to inspect code, make a change, run verification, or explain a result.[/]\n"
            "[#7f8794]PageUp/PageDown scroll | Ctrl+T task plan | Ctrl+Enter send | Ctrl+Q quit[/]"
        )
    else:
        total = len(rendered_items)
        start = 0
        visible_items = rendered_items
        if max_lines is not None:
            body_budget = max(4, max_lines - 2)
            start = total
            used_lines = 0
            while start > 0:
                candidate = rendered_items[start - 1]
                candidate_lines = candidate.count("\n") + 1
                separator_lines = 2 if used_lines else 0
                if used_lines and used_lines + separator_lines + candidate_lines > body_budget:
                    break
                if not used_lines and candidate_lines > body_budget:
                    start -= 1
                    break
                used_lines += separator_lines + candidate_lines
                start -= 1
            visible_items = rendered_items[start:]
        header = _timeline_window_header(start, total, total, mode="main")
        sections.append("\n\n".join([header, *visible_items]))

    return "\n\n".join(sections)


def render_task_plan_panel(state: TuiState) -> str:
    """Render the full task plan for the dedicated task plan screen."""
    if not state.todo_manager:
        return "[#7f8794]No task plan is available for this session yet.[/]"
    return _render_todo_section(state.todo_manager)


def _render_timeline_blocks(state: TuiState) -> list[str]:
    """Render timeline items as human-readable activity blocks."""
    blocks: list[str] = []
    items = state.latest_timeline_items(MAX_TIMELINE_ITEMS)
    index = 0
    while index < len(items):
        item = items[index]
        role_prefix = _role_prefix(item)

        if item.event_type == "tool_start":
            matching_end_index = _find_matching_tool_end(items, index)
            end_item = items[matching_end_index] if matching_end_index is not None else None
            rendered = _render_tool_activity(item, end_item, role_prefix)
            if rendered:
                blocks.append(rendered)
            if matching_end_index is not None:
                index = matching_end_index + 1
                continue
        elif item.event_type == "tool_end":
            if item.tool_name != "todo":
                rendered = _render_tool_activity(None, item, role_prefix)
                if rendered:
                    blocks.append(rendered)
        else:
            rendered = _render_timeline_item(item, state)
            if rendered:
                blocks.append(rendered)
        index += 1
    return blocks


def _find_matching_tool_end(items: list[TimelineItem], start_index: int) -> int | None:
    """Return the next matching tool_end index before another tool_start appears."""
    start = items[start_index]
    for index in range(start_index + 1, len(items)):
        candidate = items[index]
        if candidate.event_type == "tool_start":
            return None
        if candidate.event_type != "tool_end":
            continue
        if candidate.tool_name == "todo":
            continue
        if start.tool_name and candidate.tool_name and start.tool_name != candidate.tool_name:
            continue
        if start.detail and candidate.detail and start.detail != candidate.detail:
            continue
        return index
    return None


def _render_todo_section(todo_manager) -> str:
    """Render todo items in a minimal style."""
    items = todo_manager.todo_items
    memory = todo_manager.memory

    lines = []
    lines.append("[bold #c9a6ff]📋 Task Plan[/]")
    lines.append("")

    if not items:
        # No todo items yet - show a placeholder
        lines.append("  [#7f8794]No task plan yet. The agent will create one shortly...[/]")
    else:
        # 计算总数和剩余
        total_count = len(items)
        pending_count = len([item for item in items if item.get("status") != "completed"])
        completed_count = total_count - pending_count

        # 显示总结
        if pending_count > 0:
            lines.append(f"  [#7f8794]Total: {total_count} | Remaining: {pending_count} | Completed: {completed_count}[/]")
        else:
            lines.append(f"  [#8fd6a3]Total: {total_count} | All {completed_count} tasks completed![/]")
        lines.append("")

        for i, item in enumerate(items):
            status = item.get("status", "pending")
            status_icon = {
                "pending": "[#7f8794]○[/]",
                "in_progress": "[#d7ba7d]●[/]",
                "completed": "[#8fd6a3]✓[/]",
            }.get(status, "[#7f8794]○[/]")
            status_color = {
                "pending": "#7f8794",
                "in_progress": "#d7ba7d",
                "completed": "#8fd6a3",
            }.get(status, "#7f8794")

            item_text = _safe_text(item.get("text", ""))
            item_id = _safe_text(item.get("id", ""))

            # Main todo line
            lines.append(f"  {status_icon} [{status_color}]{item_id}[/{status_color}] {item_text}")

            # Add ALL item fields
            extra_details = []

            # List all available fields in the item
            for key, value in item.items():
                if key in ["id", "text", "status"]:
                    continue  # already displayed
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue

                # Format the key for display
                display_key = key.replace("_", " ").title()
                value_str = _safe_text(str(value))

                if key == "priority":
                    extra_details.append(f"    [#c9a6ff]{display_key}: {value_str}[/]")
                else:
                    extra_details.append(f"    [#7f8794]{display_key}: {value_str}[/]")

            if extra_details:
                lines.extend(extra_details)
            if i < len(items) - 1:
                lines.append("")

    # Add memory info if available
    if memory:
        has_memory_content = False
        memory_lines = []

        user_goal = memory.get("user_goal", "")
        if user_goal:
            has_memory_content = True
            memory_lines.append(f"[#d7ba7d]🎯[/] {_safe_text(user_goal)}")

        labels = {
            "constraints": "📌",
            "files_inspected": "📂",
            "files_modified": "✏️",
            "decisions": "💡",
            "test_results": "🧪",
            "open_risks": "⚠️",
            "next_steps": "⏭️",
        }

        for field, icon in labels.items():
            values = memory.get(field, [])
            if values:
                has_memory_content = True
                label = {
                    "constraints": "Constraints",
                    "files_inspected": "Files",
                    "files_modified": "Modified",
                    "decisions": "Decisions",
                    "test_results": "Tests",
                    "open_risks": "Risks",
                    "next_steps": "Next",
                }.get(field, field)
                if len(values) == 1:
                    # Single value - show inline
                    value_str = _safe_text(values[0])
                    memory_lines.append(f"[#7f8794]{icon} {label}:[/] {value_str}")
                else:
                    # Multiple values - show as list
                    memory_lines.append(f"[#7f8794]{icon} {label}:[/]")
                    for v in values[:5]:  # Show up to 5
                        memory_lines.append(f"  {_safe_text(v)}")
                    if len(values) > 5:
                        memory_lines.append(f"  ... and {len(values)-5} more")

        if has_memory_content:
            if items:
                lines.append("")
            lines.extend(memory_lines)

    return "\n".join(lines)


def _timeline_window_header(start: int, end: int, total: int, *, mode: str) -> str:
    if total <= 0:
        return ""
    position = "latest" if end >= total else "history"
    if mode == "main":
        extra = "Ctrl+T task plan | PageUp/PageDown scroll | Home/End jump | Ctrl+Enter send | Ctrl+Q quit"
    else:
        extra = "Up older | Down newer | PageUp/PageDown jump | Home first | End latest | Esc back"
    return (
        f"[#7f8794]\\[{position}] showing {start + 1}-{end} of {total} "
        f"events | {extra}[/]"
    )


def _render_active_task_as_item(task: dict[str, Any], state: TuiState) -> str:
    """渲染活动任务状态为 item 形式"""
    lines = []

    # 第一行：任务标题
    intent_text = task.get('intent', '') or ''
    intent = _safe_text(intent_text[:60])
    if len(intent_text) > 60:
        intent += "..."
    lines.append(f"[bold #c9a6ff]Task in Progress[/]: {intent}")

    # 第二行：当前活动
    action = _safe_text(task.get('current_action', ''))
    if action:
        lines.append(f"  [#d7ba7d]●[/] {action}")

    # 第三行：时间和 tokens
    elapsed_ms = 0
    start_time = task.get('start_time_ms')
    if start_time:
        elapsed_ms = int(time.time() * 1000) - start_time
    elapsed_str = _format_duration(elapsed_ms)

    usage = task.get('usage', {}) or {}
    total = usage.get('total_tokens', 0)
    input_tok = usage.get('input_tokens', 0)
    output_tok = usage.get('output_tokens', 0)

    usage_str = f"Tokens: {_format_tokens(total)} (in: {_format_tokens(input_tok)}, out: {_format_tokens(output_tok)})"

    lines.append(f"  [#7f8794]Elapsed:[/] {elapsed_str}  [#7f8794]{usage_str}[/]")

    return "\n".join(lines)


def render_approval_text(approval: PendingApproval) -> str:
    """Render one approval request."""
    lines = [
        f"[bold #e6e8ee]{_safe_text(approval.title)}[/]",
        f"[#aeb6c2]{_safe_text(approval.detail)}[/]",
        "",
        _safe_text(approval.request_text),
    ]
    if approval.diff_preview:
        lines.extend(["", "[#7f8794]diff_preview:[/]", _safe_text(approval.diff_preview)])
    return "\n".join(lines)


def _render_subagent(subagent: SubagentStatus) -> str:
    elapsed = f" ({subagent.elapsed_ms} ms)" if subagent.elapsed_ms is not None else ""
    return (
        f"[#9cdcfe]@{_safe_text(subagent.role)}[/] "
        f"{_status_badge(subagent.status)} "
        f"{_safe_text(subagent.detail)}{elapsed}"
    )


def _role_prefix(item: TimelineItem) -> str:
    return f"[#7f8794]@{_safe_text(item.role)}[/] " if item.role and item.source == "subagent" else ""


def _render_timeline_item(item: TimelineItem, state: TuiState | None = None) -> str:
    role_prefix = _role_prefix(item)

    if item.event_type == "user_message":
        content = _safe_text(item.content.strip() or item.detail.strip())
        return f"[bold #f0f2f5]You[/]\n  [#d7dae0]{content}[/]"
    if item.event_type in {"text_delta"}:
        content = _safe_text(item.content)
        return f"{role_prefix}[bold #c9a6ff]Yoyo[/]\n  [#d7dae0]{content}[/]"
    if item.event_type == "thinking_start":
        return f"{role_prefix}[#7f8794]Thinking...[/]"
    if item.event_type == "thinking_end":
        return f"{role_prefix}[#7f8794][done][/]"
    if item.event_type == "thinking_delta":
        return None  # 跳过，不单独显示
    if item.event_type == "tool_start":
        return _render_tool_call(item, role_prefix)
    if item.event_type == "tool_end":
        if item.tool_name == "todo":
            return None
        return _render_tool_return(item, role_prefix)
    if item.event_type == "tool_result":
        if item.content and item.content.strip():
            title = _safe_text(_human_tool_result_title(item))
            lines = [f"{role_prefix}[bold #8fd6a3]{title}[/]"]
            detail = item.detail or ""
            if detail and detail != item.title and detail != item.content:
                lines.append(f"  [#8b949e]{_safe_text(detail)}[/]")
            lines.append(_indent_block(colorize_diff_for_tui(item.content)))
            return "\n".join(lines)
        return None
    if item.event_type == "usage":
        usage = item.usage or {}
        input_tok = usage.get('input_tokens', 0)
        output_tok = usage.get('output_tokens', 0)
        total_tok = usage.get('total_tokens', input_tok + output_tok)
        return f"{role_prefix}[#7f8794][usage] input={_format_tokens(input_tok)} output={_format_tokens(output_tok)} total={_format_tokens(total_tok)}[/]"
    if item.event_type == "context_compressed":
        return f"{role_prefix}[#7f8794][context] {_safe_text(item.content)}[/]"
    if item.event_type == "llm_waiting":
        return _render_llm_waiting_item(item, role_prefix, state)
    if item.event_type == "llm_timeout":
        return f"{role_prefix}[#d7ba7d][timeout] {_safe_text(item.content)}[/]"
    if item.event_type == "llm_retry":
        return f"{role_prefix}[#9cdcfe][retry] {_safe_text(item.content)}[/]"
    if item.event_type == "llm_error":
        return f"{role_prefix}[#ff8f8f][error] {_safe_text(item.content)}[/]"
    if item.event_type == "file_changed":
        files = ", ".join(_safe_text(fp) for fp in item.file_paths) if item.file_paths else _safe_text(item.content or "file")
        return f"{role_prefix}[#8fd6a3]+[/] [#cfd3dc]modified[/] {files}"
    if item.event_type == "approval_required":
        status = _status_badge(item.status)
        lines = [
            f"{role_prefix}[bold #d7ba7d]Needs your approval[/] {status}",
        ]
        if item.detail:
            lines.append(f"  [#cfd3dc]{_safe_text(item.detail)}[/]")
        # 显示完整的内容（含 diff），并高亮显示
        if item.content:
            lines.append(_indent_block(colorize_diff_for_tui(item.content)))
        return "\n".join(lines)
    if item.event_type == "approval_resolved":
        status = _status_badge(item.status)
        title = _approval_resolved_title(item.status)
        lines = [f"{role_prefix}[bold #8fd6a3]{title}[/] {status}"]
        if item.detail:
            lines.append(f"  [#8b949e]{_safe_text(item.detail)}[/]")
        return "\n".join(lines)
    if item.event_type in {"subagent_started", "subagent_finished"}:
        status = _status_badge(item.status)
        detail = _detail_line(item.detail)
        return _activity_line("@", "#9cdcfe", role_prefix, item, status, detail)
    if item.event_type in {"agent_thinking"}:
        return None  # 临时状态不显示在最终时间线中
    return None


def _render_llm_waiting_item(
    item: TimelineItem,
    role_prefix: str,
    state: TuiState | None = None,
) -> str:
    """Render the model waiting item with live timing and token details."""
    status = item.status or "running"
    color = {
        "running": "#d7ba7d",
        "retrying": "#9cdcfe",
        "timeout": "#d7ba7d",
        "failed": "#ff8f8f",
        "completed": "#8fd6a3",
    }.get(status, "#7f8794")
    title = _safe_text(item.title or "Waiting for model response")
    marker = "●" if status == "completed" else "⏺"

    metadata = item.metadata or {}
    attempt = metadata.get("attempt")
    attempts = metadata.get("attempts")
    attempt_text = f"attempt {attempt}/{attempts}" if attempt and attempts else ""

    if status in {"running", "retrying"} and item.start_time_ms is not None:
        elapsed_ms = int(time.time() * 1000) - item.start_time_ms
    else:
        elapsed_ms = item.elapsed_ms or 0
    if metadata.get("elapsed_ms") and status not in {"running", "retrying"}:
        elapsed_ms = int(metadata.get("elapsed_ms") or elapsed_ms)

    since_ms = metadata.get("since_last_token_ms")
    if since_ms is None and metadata.get("idle_seconds") is not None:
        since_ms = int(metadata.get("idle_seconds") or 0) * 1000

    usage = item.usage or (state.latest_usage if state else {}) or {}
    total = _usage_total(usage)
    if total > 0:
        token_text = (
            f"Tokens {_format_tokens(total)} "
            f"(input {_format_tokens(int(usage.get('input_tokens', 0) or 0))}, "
            f"output {_format_tokens(int(usage.get('output_tokens', 0) or 0))})"
        )
    else:
        token_text = "Tokens -"

    details = [f"elapsed {_format_duration(elapsed_ms)}"]
    if since_ms is not None and status in {"running", "retrying"}:
        details.append(f"last token {_format_duration(int(since_ms))}")
    if attempt_text:
        details.append(attempt_text)
    details.append(token_text)

    return (
        f"{role_prefix}[{color}]{marker}[/] [bold {color}]{title}[/]\n"
        f"  [#8b949e]{' · '.join(details)}[/]"
    )


def _render_tool_activity(
    start: TimelineItem | None,
    end: TimelineItem | None,
    role_prefix: str,
) -> str | None:
    """Render a tool start/end pair as one readable activity block."""
    item = start or end
    if item is None or item.tool_name == "todo":
        return None

    status = (end.status if end is not None else item.status) or "running"
    title = _tool_activity_title(item, status)
    color = "#ff8f8f" if status == "failed" else "#8fd6a3" if status == "completed" else "#9cdcfe"
    lines = [f"{role_prefix}[bold {color}]{title}[/] {_status_badge(status)}"]

    target = _tool_target_line(start, end)
    if target:
        lines.append(f"  [#cfd3dc]{target}[/]")

    purpose = _safe_text((start.title if start else end.title) or "")
    if purpose and purpose != target:
        lines.append(f"  [#8b949e]{purpose}[/]")

    args = start.metadata.get("args") if start and isinstance(start.metadata, dict) else None
    if args:
        lines.append(f"  [#7f8794]Input[/] {_format_args(args)}")

    if end and end.elapsed_ms is not None:
        lines.append(f"  [#7f8794]Time[/] [#cfd3dc]{_format_duration(end.elapsed_ms)}[/]")
    elif status == "running":
        lines.append("  [#7f8794]Status[/] [#cfd3dc]in progress[/]")
    return "\n".join(lines)


def _tool_activity_title(item: TimelineItem, status: str) -> str:
    tool_name = item.tool_name or item.metadata.get("tool_name", "") if isinstance(item.metadata, dict) else item.tool_name
    title = item.title or ""
    if status == "failed":
        return "Tool failed"
    if tool_name in {"read_file", "read_many_files"} or "read file" in title.lower():
        return "Read file"
    if tool_name in {"grep"} or "search" in title.lower() or "grep" in title.lower():
        return "Search code"
    if tool_name == "bash":
        return "Run command"
    if tool_name in {"apply_patch", "edit_file", "write_file"}:
        return "Edit file"
    if tool_name in {"git_diff", "git_show"}:
        return "Inspect git"
    if tool_name == "list_files":
        return "List files"
    if tool_name == "subagent":
        return "Delegate work"
    if tool_name in {"list_skills", "load_skill"}:
        return "Use skill"
    if title:
        return title
    return "Run tool"


def _tool_target_line(start: TimelineItem | None, end: TimelineItem | None) -> str:
    item = start or end
    if item is None:
        return ""
    if item.file_paths:
        return "Files: " + ", ".join(_safe_text(path) for path in item.file_paths)
    detail = (start.detail if start and start.detail else end.detail if end and end.detail else "") or ""
    if detail:
        return _safe_text(detail)
    content = (start.content if start and start.content else end.content if end and end.content else "") or ""
    if content and content != item.tool_name:
        return _safe_text(content)
    return ""


def _human_tool_result_title(item: TimelineItem) -> str:
    title = (item.title or "").lower()
    if item.metadata.get("approval_preview") if isinstance(item.metadata, dict) else False:
        return "Review full diff before approval"
    if "diff" in title or item.content.startswith(("diff --git", "--- ", "@@")):
        return "Review full diff"
    if "task state" in title:
        return "Task state"
    return item.title or "Tool result"


def _approval_resolved_title(status: str | None) -> str:
    if status in {"approved", "cached_approved"}:
        return "Approved"
    if status == "denied":
        return "Denied"
    return "Approval resolved"


def _render_tool_call(item: TimelineItem, role_prefix: str) -> str:
    tool_name = _safe_text(item.tool_name or item.metadata.get("tool_name", "") or "tool")
    title = _safe_text(item.title or "Tool call")
    detail = _safe_text(item.detail or item.content or "")
    args = item.metadata.get("args") if isinstance(item.metadata, dict) else None
    lines = [
        f"{role_prefix}[#9cdcfe]⏺[/] [bold #9cdcfe]Tool call[/] [#7f8794]{tool_name}[/] {_status_badge(item.status)}",
        f"  [#cfd3dc]{title}[/]",
    ]
    if detail:
        lines.append(f"  [#8b949e]{detail}[/]")
    if args:
        lines.append(f"  [#7f8794]args[/] {_format_args(args)}")
    return "\n".join(lines)


def _render_tool_return(item: TimelineItem, role_prefix: str) -> str:
    tool_name = _safe_text(item.tool_name or item.metadata.get("tool_name", "") or "tool")
    title = _safe_text(item.title or "Tool finished")
    detail = _safe_text(item.detail or item.content or "")
    elapsed = f"  [#7f8794]elapsed[/] [#cfd3dc]{_format_duration(item.elapsed_ms)}[/]" if item.elapsed_ms is not None else ""
    status = _status_badge(item.status)
    lines = [
        f"{role_prefix}[#8fd6a3]⏺[/] [bold #8fd6a3]Tool returned[/] [#7f8794]{tool_name}[/] {status}",
        f"  [#cfd3dc]{title}[/]",
    ]
    if detail:
        lines.append(f"  [#8b949e]{detail}[/]")
    if elapsed:
        lines.append(elapsed)
    return "\n".join(lines)


def _format_args(args: object) -> str:
    if not isinstance(args, dict) or not args:
        return "[#7f8794]{}[/]"
    parts = []
    for key, value in list(args.items())[:5]:
        parts.append(f"{_safe_text(key)}={_safe_repr(value, 120)}")
    suffix = " ..." if len(args) > 5 else ""
    return f"[#8b949e]{', '.join(parts)}{suffix}[/]"


def _indent_block(text: str) -> str:
    if not text:
        return ""
    return "\n".join(f"  {line}" if line else "" for line in text.splitlines())


def _activity_line(
    marker: str,
    marker_color: str,
    role_prefix: str,
    item: TimelineItem,
    status: str,
    detail: str,
) -> str:
    title = _safe_text(str(item.title).lower())
    phase = f" [#7f8794]{_safe_text(item.phase)}[/]" if item.phase else ""
    return f"{role_prefix}[{marker_color}]{marker}[/] [#cfd3dc]{title}[/]{phase} {status}{detail}"


def _task_running_line(
    role_prefix: str,
    item: TimelineItem,
    status: str,
    detail: str,
    state: TuiState | None = None,
) -> str:
    phase = f" [#7f8794]{_safe_text(item.phase)}[/]" if item.phase else ""

    # 从 metadata 或 todo_manager 获取当前意图
    intent = ""
    if item.metadata and item.metadata.get('intent'):
        intent = item.metadata['intent']
    elif state and state.todo_manager and state.todo_manager.get_memory().get('user_goal'):
        intent = state.todo_manager.get_memory()['user_goal']
    elif item.detail and item.detail != "Thinking / waiting for model response":
        intent = item.detail

    # 获取当前进行中的任务描述
    current_activity = _safe_text(item.title)
    if item.event_type == "llm_waiting":
        current_activity = "等待模型响应"
    elif item.event_type == "agent_thinking" and item.title == "Task running":
        current_activity = "处理中"

    # 计算耗时
    elapsed_ms = 0
    if state and hasattr(state, 'get_elapsed_ms'):
        elapsed_ms = state.get_elapsed_ms(item)
    elif item.elapsed_ms:
        elapsed_ms = item.elapsed_ms
    elapsed_str = _format_duration(elapsed_ms)

    # 构建信息行
    lines = [
        f"{role_prefix}[#d7ba7d]⏺[/] [bold #f0d48a]{current_activity}[/]{phase}"
    ]

    # 添加意图
    if intent:
        # 截断过长的意图
        intent_display = _safe_text(intent[:80])
        if len(intent) > 80:
            intent_display += "..."
        lines.append(f"  [#cfd3dc]{intent_display}[/]")

    # 添加详细信息
    details = []
    if elapsed_str:
        details.append(f"耗时: {elapsed_str}")

    # 添加 token 使用信息
    if state and state.latest_usage:
        usage = state.latest_usage
        input_tok = usage.get('input_tokens', 0)
        output_tok = usage.get('output_tokens', 0)
        total_tok = usage.get('total_tokens', input_tok + output_tok)
        if total_tok > 0:
            details.append(f"Tokens: {total_tok} (in:{input_tok}, out:{output_tok})")

    if details:
        lines.append(f"  [#8b949e]{' | '.join(details)}[/]")

    return "\n".join(lines)


def _detail_line(detail: str) -> str:
    if not detail:
        return ""
    return f"\n  [#8b949e]{_safe_text(detail)}[/]"


def _status_badge(status: str | None) -> str:
    if not status:
        return ""
    color = {
        "running": "#d7ba7d",
        "completed": "#8fd6a3",
        "approved": "#8fd6a3",
        "cached_approved": "#8fd6a3",
        "waiting_for_user": "#d7ba7d",
        "denied": "#ff8f8f",
        "failed": "#ff8f8f",
    }.get(status, "#7f8794")
    return f"[{color}]⏺[/] [#7f8794]{_safe_text(status)}[/]"


def _marker_for_event(item: TimelineItem) -> tuple[str, str]:
    if item.event_type == "file_changed":
        return "+", "#8fd6a3"
    if item.event_type.startswith("approval"):
        return "?", "#d7ba7d"
    if item.event_type == "tool_end":
        if item.status == "failed":
            return "!", "#ff8f8f"
        return "<", "#8fd6a3"
    return ">", "#9cdcfe"
