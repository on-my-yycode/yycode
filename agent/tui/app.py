"""Textual application entrypoint for yoyoagent."""

from __future__ import annotations

from argparse import Namespace

from agent.message_context_manager import ContextBlockStat, MessageTokenStat
from tools import TOOLS


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
MAX_SKILL_SUGGESTIONS = 8
SUBAGENT_ROLE_DESCRIPTIONS = {
    "explorer": "investigate codebase",
    "architect": "design technical approach",
    "worker": "implement focused changes",
    "tester": "verify and test",
    "security": "review security risks",
}


def _safe_text(value: object, limit: int | None = None) -> str:
    """Return dynamic content escaped for Textual/Rich markup."""
    text = str(value)
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text.replace("[", r"\[")


def _is_submit_key_event(event: object) -> bool:
    """Return whether a Textual key event should submit the prompt."""
    names = {
        str(getattr(event, "key", "") or "").lower(),
        str(getattr(event, "name", "") or "").lower(),
    }
    return bool(names & {"ctrl+enter", "ctrl+j"})


def _is_changed_files_key_event(event: object) -> bool:
    names = {
        str(getattr(event, "key", "") or "").lower(),
        str(getattr(event, "name", "") or "").lower(),
    }
    return "ctrl+d" in names


def _is_message_tokens_key_event(event: object) -> bool:
    names = {
        str(getattr(event, "key", "") or "").lower(),
        str(getattr(event, "name", "") or "").lower(),
    }
    return "ctrl+m" in names


def _completion_context(
    text: str,
    cursor_location: tuple[int, int],
) -> tuple[str, str, tuple[int, int], tuple[int, int]] | None:
    """Return completion kind, token, start and end locations at the cursor."""
    row, column = cursor_location
    lines = text.split("\n")
    if row < 0 or row >= len(lines):
        return None
    line = lines[row]
    column = max(0, min(column, len(line)))
    start = column
    while start > 0 and not line[start - 1].isspace():
        start -= 1
    token = line[start:column]
    if not token or token[0] not in {"/", "@"}:
        return None
    kind = "skill" if token[0] == "/" else "role"
    return kind, token[1:].strip().lower(), (row, start), (row, column)


def _indent_diff_for_panel(diff: str) -> str:
    if not diff:
        return ""
    return "\n".join(f"  {line}" if line else "" for line in diff.splitlines())


