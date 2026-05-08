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


def _format_match_with_context(
    relative_path: Path,
    lines: list[str],
    line_number: int,
    before_context: int,
    after_context: int,
) -> str:
    if before_context <= 0 and after_context <= 0:
        return f"{relative_path}:{line_number}:{lines[line_number - 1]}"

    start = max(line_number - before_context, 1)
    end = min(line_number + after_context, len(lines))
    section = [f"{relative_path}:{line_number}:"]
    for current in range(start, end + 1):
        marker = ">" if current == line_number else " "
        section.append(f"{marker} {current}: {lines[current - 1]}")
    return "\n".join(section)


def grep(
    pattern: str,
    path: str = ".",
    max_results: int = 100,
    before_context: int = 0,
    after_context: int = 0,
    workdir: Path | str | None = None,
) -> str:
    """Search workspace files using Python regex matching."""
    try:
        workspace = read_file.workspace_for(workdir)
        search_path = workspace.safe_path(path)
        max_results = max(1, min(int(max_results), 500))
        before_context = max(0, min(int(before_context), 20))
        after_context = max(0, min(int(after_context), 20))
        regex = re.compile(pattern)
        matches = []
        for file_path in _iter_files(search_path):
            text = _read_text(file_path)
            if text is None:
                continue
            relative_path = file_path.relative_to(workspace.root)
            lines = text.splitlines()
            for line_number, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(
                        _format_match_with_context(
                            relative_path,
                            lines,
                            line_number,
                            before_context,
                            after_context,
                        )
                    )
                    if len(matches) >= max_results:
                        output = "\n\n".join(matches)
                        return output[:MAX_OUTPUT_CHARS]

        output = "\n\n".join(matches)
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
            "before_context": {
                "type": "integer",
                "description": "Number of lines to include before each match, capped at 20.",
            },
            "after_context": {
                "type": "integer",
                "description": "Number of lines to include after each match, capped at 20.",
            },
        },
        "required": ["pattern"],
    },
}
