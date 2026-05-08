"""Read file tool."""

from pathlib import Path

from .workspace import Workspace

WORKDIR = Path.cwd()


def workspace_for(workdir: Path | str | None = None) -> Workspace:
    """Return the workspace for a tool call."""
    return Workspace(Path(workdir) if workdir is not None else WORKDIR)


def safe_path(p: str, workdir: Path | str | None = None) -> Path:
    """Get a safe path within the workspace."""
    return workspace_for(workdir).safe_path(p)


def read_file(
    path: str,
    limit: int = None,
    start_line: int | None = None,
    end_line: int | None = None,
    workdir: Path | str | None = None,
) -> str:
    """Read file contents."""
    try:
        text = safe_path(path, workdir).read_text()
        lines = text.splitlines()
        if start_line is not None or end_line is not None:
            start = max((start_line or 1) - 1, 0)
            end = max(end_line or len(lines), 0)
            if end < start + 1:
                return "Error: end_line must be greater than or equal to start_line"
            selected = lines[start:end]
            return "\n".join(selected)[:50000]
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


read_file_tool = {
    "name": "read_file",
    "description": "Read file contents.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "limit": {"type": "integer"},
            "start_line": {"type": "integer"},
            "end_line": {"type": "integer"},
        },
        "required": ["path"],
    },
}
