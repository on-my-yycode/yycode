"""Formatting helpers for TUI widgets."""

from __future__ import annotations

import time
from typing import Any

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
    cells = ["[#2b3038]·[/]" for _ in range(PROGRESS_TRACK_WIDTH)]
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


def render_markdown_for_tui(markdown: str) -> str:
    """Render a small, safe Markdown subset as Rich markup for timeline text."""
    return _render_markdown_for_tui(markdown, full=True)


def render_markdown_light_for_tui(markdown: str) -> str:
    """Render Markdown cheaply while the model is still streaming."""
    return _render_markdown_for_tui(markdown, full=False)


def _render_markdown_for_tui(markdown: str, *, full: bool) -> str:
    """Render a small, safe Markdown subset as Rich markup for timeline text."""
    lines: list[str] = []
    in_fence = False
    fence_lang = ""

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_lang = stripped[3:].strip()
                label = f" {fence_lang}" if fence_lang else ""
                lines.append(f"[#7f8794]code{_safe_text(label)}[/]")
            else:
                in_fence = False
                fence_lang = ""
            continue

        if in_fence:
            rendered_code = _highlight_code_line_for_tui(raw_line, fence_lang) if full else f"[#cfd3dc]{_safe_text(raw_line)}[/]"
            lines.append(f"  {rendered_code}")
            continue

        if not stripped:
            lines.append("")
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            color = "#c9a6ff" if level <= 2 else "#d7ba7d"
            heading_text = _render_inline_markdown(heading.group(2)) if full else _safe_text(heading.group(2))
            lines.append(f"[bold {color}]{heading_text}[/]")
            continue

        quote = re.match(r"^>\s?(.*)$", stripped)
        if quote:
            quote_text = _render_inline_markdown(quote.group(1)) if full else _safe_text(quote.group(1))
            lines.append(f"[#7f8794]│[/] [#aeb6c2]{quote_text}[/]")
            continue

        task = re.match(r"^[-*]\s+\[([ xX])\]\s+(.+)$", stripped)
        if task:
            checked = task.group(1).lower() == "x"
            marker = "[#8fd6a3]✓[/]" if checked else "[#7f8794]○[/]"
            task_text = _render_inline_markdown(task.group(2)) if full else _safe_text(task.group(2))
            lines.append(f"  {marker} {task_text}")
            continue

        bullet = re.match(r"^([-*])\s+(.+)$", stripped)
        if bullet:
            bullet_text = _render_inline_markdown(bullet.group(2)) if full else _safe_text(bullet.group(2))
            lines.append(f"  [#7f8794]•[/] {bullet_text}")
            continue

        numbered = re.match(r"^(\d+)[.)]\s+(.+)$", stripped)
        if numbered:
            numbered_text = _render_inline_markdown(numbered.group(2)) if full else _safe_text(numbered.group(2))
            lines.append(f"  [#7f8794]{numbered.group(1)}.[/] {numbered_text}")
            continue

        line_text = _render_inline_markdown(raw_line) if full else _safe_text(raw_line)
        lines.append(f"[#d7dae0]{line_text}[/]")

    if markdown.endswith("\n"):
        return "\n".join(lines) + "\n"
    return "\n".join(lines)


def _render_inline_markdown(text: str) -> str:
    """Render safe inline Markdown markers after escaping Rich markup."""
    escaped = _safe_text(text)

    code_spans: list[str] = []

    def replace_code(match: re.Match) -> str:
        code_spans.append(f"[#9cdcfe]`{_safe_text(match.group(1))}`[/]")
        return f"\0CODE{len(code_spans) - 1}\0"

    escaped = re.sub(r"`([^`]+)`", replace_code, escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"[bold #f0f2f5]\1[/]", escaped)
    escaped = re.sub(r"__([^_]+)__", r"[bold #f0f2f5]\1[/]", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"[italic]\1[/]", escaped)
    escaped = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"[italic]\1[/]", escaped)

    for index, rendered in enumerate(code_spans):
        escaped = escaped.replace(f"\0CODE{index}\0", rendered)
    return escaped


def _highlight_code_line_for_tui(line: str, lang: str) -> str:
    """Apply lightweight syntax coloring to one fenced code line."""
    normalized = _normalize_code_lang(lang)
    if normalized == "diff":
        return colorize_diff_for_tui(line)

    text = _safe_text(line)
    if normalized in {"python", "py"}:
        return _highlight_keyword_line(
            text,
            {
                "and", "as", "assert", "async", "await", "break", "class", "continue",
                "def", "elif", "else", "except", "False", "finally", "for", "from",
                "if", "import", "in", "is", "lambda", "None", "not", "or", "pass",
                "raise", "return", "True", "try", "while", "with", "yield",
            },
            comment_prefix="#",
        )
    if normalized in {"bash", "sh", "shell", "zsh"}:
        return _highlight_bash_line(text)
    if normalized == "json":
        return _highlight_json_line(text)
    if normalized in {"javascript", "js", "typescript", "ts", "tsx", "jsx"}:
        return _highlight_keyword_line(
            text,
            {
                "async", "await", "break", "case", "catch", "class", "const", "continue",
                "default", "else", "export", "false", "finally", "for", "from", "function",
                "if", "import", "let", "new", "null", "return", "switch", "this", "throw",
                "true", "try", "type", "undefined", "var", "while",
            },
            comment_prefix="//",
        )
    if normalized in {"java"}:
        return _highlight_keyword_line(
            text,
            {
                "abstract", "boolean", "break", "case", "catch", "class", "continue",
                "else", "extends", "false", "final", "finally", "for", "if", "implements",
                "import", "interface", "new", "null", "private", "protected", "public",
                "return", "static", "super", "switch", "this", "throw", "true", "try",
                "void", "while",
            },
            comment_prefix="//",
        )
    if normalized in {"csharp", "cs", "c#"}:
        return _highlight_keyword_line(
            text,
            {
                "abstract", "async", "await", "bool", "break", "case", "catch", "class",
                "const", "continue", "else", "false", "finally", "for", "foreach", "if",
                "interface", "namespace", "new", "null", "private", "protected", "public",
                "return", "static", "string", "switch", "this", "throw", "true", "try",
                "using", "var", "void", "while",
            },
            comment_prefix="//",
        )
    if normalized in {"go", "golang"}:
        return _highlight_keyword_line(
            text,
            {
                "break", "case", "chan", "const", "continue", "default", "defer", "else",
                "fallthrough", "false", "for", "func", "go", "goto", "if", "import",
                "interface", "map", "nil", "package", "range", "return", "select",
                "struct", "switch", "true", "type", "var",
            },
            comment_prefix="//",
        )
    if normalized in {"css"}:
        return _highlight_css_line(text)
    if normalized in {"html", "xml"}:
        return _highlight_html_line(text)
    return f"[#cfd3dc]{text}[/]"


