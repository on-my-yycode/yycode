"""Bash tool."""

import subprocess
from pathlib import Path

from .safety import unsafe_command_response

WORKDIR = Path.cwd()


def bash(command: str, approved: bool = False) -> str:
    """Run a shell command."""
    unsafe_response = unsafe_command_response(command)
    if unsafe_response and not approved:
        return unsafe_response
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


bash_tool = {
    "name": "bash",
    "description": "Run a shell command.",
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
