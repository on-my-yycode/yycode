"""Workspace state inspection tool."""

import subprocess
from pathlib import Path

WORKDIR = Path.cwd()
MAX_OUTPUT_CHARS = 20_000


def _run_git(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=WORKDIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def workspace_state() -> str:
    """Return branch and working tree status."""
    try:
        code, branch = _run_git(["branch", "--show-current"])
        if code != 0:
            return f"Error: {branch or 'not a git repository'}"

        _, status = _run_git(["status", "--short"])
        lines = [line for line in status.splitlines() if line.strip()]
        changed = len(lines)
        status_text = "\n".join(lines) if lines else "clean"

        return (
            f"branch: {branch or '(detached)'}\n"
            f"changed_files: {changed}\n"
            f"status:\n{status_text}"
        )[:MAX_OUTPUT_CHARS]
    except subprocess.TimeoutExpired:
        return "Error: Timeout (30s)"
    except Exception as exc:
        return f"Error: {exc}"


workspace_state_tool = {
    "name": "workspace_state",
    "description": "Inspect the current git branch and working tree status.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
