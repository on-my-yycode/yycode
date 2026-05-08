"""Read multiple workspace files in one tool call."""

from .read_file import read_file

from pathlib import Path

MAX_FILES = 20
MAX_OUTPUT_CHARS = 80_000


def read_many_files(paths: list[str], limit: int | None = None, workdir: Path | str | None = None) -> str:
    """Read several files and separate each result with a header."""
    try:
        if not paths:
            return "Error: paths is required"
        selected_paths = paths[:MAX_FILES]
        sections = []
        for path in selected_paths:
            sections.append(f"--- {path} ---\n{read_file(path, limit=limit, workdir=workdir)}")
        if len(paths) > MAX_FILES:
            sections.append(f"... skipped {len(paths) - MAX_FILES} file(s); max is {MAX_FILES}")
        return "\n\n".join(sections)[:MAX_OUTPUT_CHARS]
    except Exception as exc:
        return f"Error: {exc}"


read_many_files_tool = {
    "name": "read_many_files",
    "description": "Read multiple workspace files at once with per-file headers.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Workspace-relative file paths to read, capped at 20.",
            },
            "limit": {
                "type": "integer",
                "description": "Optional maximum number of lines per file.",
            },
        },
        "required": ["paths"],
    },
}
