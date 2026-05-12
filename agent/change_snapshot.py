"""Shared changed-files snapshot helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ChangedFile:
    """One changed file and its diff stats."""

    path: str
    added: int
    removed: int
    diff: str = ""


@dataclass(frozen=True)
class ChangedFilesSnapshot:
    """A stable changed-files snapshot for TUI/protocol adapters."""

    files: list[ChangedFile] = field(default_factory=list)
    total_added: int = 0
    total_removed: int = 0
    source: str = ""


def extract_diff_text(content: str) -> str:
    """Return the unified diff portion from a tool result, if present."""
    if not content:
        return ""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(("diff --git ", "--- ")):
            return "\n".join(lines[index:])
    return ""


def build_changed_files_snapshot(diff: str, *, source: str = "diff") -> ChangedFilesSnapshot:
    """Return per-file stats and diff sections from a unified diff blob."""
    sections: list[dict] = []
    current: dict | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                sections.append(current)
            current = {"path": _path_from_diff_header(line), "added": 0, "removed": 0, "lines": [line]}
            continue
        if line.startswith("--- "):
            if current is not None and _diff_section_has_changes(current):
                sections.append(current)
                current = {
                    "path": _strip_diff_prefix(line[4:].split("\t", 1)[0].strip()),
                    "added": 0,
                    "removed": 0,
                    "lines": [line],
                }
            elif current is None:
                current = {
                    "path": _strip_diff_prefix(line[4:].split("\t", 1)[0].strip()),
                    "added": 0,
                    "removed": 0,
                    "lines": [line],
                }
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
        sections.append(current)
    files = _merge_changed_file_sections(sections)
    return ChangedFilesSnapshot(
        files=files,
        total_added=sum(item.added for item in files),
        total_removed=sum(item.removed for item in files),
        source=source,
    )


def changed_files_as_dicts(snapshot: ChangedFilesSnapshot) -> list[dict]:
    """Return snapshot files in the legacy dict shape used by TUI state."""
    return [
        {
            "path": file.path,
            "added": file.added,
            "removed": file.removed,
            "diff": file.diff,
        }
        for file in snapshot.files
    ]


def merge_changed_paths(items: Iterable[object]) -> list[str]:
    """Return unique changed paths from timeline-like items."""
    paths: list[str] = []
    for item in items:
        event_type = getattr(item, "event_type", "")
        tool_name = getattr(item, "tool_name", "")
        if event_type == "file_changed":
            candidates = list(getattr(item, "file_paths", []) or [])
        elif event_type in {"tool_start", "tool_end"} and tool_name in {
            "apply_patch",
            "write_file",
            "edit_file",
        }:
            candidates = list(getattr(item, "file_paths", []) or [])
        else:
            candidates = []
        for path in candidates:
            if path and path not in paths:
                paths.append(path)
    return paths


def turn_had_successful_write(items: Iterable[object]) -> bool:
    """Return whether timeline-like items include a successful write tool."""
    return any(
        getattr(item, "event_type", "") == "tool_end"
        and getattr(item, "status", None) != "failed"
        and getattr(item, "tool_name", "") in {"apply_patch", "write_file", "edit_file"}
        for item in items
    )


def _merge_changed_file_sections(sections: list[dict]) -> list[ChangedFile]:
    merged: dict[str, dict] = {}
    order: list[str] = []
    for item in sections:
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
        ChangedFile(
            path=merged[path]["path"],
            added=merged[path]["added"],
            removed=merged[path]["removed"],
            diff="\n\n".join(diff for diff in merged[path]["diffs"] if diff),
        )
        for path in order
    ]


def _diff_section_has_changes(section: dict) -> bool:
    return bool(
        section.get("added")
        or section.get("removed")
        or any(str(line).startswith("@@") for line in section.get("lines", []))
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
