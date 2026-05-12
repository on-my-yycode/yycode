"""Replay view model derived from canonical session messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent.task_memory import is_task_summary_memory


ReplayRole = Literal["user", "assistant", "tool", "system"]
ReplayKind = Literal["message", "summary", "tool", "context"]


@dataclass(frozen=True)
class ReplayEvent:
    """One UI/protocol replay event derived from a stored message."""

    role: ReplayRole
    kind: ReplayKind
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def build_session_replay(messages: list[BaseMessage]) -> list[ReplayEvent]:
    """Build a display-friendly replay model from canonical session messages."""
    events: list[ReplayEvent] = []
    for index, message in enumerate(messages):
        metadata = {
            "message_index": index,
            "message_type": type(message).__name__,
        }
        metadata.update(getattr(message, "additional_kwargs", {}) or {})
        if is_task_summary_memory(message):
            events.append(
                ReplayEvent(
                    role="system",
                    kind="summary",
                    content=_message_text(message),
                    metadata=metadata,
                )
            )
        elif isinstance(message, HumanMessage):
            events.append(
                ReplayEvent(
                    role="user",
                    kind="message",
                    content=_message_text(message),
                    metadata=metadata,
                )
            )
        elif isinstance(message, AIMessage):
            content = _message_text(message)
            if not content.strip():
                continue
            events.append(
                ReplayEvent(
                    role="assistant",
                    kind="message",
                    content=content,
                    metadata=metadata,
                )
            )
        elif isinstance(message, ToolMessage):
            content = _message_text(message)
            if not _should_replay_tool_message(content, metadata):
                continue
            metadata["tool_name"] = message.name or ""
            metadata["tool_call_id"] = message.tool_call_id
            events.append(
                ReplayEvent(
                    role="tool",
                    kind="tool",
                    content=content,
                    metadata=metadata,
                )
            )
    return events


def _should_replay_tool_message(content: str, metadata: dict[str, Any]) -> bool:
    if metadata.get("context_compressed"):
        return True
    return len(content) <= 2_000


def _message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)