def _normalize_code_lang(lang: str) -> str:
    parts = (lang or "").strip().lower().split(None, 1)
    return parts[0] if parts else ""


def _highlight_keyword_line(
    text: str,
    keywords: set[str],
    *,
    comment_prefix: str | None = None,
) -> str:
    code, comment = _split_comment(text, comment_prefix)
    placeholders: list[str] = []

    def stash(style: str, value: str) -> str:
        placeholders.append(f"[{style}]{value}[/]")
        return f"\0TOK{len(placeholders) - 1}\0"

    code = re.sub(r"(&quot;.*?&quot;|'.*?')", lambda m: stash("#ce9178", m.group(0)), code)
    code = re.sub(r"\b\d+(?:\.\d+)?\b", lambda m: stash("#b5cea8", m.group(0)), code)

    pattern = r"\b(" + "|".join(re.escape(word) for word in sorted(keywords, key=len, reverse=True)) + r")\b"
    code = re.sub(pattern, lambda m: stash("bold #c586c0", m.group(0)), code)

    for index, rendered in enumerate(placeholders):
        code = code.replace(f"\0TOK{index}\0", rendered)
    if comment:
        code += f"[#6a9955]{comment}[/]"
    return f"[#cfd3dc]{code}[/]"


def _split_comment(text: str, comment_prefix: str | None) -> tuple[str, str]:
    if not comment_prefix:
        return text, ""
    index = text.find(comment_prefix)
    if index < 0:
        return text, ""
    return text[:index], text[index:]


def _highlight_bash_line(text: str) -> str:
    stripped = text.lstrip()
    indent = text[: len(text) - len(stripped)]
    if stripped.startswith("#"):
        return f"[#6a9955]{text}[/]"
    parts = stripped.split(" ", 1)
    command = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    rest = re.sub(r"(--?[A-Za-z0-9][A-Za-z0-9_-]*)", r"[#9cdcfe]\1[/]", rest)
    rest = re.sub(r"(&quot;.*?&quot;|'.*?')", r"[#ce9178]\1[/]", rest)
    return f"[#cfd3dc]{indent}[bold #dcdcaa]{command}[/] {rest}[/]" if rest else f"[#cfd3dc]{indent}[bold #dcdcaa]{command}[/][/]"


def _highlight_json_line(text: str) -> str:
    text = re.sub(r"(&quot;[^&]*?&quot;)(\s*:)", r"[#9cdcfe]\1[/]\2", text)
    text = re.sub(r":\s*(&quot;[^&]*?&quot;)", r": [#ce9178]\1[/]", text)
    text = re.sub(r"\b(true|false|null)\b", r"[bold #569cd6]\1[/]", text)
    text = re.sub(r"\b\d+(?:\.\d+)?\b", r"[#b5cea8]\g<0>[/]", text)
    return f"[#cfd3dc]{text}[/]"


def _highlight_css_line(text: str) -> str:
    text = re.sub(r"([.#]?[A-Za-z_][A-Za-z0-9_-]*)(\s*\{)", r"[#d7ba7d]\1[/]\2", text)
    text = re.sub(r"([A-Za-z-]+)(\s*:)", r"[#9cdcfe]\1[/]\2", text)
    text = re.sub(r"(#[0-9A-Fa-f]{3,8})", r"[#ce9178]\1[/]", text)
    return f"[#cfd3dc]{text}[/]"


def _highlight_html_line(text: str) -> str:
    text = re.sub(r"(&lt;/?)([A-Za-z][A-Za-z0-9-]*)", r"\1[bold #569cd6]\2[/]", text)
    text = re.sub(r"\s([A-Za-z_:][-A-Za-z0-9_:.]*)(=)", r" [#9cdcfe]\1[/]\2", text)
    text = re.sub(r"=(&quot;.*?&quot;|'.*?')", r"=[#ce9178]\1[/]", text)
    return f"[#cfd3dc]{text}[/]"


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
    workspace_text = _safe_text(state.workspace_path if state.workspace_path else "(not set)", max(12, W - 18))
    session_text = _safe_text(state.session_id if state.session_id else "(starting)", max(12, W - 10))
    restored = int(getattr(state, "restored_message_count", 0) or 0)
    header = getattr(state, "message_context_header", None)
    message_count = int(getattr(header, "message_count", 0) or 0)
    session_line = _join_status_parts(
        [
            f"[#7f8794]session[/] [#cfd3dc]{session_text}[/]",
            f"[#7f8794]msgs[/] [#cfd3dc]{message_count}[/]",
            f"[#7f8794]restored[/] [#cfd3dc]{restored}[/]" if restored else "",
            _render_header_context(header),
        ]
    )
    return "\n".join(
        [
            brand_line,
            f"{_render_git_header(getattr(state, 'git_header', None))}   [#cfd3dc]{workspace_text}[/]",
            session_line,
        ]
    )


