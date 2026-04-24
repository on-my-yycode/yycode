"""Git show inspection tool."""

import subprocess

from . import read_file

MAX_OUTPUT_CHARS = 50_000


def _relative_path(path: str) -> str:
    return str(read_file.safe_path(path).relative_to(read_file.WORKDIR))


def git_show(ref: str = "HEAD", path: str = "") -> str:
    """Show a git object or a file at a git ref."""
    try:
        command = ["git", "show", "--no-ext-diff", "--color=never"]
        if path:
            command.append(f"{ref}:{_relative_path(path)}")
        else:
            command.append(ref)
        result = subprocess.run(
            command,
            cwd=read_file.WORKDIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"Error: {output or f'git show exited with {result.returncode}'}"
        return output[:MAX_OUTPUT_CHARS] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (30s)"
    except Exception as exc:
        return f"Error: {exc}"


git_show_tool = {
    "name": "git_show",
    "description": "Show git commit content or a workspace file at a specific ref.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "ref": {
                "type": "string",
                "description": "Git ref, commit, tag, or range. Defaults to HEAD.",
            },
            "path": {
                "type": "string",
                "description": "Optional workspace-relative path to show at the ref.",
            },
        },
        "required": [],
    },
}
