"""Async bridge between Session and the TUI state."""

from __future__ import annotations

import asyncio
import contextlib
import re
from argparse import Namespace
from typing import Awaitable, Callable, Optional

from agent.approval import ApprovalRequest
from agent.message_context_manager import MessageContextSummary
from agent.session import Session
from agent.streaming import StreamEvent
from tools.git_diff import git_diff

from .approval import TuiApprovalAdapter
from .state import TuiState


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
        self.current_task: asyncio.Task | None = None

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
        self.current_task = asyncio.create_task(self._send_current(text))

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
            self.current_task = None

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
            _extract_diff_text(item.content)
            for item in turn_items
            if (
                item.event_type == "tool_result"
                and not item.metadata.get("approval_preview")
                and _extract_diff_text(item.content)
            )
        ]
        if not diffs:
            changed_paths = _changed_paths_from_items(turn_items)
            if changed_paths or _turn_had_successful_write(turn_items):
                final_diff = git_diff(paths=changed_paths or None)
                if final_diff and not final_diff.startswith(("Error:", "No diff.")):
                    diffs.append(final_diff)
        if not diffs:
            return
        diff_text = "\n".join(diffs)
        changed_files = _changed_files_from_diff(diff_text)
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

    async def cancel_current_task(self) -> bool:
        """Cancel the active request, if any."""
        if self.current_task is None or self.current_task.done():
            return False
        self.current_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.current_task
        return True

    async def handle_stream_event(self, event: StreamEvent) -> None:
        """Update state and forward the event to the UI."""
        self.state.apply_event(event)
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

    async def compress_message_context(self, indexes: list[int]) -> int:
        """Compress selected old tool outputs and refresh state."""
        if self.session is None:
            raise RuntimeError("TUI runner has not been started")
        compressed = await self.session.compress_message_context(indexes)
        return compressed

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


def _extract_diff_text(content: str) -> str:
    """Return the unified diff portion from a tool result, if present."""
    if not content:
        return ""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(("diff --git ", "--- ")):
            return "\n".join(lines[index:])
    return ""


def _changed_files_from_diff(diff: str) -> list[dict]:
    """Return per-file stats and diff sections from a unified diff blob."""
    files: list[dict] = []
    current: dict | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                files.append(current)
            current = {"path": _path_from_diff_header(line), "added": 0, "removed": 0, "lines": [line]}
            continue
        if line.startswith("--- "):
            if current is not None and _diff_section_has_changes(current):
                files.append(current)
                current = {"path": _strip_diff_prefix(line[4:].split("\t", 1)[0].strip()), "added": 0, "removed": 0, "lines": [line]}
            elif current is None:
                current = {"path": _strip_diff_prefix(line[4:].split("\t", 1)[0].strip()), "added": 0, "removed": 0, "lines": [line]}
            else:
                current["lines"].append(line)
            continue
        if current is None:
            continue
        current["lines"].append(line)
        if line.startswith("+++ "):
            path = _strip_diff_prefix(line[4:].split("\t", 1)[0].strip())
            if path != "/dev/null":
                current["path"] = path
            continue
        if line.startswith("--- ") or line.startswith("@@") or line.startswith("index "):
            continue
        if line.startswith("+"):
            current["added"] += 1
        elif line.startswith("-"):
            current["removed"] += 1
    if current is not None:
        files.append(current)
    return _merge_changed_file_sections(files)


def _merge_changed_file_sections(files: list[dict]) -> list[dict]:
    """Merge repeated diff sections for the same path while preserving section content."""
    merged: dict[str, dict] = {}
    order: list[str] = []
    for item in files:
        if not item.get("added") and not item.get("removed"):
            continue
        path = str(item.get("path", ""))
        if not path:
            continue
        if path not in merged:
            merged[path] = {"path": path, "added": 0, "removed": 0, "diffs": []}
            order.append(path)
        merged_item = merged[path]
        merged_item["added"] += int(item.get("added", 0) or 0)
        merged_item["removed"] += int(item.get("removed", 0) or 0)
        merged_item["diffs"].append("\n".join(item.get("lines", [])))
    return [
        {
            "path": merged[path]["path"],
            "added": merged[path]["added"],
            "removed": merged[path]["removed"],
            "diff": "\n\n".join(diff for diff in merged[path]["diffs"] if diff),
        }
        for path in order
    ]


def _changed_paths_from_items(items) -> list[str]:
    paths: list[str] = []
    for item in items:
        if item.event_type == "file_changed":
            candidates = list(item.file_paths)
        elif item.event_type in {"tool_start", "tool_end"} and item.tool_name in {"apply_patch", "write_file", "edit_file"}:
            candidates = list(item.file_paths)
        else:
            candidates = []
        for path in candidates:
            if path and path not in paths:
                paths.append(path)
    return paths


def _diff_section_has_changes(section: dict) -> bool:
    return bool(section.get("added") or section.get("removed") or any(str(line).startswith("@@") for line in section.get("lines", [])))


def _turn_had_successful_write(items) -> bool:
    return any(
        item.event_type == "tool_end"
        and item.status != "failed"
        and item.tool_name in {"apply_patch", "write_file", "edit_file"}
        for item in items
    )


def _path_from_diff_header(line: str) -> str:
    match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
    if match:
        return match.group(2)
    parts = line.split()
    return _strip_diff_prefix(parts[-1]) if parts else "file"


def _strip_diff_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path
