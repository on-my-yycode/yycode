"""Textual application entrypoint for yoyoagent."""

from __future__ import annotations

from argparse import Namespace


MIN_INPUT_RULE_WIDTH = 40
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


def _safe_text(value: object, limit: int | None = None) -> str:
    """Return dynamic content escaped for Textual/Rich markup."""
    text = str(value)
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text.replace("[", r"\[")


def run_tui(args: Namespace) -> None:
    """Launch the Textual app."""
    try:
        from textual import events
        from textual.app import App, ComposeResult
        from textual.containers import Container, Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import Button, RichLog, Static, TextArea
    except ImportError as exc:  # pragma: no cover - depends on optional runtime dep
        raise RuntimeError(
            "Textual is required for the TUI. Install project dependencies before running."
        ) from exc

    from .renderers import (
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
            ("escape", "close_task_plan", "Back"),
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
                "[bold #c9a6ff]Task Plan[/] [#7f8794]Esc/Ctrl+T back[/]",
                "",
                render_task_plan_panel(self.state),
            ]
            body.update("\n".join(lines))

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
            self._skill_suggestions: list[tuple[str, str]] = []
            self._skill_suggestion_index = 0
            self._skill_completion_open = False

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
                Container(
                    Container(
                        Static("", id="approval-title"),
                        Static("", id="approval-detail"),
                        Static("[#7f8794]Y/Enter approve | N/Esc deny | Ctrl+T task plan[/]", id="approval-hint"),
                        Horizontal(
                            Button("[Y] Approve", id="approve", variant="success"),
                            Button("[N] Deny", id="deny", variant="error"),
                            id="approval-actions",
                        ),
                        id="approval-panel",
                    ),
                    id="approval-wrapper",
                ),
                id="root-layout",
            )

        async def on_mount(self) -> None:
            self._refresh_all()
            self.query_one("#prompt-input", TextArea).disabled = True
            self.set_interval(1.0, self._refresh_status_tick)
            self.set_interval(0.12, self._refresh_progress_tick)
            self.run_worker(self._initialize_session(), exclusive=True)

        async def on_unmount(self) -> None:
            await self.runner.close()

        def on_key(self, event: events.Key) -> None:
            if self._skill_completion_open:
                if event.key in {"up", "ctrl+p"}:
                    self._move_skill_selection(-1)
                    event.prevent_default()
                    event.stop()
                    return
                if event.key in {"down", "ctrl+n"}:
                    self._move_skill_selection(1)
                    event.prevent_default()
                    event.stop()
                    return
                if event.key in {"enter", "tab"}:
                    self._complete_selected_skill()
                    event.prevent_default()
                    event.stop()
                    return
                if event.key == "escape":
                    self._hide_skill_completion()
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

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "approve":
                self._resolve_current_approval(True)
                event.stop()
            elif event.button.id == "deny":
                self._resolve_current_approval(False)
                event.stop()

        def on_text_area_changed(self, event: TextArea.Changed) -> None:
            if event.text_area.id != "prompt-input":
                return
            self._update_skill_completion(event.text_area.text)

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
            self._hide_skill_completion()
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

        def action_timeline_line_up(self) -> None:
            if self._skill_completion_open:
                self._move_skill_selection(-1)
                return
            self._scroll_timeline_relative(-1)

        def action_timeline_line_down(self) -> None:
            if self._skill_completion_open:
                self._move_skill_selection(1)
                return
            self._scroll_timeline_relative(1)

        async def _on_stream_event(self, _event) -> None:
            self.call_after_refresh(self._refresh_all)

        def _refresh_status_tick(self) -> None:
            if self.runner.state.active_task.get("is_running"):
                self._refresh_all()

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

        def _refresh_all(self) -> None:
            state = self.runner.state
            self._refresh_status_surfaces()

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
                # Always scroll to end when there's new content
                self.call_after_refresh(lambda: self._scroll_to_end(timeline_panel))

            self._refresh_input_rules()
            self._update_skill_completion(self.query_one("#prompt-input", TextArea).text)
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
            self._force_follow_timeline = False
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
            timeline.scroll_end(animate=False)

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
            rule_width = max(MIN_INPUT_RULE_WIDTH, self.size.width - 4)
            rule = "-" * rule_width
            self.query_one("#input-top-rule", Static).update(rule)
            self.query_one("#input-bottom-rule", Static).update(rule)

        def _update_skill_completion(self, text: str) -> None:
            token = self._skill_completion_token(text)
            if token is None:
                self._hide_skill_completion()
                return

            suggestions = self._matching_skills(token)
            if not suggestions:
                self._hide_skill_completion()
                return

            if suggestions != self._skill_suggestions:
                self._skill_suggestions = suggestions
                self._skill_suggestion_index = 0
            else:
                self._skill_suggestion_index = min(
                    self._skill_suggestion_index,
                    max(0, len(self._skill_suggestions) - 1),
                )
            self._skill_completion_open = True
            panel = self.query_one("#skill-completion", Static)
            panel.display = True
            panel.update(self._render_skill_completion())

        def _hide_skill_completion(self) -> None:
            self._skill_completion_open = False
            self._skill_suggestions = []
            self._skill_suggestion_index = 0
            panel = self.query_one("#skill-completion", Static)
            panel.display = False
            panel.update("")

        def _skill_completion_token(self, text: str) -> str | None:
            if "\n" in text:
                return None
            if not text.startswith("/"):
                return None
            first = text.split(" ", 1)[0]
            if first != text:
                return None
            return first[1:].strip().lower()

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

        def _render_skill_completion(self) -> str:
            lines = ["[#7f8794]skills[/] [#555d6b]Up/Down select · Enter/Tab complete · Esc close[/]"]
            for index, (name, description) in enumerate(self._skill_suggestions):
                selected = index == self._skill_suggestion_index
                marker = ">" if selected else " "
                name_style = "bold #c9a6ff" if selected else "#d7dae0"
                desc_style = "#a1a8b3" if selected else "#6f7785"
                detail = f" [{desc_style}]{_safe_text(description, 70)}[/]" if description else ""
                lines.append(f"[#7f8794]{marker}[/] [{name_style}]/{_safe_text(name)}[/]{detail}")
            return "\n".join(lines)

        def _move_skill_selection(self, delta: int) -> None:
            if not self._skill_suggestions:
                return
            self._skill_suggestion_index = (
                self._skill_suggestion_index + delta
            ) % len(self._skill_suggestions)
            self.query_one("#skill-completion", Static).update(self._render_skill_completion())

        def _complete_selected_skill(self) -> None:
            if not self._skill_suggestions:
                self._hide_skill_completion()
                return
            skill_name = self._skill_suggestions[self._skill_suggestion_index][0]
            input_widget = self.query_one("#prompt-input", TextArea)
            completion = f"/{skill_name} "
            input_widget.load_text(completion)
            input_widget.move_cursor((0, len(completion)))
            self._hide_skill_completion()
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
            self.query_one("#approval-title", Static).update(
                f"[bold #c9a6ff]Approval required[/] [#7f8794]{_safe_text(approval.tool_name or '')}[/]"
            )
            self.query_one("#approval-detail", Static).update(
                f"[#d7dae0]{_safe_text(approval.title, 46)}[/]\n[#8b949e]{_safe_text(approval.detail, 46)}[/]"
            )
            wrapper = self.query_one("#approval-wrapper", Container)
            wrapper.display = True
            self.query_one("#approve", Button).focus()

        def _hide_approval_panel(self) -> None:
            self._approval_open = False
            self._current_approval = None
            self.query_one("#approval-wrapper", Container).display = False
            input_widget = self.query_one("#prompt-input", TextArea)
            if not input_widget.disabled:
                input_widget.focus()

        def _resolve_current_approval(self, approved: bool) -> None:
            approval = self._current_approval
            if approval is None:
                return
            self.runner.resolve_approval(approval.approval_id, approved)
            self._hide_approval_panel()
            self._refresh_all()

    YoyoTuiApp(args).run()
