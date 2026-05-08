"""State store for the terminal UI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agent.streaming import StreamEvent
from agent.todo_manager import TodoManager


MAX_TIMELINE_ITEMS = 500


@dataclass
class TimelineItem:
    """A rendered timeline item derived from a stream event."""

    id: str
    session_id: str
    event_type: str
    title: str
    detail: str
    phase: str | None
    status: str | None
    source: str
    role: str | None
    tool_name: str | None = None
    file_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int | None = None
    content: str = ""
    start_time_ms: int | None = None
    is_transient: bool = False  # 标记是否为临时状态项，完成后可删除
    usage: dict[str, int] | None = None


@dataclass
class PendingApproval:
    """A user decision currently blocking execution."""

    approval_id: str
    title: str
    detail: str
    request_text: str
    diff_preview: str = ""
    tool_name: str | None = None
    file_paths: list[str] = field(default_factory=list)
    status: str = "waiting_for_user"


@dataclass
class SubagentStatus:
    """Current status snapshot for one subagent."""

    session_id: str
    role: str
    title: str
    detail: str
    status: str
    elapsed_ms: int | None = None


@dataclass
class ChangedFileDiff:
    """A changed file and its diff from the latest task."""

    path: str
    added: int
    removed: int
    diff: str
    collapsed: bool = False


class TuiState:
    """Mutable state used by the TUI renderer."""

    def __init__(self) -> None:
        self.timeline: list[TimelineItem] = []
        self.pending_approvals: dict[str, PendingApproval] = {}
        self.subagents: dict[str, SubagentStatus] = {}
        self.changed_files: list[str] = []
        self.latest_changed_file_diffs: list[ChangedFileDiff] = []
        self.active_phase: str = "planning"
        self.status_line: str = "Initializing session"
        self.model_name: str = "(unknown)"
        self.session_id: str = ""
        self.skills_text: str = "(none)"
        self.workspace_path: str = ""
        self.context_window_tokens: int = 0
        self.restored_message_count: int = 0
        self.latest_usage: dict[str, int] = {}
        self.todo_manager: TodoManager | None = None
        self._counter = 0
        self._start_time_ms: int = int(time.time() * 1000)
        # 任务运行状态跟踪
        self.active_task: dict[str, Any] = {
            'is_running': False,
            'start_time_ms': None,
            'intent': '',
            'current_action': '',
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
        }
        self.last_task: dict[str, Any] = {
            'elapsed_ms': None,
            'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0},
            'status': '',
            'finished_at_ms': None,
        }

    def set_startup_info(
        self,
        *,
        session_id: str,
        model_name: str,
        skills_text: str,
        workspace_path: str = "",
        context_window_tokens: int = 0,
        restored_message_count: int = 0,
        todo_manager: TodoManager | None = None,
    ) -> None:
        """Set the startup/session summary shown in the header."""
        self.session_id = session_id
        self.model_name = model_name
        self.skills_text = skills_text or "(none)"
        self.workspace_path = workspace_path
        self.context_window_tokens = max(0, int(context_window_tokens or 0))
        self.restored_message_count = max(0, int(restored_message_count or 0))
        self.status_line = "Ready for input"
        self.todo_manager = todo_manager

    def has_tasks(self) -> bool:
        """Return whether there is an active task state."""
        if not self.todo_manager:
            return False
        return self.todo_manager.task_state_started

    def add_user_input(self, session_id: str, text: str) -> TimelineItem:
        """Append the user's submitted prompt to the transcript."""
        # 先结束之前的任务
        self.end_active_task()

        self._counter += 1
        item = TimelineItem(
            id=f"evt-{self._counter}",
            session_id=session_id,
            event_type="user_message",
            title="You",
            detail=text,
            phase="planning",
            status=None,
            source="user",
            role=None,
            content=text,
        )
        self.timeline.append(item)
        if len(self.timeline) > MAX_TIMELINE_ITEMS:
            self.timeline = self.timeline[-MAX_TIMELINE_ITEMS:]
        self.active_phase = "planning"
        self.status_line = "Waiting for agent response"

        # 开始跟踪新任务
        self.active_task['is_running'] = True
        self.active_task['start_time_ms'] = int(time.time() * 1000)
        self.active_task['intent'] = text
        self.active_task['current_action'] = "Starting..."
        self.active_task['usage'] = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}

        return item

    def apply_event(self, event: StreamEvent) -> TimelineItem:
        """Apply a stream event and return the appended timeline item."""
        # 更新任务状态跟踪
        self._update_active_task(event)

        if event.event_type in {"text_delta", "tool_start", "tool_result", "tool_end"}:
            self.complete_llm_waiting_items(event.session_id)

        if event.event_type in {"llm_waiting", "llm_retry", "llm_timeout", "llm_error"}:
            existing_waiting = self._find_latest_llm_waiting(event)
            if existing_waiting is not None:
                return self._merge_llm_status_event(existing_waiting, event)

        # 模拟 ConsoleStreamRenderer 的 thinking 处理逻辑
        # 如果在 thinking 过程中来了 tool_start、tool_result 或 text_delta，添加 thinking_end
        needs_thinking_end = False
        if self.timeline:
            latest = self.timeline[-1]
            if latest.event_type == "thinking_start" and event.event_type in {"tool_start", "tool_result", "text_delta", "llm_waiting", "llm_timeout", "llm_retry", "llm_error"}:
                needs_thinking_end = True

        if needs_thinking_end:
            self._counter += 1
            now_ms = int(time.time() * 1000)
            thinking_end_item = TimelineItem(
                id=f"evt-{self._counter}",
                session_id=event.session_id,
                event_type="thinking_end",
                title="Thinking finished",
                detail="",
                phase=None,
                status=None,
                source=event.source,
                role=event.role,
                tool_name=None,
                file_paths=[],
                metadata={},
                elapsed_ms=None,
                content="",
                start_time_ms=now_ms,
                is_transient=False,
                usage=None,
            )
            self.timeline.append(thinking_end_item)

        # 移除临时状态项
        if event.event_type not in {"agent_thinking", "thinking_delta", "text_delta"}:
            self._remove_transient_items()

        # 只有 text_delta 和 thinking_delta 能合并，其他都新建条目
        # 确保所有信息都显示在时间线上
        always_new = {"usage", "context_compressed", "llm_timeout", "llm_retry", "llm_error", "file_changed", "files_changed_summary", "llm_waiting", "tool_start", "tool_end", "tool_result", "thinking_start", "thinking_end", "user_message", "agent_thinking"}
        existing = None
        if event.event_type == "text_delta" and self.timeline and self.timeline[-1].event_type == "text_delta":
            existing = self.timeline[-1] if self.timeline[-1].session_id == event.session_id else None
        elif event.event_type == "thinking_delta":
            if self.timeline and self.timeline[-1].event_type in {"thinking_start", "thinking_delta"}:
                existing = self.timeline[-1]
        elif event.event_type not in always_new:
            existing = self._find_merge_target(event)

        if existing is not None:
            return self._merge_event(existing, event)

        self._counter += 1
        now_ms = int(time.time() * 1000)
        item = TimelineItem(
            id=f"evt-{self._counter}",
            session_id=event.session_id,
            event_type=event.event_type,
            title=event.title or self._default_title(event),
            detail=event.detail or event.content,
            phase=event.phase,
            status=event.status,
            source=event.source,
            role=event.role,
            tool_name=event.tool_name,
            file_paths=list(event.file_paths or []),
            metadata=dict(event.metadata or {}),
            elapsed_ms=event.elapsed_ms,
            content=event.content,
            start_time_ms=now_ms,
            is_transient=event.event_type in {"agent_thinking"},  # 只有 agent_thinking 是临时的
            usage=event.usage,
        )
        self.timeline.append(item)
        if len(self.timeline) > MAX_TIMELINE_ITEMS:
            self.timeline = self.timeline[-MAX_TIMELINE_ITEMS:]

        self._update_phase(item)
        self._update_status_line(item)
        self._update_usage(event)
        self._update_changed_files(item)
        self._update_approvals(item)
        self._update_subagents(event, item)
        return item

    def _find_latest_llm_waiting(self, event: StreamEvent) -> TimelineItem | None:
        """Find an active model-wait timeline item for the same session."""
        for item in reversed(self.timeline):
            if item.session_id != event.session_id:
                continue
            if item.event_type == "llm_waiting" and item.status in {"running", "retrying", "timeout", "failed", None}:
                return item
            if item.event_type in {"text_delta", "tool_start", "tool_result", "tool_end", "user_message"}:
                return None
        return None

    def _merge_llm_status_event(self, item: TimelineItem, event: StreamEvent) -> TimelineItem:
        """Update one model-wait item instead of appending heartbeat rows."""
        previous_start = item.start_time_ms
        if event.event_type == "llm_waiting":
            item.event_type = "llm_waiting"
            item.status = event.status or "running"
        elif event.event_type == "llm_retry":
            item.status = event.status or "retrying"
        elif event.event_type in {"llm_timeout", "llm_error"}:
            item.status = event.status or ("timeout" if event.event_type == "llm_timeout" else "failed")
        item.title = event.title or self._default_title(event)
        item.detail = event.detail or event.content
        item.content = event.content
        item.phase = event.phase or item.phase
        item.elapsed_ms = event.elapsed_ms if event.elapsed_ms is not None else item.elapsed_ms
        item.metadata.update(dict(event.metadata or {}))
        item.usage = event.usage or item.usage
        item.start_time_ms = previous_start
        self._update_phase(item)
        self._update_status_line(item)
        self._update_usage(event)
        return item

    def complete_llm_waiting_items(self, session_id: str) -> None:
        """Mark active model-wait timeline items as completed."""
        for item in reversed(self.timeline):
            if item.session_id != session_id:
                continue
            if item.event_type == "llm_waiting" and item.status in {"running", "retrying", "timeout", None}:
                item.status = "completed"
                item.title = "Model response started"
                return
            if item.event_type in {"text_delta", "tool_start", "tool_result", "tool_end", "user_message"}:
                return

    def _update_active_task(self, event: StreamEvent) -> None:
        """更新活动任务状态"""
        if not self.active_task['is_running']:
            return

        # 更新当前活动
        if event.event_type == "thinking_start":
            self.active_task['current_action'] = "Thinking..."
        elif event.event_type == "tool_start":
            self.active_task['current_action'] = "Running tool"
        elif event.event_type == "llm_waiting":
            self.active_task['current_action'] = "Waiting for model..."
        elif event.event_type == "text_delta":
            self.active_task['current_action'] = "Generating response..."

        # 更新 usage
        if event.usage:
            self.active_task['usage'] = event.usage

    def end_active_task(self) -> None:
        """结束活动任务"""
        if self.active_task.get('is_running'):
            elapsed_ms = None
            start_time_ms = self.active_task.get('start_time_ms')
            if start_time_ms:
                elapsed_ms = int(time.time() * 1000) - int(start_time_ms)
            usage = self.active_task.get('usage') or self.latest_usage or {}
            self.last_task = {
                'elapsed_ms': elapsed_ms,
                'usage': dict(usage),
                'status': 'completed',
                'finished_at_ms': int(time.time() * 1000),
            }
        self.active_task['is_running'] = False
        self.active_task['start_time_ms'] = None
        self.active_task['intent'] = ""
        self.active_task['current_action'] = ""
        self.active_task['usage'] = {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}

    def _remove_transient_items(self) -> None:
        """Remove transient status items from timeline."""
        self.timeline = [item for item in self.timeline if not item.is_transient]

    def get_elapsed_ms(self, item: TimelineItem) -> int:
        """Get elapsed time for a timeline item."""
        if item.elapsed_ms is not None:
            return item.elapsed_ms
        if item.start_time_ms is not None:
            return int(time.time() * 1000) - item.start_time_ms
        return 0

    def latest_timeline_items(self, limit: int = 50) -> list[TimelineItem]:
        """Return the newest timeline items."""
        return self.timeline[-limit:]

    def latest_item(self) -> TimelineItem | None:
        """Return the newest timeline item, if any."""
        if not self.timeline:
            return None
        return self.timeline[-1]

    def next_pending_approval(self) -> PendingApproval | None:
        """Return the next pending approval, if any."""
        for approval in self.pending_approvals.values():
            if approval.status == "waiting_for_user":
                return approval
        return None

    def set_changed_file_diffs(self, files: list[dict]) -> None:
        """Store changed file diffs for the dedicated diff viewer."""
        self.latest_changed_file_diffs = [
            ChangedFileDiff(
                path=str(item.get("path", "")),
                added=int(item.get("added", 0) or 0),
                removed=int(item.get("removed", 0) or 0),
                diff=str(item.get("diff", "") or ""),
            )
            for item in files
            if item.get("path")
        ]

    def _default_title(self, event: StreamEvent) -> str:
        mapping = {
            "thinking_start": "Thinking",
            "thinking_end": "Thinking finished",
            "text_delta": "Assistant response",
            "user_message": "You",
            "tool_start": "Run tool",
            "tool_end": "Tool finished",
            "tool_result": "Tool result",
            "usage": "Usage updated",
            "context_compressed": "Context compressed",
            "llm_waiting": "Waiting for model response",
            "llm_timeout": "Model request timed out",
            "llm_retry": "Retrying model request",
            "llm_error": "Model request failed",
            "approval_required": "Approval required",
            "approval_resolved": "Approval resolved",
            "file_changed": "File changed",
            "files_changed_summary": "Files changed",
            "subagent_started": "Subagent started",
            "subagent_finished": "Subagent finished",
        }
        return mapping.get(event.event_type, event.event_type.replace("_", " ").title())

    def _find_merge_target(self, event: StreamEvent) -> TimelineItem | None:
        if not self.timeline:
            return None
        latest = self.timeline[-1]
        if event.event_type == "thinking_delta":
            return latest if latest.event_type in {"thinking_start", "thinking_delta"} else None
        if event.event_type == "text_delta":
            if latest.event_type != "text_delta":
                return None
            if latest.session_id != event.session_id:
                return None
            return latest
        return None

    def _merge_event(self, item: TimelineItem, event: StreamEvent) -> TimelineItem:
        if event.event_type == "thinking_delta":
            item.content += event.content
            item.detail = event.content or item.detail
        elif event.event_type == "text_delta":
            item.content += event.content
            item.detail = item.content
        # 更新 usage
        if event.usage:
            item.usage = event.usage
        self._update_phase(item)
        self._update_status_line(item)
        self._update_approvals(item)
        self._update_subagents(event, item)
        return item

    def _find_latest_matching_tool_start(self, event: StreamEvent) -> TimelineItem | None:
        for item in reversed(self.timeline):
            if item.event_type != "tool_start":
                continue
            if item.session_id != event.session_id:
                continue
            if item.tool_name and event.tool_name and item.tool_name != event.tool_name:
                continue
            return item
        return None

    def _find_latest_matching_approval(self, event: StreamEvent) -> TimelineItem | None:
        approval_id = str((event.metadata or {}).get("approval_id", ""))
        if not approval_id:
            return None
        for item in reversed(self.timeline):
            if item.event_type != "approval_required":
                continue
            if str(item.metadata.get("approval_id", "")) == approval_id:
                return item
        return None

    def _find_latest_matching_subagent(self, event: StreamEvent) -> TimelineItem | None:
        for item in reversed(self.timeline):
            if item.event_type != "subagent_started":
                continue
            if item.session_id == event.session_id:
                return item
        return None

    def _update_phase(self, item: TimelineItem) -> None:
        if item.phase:
            self.active_phase = item.phase
        elif item.event_type.startswith("llm_"):
            self.active_phase = "waiting"

    def _update_status_line(self, item: TimelineItem) -> None:
        detail = f": {item.detail}" if item.detail else ""
        self.status_line = f"{item.title}{detail}"

    def _update_usage(self, event: StreamEvent) -> None:
        if event.usage:
            self.latest_usage = dict(event.usage)

    def _update_changed_files(self, item: TimelineItem) -> None:
        if item.event_type != "file_changed":
            return
        for path in item.file_paths:
            if path and path not in self.changed_files:
                self.changed_files.append(path)

    def _update_approvals(self, item: TimelineItem) -> None:
        approval_id = str(item.metadata.get("approval_id", ""))
        if not approval_id:
            return
        if item.event_type == "approval_required":
            self.pending_approvals[approval_id] = PendingApproval(
                approval_id=approval_id,
                title=item.title,
                detail=item.detail,
                request_text=item.content,
                diff_preview=str(item.metadata.get("diff_preview", "") or ""),
                tool_name=item.tool_name,
                file_paths=list(item.file_paths),
                status=item.status or "waiting_for_user",
            )
            return
        if item.event_type == "approval_resolved" and approval_id in self.pending_approvals:
            approval = self.pending_approvals[approval_id]
            approval.status = item.status or "resolved"
            if approval.status != "waiting_for_user":
                self.pending_approvals.pop(approval_id, None)

    def _update_subagents(self, event: StreamEvent, item: TimelineItem) -> None:
        if event.event_type == "subagent_started":
            self.subagents[event.session_id] = SubagentStatus(
                session_id=event.session_id,
                role=event.role or "subagent",
                title=item.title,
                detail=item.detail,
                status=item.status or "running",
                elapsed_ms=item.elapsed_ms,
            )
            return
        if event.event_type == "subagent_finished":
            self.subagents[event.session_id] = SubagentStatus(
                session_id=event.session_id,
                role=event.role or "subagent",
                title=item.title,
                detail=item.detail,
                status=item.status or "completed",
                elapsed_ms=item.elapsed_ms,
            )
            return
        if event.source == "subagent":
            existing = self.subagents.get(event.session_id)
            self.subagents[event.session_id] = SubagentStatus(
                session_id=event.session_id,
                role=event.role or "subagent",
                title=item.title,
                detail=item.detail,
                status=item.status or (existing.status if existing else "running"),
                elapsed_ms=item.elapsed_ms,
            )
