"""Async bridge between Session and the TUI state."""

from __future__ import annotations

import asyncio
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Awaitable, Callable, Optional

from agent.approval import ApprovalRequest
from agent.cancellation import CancellationController, CancelResult
from agent.change_snapshot import (
    build_changed_files_snapshot,
    changed_files_as_dicts,
    extract_diff_text,
    merge_changed_paths,
    turn_had_successful_write,
)
from agent.message_context_manager import MessageContextSummary
from agent.session import Session
from agent.streaming import StreamEvent
from agent.tui.commands import CommandRegistry
from agent.tui.commands.base import CommandContext, CommandResult
from tools.git_diff import git_diff

from .approval import TuiApprovalAdapter
from .state import GitHeader, TuiState


StateChangeCallback = Callable[[StreamEvent], Awaitable[None]]


async def auto_approval_callback(_request: ApprovalRequest) -> bool:
    """Approve all requests immediately."""
    return True


class AgentTuiRunner:
    """Own the session lifecycle and feed stream events into TUI state."""

    def __init__(
        self,
        args: Namespace,
        *,
        state: Optional[TuiState] = None,
        on_state_change: Optional[StateChangeCallback] = None,
    ) -> None:
        self.args = args
        self.state = state or TuiState()
        self.on_state_change = on_state_change
        self.approval_adapter = TuiApprovalAdapter()
        self.session: Session | None = None
        self.cancel_controller = CancellationController()

    @property
    def current_task(self) -> asyncio.Task | None:
        """Return the active task for backwards compatibility."""
        return self.cancel_controller.current_task

    async def start(self) -> None:
        """Create the underlying agent session."""
        silent_mode = bool(getattr(self.args, "auto", False))
        approval_callback = auto_approval_callback if silent_mode else self.approval_adapter.callback
        self.session = Session.from_config(
            workdir=getattr(self.args, "workdir", None),
            approval_callback=approval_callback,
            session_id=getattr(self.args, "session_id", None),
            persist_messages=not bool(getattr(self.args, "temp", False)),
            resume=bool(getattr(self.args, "session_id", None)),
        )
        self.session.stream_callback = self.handle_stream_event
        self.state.set_startup_info(
            session_id=self.session.id,
            model_name=getattr(self.session.provider, "model", "(unknown)"),
            skills_text=self._skills_text(),
            workspace_path=str(self.session.workdir),
            context_window_tokens=self.session.context_window_tokens,
            restored_message_count=self.session.restored_message_count,
            auto_mode=silent_mode,
            todo_manager=self.session.todo_manager,
        )
        await self.refresh_message_context_header()
        await self.refresh_git_header()
        if warning := getattr(self.session, "_session_persistence_warning", None):
            event = StreamEvent(
                source="tui",
                session_id=self.session.id,
                event_type="session_warning",
                title="Session persistence disabled",
                content=f"Session history is memory-only for this run: {warning}",
                status="warning",
                phase="planning",
            )
            self.state.apply_event(event)
            if self.on_state_change is not None:
                await self.on_state_change(event)

    async def close(self) -> None:
        """Close the session and cancel in-flight work."""
        await self.cancel_current_task()
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def submit(self, text: str) -> None:
        """Run one user request."""
        await self.submit_nowait(text)
        if self.current_task is not None:
            await self.current_task

    async def submit_nowait(self, text: str) -> None:
        """Record user input immediately and run the request in the background."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        if self.current_task and not self.current_task.done():
            raise RuntimeError("A task is already running")
        self.state.add_user_input(self.session.id, text)
        if self.on_state_change is not None:
            await self.on_state_change(
                StreamEvent(
                    source="user",
                    session_id=self.session.id,
                    event_type="user_message",
                    content=text,
                    title="You",
                    detail=text,
                    phase="planning",
                )
            )
        thinking_event = StreamEvent(
            source="main",
            session_id=self.session.id,
            event_type="agent_thinking",
            title="Task running",
            detail=text,
            phase="executing",
            status="running",
            metadata={"intent": text},
        )
        self.state.apply_event(thinking_event)
        if self.on_state_change is not None:
            await self.on_state_change(thinking_event)
        self.cancel_controller.set_task(asyncio.create_task(self._send_current(text)))

    async def _send_current(self, text: str) -> None:
        start_index = self._latest_user_message_index()
        try:
            if self.session is None:
                return
            response = await self.session.send(text)
            await self._emit_final_response_if_missing(response, start_index)
        finally:
            await self._emit_changed_files_summary(start_index)
            # 任务完成时移除临时状态项并结束任务跟踪
            if self.session is not None:
                await self.refresh_message_context_header()
                await self.refresh_git_header()
            self.state._remove_transient_items()
            self.state.end_active_task()
            if self.on_state_change is not None:
                # 创建一个空事件来触发 UI 刷新
                await self.on_state_change(
                    StreamEvent(
                        source="main",
                        session_id=self.session.id if self.session else "",
                        event_type="task_finished",
                        title="Task finished",
                    )
                )
            self.cancel_controller.clear_task(asyncio.current_task())

    async def _emit_final_response_if_missing(self, response, start_index: int) -> None:
        """Show final assistant content when the provider did not stream text deltas."""
        if self.session is None or response is None:
            return
        content = getattr(response, "content", "")
        if not isinstance(content, str) or not content.strip():
            return
        streamed_text = any(
            item.event_type == "text_delta"
            and item.session_id == self.session.id
            and bool(item.content.strip())
            for item in self.state.timeline[start_index:]
        )
        if streamed_text:
            return
        event = StreamEvent(
            source="main",
            session_id=self.session.id,
            event_type="text_delta",
            content=content,
            title="Assistant response",
            phase="responding",
            status="completed",
        )
        self.state.apply_event(event)
        if self.on_state_change is not None:
            await self.on_state_change(event)

    async def _emit_changed_files_summary(self, start_index: int) -> None:
        """Show one end-of-task file summary when the turn changed files."""
        if self.session is None:
            return
        turn_items = self.state.timeline[start_index:]
        diffs = [
            extract_diff_text(item.content)
            for item in turn_items
            if (
                item.event_type == "tool_result"
                and not item.metadata.get("approval_preview")
                and extract_diff_text(item.content)
            )
        ]
        if not diffs:
            changed_paths = merge_changed_paths(turn_items)
            if changed_paths or turn_had_successful_write(turn_items):
                final_diff = git_diff(paths=changed_paths or None)
                if final_diff and not final_diff.startswith(("Error:", "No diff.")):
                    diffs.append(final_diff)
        if not diffs:
            return
        diff_text = "\n".join(diffs)
        snapshot = build_changed_files_snapshot(diff_text, source="task")
        changed_files = changed_files_as_dicts(snapshot)
        if not changed_files:
            return
        self.state.set_changed_file_diffs(changed_files)
        event = StreamEvent(
            source="main",
            session_id=self.session.id,
            event_type="files_changed_summary",
            content=diff_text,
            title="Files changed",
            phase="summarizing",
            status="completed",
            metadata={"files": changed_files},
        )
        self.state.apply_event(event)
        if self.on_state_change is not None:
            await self.on_state_change(event)

    async def cancel_current_task_result(self) -> CancelResult:
        """Cancel the active request and return a stable result."""
        self.approval_adapter.cancel_pending()
        return await self.cancel_controller.cancel()

    async def cancel_current_task(self) -> bool:
        """Cancel the active request, if any."""
        return (await self.cancel_current_task_result()).status == "cancelled"

    async def handle_stream_event(self, event: StreamEvent) -> None:
        """Update state and forward the event to the UI."""
        self.state.apply_event(event)
        if event.event_type in {"context_compressed", "context_summarized"}:
            await self.refresh_message_context_header()
        if self.on_state_change is not None:
            await self.on_state_change(event)

    def resolve_approval(self, approval_id: str, approved: bool) -> bool:
        """Resolve a pending approval decision."""
        return self.approval_adapter.resolve(approval_id, approved)

    async def analyze_message_context(self) -> MessageContextSummary:
        """Return current message token summary."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        return await self.session.analyze_message_context()

    async def refresh_message_context_header(self) -> MessageContextSummary | None:
        """Refresh top-panel message count and context token summary."""
        if self.session is None:
            return None
        message_count = len(getattr(self.session, "messages", []) or [])
        self.state.update_message_context_header(message_count=message_count, refreshing=True)
        if not hasattr(self.session, "analyze_message_context"):
            self.state.update_message_context_header(message_count=message_count, refreshing=False)
            return None
        summary = await self.session.analyze_message_context()
        self.state.update_message_context_header(message_count=message_count, summary=summary, refreshing=False)
        return summary

    async def refresh_git_header(self) -> GitHeader:
        """Refresh compact git branch/dirty status for the top panel."""
        workdir = getattr(self.session, "workdir", None) if self.session is not None else None
        header = await asyncio.to_thread(_read_git_header, workdir)
        self.state.update_git_header(branch=header.branch, dirty=header.dirty, available=header.available)
        return header

    async def compress_message_context(self, indexes: list[int]) -> int:
        """Compress selected old tool outputs and refresh state."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        self._message_context_backup = list(self.session.messages)
        compressed = await self.session.compress_message_context(indexes)
        if compressed <= 0:
            self._message_context_backup = None
        await self.refresh_message_context_header()
        return compressed

    async def undo_message_context_compression(self) -> bool:
        """Restore the most recent message context compression backup."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        backup = getattr(self, "_message_context_backup", None)
        if not backup:
            return False
        self.session.messages = list(backup)
        self.session._save_messages()
        self._message_context_backup = None
        await self.refresh_message_context_header()
        return True

    async def execute_command(
        self,
        command_line: str,
        registry: CommandRegistry,
        *,
        emit_result: bool = True,
    ) -> CommandResult:
        """Execute a TUI-only command without sending it to the LLM."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        parsed = registry.parse(command_line)
        if parsed is None:
            result = CommandResult(
                title="Unknown command",
                content=f"Unknown command: {command_line.strip()}. Try :help.",
                severity="warning",
                status="warning",
            )
            if emit_result:
                await self.emit_command_result(command_line, result)
            return result
        if parsed.command.destructive and self.current_task is not None and not self.current_task.done():
            result = CommandResult(
                title="Command blocked",
                content=f"Cannot run :{parsed.command.name} while a task is running.",
                severity="warning",
                status="warning",
            )
            if emit_result:
                await self.emit_command_result(command_line, result)
            return result
        ctx = CommandContext(
            runner=self,
            registry=registry,
            confirmed=parsed.confirmed,
            raw_text=parsed.raw_text,
        )
        result = await parsed.command.execute(ctx, parsed.args)
        if emit_result:
            await self.emit_command_result(parsed.raw_text, result)
        return result

    async def clear_session_history(self) -> None:
        """Clear session messages and reset the TUI transcript view."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        if self.current_task is not None and not self.current_task.done():
            raise RuntimeError("Cannot clear while a task is running")
        self.session.clear()
        self.state.clear_session_view()
        await self.refresh_message_context_header()

    async def emit_command_result(self, command_line: str, result: CommandResult) -> None:
        """Append a local command result to the timeline."""
        session_id = self.session.id if self.session is not None else self.state.session_id
        event = StreamEvent(
            source="tui",
            session_id=session_id,
            event_type="command_result",
            title=result.title,
            detail=command_line.strip(),
            content=result.content,
            status=result.status,
            phase="planning",
            metadata={"command": command_line.strip(), "severity": result.severity},
        )
        self.state.apply_event(event)
        if self.on_state_change is not None:
            await self.on_state_change(event)

    def _skills_text(self) -> str:
        if self.session is None:
            return "(none)"
        skill_names = [skill.name for skill in self.session.skill_registry.list_skills()]
        return ", ".join(skill_names) if skill_names else "(none)"

    def _latest_user_message_index(self) -> int:
        for index in range(len(self.state.timeline) - 1, -1, -1):
            if self.state.timeline[index].event_type == "user_message":
                return index
        return 0


def _read_git_header(workdir: Path | str | None) -> GitHeader:
    """Read git branch and dirty state for a workspace."""
    if workdir is None:
        return GitHeader()
    cwd = Path(workdir)
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
        if branch == "HEAD":
            commit = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=2,
                check=True,
            ).stdout.strip()
            branch = f"detached:{commit}" if commit else "detached"
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return GitHeader()
    return GitHeader(branch=branch, dirty=bool(status.strip()), available=bool(branch))


def _changed_files_from_diff(diff: str) -> list[dict]:
    """Return per-file stats and diff sections from a unified diff blob."""
    return changed_files_as_dicts(build_changed_files_snapshot(diff, source="diff"))
