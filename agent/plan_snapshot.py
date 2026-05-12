"""Shared task plan snapshot models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from agent.todo_manager import TodoManager


PlanStatus = Literal["pending", "in_progress", "completed"]


@dataclass(frozen=True)
class PlanEntry:
    """One stable task plan entry for UI/protocol adapters."""

    id: str
    title: str
    status: PlanStatus
    priority: str = "medium"


@dataclass(frozen=True)
class PlanSnapshot:
    """Public snapshot of the current task plan and compact memory."""

    entries: list[PlanEntry] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""
    task_started: bool = False
    task_completed: bool = False


def build_plan_snapshot(todo_manager: TodoManager | None) -> PlanSnapshot:
    """Return a stable task plan snapshot independent of any UI renderer."""
    if todo_manager is None:
        return PlanSnapshot(updated_at=_utc_now())
    state = todo_manager.get_task_state()
    raw_items = state.get("items") or []
    entries = [
        PlanEntry(
            id=str(item.get("id") or index + 1),
            title=str(item.get("text") or ""),
            status=_normalize_status(item.get("status")),
            priority="high" if item.get("status") == "in_progress" else "medium",
        )
        for index, item in enumerate(raw_items)
        if isinstance(item, dict)
    ]
    return PlanSnapshot(
        entries=entries,
        memory=dict(state.get("memory") or {}),
        updated_at=_utc_now(),
        task_started=bool(todo_manager.task_state_started),
        task_completed=bool(todo_manager.task_completed),
    )


def _normalize_status(value: object) -> PlanStatus:
    if value == "completed":
        return "completed"
    if value == "in_progress":
        return "in_progress"
    return "pending"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