def _render_git_header(git_header) -> str:
    """Render branch/status marker for the top panel."""
    if git_header is None or not getattr(git_header, "available", False):
        return "[#7f8794]git -[/]"
    branch = _safe_text(getattr(git_header, "branch", "") or "-", 32)
    dirty = bool(getattr(git_header, "dirty", False))
    status = "[#facc15]±[/]" if dirty else "[#8fd6a3]✓[/]"
    return f"[#7f8794][/] [#7dd3fc]{branch}[/] {status}"


def _render_header_context(header) -> str:
    """Render compact session context usage for the top panel."""
    if header is None:
        return "[#7f8794]Ctx[/] [#cfd3dc]calculating...[/]"
    total = int(getattr(header, "total_tokens", 0) or 0)
    window = int(getattr(header, "context_window_tokens", 0) or 0)
    refreshing = bool(getattr(header, "refreshing", False))
    if total <= 0 and refreshing:
        return "[#7f8794]Ctx[/] [#cfd3dc]calculating...[/]"
    if total <= 0:
        return "[#7f8794]Ctx[/] [#cfd3dc]not measured[/]"
    pressure = str(getattr(header, "pressure", "low") or "low")
    pressure_color = {
        "low": "#8fd6a3",
        "medium": "#d7ba7d",
        "high": "#f97316",
        "critical": "#ff8f8f",
    }.get(pressure, "#cfd3dc")
    source = str(getattr(header, "token_source", "estimated") or "estimated")
    source_text = "exact" if source == "exact" else "est"
    if window > 0:
        percent = min(int(total / window * 100), 100)
        usage = f"{_format_tokens(total)}/{_format_tokens(window)} {percent}%"
    else:
        usage = f"{_format_tokens(total)}/-"
    suffix = " ↻" if refreshing else ""
    return f"[#7f8794]Ctx[/] [#cfd3dc]{usage}[/] [{pressure_color}]{pressure.upper()}[/] [#7f8794]{source_text}{suffix}[/]"


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
    status_part = f"[#7f8794]Status[/] {status_text}"
    elapsed_part = f"[#7f8794]{elapsed_label}[/] [#cfd3dc]{elapsed_text}[/]"
    tokens_part = (
        f"[#7f8794]Tokens[/] [#cfd3dc]{_format_tokens(total)}[/] "
        f"[#7f8794](input[/] [#cfd3dc]{_format_tokens(input_tokens)}[/][#7f8794], "
        f"output[/] [#cfd3dc]{_format_tokens(output_tokens)}[/][#7f8794])[/]"
    )
    todo_items = getattr(state.todo_manager, "todo_items", []) if state.todo_manager else []
    todo_reserve = 40 if todo_items else 8

    parts = [status_part, elapsed_part, tokens_part]
    if _parts_visible_len([model_part, *parts]) + 2 + todo_reserve <= W:
        parts.insert(0, model_part)

    todo_width = max(8, W - _parts_visible_len(parts) - 2)
    todo_summary = _render_todo_header_summary(state.todo_manager, todo_width)
    if not todo_summary:
        todo_summary = "[#7f8794]Todo[/] [#cfd3dc]-[/]"
    parts.insert(1 if parts and parts[0] == status_part else len(parts), todo_summary)

    while _parts_visible_len(parts) > W and len(parts) > 3:
        for candidate in (model_part, elapsed_part):
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
            rendered, next_index = _render_tool_run(items, index)
            blocks.extend(rendered)
            index = next_index
            continue
        elif item.event_type == "tool_end":
            if item.tool_name != "todo":
                rendered = _render_cached_timeline_item(item, state, role_prefix=role_prefix)
                if rendered:
                    blocks.append(rendered)
        else:
            rendered = _render_cached_timeline_item(item, state)
            if rendered:
                blocks.append(rendered)
        index += 1
    return blocks


def _render_cached_timeline_item(
    item: TimelineItem,
    state: TuiState | None = None,
    *,
    role_prefix: str | None = None,
) -> str | None:
    mode = _timeline_item_render_mode(item, state)
    key = _timeline_item_cache_key(item, mode)
    if item.render_cache_key == key:
        return item.rendered_text
    rendered = (
        _render_tool_activity(None, item, role_prefix)
        if role_prefix is not None and item.event_type == "tool_end"
        else _render_timeline_item(item, state, markdown_mode=mode)
    )
    item.render_cache_key = key
    item.rendered_text = rendered
    return rendered


def _timeline_item_render_mode(item: TimelineItem, state: TuiState | None) -> str:
    if item.event_type == "text_delta" and state and state.active_task.get("is_running"):
        return "light"
    return "full"


def _timeline_item_cache_key(item: TimelineItem, mode: str) -> tuple[Any, ...]:
    metadata_items = tuple(sorted((str(key), repr(value)) for key, value in item.metadata.items()))
    usage_items = tuple(sorted((str(key), int(value or 0)) for key, value in (item.usage or {}).items()))
    return (
        mode,
        item.event_type,
        item.title,
        item.detail,
        item.phase,
        item.status,
        item.source,
        item.role,
        item.tool_name,
        tuple(item.file_paths),
        metadata_items,
        item.elapsed_ms,
        item.content,
        item.start_time_ms,
        usage_items,
    )


