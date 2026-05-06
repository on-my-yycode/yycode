"""Async bridge between Session and the TUI state."""

from __future__ import annotations

import asyncio
import contextlib
from argparse import Namespace
from typing import Awaitable, Callable, Optional

from agent.approval import ApprovalRequest
from agent.session import Session
from agent.streaming import StreamEvent

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
        silent_mode = bool(getattr(self.args, "silent", False))
        approval_callback = auto_approval_callback if silent_mode else self.approval_adapter.callback
        self.session = Session.from_config(approval_callback=approval_callback)
        self.session.stream_callback = self.handle_stream_event
        self.state.set_startup_info(
            session_id=self.session.id,
            model_name=getattr(self.session.provider, "model", "(unknown)"),
            skills_text=self._skills_text(),
            workspace_path=str(self.session.workdir),
            context_window_tokens=self.session.context_window_tokens,
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
        start_index = len(self.state.timeline)
        try:
            if self.session is None:
                return
            response = await self.session.send(text)
            await self._emit_final_response_if_missing(response, start_index)
        finally:
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

    def _skills_text(self) -> str:
        if self.session is None:
            return "(none)"
        skill_names = [skill.name for skill in self.session.skill_registry.list_skills()]
        return ", ".join(skill_names) if skill_names else "(none)"