def _format_tokens_short(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}m"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def run_tui(args: Namespace) -> None:
    """Launch the Textual app."""
    try:
        from textual import events
        from textual.app import App, ComposeResult
        from textual.containers import Container, Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import Label, ListItem, ListView, RichLog, Static, TextArea
    except ImportError as exc:  # pragma: no cover - depends on optional runtime dep
        raise RuntimeError(
            "Textual is required for the TUI. Install project dependencies before running."
        ) from exc

    from .renderers import (
        colorize_diff_for_tui,
        render_brand_text,
        render_status_bar_text,
        render_task_plan_panel,
        render_timeline_lines,
    )
    from .runner import AgentTuiRunner
    from .state import MAX_TIMELINE_ITEMS, PendingApproval, TuiState


    class TaskPlanScreen(ModalScreen[None]):
        """Full task plan viewer."""

        BINDINGS = [
            ("ctrl+t", "close_task_plan", "Back"),
        ]

        def __init__(self, state: TuiState) -> None:
            super().__init__()
            self.state = state

        def compose(self) -> ComposeResult:
            yield Container(
                Static("", id="task-plan-body"),
                id="task-plan-dialog",
            )

        def on_mount(self) -> None:
            self.set_interval(0.5, self.refresh_task_plan)
            self.refresh_task_plan()

        def action_close_task_plan(self) -> None:
            self.dismiss(None)

        def refresh_task_plan(self) -> None:
            body = self.query_one("#task-plan-body", Static)
            lines = [
                "[bold #c9a6ff]Task Plan[/] [#7f8794]Press Ctrl+T to close[/]",
                "",
                render_task_plan_panel(self.state),
            ]
            body.update("\n".join(lines))

    class ChangedFilesScreen(ModalScreen[None]):
        """Changed files and per-file diff viewer."""

        BINDINGS = [
            ("ctrl+d", "close_changed_files", "Back"),
            ("up", "move_selection_up", "Up"),
            ("down", "move_selection_down", "Down"),
            ("enter", "toggle_file", "Toggle"),
            ("space", "toggle_file", "Toggle"),
        ]

        def __init__(self, state: TuiState) -> None:
            super().__init__()
            self.state = state
            self.selected_index = 0

        def compose(self) -> ComposeResult:
            yield Container(
                Static("", id="changed-files-header"),
                Horizontal(
                    ListView(id="changed-files-list"),
                    RichLog(
                        markup=True,
                        wrap=True,
                        highlight=False,
                        auto_scroll=False,
                        id="changed-files-diff",
                    ),
                    id="changed-files-split",
                ),
                id="changed-files-dialog",
            )

        def on_mount(self) -> None:
            self.refresh_changed_files()

        def action_close_changed_files(self) -> None:
            self.dismiss(None)

        def action_move_selection_up(self) -> None:
            if self.state.latest_changed_file_diffs:
                self.selected_index = (self.selected_index - 1) % len(self.state.latest_changed_file_diffs)
                self._sync_file_selection()

        def action_move_selection_down(self) -> None:
            if self.state.latest_changed_file_diffs:
                self.selected_index = (self.selected_index + 1) % len(self.state.latest_changed_file_diffs)
                self._sync_file_selection()

        def action_toggle_file(self) -> None:
            files = self.state.latest_changed_file_diffs
            if not files:
                return
            current = files[self.selected_index]
            current.collapsed = not current.collapsed
            self._refresh_diff_view()

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            files = self.state.latest_changed_file_diffs
            if event.list_view.id != "changed-files-list" or event.item is None or not files:
                return
            index = event.list_view.index or 0
            if 0 <= index < len(files):
                self.selected_index = index
                self._refresh_diff_view()

        def refresh_changed_files(self) -> None:
            header = self.query_one("#changed-files-header", Static)
            file_list = self.query_one("#changed-files-list", ListView)
            diff_view = self.query_one("#changed-files-diff", RichLog)
            files = self.state.latest_changed_file_diffs
            if not files:
                header.update("[bold #c9a6ff]Changed Files[/] [#7f8794]Press Ctrl+D to close[/]")
                file_list.clear()
                diff_view.clear()
                diff_view.write("[#7f8794]No changed files for the latest task.[/]")
                return
            total_added = sum(item.added for item in files)
            total_removed = sum(item.removed for item in files)
            header.update(
                f"[bold #c9a6ff]Changed Files[/] [#7f8794]Press Ctrl+D to close · click/select files · Enter fold[/] "
                f"[#7f8794]{len(files)} files[/] [#8fd6a3]+{total_added}[/] [#ff8f8f]-{total_removed}[/]"
            )
            file_list.clear()
            for item in files:
                file_list.append(
                    ListItem(
                        Label(
                            f"{_safe_text(item.path, 42)}  [#8fd6a3]+{item.added}[/] [#ff8f8f]-{item.removed}[/]"
                        )
                    )
                )
            self.selected_index = min(self.selected_index, len(files) - 1)
            self._sync_file_selection()

        def _sync_file_selection(self) -> None:
            file_list = self.query_one("#changed-files-list", ListView)
            file_list.index = self.selected_index
            file_list.focus()
            self._refresh_diff_view()

        def _refresh_diff_view(self) -> None:
            files = self.state.latest_changed_file_diffs
            diff_view = self.query_one("#changed-files-diff", RichLog)
            diff_view.clear()
            if not files:
                return
            item = files[self.selected_index]
            fold = "collapsed" if item.collapsed else "expanded"
            diff_view.write(
                f"[bold #f0f2f5]{_safe_text(item.path)}[/] "
                f"[#8fd6a3]+{item.added}[/] [#ff8f8f]-{item.removed}[/] "
                f"[#7f8794]{fold} · Enter/Space toggle[/]\n"
            )
            if item.collapsed:
                diff_view.write("[#7f8794]Diff hidden.[/]")
                return
            diff_view.write(_indent_diff_for_panel(colorize_diff_for_tui(item.diff)))
            diff_view.scroll_home(animate=False)

    class MessageTokenManagerScreen(ModalScreen[None]):
        """Current session message token manager."""

        BINDINGS = [
            ("ctrl+m", "close_message_tokens", "Back"),
            ("up", "move_selection_up", "Up"),
            ("down", "move_selection_down", "Down"),
            ("c", "compress_selected", "Compress selected"),
            ("a", "compress_suggested", "Compress suggested"),
        ]

        def __init__(self, runner: AgentTuiRunner) -> None:
            super().__init__()
            self.runner = runner
            self.selected_index = 0
            self.blocks: list[ContextBlockStat] = []
            self.stats: list[MessageTokenStat] = []
            self.summary = None
            self.suggestions = []
            self.pending_compression_indexes: list[int] = []
            self.pending_compression_action = ""

        def compose(self) -> ComposeResult:
            yield Container(
                Static("", id="message-token-header"),
                Horizontal(
                    ListView(id="message-token-list"),
                    RichLog(
                        markup=True,
                        wrap=True,
                        highlight=False,
                        auto_scroll=False,
                        id="message-token-detail",
                    ),
                    id="message-token-split",
                ),
                Static("↑↓ select · C compress selected · A compress suggested · Ctrl+M close", id="message-token-footer"),
                id="message-token-dialog",
            )

        async def on_mount(self) -> None:
            await self.refresh_message_tokens()

        def action_close_message_tokens(self) -> None:
            self.dismiss(None)

        def action_move_selection_up(self) -> None:
            entries = self._entries()
            if entries:
                self._clear_pending_compression()
                self.selected_index = (self.selected_index - 1) % len(entries)
                self._sync_selection()

        def action_move_selection_down(self) -> None:
            entries = self._entries()
            if entries:
                self._clear_pending_compression()
                self.selected_index = (self.selected_index + 1) % len(entries)
                self._sync_selection()

        async def action_compress_selected(self) -> None:
            entry = self._selected_entry()
            if not isinstance(entry, MessageTokenStat) or not entry.compressible:
                self.notify("Selected message is not compressible.", severity="warning")
                self._clear_pending_compression()
                return
            await self._request_or_confirm_compression([entry.index], "selected", "C")

        async def action_compress_suggested(self) -> None:
            indexes = [index for suggestion in self.suggestions for index in suggestion.message_indexes]
            if not indexes:
                self.notify("No compression suggestions.", severity="information")
                self._clear_pending_compression()
                return
            await self._request_or_confirm_compression(indexes, "suggested", "A")

        async def _request_or_confirm_compression(
            self,
            indexes: list[int],
            action: str,
            key_hint: str,
        ) -> None:
            unique_indexes = sorted(set(indexes))
            if self.pending_compression_indexes == unique_indexes and self.pending_compression_action == action:
                compressed = await self.runner.compress_message_context(unique_indexes)
                self.notify(f"Compressed {compressed} message(s).", severity="information")
                self._clear_pending_compression()
                await self.refresh_message_tokens()
                return
            self.pending_compression_indexes = unique_indexes
            self.pending_compression_action = action
            self.notify(
                f"Press {key_hint} again to confirm compressing {len(unique_indexes)} message(s).",
                severity="warning",
            )
            self._refresh_detail()

        def _clear_pending_compression(self) -> None:
            self.pending_compression_indexes = []
            self.pending_compression_action = ""

        def _pending_hint(self) -> str:
            if not self.pending_compression_indexes:
                return ""
            indexes = ", ".join(str(index) for index in self.pending_compression_indexes[:6])
            if len(self.pending_compression_indexes) > 6:
                indexes += ", ..."
            key_hint = "A" if self.pending_compression_action == "suggested" else "C"
            return (
                f"\n[#d7ba7d]Confirm compression:[/] press {key_hint} again to compact "
                f"{len(self.pending_compression_indexes)} message(s): {indexes}."
            )

        def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
            if event.list_view.id != "message-token-list" or event.item is None:
                return
            self.selected_index = event.list_view.index or 0
            self._refresh_detail()

        async def refresh_message_tokens(self) -> None:
            session = self.runner.session
            header = self.query_one("#message-token-header", Static)
            item_list = self.query_one("#message-token-list", ListView)
            detail = self.query_one("#message-token-detail", RichLog)
            if session is None:
                header.update("[bold #c9a6ff]Message Token Manager[/] [#7f8794]Press Ctrl+M to close[/]")
                item_list.clear()
                detail.clear()
                detail.write("[#7f8794]Session is not ready.[/]")
                return
            self.summary = await self.runner.analyze_message_context()
            manager = session.message_context_manager
            self.blocks = manager.context_blocks(session.system_prompt, TOOLS)
            self.stats = manager.message_stats(session.messages)
            self.suggestions = manager.suggest_compression(session.messages)
            header.update(self._render_header())
            item_list.clear()
            for entry in self._entries():
                item_list.append(ListItem(Label(self._entry_label(entry))))
            self.selected_index = min(self.selected_index, max(0, len(self._entries()) - 1))
            self._sync_selection()

        def _render_header(self) -> str:
            if self.summary is None:
                return "[bold #c9a6ff]Message Tokens[/]\n[#7f8794]Loading current session context...[/]"
            total = _format_tokens_short(self.summary.total_tokens)
            window = _format_tokens_short(self.summary.context_window_tokens)
            remaining = _format_tokens_short(self.summary.remaining_tokens)
            savings = _format_tokens_short(self.summary.compression_savings_estimate)
            percent = self._context_percent()
            bar = self._usage_bar(percent)
            pressure = str(self.summary.pressure).upper()
            pressure_color = self._pressure_color(str(self.summary.pressure))
            pending = ""
            if self.pending_compression_indexes:
                pending = f"\n[#d7ba7d]⚠ Confirm compression: press {'A' if self.pending_compression_action == 'suggested' else 'C'} again for {len(self.pending_compression_indexes)} message(s).[/]"
            return (
                f"[bold #c9a6ff]Message Tokens[/]  "
                f"[#cfd3dc]{total} / {window}[/]  "
                f"[{pressure_color}]{percent:.0f}% {pressure}[/]\n"
                f"[{pressure_color}]{bar}[/]  "
                f"[#7f8794]remaining[/] [#cfd3dc]{remaining}[/]  "
                f"[#7f8794]save ~[/][#8fd6a3]{savings}[/]  "
                f"[#7f8794]source {self.summary.token_source}[/]"
                f"{pending}"
            )

        def _context_percent(self) -> float:
            if self.summary is None or self.summary.context_window_tokens <= 0:
                return 0.0
            return min((self.summary.total_tokens / self.summary.context_window_tokens) * 100, 100.0)

        def _usage_bar(self, percent: float, width: int = 18) -> str:
            filled = max(0, min(width, int(round(width * percent / 100))))
            return "█" * filled + "░" * (width - filled)

        def _pressure_color(self, pressure: str) -> str:
            return {
                "low": "#8fd6a3",
                "medium": "#d7ba7d",
                "high": "#f97316",
                "critical": "#ff8f8f",
            }.get(pressure.lower(), "#7f8794")

        def _entries(self) -> list[ContextBlockStat | MessageTokenStat]:
            return [*self.blocks, *self.stats]

        def _selected_entry(self) -> ContextBlockStat | MessageTokenStat | None:
            entries = self._entries()
            if not entries:
                return None
            return entries[self.selected_index]

        def _entry_label(self, entry: ContextBlockStat | MessageTokenStat) -> str:
            if isinstance(entry, ContextBlockStat):
                return (
                    f"[#7f8794]◆ protected[/] [#d7dae0]{_safe_text(entry.name, 18):<18}[/] "
                    f"[#cfd3dc]{_format_tokens_short(entry.estimated_tokens):>6}[/] "
                    f"[#7f8794]system[/]"
                )
            marker = "[#d7ba7d]⚠ compress[/]" if entry.compressible else f"[#7f8794]{entry.recommendation}[/]"
            policy = "" if entry.context_policy == "full" else f" [#8fd6a3]{entry.context_policy}[/]"
            ephemeral = f" [#d7ba7d]{entry.ephemeral_kind}[/]" if entry.ephemeral_kind else ""
            return (
                f"[#7f8794]#{entry.index:<3}[/] [#d7dae0]{entry.role:<9}[/] "
                f"[#cfd3dc]{_format_tokens_short(entry.estimated_tokens):>6}[/] "
                f"[#7f8794]{entry.percent:>4.0f}%[/]  "
                f"{marker}{policy}{ephemeral}  [#7f8794]{_safe_text(entry.preview, 34)}[/]"
            )

        def _sync_selection(self) -> None:
            item_list = self.query_one("#message-token-list", ListView)
            item_list.index = self.selected_index
            item_list.focus()
            self._refresh_detail()

        def _refresh_detail(self) -> None:
            detail = self.query_one("#message-token-detail", RichLog)
            detail.clear()
            if self.summary is not None:
                breakdown = "  ".join(
                    f"{key} {_format_tokens_short(value)}"
                    for key, value in sorted(self.summary.by_role.items())
                )
                detail.write(
                    f"[bold #c9a6ff]Session context[/]\n"
                    f"[#7f8794]Usage[/] [#cfd3dc]{_format_tokens_short(self.summary.total_tokens)} / {_format_tokens_short(self.summary.context_window_tokens)}[/]  "
                    f"[{self._pressure_color(str(self.summary.pressure))}]{self._context_percent():.0f}% {str(self.summary.pressure).upper()}[/]\n"
                    f"[#7f8794]Remaining[/] [#cfd3dc]{_format_tokens_short(self.summary.remaining_tokens)}[/]  "
                    f"[#7f8794]Potential saving[/] [#8fd6a3]~{_format_tokens_short(self.summary.compression_savings_estimate)}[/]\n"
                    f"[#7f8794]By role[/] [#cfd3dc]{_safe_text(breakdown or '-')}[/]"
                    f"{self._pending_hint()}\n"
                )
            entry = self._selected_entry()
            if entry is None:
                detail.write("[#7f8794]No messages yet.[/]")
                return
            if isinstance(entry, ContextBlockStat):
                detail.write(
                    f"[bold #f0f2f5]Protected block[/]\n"
                    f"[#7f8794]Name[/]        [#cfd3dc]{_safe_text(entry.name)}[/]\n"
                    f"[#7f8794]Tokens[/]      [#cfd3dc]{_format_tokens_short(entry.estimated_tokens)}[/]\n"
                    f"[#7f8794]Action[/]      [#cfd3dc]Protected, never compressed[/]\n\n"
                    f"[bold #f0f2f5]Preview[/]\n"
                    f"[#7f8794]{_safe_text(entry.preview or '(empty)')}[/]"
                )
                return
            detail.write(
                f"[bold #f0f2f5]Selected message[/]\n"
                f"[#7f8794]Index[/]       [#cfd3dc]#{entry.index}[/]\n"
                f"[#7f8794]Role[/]        [#cfd3dc]{entry.role}[/]\n"
                f"[#7f8794]Type[/]        [#cfd3dc]{entry.message_type}[/]\n"
                f"[#7f8794]Tokens[/]      [#cfd3dc]{_format_tokens_short(entry.estimated_tokens)}[/]  [#7f8794]{entry.percent:.1f}% of context[/]\n"
                f"[#7f8794]Risk[/]        [#cfd3dc]{entry.risk}[/]\n"
                f"[#7f8794]Action[/]      [#cfd3dc]{entry.recommendation}[/]\n\n"
                f"[#7f8794]Policy[/]      [#cfd3dc]{entry.context_policy}[/]\n"
                f"[#7f8794]Ephemeral[/]   [#cfd3dc]{entry.ephemeral_kind or '-'}[/]\n\n"
                f"[bold #f0f2f5]Recommendation[/]\n"
                f"{self._recommendation_text(entry)}\n\n"
                f"[bold #f0f2f5]Preview[/]\n"
                f"[#7f8794]{_safe_text(entry.preview or '(empty)')}[/]"
            )
            if entry.compressible:
                detail.write("\n\n[#d7ba7d]Press C to compact this old tool output. Press C again to confirm.[/]")

        def _recommendation_text(self, entry: MessageTokenStat) -> str:
            if entry.compressible:
                return (
                    "[#d7ba7d]Compress recommended.[/] "
                    "[#7f8794]This is an older tool output and can be replaced with a compact marker to recover context.[/]"
                )
            if entry.protected:
                return "[#7f8794]Protected because it is recent or user-facing context. Keep unchanged.[/]"
            if entry.recommendation == "keep compressed":
                return "[#7f8794]Already compacted. No further action needed.[/]"
            return "[#7f8794]Keep this message. Expected savings are low or the content may still be useful.[/]"

    class YoyoTuiApp(App[None]):
        """Main terminal UI."""

        CSS_PATH = "styles.tcss"
        BINDINGS = [
            ("y", "approve_current", "Approve"),
            ("Y", "approve_current", "Approve"),
            ("n", "deny_current", "Deny"),
            ("N", "deny_current", "Deny"),
            ("enter", "approve_current", "Approve"),
            ("escape", "deny_current", "Deny"),
            ("ctrl+shift+c", "copy_timeline", "Copy timeline"),
            ("ctrl+c", "cancel_task", "Cancel task"),
            ("ctrl+t", "open_task_plan", "Task plan"),
            ("ctrl+d", "open_changed_files", "Changed files"),
            ("ctrl+m", "open_message_tokens", "Message tokens"),
            ("ctrl+enter", "submit_prompt", "Submit"),
            ("ctrl+j", "submit_prompt", "Submit"),
            ("ctrl+q", "quit", "Quit"),
            ("up", "timeline_line_up", "Timeline up"),
            ("down", "timeline_line_down", "Timeline down"),
            ("pageup", "timeline_page_up", "Scroll up"),
            ("pagedown", "timeline_page_down", "Scroll down"),
            ("home", "timeline_home", "Scroll to top"),
            ("end", "timeline_end", "Scroll to bottom"),
        ]

        def __init__(self, args: Namespace) -> None:
            super().__init__()
            self.args = args
            self.runner = AgentTuiRunner(args, on_state_change=self._on_stream_event)
            self._approval_open = False
            self._current_approval: PendingApproval | None = None
            self._session_ready = False
            self._last_timeline_content = ""
            self._progress_frame = 0
            self._completion_kind: str | None = None
            self._completion_range: tuple[tuple[int, int], tuple[int, int]] | None = None
            self._completion_suggestions: list[tuple[str, str]] = []
            self._completion_suggestion_index = 0
            self._completion_open = False

        def compose(self) -> ComposeResult:
            yield Vertical(
                Static("Starting...", id="top-panel"),
                RichLog(
                    markup=True,
                    wrap=True,
                    highlight=False,
                    auto_scroll=False,
                    id="timeline-panel",
                    classes="selectable",
                ),
                Static("", id="skill-completion"),
                Container(
                    Static("", id="input-top-rule"),
                    Container(
                        Static("", id="approval-title"),
                        Static("", id="approval-detail"),
                        Static("", id="approval-actions"),
                        id="approval-inline",
                    ),
                    Horizontal(
                        Static(">", id="input-prompt"),
                        TextArea(
                            "",
                            placeholder="Initializing yoyoagent...",
                            id="prompt-input",
                            compact=True,
                            show_line_numbers=False,
                            highlight_cursor_line=False,
                        ),
                        id="input-row",
                    ),
                    Static("", id="input-bottom-rule"),
                    Static("", id="input-status-bar"),
                    id="input-shell",
                ),
                id="root-layout",
            )

        async def on_mount(self) -> None:
            self._refresh_all()
            self.query_one("#prompt-input", TextArea).disabled = True
            self.set_interval(1.0, self._refresh_status_tick)
            self.set_interval(0.25, self._refresh_progress_tick)
            self.run_worker(self._initialize_session(), exclusive=True)

        async def on_unmount(self) -> None:
            await self.runner.close()

        def on_key(self, event: events.Key) -> None:
            if (
                _is_submit_key_event(event)
                and getattr(self.focused, "id", None) == "prompt-input"
            ):
                event.prevent_default()
                event.stop()
                self.run_worker(self.action_submit_prompt(), exclusive=False)
                return

            if _is_changed_files_key_event(event):
                event.prevent_default()
                event.stop()
                self.action_toggle_changed_files()
                return

            if _is_message_tokens_key_event(event):
                event.prevent_default()
                event.stop()
                self.action_toggle_message_tokens()
                return

            if self._completion_open:
                if event.key in {"up", "ctrl+p"}:
                    self._move_completion_selection(-1)
                    event.prevent_default()
                    event.stop()
                    return
                if event.key in {"down", "ctrl+n"}:
                    self._move_completion_selection(1)
                    event.prevent_default()
                    event.stop()
                    return
                if event.key in {"enter", "tab"}:
                    self._complete_selected_completion()
                    event.prevent_default()
                    event.stop()
                    return
                if event.key == "escape":
                    self._hide_completion()
                    event.prevent_default()
                    event.stop()
                    return

            if not self._approval_open:
                return
            if event.key in {"y", "Y", "enter"}:
                self._resolve_current_approval(True)
                event.prevent_default()
                event.stop()
            elif event.key in {"n", "N", "escape"}:
                self._resolve_current_approval(False)
                event.prevent_default()
                event.stop()

        def on_text_area_changed(self, event: TextArea.Changed) -> None:
            if event.text_area.id != "prompt-input":
                return
            self._update_completion(event.text_area)

        def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
            if self._approval_open:
                return
            self._scroll_timeline_relative(-3)
            event.prevent_default()
            event.stop()

        def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
            if self._approval_open:
                return
            self._scroll_timeline_relative(3)
            event.prevent_default()
            event.stop()

        def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
            if action in {"approve_current", "deny_current"}:
                return self._approval_open
            return True

        async def action_submit_prompt(self) -> None:
            input_widget = self.query_one("#prompt-input", TextArea)
            if not self._session_ready:
                self.notify("Session is still starting up.", severity="warning")
                return
            text = input_widget.text.strip()
            if not text:
                return
            self._hide_completion()
            if text.lower() in {"q", "exit"}:
                await self.action_quit()
                return
            input_widget.load_text("")
            try:
                await self.runner.submit_nowait(text)
            except RuntimeError as exc:
                self.notify(str(exc), severity="warning")
            self._refresh_all()

        async def action_cancel_task(self) -> None:
            cancelled = await self.runner.cancel_current_task()
            if cancelled:
                self.notify("Current task cancelled.")
            self._refresh_all()

        def action_approve_current(self) -> None:
            self._resolve_current_approval(True)

        def action_deny_current(self) -> None:
            self._resolve_current_approval(False)

        def action_open_task_plan(self) -> None:
            self.push_screen(TaskPlanScreen(self.runner.state))

        def action_open_changed_files(self) -> None:
            self.action_toggle_changed_files()

        def action_toggle_changed_files(self) -> None:
            if isinstance(self.screen, ChangedFilesScreen):
                self.pop_screen()
                return
            self.push_screen(ChangedFilesScreen(self.runner.state))

        def action_open_message_tokens(self) -> None:
            self.action_toggle_message_tokens()

        def action_toggle_message_tokens(self) -> None:
            if isinstance(self.screen, MessageTokenManagerScreen):
                self.pop_screen()
                return
            self.push_screen(MessageTokenManagerScreen(self.runner))

        def action_timeline_line_up(self) -> None:
            if self._completion_open:
                self._move_completion_selection(-1)
                return
            self._scroll_timeline_relative(-1)

        def action_timeline_line_down(self) -> None:
            if self._completion_open:
                self._move_completion_selection(1)
                return
            self._scroll_timeline_relative(1)

        async def _on_stream_event(self, event) -> None:
            if getattr(event, "event_type", "") == "task_finished":
                self.call_after_refresh(lambda: self._refresh_all(force_scroll_end=True))
                return
            self.call_after_refresh(self._refresh_all)

        def _refresh_status_tick(self) -> None:
            if self.runner.state.active_task.get("is_running"):
                self._refresh_status_surfaces()

        def _refresh_progress_tick(self) -> None:
            if self.runner.state.active_task.get("is_running"):
                self._progress_frame += 1
                self._refresh_status_surfaces()

        async def _initialize_session(self) -> None:
            try:
                await self.runner.start()
            except Exception as exc:
                self.notify(f"Failed to initialize session: {exc}", severity="error")
                return
            self._session_ready = True
            input_widget = self.query_one("#prompt-input", TextArea)
            input_widget.disabled = False
            input_widget.placeholder = "Ask yoyoagent... Ctrl+Enter send | Ctrl+T task plan"
            input_widget.focus()
            self._refresh_all()

        def _refresh_all(self, *, force_scroll_end: bool = False) -> None:
            state = self.runner.state
            self._refresh_status_surfaces()
            pending_approval = state.next_pending_approval()

            timeline_content = render_timeline_lines(
                state,
                limit=MAX_TIMELINE_ITEMS,
                header_mode="main",
            )

            timeline_panel = self.query_one("#timeline-panel", RichLog)
            if timeline_content != self._last_timeline_content:
                self._last_timeline_content = timeline_content
                timeline_panel.clear()
                timeline_panel.write(timeline_content)
                if (
                    force_scroll_end
                    or pending_approval is not None
                    or (
                        self.runner.state.active_task.get("is_running")
                        and pending_approval is None
                    )
                ):
                    self.call_after_refresh(lambda: self._scroll_to_end(timeline_panel))
            elif force_scroll_end:
                self.call_after_refresh(lambda: self._scroll_to_end(timeline_panel))

            self._refresh_input_rules()
            self._update_completion(self.query_one("#prompt-input", TextArea))
            self._maybe_show_approval_prompt()

        def _refresh_status_surfaces(self) -> None:
            content_width = max(72, self.size.width - 4)
            self.query_one("#top-panel", Static).update(render_brand_text(self.runner.state, content_width))
            self.query_one("#input-status-bar", Static).update(
                render_status_bar_text(
                    self.runner.state,
                    width=content_width,
                    progress_frame=self._progress_frame,
                )
            )

        def _scroll_to_end(self, timeline: RichLog) -> None:
            timeline.scroll_end(animate=False)

        def action_timeline_page_up(self) -> None:
            timeline = self.query_one("#timeline-panel", RichLog)
            timeline.focus()
            step = max(1, timeline.content_size.height // 3)
            timeline.scroll_to(y=max(0, timeline.scroll_y - step), animate=False)

        def action_timeline_page_down(self) -> None:
            timeline = self.query_one("#timeline-panel", RichLog)
            timeline.focus()
            step = max(1, timeline.content_size.height // 3)
            new_y = min(timeline.max_scroll_y, timeline.scroll_y + step)
            timeline.scroll_to(y=new_y, animate=False)

        def action_timeline_home(self) -> None:
            timeline = self.query_one("#timeline-panel", RichLog)
            timeline.focus()
            timeline.scroll_to(y=0, animate=False)

        def action_timeline_end(self) -> None:
            timeline = self.query_one("#timeline-panel", RichLog)
            timeline.focus()
            self._scroll_to_end(timeline)

        def _scroll_timeline_relative(self, amount: int) -> None:
            timeline = self.query_one("#timeline-panel", RichLog)
            timeline.focus()
            new_y = min(timeline.max_scroll_y, max(0, timeline.scroll_y + amount))
            timeline.scroll_to(y=new_y, animate=False)

        def action_focus_input(self) -> None:
            input_widget = self.query_one("#prompt-input", TextArea)
            if not input_widget.disabled:
                input_widget.focus()

        def action_copy_timeline(self) -> None:
            """Copy timeline content to clipboard."""
            try:
                import pyperclip
                # Get the plain text version of timeline content
                timeline_content = self._last_timeline_content
                # Remove Rich markup tags for cleaner copy
                import re
                clean_content = re.sub(r'\[/?[^\]]*\]', '', timeline_content)
                pyperclip.copy(clean_content)
                self.notify("Timeline copied to clipboard!", severity="information")
            except ImportError:
                self.notify("pyperclip not installed. Install with: pip install pyperclip", severity="warning")
            except Exception as e:
                self.notify(f"Failed to copy: {str(e)}", severity="warning")

        def _refresh_input_rules(self) -> None:
            rule_width = max(40, self.size.width - 4)
            rule = "-" * rule_width
            self.query_one("#input-top-rule", Static).update(rule)
            self.query_one("#input-bottom-rule", Static).update(rule)

        def _update_completion(self, input_widget: TextArea) -> None:
            context = _completion_context(input_widget.text, input_widget.cursor_location)
            if context is None:
                self._hide_completion()
                return
            kind, token, start, end = context

            suggestions = self._matching_skills(token) if kind == "skill" else self._matching_roles(token)
            if not suggestions:
                self._hide_completion()
                return

            if (
                kind != self._completion_kind
                or start != (self._completion_range[0] if self._completion_range else None)
                or suggestions != self._completion_suggestions
            ):
                self._completion_suggestions = suggestions
                self._completion_suggestion_index = 0
            else:
                self._completion_suggestion_index = min(
                    self._completion_suggestion_index,
                    max(0, len(self._completion_suggestions) - 1),
                )
            self._completion_kind = kind
            self._completion_range = (start, end)
            self._completion_open = True
            panel = self.query_one("#skill-completion", Static)
            panel.display = True
            panel.update(self._render_completion())

        def _hide_completion(self) -> None:
            self._completion_kind = None
            self._completion_range = None
            self._completion_open = False
            self._completion_suggestions = []
            self._completion_suggestion_index = 0
            panel = self.query_one("#skill-completion", Static)
            panel.display = False
            panel.update("")

        def _matching_skills(self, token: str) -> list[tuple[str, str]]:
            if self.runner.session is None:
                return []
            skills = self.runner.session.skill_registry.list_skills()
            rows = [
                (skill.name, skill.description or "")
                for skill in skills
                if skill.name.lower().startswith(token)
            ]
            if token and not rows:
                rows = [
                    (skill.name, skill.description or "")
                    for skill in skills
                    if token in skill.name.lower()
                ]
            return rows[:MAX_SKILL_SUGGESTIONS]

        def _matching_roles(self, token: str) -> list[tuple[str, str]]:
            roles = list(SUBAGENT_ROLE_DESCRIPTIONS.items())
            rows = [(name, description) for name, description in roles if name.startswith(token)]
            if token and not rows:
                rows = [(name, description) for name, description in roles if token in name]
            return rows

        def _render_completion(self) -> str:
            header = "skills" if self._completion_kind == "skill" else "subagents"
            prefix = "/" if self._completion_kind == "skill" else "@"
            lines = [f"[#7f8794]{header}[/] [#555d6b]Up/Down select · Enter/Tab complete · Esc close[/]"]
            for index, (name, description) in enumerate(self._completion_suggestions):
                selected = index == self._completion_suggestion_index
                marker = ">" if selected else " "
                name_style = "bold #c9a6ff" if selected else "#d7dae0"
                desc_style = "#a1a8b3" if selected else "#6f7785"
                detail = f" [{desc_style}]{_safe_text(description, 70)}[/]" if description else ""
                lines.append(f"[#7f8794]{marker}[/] [{name_style}]{prefix}{_safe_text(name)}[/]{detail}")
            return "\n".join(lines)

        def _move_completion_selection(self, delta: int) -> None:
            if not self._completion_suggestions:
                return
            self._completion_suggestion_index = (
                self._completion_suggestion_index + delta
            ) % len(self._completion_suggestions)
            self.query_one("#skill-completion", Static).update(self._render_completion())

        def _complete_selected_completion(self) -> None:
            if not self._completion_suggestions or self._completion_range is None:
                self._hide_completion()
                return
            name = self._completion_suggestions[self._completion_suggestion_index][0]
            prefix = "/" if self._completion_kind == "skill" else "@"
            input_widget = self.query_one("#prompt-input", TextArea)
            start, end = self._completion_range
            completion = f"{prefix}{name} "
            input_widget.replace(completion, start, end)
            input_widget.move_cursor((start[0], start[1] + len(completion)))
            self._hide_completion()
            input_widget.focus()

        def _maybe_show_approval_prompt(self) -> None:
            approval = self.runner.state.next_pending_approval()
            if approval and not self._approval_open:
                self._show_approval_panel(approval)
            elif approval is None and self._approval_open:
                self._hide_approval_panel()

        def _show_approval_panel(self, approval: PendingApproval) -> None:
            self._approval_open = True
            self._current_approval = approval
            title, detail = self._approval_copy(approval)
            self.query_one("#approval-title", Static).update(
                f"[bold #d7ba7d]{_safe_text(title, 96)}[/]"
            )
            self.query_one("#approval-detail", Static).update(
                f"[#8b949e]{_safe_text(detail, 120)}[/]"
            )
            self.query_one("#approval-actions", Static).update(
                "[#7f8794]Press[/] [#8fd6a3]Y[/][#7f8794]/[/][#8fd6a3]Enter[/] [#7f8794]to approve   Press[/] [#ff8f8f]N[/][#7f8794]/[/][#ff8f8f]Esc[/] [#7f8794]to deny   Ctrl+T task plan[/]"
            )
            self.query_one("#approval-inline", Container).display = True
            self.query_one("#input-row", Horizontal).display = False
            self.query_one("#input-shell", Container).add_class("approving")
            timeline_panel = self.query_one("#timeline-panel", RichLog)
            timeline_panel.focus()
            self.call_after_refresh(lambda: self._scroll_to_end(timeline_panel))

        def _hide_approval_panel(self) -> None:
            self._approval_open = False
            self._current_approval = None
            self.query_one("#approval-inline", Container).display = False
            self.query_one("#input-row", Horizontal).display = True
            self.query_one("#input-shell", Container).remove_class("approving")
            input_widget = self.query_one("#prompt-input", TextArea)
            if not input_widget.disabled:
                input_widget.focus()

        def _approval_copy(self, approval: PendingApproval) -> tuple[str, str]:
            target = approval.detail or ", ".join(approval.file_paths) or approval.tool_name or "this action"
            request_text = approval.request_text
            if "action: run_command" in request_text:
                command = self._approval_field(request_text, "command") or target
                return "Approve command?", command
            if "action: create_file" in request_text:
                path = self._approval_field(request_text, "path") or target
                hint = "Review the preview above" if approval.diff_preview else "File creation requires approval"
                return f"Create {path}?", hint
            if "action: edit_file" in request_text:
                path = self._approval_field(request_text, "path") or target
                hint = "Review the diff above" if approval.diff_preview else "File edit requires approval"
                return f"Approve changes to {path}?", hint
            return "Approve action?", target

        def _approval_field(self, request_text: str, field: str) -> str:
            prefix = f"{field}:"
            for line in request_text.splitlines():
                if line.startswith(prefix):
                    return line[len(prefix):].strip()
            return ""

        def _resolve_current_approval(self, approved: bool) -> None:
            approval = self._current_approval
            if approval is None:
                return
            resolved = self.runner.resolve_approval(approval.approval_id, approved)
            if approved:
                message = "Approved. Continuing task..." if resolved else "Approval was no longer pending."
                severity = "information" if resolved else "warning"
            else:
                message = "Approval denied. Task will stop without applying this change." if resolved else "Approval was no longer pending."
                severity = "warning"
            self.notify(message, severity=severity)
            self._hide_approval_panel()
            self._refresh_all()

    YoyoTuiApp(args).run()
