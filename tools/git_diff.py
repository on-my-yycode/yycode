"""Git diff inspection tool."""

import subprocess
from pathlib import Path

from .read_file import WORKDIR, safe_path

MAX_OUTPUT_CHARS = 50_000


def _relative_path(path: str) -> str:
    return str(safe_path(path).relative_to(WORKDIR))


def git_diff(paths: list[str] | None = None, staged: bool = False) -> str:
    """Return git diff for workspace-relative paths."""
    try:
        command = ["git", "diff"]
        if staged:
            command.append("--cached")
        command.append("--")
        if paths:
            command.extend(_relative_path(path) for path in paths)

        result = subprocess.run(
            command,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"Error: {output or f'git diff exited with {result.returncode}'}"
        return output[:MAX_OUTPUT_CHARS] if output else "No diff."
    except subprocess.TimeoutExpired:
        return "Error: Timeout (30s)"
    except Exception as exc:
        return f"Error: {exc}"


git_diff_tool = {
    "name": "git_diff",
    "description": "Show the current git diff, optionally scoped to workspace-relative paths.",
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
                "description": "Optional workspace-relative paths to diff.",
            },
            "staged": {
                "type": "boolean",
                "description": "When true, show staged diff with git diff --cached.",
            },
        },
        "required": [],
    },
}
