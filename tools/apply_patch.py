"""Apply unified diff patches safely inside the workspace."""

import re
import subprocess
from pathlib import Path

from .read_file import WORKDIR, safe_path

MAX_PATCH_CHARS = 100_000


def _strip_fence(patch: str) -> str:
    text = patch
    if text.lstrip().startswith("```"):
        lines = text.strip().splitlines()
        if lines and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]) + "\n"
    return text


def _changed_paths(patch: str) -> set[str]:
    paths = set()
    for line in patch.splitlines():
        if line.startswith("deleted file mode") or line.startswith("+++ /dev/null"):
            raise ValueError("file deletion is not allowed by apply_patch")
        if line.startswith(("--- ", "+++ ")):
            raw = line[4:].split("\t", 1)[0].strip()
            if raw == "/dev/null":
                continue
            if raw.startswith(("a/", "b/")):
                raw = raw[2:]
            paths.add(raw)
        elif line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if match:
                paths.update(match.groups())
    return paths


def _validate_paths(paths: set[str]) -> None:
    if not paths:
        raise ValueError("no changed paths found in patch")
    for path in paths:
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError(f"path escapes workspace: {path}")
        safe_path(path)


def apply_patch(patch: str) -> str:
    """Apply a unified diff patch after path validation."""
    try:
        patch_text = _strip_fence(patch)
        if not patch_text.strip():
            return "Error: Patch is empty"
        if patch_text.lstrip().startswith("*** Begin Patch"):
            return "Error: apply_patch expects a unified diff patch, not Begin Patch format"
        if len(patch_text) > MAX_PATCH_CHARS:
            return f"Error: Patch exceeds {MAX_PATCH_CHARS} characters"

        _validate_paths(_changed_paths(patch_text))

        check = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", "-"],
            input=patch_text,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check.returncode != 0:
            output = (check.stdout + check.stderr).strip()
            return f"Error: {output or 'git apply --check failed'}"

        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            input=patch_text,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            return f"Error: {output or 'git apply failed'}"

        stat = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        summary = (stat.stdout + stat.stderr).strip()
        return f"Applied patch.\n{summary}" if summary else "Applied patch."
    except subprocess.TimeoutExpired:
        return "Error: Timeout"
    except Exception as exc:
        return f"Error: {exc}"


apply_patch_tool = {
    "name": "apply_patch",
    "description": "Apply a workspace-scoped unified diff patch after safety checks.",
    "execution": {
        "side_effects": "workspace_write",
        "concurrency": "serial",
        "timeout_seconds": 60,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "patch": {
                "type": "string",
                "description": "Unified diff patch to apply inside the workspace.",
            },
        },
        "required": ["patch"],
    },
}