def _render_tool_run(items: list[TimelineItem], start_index: int) -> tuple[list[str], int]:
    """Render one contiguous run of tool activity as lightweight phase blocks."""
    blocks: list[str] = []
    activities: list[tuple[TimelineItem, TimelineItem | None, str]] = []
    index = start_index
    while index < len(items):
        item = items[index]
        if item.event_type != "tool_start":
            break
        role_prefix = _role_prefix(item)
        matching_end_index = _find_matching_tool_end(items, index)
        end_item = items[matching_end_index] if matching_end_index is not None else None
        if item.tool_name != "todo":
            activities.append((item, end_item, role_prefix))
        if matching_end_index is None:
            index += 1
        else:
            index = matching_end_index + 1

    for phase, phase_activities in _group_tool_activities_by_phase(activities):
        rendered = _render_phase_activity_block(phase, phase_activities)
        if rendered:
            blocks.append(rendered)
    return blocks, index


def _group_tool_activities_by_phase(
    activities: list[tuple[TimelineItem, TimelineItem | None, str]],
) -> list[tuple[str, list[tuple[TimelineItem, TimelineItem | None, str]]]]:
    """Group adjacent tool activities by display phase."""
    max_group_size = 2
    groups: list[tuple[str, list[tuple[TimelineItem, TimelineItem | None, str]]]] = []
    for activity in activities:
        phase = _tool_activity_phase(activity[0])
        if groups and groups[-1][0] == phase and len(groups[-1][1]) < max_group_size:
            groups[-1][1].append(activity)
        else:
            groups.append((phase, [activity]))
    return groups


def _render_phase_activity_block(
    phase: str,
    activities: list[tuple[TimelineItem, TimelineItem | None, str]],
) -> str | None:
    if not activities:
        return None

    role_prefix = activities[0][2]
    summary = _activity_summary(activities)
    lines = [f"{role_prefix}[bold #c9a6ff]◇ {_safe_text(phase)}[/]"]
    if summary:
        lines.append(f"  [#7f8794]{_safe_text(summary)}[/]")
    usage = _usage_for_activities(activities)
    if usage:
        lines.append(f"  [#7f8794]{_format_usage_inline(usage)}[/]")
    lines.append("")

    for activity_index, (start, end, _role_prefix) in enumerate(activities):
        lines.extend(
            _render_tool_activity_tree_lines(
                start,
                end,
                is_last=activity_index == len(activities) - 1,
            )
        )
    return "\n".join(lines).rstrip()


def _render_tool_activity_tree_lines(
    start: TimelineItem | None,
    end: TimelineItem | None,
    *,
    is_last: bool,
) -> list[str]:
    item = start or end
    if item is None or item.tool_name == "todo":
        return []

    status = (end.status if end is not None else item.status) or "running"
    title = _tool_activity_tree_title(start, end, status)
    branch = "└─" if is_last else "├─"
    detail_prefix = "   " if is_last else "│  "
    color = "#ff8f8f" if status == "failed" else "#d7dae0"
    lines = [f"  [#7f8794]{branch}[/] [{color}]{title}[/]"]

    for detail in _tool_activity_tree_details(start, end, status):
        lines.append(f"  [#7f8794]{detail_prefix}[/] [#7f8794]{_safe_text(detail)}[/]")
    return lines


def _tool_activity_tree_title(
    start: TimelineItem | None,
    end: TimelineItem | None,
    status: str,
) -> str:
    item = start or end
    if item is None:
        return "Use tool"
    tool_name = item.tool_name or ""
    title_text = (item.title or "").lower()
    if status == "failed":
        return _safe_text(f"Failed {item.title or tool_name or 'tool'}")
    if tool_name.startswith("lsp_"):
        return _safe_text(item.title or "LSP semantic lookup")
    if tool_name in {"read_file", "read_many_files"} or "read file" in title_text:
        return "Inspect file"
    if tool_name == "list_files":
        return "List files"
    if tool_name == "grep" or "search" in title_text:
        return "Search code"
    if tool_name in {"git_diff", "git_show", "workspace_state"}:
        return "Inspect workspace"
    if tool_name in {"apply_patch", "edit_file", "write_file"}:
        return "Edit file"
    if tool_name in {"bash", "verify"}:
        command = _command_for_tool(item)
        lowered = command.lower()
        if any(name in lowered for name in ("pytest", "ruff", "mypy", "compileall")):
            return "Run verification"
        return "Run command"
    if tool_name == "subagent":
        return "Delegate work"
    return _safe_text(item.title or tool_name or "Use tool")


def _tool_activity_tree_details(
    start: TimelineItem | None,
    end: TimelineItem | None,
    status: str,
) -> list[str]:
    item = start or end
    if item is None:
        return []

    details: list[str] = []
    args = item.metadata.get("args") if isinstance(item.metadata, dict) else {}
    tool_name = item.tool_name or ""

    if tool_name.startswith("lsp_"):
        if isinstance(args, dict):
            path = args.get("path")
            query = args.get("query")
            line = args.get("line")
            character = args.get("character")
            if path:
                details.append(str(path))
            if query:
                details.append(f"query={query}")
            if line is not None and character is not None:
                details.append(f"position={line}:{character}")
        if not details:
            target = _tool_target_plain(item)
            if target:
                details.append(target)
    elif tool_name == "grep" or "search" in (item.title or "").lower():
        if isinstance(args, dict):
            pattern = args.get("pattern")
            path = args.get("path")
            if pattern:
                details.append(str(pattern))
            if path:
                details.append(str(path))
        if not details:
            target = _tool_target_plain(item)
            if target:
                details.append(target)
    elif tool_name in {"bash", "verify"}:
        command = _command_for_tool(item)
        if command:
            details.append(command)
    else:
        target = _tool_target_plain(item)
        if target:
            details.append(target)
        elif item.title:
            details.append(item.title)

    if start and _should_show_tool_input(start):
        details.append(f"Input {_format_args_plain(args)}")
    if end and end.elapsed_ms is not None:
        details.append(_format_duration(end.elapsed_ms))
    elif status in {"running", "in_progress"}:
        details.append(f"running {_task_spinner()}")
    elif status:
        details.append(status.replace("_", " "))
    return details


