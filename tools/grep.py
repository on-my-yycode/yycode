"""Grep search tool powered by ripgrep."""

import subprocess
from pathlib import Path

from .read_file import safe_path

WORKDIR = Path.cwd()
MAX_OUTPUT_CHARS = 50_000


def grep(pattern: str, path: str = ".", max_results: int = 100) -> str:
    """Search workspace files using ripgrep."""
    try:
        search_path = safe_path(path)
        max_results = max(1, min(int(max_results), 500))
        command = [
            "rg",
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--max-count",
            str(max_results),
            pattern,
            str(search_path),
        ]
        result = subprocess.run(
            command,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 1 and not output:
            return "No matches found."
        if result.returncode not in (0, 1):
            return f"Error: {output or f'rg exited with {result.returncode}'}"
        return output[:MAX_OUTPUT_CHARS] if output else "No matches found."
    except subprocess.TimeoutExpired:
        return "Error: Timeout (30s)"
    except Exception as exc:
        return f"Error: {exc}"


grep_tool = {
    "name": "grep",
    "description": "A powerful search tool built on ripgrep",
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
                "description": "Ripgrep search pattern.",
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
