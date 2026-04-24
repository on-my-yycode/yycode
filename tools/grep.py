"""Python grep search tool."""

import re
from pathlib import Path

from . import read_file

MAX_OUTPUT_CHARS = 50_000
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


def _iter_files(path: Path):
    if path.is_file():
        yield path
        return
    for child in path.iterdir():
        if child.is_dir():
            if child.name in SKIP_DIRS or child.name.startswith("."):
                continue
            yield from _iter_files(child)
        elif child.is_file():
            yield child


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return None


def grep(pattern: str, path: str = ".", max_results: int = 100) -> str:
    """Search workspace files using Python regex matching."""
    try:
        search_path = read_file.safe_path(path)
        max_results = max(1, min(int(max_results), 500))
        regex = re.compile(pattern)
        matches = []
        for file_path in _iter_files(search_path):
            text = _read_text(file_path)
            if text is None:
                continue
            relative_path = file_path.relative_to(read_file.WORKDIR)
            for line_number, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{relative_path}:{line_number}:{line}")
                    if len(matches) >= max_results:
                        output = "\n".join(matches)
                        return output[:MAX_OUTPUT_CHARS]

        output = "\n".join(matches)
        return output[:MAX_OUTPUT_CHARS] if output else "No matches found."
    except re.error as exc:
        return f"Error: invalid regex pattern: {exc}"
    except Exception as exc:
        return f"Error: {exc}"


grep_tool = {
    "name": "grep",
    "description": "A Python-powered grep tool for searching workspace files with regular expressions.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Python regular expression pattern.",
            },
            "path": {
                "type": "string",
                "description": "Workspace-relative path to search. Defaults to current workspace.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum matches per file, capped at 500. Defaults to 100.",
            },
        },
        "required": ["pattern"],
    },
}