def _tool_activity_phase(item: TimelineItem) -> str:
    tool = item.tool_name or ""
    title = (item.title or "").lower()
    command = _command_for_tool(item).lower() if tool in {"bash", "verify"} else ""
    phase = (item.phase or "").lower()

    if tool.startswith("lsp_") or "semantic" in phase:
        return "Semantic Navigation"
    if tool in {"grep"} or "search" in title:
        return "Search"
    if tool in {"apply_patch", "edit_file", "write_file"}:
        return "Edit"
    if tool in {"verify"} or any(name in command for name in ("pytest", "ruff", "mypy", "compileall")):
        return "Verification"
    if tool in {"read_file", "read_many_files", "list_files", "workspace_state", "git_diff", "git_show"}:
        return "Exploration"
    if tool == "bash":
        return "Verification" if any(name in command for name in ("pytest", "ruff", "mypy", "compileall")) else "Exploration"
    if "implement" in phase or "edit" in phase:
        return "Edit"
    if "verify" in phase or "test" in phase:
        return "Verification"
    if "search" in phase:
        return "Search"
    return "Exploration"


def _usage_for_activities(
    activities: list[tuple[TimelineItem, TimelineItem | None, str]],
) -> dict[str, int] | None:
    for start, end, _role_prefix in reversed(activities):
        for item in (end, start):
            if item and item.usage:
                return item.usage
    return None


def _format_usage_inline(usage: dict[str, int]) -> str:
    input_tok = int(usage.get("input_tokens", 0) or 0)
    output_tok = int(usage.get("output_tokens", 0) or 0)
    total_tok = int(usage.get("total_tokens", input_tok + output_tok) or 0)
    return (
        f"tokens {_format_tokens(total_tok)} · "
        f"input {_format_tokens(input_tok)} · output {_format_tokens(output_tok)}"
    )


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
    """Render the full task plan panel in a scannable dashboard style."""
    items = list(todo_manager.todo_items or [])
    memory = todo_manager.memory or {}
    lines: list[str] = []

    goal = str(memory.get("user_goal") or "").strip()
    if goal:
        lines.extend(["[bold #c9a6ff]Goal[/]", f"  [#d7dae0]{_safe_text(goal)}[/]", ""])

    lines.extend(_render_checklist_panel(items))

    context_lines = _render_task_memory_context(memory)
    if context_lines:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(["[bold #c9a6ff]Context[/]", *context_lines])

    if not lines:
        return "[#7f8794]No task context is available yet.[/]"
    return "\n".join(lines).rstrip()


def _render_checklist_panel(items: list[dict]) -> list[str]:
    if not items:
        return [
            "[bold #c9a6ff]Status[/]",
            "  [#7f8794]No active checklist yet.[/]",
            "  [#7f8794]Task memory below is from the current context.[/]",
        ]

    total = len(items)
    completed = len([item for item in items if item.get("status") == "completed"])
    remaining = total - completed
    active_index = next(
        (index for index, item in enumerate(items) if item.get("status") == "in_progress"),
        None,
    )
    summary = f"{completed}/{total} done"
    if remaining:
        summary += f" · {remaining} remaining"
    else:
        summary += " · complete"

    lines = ["[bold #c9a6ff]Checklist[/]", f"  [#7f8794]{summary}[/]", ""]
    for index, item in enumerate(items):
        status = item.get("status", "pending")
        item_id = str(item.get("id") or index + 1)
        text = _safe_text(item.get("text", ""))
        if status == "completed":
            marker = "[#8fd6a3]✓[/]"
            style = "#8fd6a3"
        elif status == "in_progress":
            marker = f"[#d7ba7d]{_task_spinner()}[/]"
            style = "bold #d7ba7d"
        else:
            marker = "[#7f8794]○[/]"
            style = "#d7dae0"
        current = " [#7f8794]current[/]" if active_index == index else ""
        lines.append(f"  {marker} [#7f8794]{_safe_text(item_id)}[/] [{style}]{text}[/]{current}")
    return lines


def _task_spinner() -> str:
    frames = ("◐", "◓", "◑", "◒")
    return frames[int(time.time() * 2) % len(frames)]


def _render_task_memory_context(memory: dict) -> list[str]:
    sections = [
        ("constraints", "Constraints", 4),
        ("files_inspected", "Files", 5),
        ("files_modified", "Modified", 5),
        ("decisions", "Decisions", 4),
        ("test_results", "Tests", 3),
        ("open_risks", "Risks", 3),
        ("next_steps", "Next", 4),
    ]
    lines: list[str] = []
    for field, label, limit in sections:
        values = _dedupe_text_list(memory.get(field))
        if not values:
            continue
        if lines:
            lines.append("")
        lines.append(f"  [#7f8794]{label}[/]")
        visible = values[:limit]
        for value in visible:
            lines.append(f"    [#d7dae0]{_safe_text(value)}[/]")
        hidden = len(values) - len(visible)
        if hidden > 0:
            lines.append(f"    [#7f8794]+{hidden} more[/]")
    return lines


