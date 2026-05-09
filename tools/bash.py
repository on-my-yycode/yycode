"""Bash tool."""

import subprocess
from pathlib import Path

from .safety import unsafe_command_response
from .read_file import workspace_for

MAX_OUTPUT_CHARS = 50_000


def _format_stream(name: str, content: str) -> str:
    """Format a subprocess stream with an explicit empty marker."""
    text = content.strip()
    return f"{name}:\n{text or '(empty)'}"


def _format_bash_result(returncode: int, stdout: str, stderr: str) -> str:
    """Return a model-readable command result."""
    status = "success" if returncode == 0 else "failed"
    result = (
        f"status: {status}\n"
        f"exit_code: {returncode}\n"
        f"{_format_stream('stdout', stdout)}\n"
        f"{_format_stream('stderr', stderr)}"
    )
    if len(result) > MAX_OUTPUT_CHARS:
        return result[:MAX_OUTPUT_CHARS] + f"\n... output truncated to {MAX_OUTPUT_CHARS} chars"
    return result


def bash(command: str, approved: bool = False, workdir: Path | str | None = None) -> str:
    """Run a shell command."""
    unsafe_response = unsafe_command_response(command)
    if unsafe_response and not approved:
        return unsafe_response
    try:
        workspace = workspace_for(workdir)
        r = subprocess.run(
            command,
            shell=True,
            cwd=workspace.root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return _format_bash_result(r.returncode, r.stdout, r.stderr)
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


bash_tool = {
    "name": "bash",
    "description": (
        "Run a shell command when built-in tools are insufficient. "
        "Do not use this for normal code navigation when list_files, grep, read_file, "
        "read_many_files, git_show, or git_diff can answer the question."
    ),
    "execution": {
        "side_effects": "process",
        "concurrency": "serial",
        "timeout_seconds": 130,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "approved": {
                "type": "boolean",
                "description": "Set true only after this command is approved by runtime approval.",
            },
        },
        "required": ["command"],
    },
}
