"""Map yoyoagent stream and replay events to ACP session updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.plan_snapshot import PlanSnapshot
from agent.session_replay import ReplayEvent
from agent.streaming import StreamEvent


READ_TOOLS = {"read_file", "read_many_files", "list_files", "git_show", "workspace_state", "git_diff"}
SEARCH_TOOLS = {"grep", "web_search"}
EDIT_TOOLS = {"apply_patch", "write_file", "edit_file"}
EXECUTE_TOOLS = {"bash", "verify"}


def stream_event_to_updates(event: StreamEvent, *, workdir: Path | None = None) -> list[dict[str, Any]]:
    """Return ACP session/update payloads for one yoyoagent stream event."""
    if event.event_type == "text_delta":
        return [_update("agent_message_chunk", {"content": event.content})]
    if event.event_type == "tool_start":
        return [
            _update(
                "tool_call",
                {
                    "toolCallId": _tool_call_id(event),
                    "title": event.title or event.content or event.tool_name or "Tool call",
                    "kind": _tool_kind(event.tool_name),
                    "status": _tool_status(event.status, default="in_progress"),
                    "content": _tool_content(event),
                    "locations": _locations(event.file_paths, workdir),
                    "rawInput": (event.metadata or {}).get("args") or event.metadata or {},
                    "_meta": {"yoyo": event.to_dict()},
                },
            )
        ]
    if event.event_type == "tool_end":
        return [
            _update(
                "tool_call_update",
                {
                    "toolCallId": _tool_call_id(event),
                    "status": _tool_status(event.status, default="completed"),
                    "elapsedMs": event.elapsed_ms,
                    "_meta": {"yoyo": event.to_dict()},
                },
            )
        ]
    if event.event_type == "tool_result":
        return [
            _update(
                "tool_call_update",
                {
                    "toolCallId": _tool_call_id(event),
                    "title": event.title,
                    "kind": _tool_kind(event.tool_name),
                    "status": _tool_status(event.status, default="completed"),
                    "content": [{"type": "text", "text": event.content}],
                    "locations": _locations(event.file_paths, workdir),
                    "rawOutput": event.content,
                    "_meta": {"yoyo": event.to_dict()},
                },
            )
        ]
    if event.event_type in {"context_compressed", "context_summarized", "session_warning"}:
        return [_update("agent_message_chunk", {"content": f"\n[{event.title or 'context'}] {event.content}\n"})]
    if event.event_type == "usage":
        return [_update("usage", {"usage": event.usage or {}, "_meta": {"yoyo": event.to_dict()}})]
    if event.event_type in {"llm_waiting", "llm_timeout", "llm_retry", "llm_error"}:
        return [
            _update(
                "status",
                {
                    "title": event.title or "Model status",
                    "content": event.content,
                    "status": event.status or "running",
                    "_meta": {"yoyo": event.to_dict()},
                },
            )
        ]
    return []


def plan_snapshot_to_update(snapshot: PlanSnapshot) -> dict[str, Any]:
    """Return an ACP plan update payload from a public plan snapshot."""
    return _update(
        "plan",
        {
            "entries": [
                {
                    "id": entry.id,
                    "title": entry.title,
                    "status": entry.status,
                    "priority": entry.priority,
                }
                for entry in snapshot.entries
            ],
            "_meta": {
                "yoyo": {
                    "memory": snapshot.memory,
                    "updatedAt": snapshot.updated_at,
                    "taskStarted": snapshot.task_started,
                    "taskCompleted": snapshot.task_completed,
                }
            },
        },
    )


def replay_event_to_updates(event: ReplayEvent) -> list[dict[str, Any]]:
    """Return ACP replay updates for one session replay event."""
    if event.kind == "summary":
        return [_update("agent_message_chunk", {"content": f"\n[Session summary]\n{event.content}\n"})]
    if event.role == "user":
        return [_update("user_message_chunk", {"content": event.content})]
    if event.role == "assistant":
        return [_update("agent_message_chunk", {"content": event.content})]
    if event.role == "tool":
        tool_name = str(event.metadata.get("tool_name") or "tool")
        tool_call_id = str(event.metadata.get("tool_call_id") or f"replay-{tool_name}")
        return [
            _update(
                "tool_call_update",
                {
                    "toolCallId": tool_call_id,
                    "title": tool_name,
                    "kind": _tool_kind(tool_name),
                    "status": "completed",
                    "content": [{"type": "text", "text": event.content}],
                    "rawOutput": event.content,
                    "_meta": {"yoyo": {"replay": True, **event.metadata}},
                },
            )
        ]
    return []


def _update(update_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"sessionUpdate": update_type, **payload}


def _tool_content(event: StreamEvent) -> list[dict[str, str]]:
    detail = event.detail or event.content or ""
    return [{"type": "text", "text": detail}] if detail else []


def _tool_call_id(event: StreamEvent) -> str:
    metadata = event.metadata or {}
    args = metadata.get("args") if isinstance(metadata, dict) else None
    explicit = metadata.get("tool_call_id") or metadata.get("id") if isinstance(metadata, dict) else None
    if explicit:
        return str(explicit)
    if isinstance(args, dict) and args.get("tool_call_id"):
        return str(args["tool_call_id"])
    return f"{event.session_id}:{event.tool_name or event.event_type}"


def _tool_status(status: str | None, *, default: str) -> str:
    if status in {"failed", "denied", "cancelled"}:
        return "failed" if status == "denied" else status
    if status in {"completed", "running", "in_progress", "waiting_for_user"}:
        return "in_progress" if status == "running" else status
    return default


def _tool_kind(tool_name: str | None) -> str:
    name = tool_name or ""
    if name in READ_TOOLS:
        return "read"
    if name in SEARCH_TOOLS or name.startswith("lsp_"):
        return "search"
    if name in EDIT_TOOLS:
        return "edit"
    if name in EXECUTE_TOOLS:
        return "execute"
    if name in {"todo", "subagent"}:
        return "think"
    return "other"


def _locations(paths: list[str] | None, workdir: Path | None) -> list[dict[str, Any]]:
    locations = []
    for path in paths or []:
        location: dict[str, Any] = {"path": str(path)}
        if workdir is not None and path and not str(path).startswith("/"):
            location["path"] = str((workdir / path).resolve())
        locations.append(location)
    return locations