def _dedupe_text_list(value: object) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


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

    usage = task.get('usage', {}) or {}
    total = usage.get('total_tokens', 0)
    input_tok = usage.get('input_tokens', 0)
    output_tok = usage.get('output_tokens', 0)

    usage_str = f"Tokens: {_format_tokens(total)} (in: {_format_tokens(input_tok)}, out: {_format_tokens(output_tok)})"

    lines.append(f"  [#7f8794]{usage_str}[/]")

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
    skills = _skills_suffix(subagent.skills)
    return (
        f"[#9cdcfe]@{_safe_text(subagent.role)}[/] "
        f"{skills}"
        f"{_status_badge(subagent.status)} "
        f"{_safe_text(subagent.detail)}{elapsed}"
    )


def _role_prefix(item: TimelineItem) -> str:
    return f"[#7f8794]@{_safe_text(item.role)}[/] " if item.role and item.source == "subagent" else ""


def _render_timeline_item(item: TimelineItem, state: TuiState | None = None, *, markdown_mode: str = "full") -> str | None:
    role_prefix = _role_prefix(item)

    if item.event_type == "user_message":
        content = _safe_text(item.content.strip() or item.detail.strip())
        return f"[bold #f0f2f5]You[/]\n  [#d7dae0]{content}[/]"
    if item.event_type in {"text_delta"}:
        content = render_markdown_light_for_tui(item.content) if markdown_mode == "light" else render_markdown_for_tui(item.content)
        return f"{role_prefix}{content}"
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
            if _is_task_state_result(item):
                return _render_task_state_summary(role_prefix, item)
            title = _safe_text(_human_tool_result_title(item))
            lines = [f"{role_prefix}[bold #8fd6a3]{title}[/]"]
            detail = item.detail or ""
            if detail and detail != item.title and detail != item.content:
                lines.append(f"  [#8b949e]{_safe_text(detail)}[/]")
            lines.append(_indent_block(colorize_diff_for_tui(item.content)))
            files_changed = _render_changed_files_summary(item.content)
            if files_changed:
                lines.extend(["", files_changed])
            return "\n".join(lines)
        return None
    if item.event_type == "files_changed_summary":
        files = item.metadata.get("files") if isinstance(item.metadata, dict) else None
        return _render_files_changed_table(item.content, files if isinstance(files, list) else None)
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
        if isinstance(item.metadata, dict) and item.metadata.get("diff_preview"):
            return None
        status = _status_badge(item.status)
        lines = [
            f"{role_prefix}[bold #d7ba7d]Needs your approval[/] {status}",
        ]
        if item.detail:
            lines.append(f"  [#cfd3dc]{_safe_text(item.detail)}[/]")
        if item.content:
            lines.append(_indent_block(colorize_diff_for_tui(item.content)))
        return "\n".join(lines)
    if item.event_type == "approval_resolved":
        status = _status_badge(item.status)
        title = _approval_resolved_title(item.status)
        color = "#ff8f8f" if item.status == "denied" else "#8fd6a3"
        lines = [f"{role_prefix}[bold {color}]{title}[/] {status}"]
        if item.detail:
            lines.append(f"  [#8b949e]{_safe_text(item.detail)}[/]")
        if item.status == "denied":
            lines.append("  [#ff8f8f]Task stopped because this approval was denied.[/]")
        return "\n".join(lines)
    if item.event_type in {"subagent_started", "subagent_finished"}:
        status = _status_badge(item.status)
        detail = _detail_line(item.detail)
        skills = _skills_suffix(item.metadata.get("skills") if isinstance(item.metadata, dict) else None)
        return _activity_line("@", "#9cdcfe", role_prefix, item, f"{skills}{status}", detail)
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


def _activity_summary(
    activities: list[tuple[TimelineItem, TimelineItem | None, str]],
) -> str:
    """Return a Codex-like summary for a contiguous run of tool activity."""
    explored_files: set[str] = set()
    edited_files: set[str] = set()
    searches = 0
    commands = 0
    git_checks = 0
    other = 0

    for start, _end, _role_prefix in activities:
        tool = start.tool_name or ""
        title = (start.title or "").lower()
        files = [path for path in start.file_paths if path]
        if tool in {"read_file", "read_many_files", "list_files"} or "read file" in title:
            explored_files.update(files or [_tool_target_plain(start)])
        elif tool == "grep" or "search" in title:
            searches += 1
        elif tool in {"apply_patch", "edit_file", "write_file"}:
            edited_files.update(files or [_tool_target_plain(start)])
        elif tool in {"bash", "verify"}:
            commands += 1
        elif tool in {"git_diff", "git_show", "workspace_state"}:
            git_checks += 1
        elif tool != "todo":
            other += 1

    parts: list[str] = []
    if edited_files:
        parts.append(_plural(len([path for path in edited_files if path]), "Edited {n} file", "Edited {n} files"))
    if explored_files:
        parts.append(_plural(len([path for path in explored_files if path]), "explored {n} file", "explored {n} files"))
    if searches:
        parts.append(_plural(searches, "{n} search", "{n} searches"))
    if commands:
        parts.append(_plural(commands, "ran {n} command", "ran {n} commands"))
    if git_checks:
        parts.append(_plural(git_checks, "inspected git", "inspected git {n} times"))
    if other:
        parts.append(_plural(other, "used {n} tool", "used {n} tools"))
    return ", ".join(parts)


