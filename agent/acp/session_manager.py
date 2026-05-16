"""ACP session lifecycle management."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from agent.acp.approval_adapter import AcpApprovalAdapter
from agent.acp.content_adapter import content_blocks_to_text
from agent.acp.update_adapter import (
    plan_snapshot_to_update,
    replay_event_to_updates,
    stream_event_to_updates,
)
from agent.cancellation import CancellationController
from agent.plan_snapshot import build_plan_snapshot
from agent.session import Session
from agent.streaming import StreamEvent


Notifier = Callable[[str, dict[str, Any]], Awaitable[None]]
Requester = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


async def auto_approval_callback(_request: Any) -> bool:
    """Approve runtime approval requests without asking the ACP client."""
    return True


@dataclass
class AcpManagedSession:
    """Runtime state for one ACP session."""

    session: Session
    approval_adapter: AcpApprovalAdapter
    cancel_controller: CancellationController = field(default_factory=CancellationController)


class AcpSessionManager:
    """Create, load, run, and cancel ACP-backed yoyoagent sessions."""

    def __init__(self, notify: Notifier, request: Requester, *, auto_approve: bool = False):
        self.notify = notify
        self.request = request
        self.auto_approve = auto_approve
        self.sessions: dict[str, AcpManagedSession] = {}

    async def new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new yoyoagent session for an ACP client."""
        cwd = _resolve_cwd(params)
        session = self._create_session(cwd)
        self.sessions[session.id] = self._managed(session)
        await self._send_available_commands(session)
        return {"sessionId": session.id}

    async def load_session(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Load a persisted yoyoagent session and replay display events."""
        cwd = _resolve_cwd(params)
        session_id = _session_id_from_params(params)
        session = self._create_session(cwd, session_id=session_id, resume=True)
        self.sessions[session.id] = self._managed(session)
        await self._send_available_commands(session)
        for replay_event in session.replay_view():
            for update in replay_event_to_updates(replay_event):
                await self._send_update(session.id, update)
        return {"sessionId": session.id}

    async def prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run one prompt turn."""
        session_id = _session_id_from_params(params)
        managed = self._require_session(session_id)
        prompt_text = content_blocks_to_text(
            params.get("content")
            or params.get("prompt")
            or params.get("message")
            or params.get("input")
            or ""
        )
        task = asyncio.create_task(managed.session.send(prompt_text))
        managed.cancel_controller.set_task(task)
        try:
            await task
        except asyncio.CancelledError:
            managed.approval_adapter.cancel_pending()
            return {"stopReason": "cancelled"}
        finally:
            managed.cancel_controller.clear_task(task)
        await self._send_update(session_id, plan_snapshot_to_update(build_plan_snapshot(managed.session.todo_manager)))
        return {"stopReason": "end_turn"}

    async def cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Cancel an active prompt turn."""
        session_id = _session_id_from_params(params)
        managed = self._require_session(session_id)
        managed.approval_adapter.cancel_pending()
        result = await managed.cancel_controller.cancel()
        return {"status": result.status}

    async def close(self) -> None:
        """Close all managed sessions."""
        for managed in list(self.sessions.values()):
            managed.approval_adapter.cancel_pending()
            await managed.cancel_controller.cancel()
            await managed.session.close()
        self.sessions.clear()

    def _managed(self, session: Session) -> AcpManagedSession:
        approval = AcpApprovalAdapter(
            session.id,
            self.request,
            workdir=session.workdir,
        )
        session.approval_callback = auto_approval_callback if self.auto_approve else approval.callback
        session.stream_callback = self._stream_callback(session)
        session._graph = None
        return AcpManagedSession(session=session, approval_adapter=approval)

    def _create_session(
        self,
        cwd: Path,
        *,
        session_id: str | None = None,
        resume: bool = False,
    ) -> Session:
        return Session.from_config(
            workdir=cwd,
            session_id=session_id,
            persist_messages=True,
            resume=resume,
        )

    def _stream_callback(self, session: Session):
        async def callback(event: StreamEvent) -> None:
            for update in stream_event_to_updates(event, workdir=session.workdir):
                await self._send_update(session.id, update)
            if event.event_type == "tool_result" and event.tool_name == "todo":
                await self._send_update(
                    session.id,
                    plan_snapshot_to_update(build_plan_snapshot(session.todo_manager)),
                )

        return callback

    async def _send_update(self, session_id: str, update: dict[str, Any]) -> None:
        await self.notify("session/update", {"sessionId": session_id, "update": update})

    async def _send_available_commands(self, session: Session) -> None:
        commands = [
            {
                "name": "/plan",
                "description": "Discuss requirements and produce an implementation plan without executing changes.",
            }
        ]
        for skill in session.skill_registry.list_skills():
            commands.append(
                {
                    "name": f"/{skill.name}",
                    "description": skill.description,
                }
            )
        await self._send_update(
            session.id,
            {
                "sessionUpdate": "available_commands_update",
                "commands": commands,
            },
        )

    def _require_session(self, session_id: str) -> AcpManagedSession:
        if session_id not in self.sessions:
            raise ValueError(f"Unknown ACP session: {session_id}")
        return self.sessions[session_id]


def _resolve_cwd(params: dict[str, Any]) -> Path:
    raw = params.get("cwd") or params.get("workdir") or os.getcwd()
    cwd = Path(str(raw)).expanduser()
    if not cwd.is_absolute():
        cwd = Path.cwd() / cwd
    cwd = cwd.resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise ValueError(f"cwd must be an existing directory: {cwd}")
    return cwd


def _session_id_from_params(params: dict[str, Any]) -> str:
    session_id = params.get("sessionId") or params.get("session_id") or params.get("id")
    if not session_id:
        raise ValueError("sessionId is required")
    return str(session_id)
