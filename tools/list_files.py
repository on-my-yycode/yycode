"""List workspace files without shelling out."""

import fnmatch
from pathlib import Path

from . import read_file

MAX_RESULTS = 500
SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


def _iter_files(path: Path, max_depth: int | None, depth: int = 0):
    if path.is_file():
        yield path
        return
    if max_depth is not None and depth > max_depth:
        return
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.is_dir():
            if child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            yield from _iter_files(child, max_depth, depth + 1)
        elif child.is_file():
            yield child


def list_files(
    path: str = ".",
    pattern: str = "*",
    max_results: int = 200,
    max_depth: int | None = None,
    workdir: Path | str | None = None,
) -> str:
    """List workspace-relative files, optionally filtered by glob pattern."""
    try:
        workspace = read_file.workspace_for(workdir)
        root = workspace.safe_path(path)
        max_results = max(1, min(int(max_results), MAX_RESULTS))
        files = []
        for file_path in _iter_files(root, max_depth):
            relative_path = str(file_path.relative_to(workspace.root))
            if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                files.append(relative_path)
                if len(files) >= max_results:
                    break
        return "\n".join(files) if files else "No files found."
    except Exception as exc:
        return f"Error: {exc}"


list_files_tool = {
    "name": "list_files",
    "description": "List workspace files using Python glob matching without running shell commands.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace-relative directory or file path. Defaults to current workspace.",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern matched against relative paths or file names. Defaults to *.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of files to return, capped at 500. Defaults to 200.",
            },
            "max_depth": {
                "type": "integer",
                "description": "Optional maximum directory depth from the requested path.",
            },
        },
        "required": [],
    },
}