def _plural(count: int, singular: str, plural: str) -> str:
    template = singular if count == 1 else plural
    return template.format(n=count)


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
    title = _tool_activity_line(start, end, status)
    color = "#ff8f8f" if status == "failed" else "#cfd3dc"
    lines = [f"{role_prefix}[{color}]{title}[/]"]
    if start and _should_show_tool_input(start):
        args = start.metadata.get("args") if isinstance(start.metadata, dict) else None
        lines.append(f"  [#7f8794]Input[/] {_format_args(args)}")
    if end and end.elapsed_ms is not None:
        lines.append(f"  [#7f8794]{_format_duration(end.elapsed_ms)}[/]")
    elif status == "running":
        lines.append("  [#7f8794]in progress[/]")
    return "\n".join(lines)


def _tool_activity_line(
    start: TimelineItem | None,
    end: TimelineItem | None,
    status: str,
) -> str:
    item = start or end
    if item is None:
        return "Used tool"
    tool_name = item.tool_name or ""
    title_text = (item.title or "").lower()
    target = _tool_target_plain(item)
    args = item.metadata.get("args") if isinstance(item.metadata, dict) else {}
    if status == "failed":
        prefix = "Failed"
    elif tool_name in {"apply_patch", "edit_file", "write_file"}:
        prefix = "Edited"
    elif tool_name in {"read_file", "read_many_files"} or "read file" in title_text:
        prefix = "Read"
    elif tool_name == "grep" or "search" in title_text:
        pattern = args.get("pattern") if isinstance(args, dict) else None
        path = args.get("path") if isinstance(args, dict) else None
        scope = f" in {path}" if path else ""
        return _safe_text(f"Searched for {pattern or target}{scope}")
    elif tool_name in {"bash", "verify"}:
        command = _command_for_tool(item)
        return _safe_text(f"Ran {command or target or item.title or tool_name}")
    elif tool_name in {"git_diff", "git_show", "workspace_state"}:
        prefix = "Inspected"
    elif tool_name == "list_files":
        prefix = "Listed"
    elif tool_name == "subagent":
        prefix = "Delegated"
    else:
        prefix = "Used"
    return _safe_text(" ".join(part for part in [prefix, target or item.title or tool_name] if part))


def _should_show_tool_input(item: TimelineItem) -> bool:
    """Return whether args are useful enough to show in the compact activity line."""
    if not isinstance(item.metadata, dict):
        return False
    args = item.metadata.get("args")
    if not isinstance(args, dict) or not args:
        return False
    return (item.tool_name or "") not in {
        "read_file",
        "read_many_files",
        "grep",
        "apply_patch",
        "edit_file",
        "write_file",
        "bash",
        "verify",
        "git_diff",
        "git_show",
        "workspace_state",
        "list_files",
    }


def _command_for_tool(item: TimelineItem) -> str:
    if isinstance(item.metadata, dict):
        command = item.metadata.get("command")
        if command:
            return str(command)
        args = item.metadata.get("args")
        if isinstance(args, dict):
            return str(args.get("command") or args.get("target") or args.get("kind") or "")
    return item.detail or item.content


def _tool_target_plain(item: TimelineItem) -> str:
    if item.file_paths:
        return ", ".join(path for path in item.file_paths if path)
    if item.detail and item.detail != item.tool_name:
        return item.detail
    if item.content and item.content != item.tool_name:
        return item.content
    return ""


def _human_tool_result_title(item: TimelineItem) -> str:
    title = (item.title or "").lower()
    if item.metadata.get("approval_preview") if isinstance(item.metadata, dict) else False:
        return "Review full diff before approval"
    if "diff" in title or item.content.startswith(("diff --git", "--- ", "@@")):
        return "Review full diff"
    if "task state" in title or "task plan" in title:
        return "Task plan"
    return item.title or "Tool result"


def _is_task_state_result(item: TimelineItem) -> bool:
    title = (item.title or "").strip().lower()
    return title in {"task state", "task plan"} or item.content.startswith("Task State:")


def _render_task_state_summary(role_prefix: str, item: TimelineItem) -> str:
    counts = _task_state_counts(item.content)
    summary = "Task plan"
    if counts["total"]:
        summary = f"{counts['completed']}/{counts['total']} done"
        if counts["active"]:
            summary += " · current"
    lines = [
        f"{role_prefix}[bold #8fd6a3]● Task Plan[/]",
        f"  [#7f8794]{_safe_text(summary)}[/]",
    ]
    if counts["active"]:
        lines.append(f"  [#d7dae0]{_safe_text(counts['active'])}[/]")
    lines.append("  [#7f8794]Ctrl+T full plan[/]")
    return "\n".join(lines)


def _task_state_counts(content: str) -> dict[str, int | str]:
    total = 0
    completed = 0
    active = ""
    for line in content.splitlines():
        match = re.match(r"\[(?P<status>[Xx~ ])\]\s+\[(?P<id>[^\]]+)\]\s+(?P<text>.+)", line.strip())
        if not match:
            continue
        total += 1
        status = match.group("status")
        if status.lower() == "x":
            completed += 1
        elif status == "~" and not active:
            active = match.group("text").strip()
    return {"total": total, "completed": completed, "active": active}


def _render_changed_files_summary(diff: str) -> str:
    stats = _diff_file_stats(diff)
    if not stats:
        return ""
    total_added = sum(item["added"] for item in stats)
    total_removed = sum(item["removed"] for item in stats)
    file_label = "file" if len(stats) == 1 else "files"
    lines = [
        (
            f"[bold #f0f2f5]{len(stats)} {file_label} changed[/] "
            f"[#8fd6a3]+{total_added}[/] [#ff8f8f]-{total_removed}[/] "
            f"[#7f8794]Review[/]"
        )
    ]
    path_width = min(max(len(item["path"]) for item in stats), 48)
    for item in stats:
        path = _safe_text(_plain_truncate_middle(item["path"], path_width), path_width + 3)
        padding = " " * max(2, path_width - len(_strip_markup(path)) + 2)
        lines.append(
            f"[#d7dae0]{path}[/]{padding}"
            f"[#8fd6a3]+{item['added']}[/] [#ff8f8f]-{item['removed']}[/]"
        )
    return "\n".join(lines)


