"""Deterministic task summary memory for long-running sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage


SUMMARY_MARKER = "[Task Summary Memory]"
SUMMARY_CONTEXT_POLICY = "summary_memory"
MERGED_SUMMARY_SOURCE = "automatic_merge"
MAX_MERGED_ITEMS_PER_SECTION = 24


@dataclass(frozen=True)
class TaskSummaryMemory:
    """A structured summary message for completed task context."""

    content: str
    covered_start_index: int
    covered_end_index: int
    source: str = "automatic"

    def to_message(self) -> HumanMessage:
        """Return a provider-safe message containing the summary memory."""
        message = HumanMessage(content=self.content)
        message.additional_kwargs.update(
            {
                "context_policy": SUMMARY_CONTEXT_POLICY,
                "summary_memory": True,
                "covered_start_index": self.covered_start_index,
                "covered_end_index": self.covered_end_index,
                "source": self.source,
            }
        )
        return message


class TaskSummaryMemoryBuilder:
    """Build deterministic task summary memory from Task State facts."""

    def __init__(self, *, min_messages: int = 8) -> None:
        self.min_messages = min_messages

    def should_summarize(
        self,
        messages: list[BaseMessage],
        *,
        start_index: int,
        task_state: dict[str, Any],
    ) -> bool:
        """Return whether a completed task range is worth summarizing."""
        if start_index >= len(messages):
            return False
        if _latest_summary_index(messages, start_index) is not None:
            return False
        if len(messages) - start_index >= self.min_messages:
            return True
        return _task_state_has_facts(task_state)

    def build(
        self,
        messages: list[BaseMessage],
        *,
        start_index: int,
        task_state: dict[str, Any],
        source: str = "automatic",
    ) -> TaskSummaryMemory:
        """Build summary memory for a completed task range."""
        end_index = max(len(messages) - 1, start_index)
        memory = task_state.get("memory") or {}
        items = task_state.get("items") or []
        lines = [
            SUMMARY_MARKER,
            "scope: current_session",
            f"source: {source}",
            f"created_at: {_utc_now()}",
            f"covered_messages: {start_index}-{end_index}",
            "",
        ]
        _append_section(lines, "User Goal", _scalar_or_none(memory.get("user_goal")))
        _append_list_section(lines, "Constraints", memory.get("constraints"))
        _append_plan_section(lines, items)
        _append_list_section(lines, "Decisions", memory.get("decisions"))
        _append_files_section(
            lines,
            inspected=memory.get("files_inspected"),
            modified=memory.get("files_modified"),
        )
        _append_list_section(lines, "Verification", memory.get("test_results"))
        _append_list_section(lines, "Open Risks", memory.get("open_risks"))
        _append_list_section(lines, "Next Steps", memory.get("next_steps"))
        return TaskSummaryMemory(
            content="\n".join(lines).rstrip() + "\n",
            covered_start_index=start_index,
            covered_end_index=end_index,
            source=source,
        )


def is_task_summary_memory(message: BaseMessage) -> bool:
    """Return whether a message is a task summary memory marker."""
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    if additional_kwargs.get("summary_memory") is True:
        return True
    content = getattr(message, "content", "")
    return isinstance(content, str) and content.startswith(SUMMARY_MARKER)


def build_merged_task_summary_memory(
    messages: list[BaseMessage],
    *,
    covered_start_index: int = 0,
    covered_end_index: int | None = None,
    source: str = MERGED_SUMMARY_SOURCE,
) -> TaskSummaryMemory:
    """Merge old completed task summaries and requests into one compact memory."""
    end_index = covered_end_index if covered_end_index is not None else max(len(messages) - 1, 0)
    facts: dict[str, list[str]] = {
        "previous_requests": [],
        "constraints": [],
        "current_plan": [],
        "decisions": [],
        "files_inspected": [],
        "files_modified": [],
        "verification": [],
        "open_risks": [],
        "next_steps": [],
    }
    for message in messages:
        if is_task_summary_memory(message):
            _merge_summary_sections(facts, _message_text(message))
        elif isinstance(message, HumanMessage):
            _append_unique(facts["previous_requests"], _preview(_message_text(message), 180))

    lines = [
        SUMMARY_MARKER,
        "scope: current_session",
        f"source: {source}",
        f"created_at: {_utc_now()}",
        f"covered_messages: {covered_start_index}-{end_index}",
        "",
        "## User Goal",
        "Merged completed task history from earlier conversation.",
        "",
    ]
    _append_list_section(lines, "Previous Requests", facts["previous_requests"])
    _append_list_section(lines, "Constraints", facts["constraints"])
    _append_list_section(lines, "Current Plan", facts["current_plan"])
    _append_list_section(lines, "Decisions", facts["decisions"])
    _append_files_section(
        lines,
        inspected=facts["files_inspected"],
        modified=facts["files_modified"],
    )
    _append_list_section(lines, "Verification", facts["verification"])
    _append_list_section(lines, "Open Risks", facts["open_risks"])
    _append_list_section(lines, "Next Steps", facts["next_steps"])
    return TaskSummaryMemory(
        content="\n".join(lines).rstrip() + "\n",
        covered_start_index=covered_start_index,
        covered_end_index=end_index,
        source=source,
    )


def _latest_summary_index(messages: list[BaseMessage], start_index: int) -> int | None:
    for index, message in enumerate(messages[start_index:], start=start_index):
        if is_task_summary_memory(message):
            return index
    return None


def _merge_summary_sections(facts: dict[str, list[str]], content: str) -> None:
    current = ""
    file_mode = ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current = line[3:].strip().lower()
            file_mode = ""
            continue
        if line in {SUMMARY_MARKER} or ":" in line and current == "":
            continue
        if current == "user goal":
            if line != "none recorded":
                _append_unique(facts["previous_requests"], _preview(_strip_bullet(line), 180))
        elif current == "constraints":
            _append_fact(facts["constraints"], line)
        elif current == "current plan":
            _append_fact(facts["current_plan"], line)
        elif current == "decisions":
            _append_fact(facts["decisions"], line)
        elif current == "files":
            normalized = line.rstrip(":").lower()
            if normalized == "inspected":
                file_mode = "files_inspected"
            elif normalized == "modified":
                file_mode = "files_modified"
            elif file_mode:
                _append_fact(facts[file_mode], line)
        elif current == "verification":
            _append_fact(facts["verification"], line)
        elif current == "open risks":
            _append_fact(facts["open_risks"], line)
        elif current == "next steps":
            _append_fact(facts["next_steps"], line)


def _append_fact(values: list[str], line: str) -> None:
    value = _strip_bullet(line)
    if value and value != "none recorded":
        _append_unique(values, _preview(value, 220))


def _append_unique(values: list[str], value: str) -> None:
    normalized = " ".join(str(value or "").split())
    if not normalized or normalized in values:
        return
    if len(values) >= MAX_MERGED_ITEMS_PER_SECTION:
        return
    values.append(normalized)


def _strip_bullet(line: str) -> str:
    text = line.strip()
    return text[2:].strip() if text.startswith("- ") else text


def _message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _preview(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _task_state_has_facts(task_state: dict[str, Any]) -> bool:
    items = task_state.get("items")
    if isinstance(items, list) and any(isinstance(item, dict) for item in items):
        return True
    memory = task_state.get("memory") or {}
    if not isinstance(memory, dict):
        return False
    if _scalar_or_none(memory.get("user_goal")):
        return True
    for value in memory.values():
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
    return False


def _append_section(lines: list[str], title: str, value: str | None) -> None:
    lines.extend([f"## {title}", value or "none recorded", ""])


def _append_list_section(lines: list[str], title: str, values: Any) -> None:
    lines.append(f"## {title}")
    normalized = _normalize_list(values)
    if normalized:
        lines.extend(f"- {value}" for value in normalized)
    else:
        lines.append("none recorded")
    lines.append("")


def _append_plan_section(lines: list[str], items: Any) -> None:
    lines.append("## Current Plan")
    if not isinstance(items, list) or not items:
        lines.append("none recorded")
        lines.append("")
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "pending").strip()
        text = str(item.get("text") or "").strip()
        item_id = str(item.get("id") or "").strip()
        label = f"{status}: {text}" if text else status
        if item_id:
            label = f"[{item_id}] {label}"
        lines.append(f"- {label}")
    lines.append("")


def _append_files_section(lines: list[str], *, inspected: Any, modified: Any) -> None:
    lines.append("## Files")
    inspected_values = _normalize_list(inspected)
    modified_values = _normalize_list(modified)
    lines.append("Inspected:")
    if inspected_values:
        lines.extend(f"- {value}" for value in inspected_values)
    else:
        lines.append("- none recorded")
    lines.append("")
    lines.append("Modified:")
    if modified_values:
        lines.extend(f"- {value}" for value in modified_values)
    else:
        lines.append("- none recorded")
    lines.append("")


def _normalize_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    normalized = []
    for value in values:
        text = str(value).strip()
        if text:
            normalized.append(text)
    return normalized


def _scalar_or_none(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
