"""Apply reviewable patches safely inside the workspace."""

import re
import subprocess
from pathlib import Path

from .diff_utils import format_diff_result
from .read_file import WORKDIR, safe_path
from .safety import ApprovalRequired, approval_required

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
            raise ApprovalRequired(
                approval_required(
                    action="delete_file",
                    reason="apply_patch does not delete files without explicit approval.",
                    risk="File deletion can remove user work or project assets.",
                )
            )
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


def _apply_replacement(path: str, old_text: str, new_text: str) -> str:
    fp = safe_path(path)
    content = fp.read_text()
    if old_text not in content:
        return f"Error: old_text not found in {path}"
    fp.write_text(content.replace(old_text, new_text, 1))
    return format_diff_result(f"Applied replacement patch to {path}.", [path])


def _edit_approval_required(paths: list[str]) -> str:
    path_text = ", ".join(paths) if paths else ""
    return approval_required(
        action="edit_file",
        path=path_text,
        reason="apply_patch edits workspace files and requires user approval before writing.",
        risk="File edits can overwrite user work or introduce unintended code changes.",
    )


def apply_patch(
    patch: str = "",
    path: str = "",
    old_text: str = "",
    new_text: str = "",
    approved: bool = False,
) -> str:
    """Apply a unified diff or exact replacement patch after path validation."""
    try:
        if path or old_text or new_text:
            if not path or not old_text:
                return "Error: path and old_text are required for replacement patches"
            if not approved:
                return _edit_approval_required([path])
            return _apply_replacement(path, old_text, new_text)

        patch_text = _strip_fence(patch)
        if not patch_text.strip():
            return "Error: Patch is empty"
        if patch_text.lstrip().startswith("*** Begin Patch"):
            return "Error: apply_patch expects a unified diff patch, not Begin Patch format"
        if len(patch_text) > MAX_PATCH_CHARS:
            return f"Error: Patch exceeds {MAX_PATCH_CHARS} characters"

        changed_paths = _changed_paths(patch_text)
        _validate_paths(changed_paths)
        if not approved:
            return _edit_approval_required(sorted(changed_paths))

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

        return format_diff_result("Applied patch.", sorted(changed_paths))
    except subprocess.TimeoutExpired:
        return "Error: Timeout"
    except ApprovalRequired as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


apply_patch_tool = {
    "name": "apply_patch",
    "description": (
        "Primary tool for editing existing files. Prefer path + old_text + new_text "
        "for exact replacements; use patch for full unified diffs. Requires approved=true "
        "after explicit user approval and returns the resulting diff."
    ),
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
                "description": "Optional unified diff patch to apply inside the workspace.",
            },
            "path": {
                "type": "string",
                "description": "Workspace-relative file path for exact replacement mode.",
            },
            "old_text": {
                "type": "string",
                "description": "Exact text to replace once when using replacement mode.",
            },
            "new_text": {
                "type": "string",
                "description": "Replacement text when using replacement mode.",
            },
            "approved": {
                "type": "boolean",
                "description": "Set true only after the user explicitly approves this file edit.",
            },
        },
        "required": [],
    },
}