def _render_files_changed_table(diff: str, files: list[dict] | None = None) -> str:
    stats = files or _diff_file_stats(diff)
    if not stats:
        return ""
    total_added = sum(int(item.get("added", 0) or 0) for item in stats)
    total_removed = sum(int(item.get("removed", 0) or 0) for item in stats)
    file_label = "file" if len(stats) == 1 else "files"
    lines = [
        (
            f"[bold #f0f2f5]{len(stats)} {file_label} changed[/] "
            f"[#8fd6a3]+{total_added}[/] [#ff8f8f]-{total_removed}[/]"
        ),
        "[#7f8794]Ctrl+D open changed files and diffs[/]",
        "",
    ]
    path_width = min(max(len(str(item.get("path", ""))) for item in stats), 56)
    for item in stats:
        path = _safe_text(_plain_truncate_middle(str(item.get("path", "")), path_width), path_width + 3)
        padding = " " * max(2, path_width - len(_strip_markup(path)) + 2)
        lines.append(
            f"[#d7dae0]{path}[/]{padding}"
            f"[#8fd6a3]+{int(item.get('added', 0) or 0)}[/] [#ff8f8f]-{int(item.get('removed', 0) or 0)}[/]"
        )
    return "\n".join(lines)


def _diff_file_stats(diff: str) -> list[dict[str, int | str]]:
    """Return per-file added/removed counts from a unified diff."""
    stats: list[dict[str, int | str]] = []
    current: dict[str, int | str] | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                stats.append(current)
            current = {"path": _path_from_diff_header(line), "added": 0, "removed": 0}
            continue
        if line.startswith("--- "):
            if current is not None and (int(current["added"]) or int(current["removed"])):
                stats.append(current)
                current = {"path": _strip_diff_prefix(line[4:].split("\t", 1)[0].strip()), "added": 0, "removed": 0}
            elif current is None:
                current = {"path": _strip_diff_prefix(line[4:].split("\t", 1)[0].strip()), "added": 0, "removed": 0}
            continue
        if current is None:
            continue
        if line.startswith("+++ "):
            path = _path_from_file_marker(line, "+++ ")
            if path != "/dev/null":
                current["path"] = path
            continue
        if line.startswith("--- ") or line.startswith("@@") or line.startswith("index "):
            continue
        if line.startswith("+"):
            current["added"] = int(current["added"]) + 1
        elif line.startswith("-"):
            current["removed"] = int(current["removed"]) + 1
    if current is not None:
        stats.append(current)
    return [item for item in stats if int(item["added"]) or int(item["removed"])]


def _path_from_diff_header(line: str) -> str:
    parts = line.split()
    if len(parts) >= 4:
        return _strip_diff_prefix(parts[3])
    return "file"


def _path_from_file_marker(line: str, prefix: str) -> str:
    raw = line[len(prefix):].split("\t", 1)[0].strip()
    return _strip_diff_prefix(raw)


def _strip_diff_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def _plain_truncate_middle(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    if limit <= 3:
        return "." * limit
    head = max(1, (limit - 3) // 2)
    tail = max(1, limit - 3 - head)
    return f"{text[:head]}...{text[-tail:]}"


def _strip_markup(text: str) -> str:
    return re.sub(r"(?<!\\)\[/?[^]]*\]", "", text)


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
    formatted = _format_args_plain(args)
    if formatted == "{}":
        return "[#7f8794]{}[/]"
    return f"[#8b949e]{_safe_text(formatted)}[/]"


def _format_args_plain(args: object) -> str:
    if not isinstance(args, dict) or not args:
        return "{}"
    parts = []
    for key, value in list(args.items())[:5]:
        parts.append(f"{_safe_text(key)}={_format_arg_value(value)}")
    suffix = " ..." if len(args) > 5 else ""
    return f"{', '.join(parts)}{suffix}"


def _format_arg_value(value: object) -> str:
    """Format tool argument values for compact human-readable display."""
    if isinstance(value, str):
        return _safe_text(value, 120)
    if isinstance(value, (int, float, bool)) or value is None:
        return _safe_text(value)
    if isinstance(value, list):
        items = [_format_arg_value(item) for item in value[:4]]
        suffix = ", ..." if len(value) > 4 else ""
        return f"{', '.join(items)}{suffix}"
    if isinstance(value, tuple):
        items = [_format_arg_value(item) for item in value[:4]]
        suffix = ", ..." if len(value) > 4 else ""
        return f"{', '.join(items)}{suffix}"
    if isinstance(value, dict):
        parts = []
        for key, item in list(value.items())[:4]:
            parts.append(f"{_safe_text(key)}: {_format_arg_value(item)}")
        suffix = ", ..." if len(value) > 4 else ""
        return "{" + ", ".join(parts) + suffix + "}"
    return _safe_repr(value, 120)


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


def _skills_suffix(skills: object) -> str:
    if not isinstance(skills, list) or not skills:
        return ""
    names = []
    for skill in skills:
        name = str(skill).strip().lstrip("/")
        if name and name not in names:
            names.append(name)
    if not names:
        return ""
    rendered = " ".join(f"/{_safe_text(name)}" for name in names)
    return f"[#7f8794]using[/] [#c9a6ff]{rendered}[/] "


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
