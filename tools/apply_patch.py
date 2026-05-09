"""Apply reviewable patches safely inside the workspace."""

from difflib import unified_diff
import re
import subprocess
from pathlib import Path

from .read_file import safe_path, workspace_for
from .safety import ApprovalRequired, approval_required

MAX_PATCH_CHARS = 100_000
MAX_REPLACEMENT_LINES = 80


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


def _validate_paths(paths: set[str], workdir: Path | str | None = None) -> None:
    if not paths:
        raise ValueError("no changed paths found in patch")
    for path in paths:
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError(f"path escapes workspace: {path}")
        safe_path(path, workdir)


def _read_snapshot(path: str, workdir: Path | str | None = None) -> str:
    fp = safe_path(path, workdir)
    if not fp.exists():
        return ""
    try:
        return fp.read_text()
    except UnicodeDecodeError:
        return "<binary or non-utf8 file>"


def _format_operation_diff(
    action: str,
    before_by_path: dict[str, str],
    workdir: Path | str | None = None,
) -> str:
    sections = _diff_sections(
        {
            path: (before, _read_snapshot(path, workdir))
            for path, before in before_by_path.items()
        }
    )
    if not sections:
        return f"{action}\n\ndiff: No diff."
    return f"{action}\n\ndiff:\n" + "\n".join(sections)


def _diff_sections(before_after_by_path: dict[str, tuple[str, str]]) -> list[str]:
    sections = []
    for path, (before, after) in before_after_by_path.items():
        if before == after:
            continue
        before_lines = before.splitlines()
        after_lines = after.splitlines()
        diff = "\n".join(
            unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        if diff:
            sections.append(diff)
    return sections


def _format_preview_diff(before_after_by_path: dict[str, tuple[str, str]]) -> str:
    sections = _diff_sections(before_after_by_path)
    return "\n".join(sections)


def _preview_replacement(
    path: str,
    old_text: str,
    new_text: str,
    workdir: Path | str | None = None,
) -> str:
    try:
        fp = safe_path(path, workdir)
        content = fp.read_text()
    except Exception as exc:
        return f"Error: {exc}"
    if old_text not in content:
        return f"Error: old_text not found in {path}"
    after = content.replace(old_text, new_text, 1)
    return _format_preview_diff({path: (content, after)})


def preview_apply_patch_diff(
    patch: str = "",
    path: str = "",
    old_text: str = "",
    new_text: str = "",
    workdir: Path | str | None = None,
) -> str:
    """Return the diff that apply_patch would apply without modifying files."""
    if path or old_text or new_text:
        if not path or not old_text:
            return ""
        return _preview_replacement(path, old_text, new_text, workdir)

    patch_text = _strip_fence(patch)
    if not patch_text.strip() or patch_text.lstrip().startswith("*** Begin Patch"):
        return ""
    if len(patch_text) > MAX_PATCH_CHARS:
        return ""
    try:
        changed_paths = _changed_paths(patch_text)
        _validate_paths(changed_paths, workdir)
    except Exception:
        return ""
    return patch_text.strip()


def _looks_like_whole_file(content: str, old_text: str) -> bool:
    return old_text == content and len(content.splitlines()) > MAX_REPLACEMENT_LINES


def _replacement_is_too_large(old_text: str, new_text: str) -> bool:
    return (
        len(old_text.splitlines()) > MAX_REPLACEMENT_LINES
        or len(new_text.splitlines()) > MAX_REPLACEMENT_LINES
    )


def _apply_replacement(
    path: str,
    old_text: str,
    new_text: str,
    workdir: Path | str | None = None,
) -> str:
    fp = safe_path(path, workdir)
    content = fp.read_text()
    if old_text not in content:
        return f"Error: old_text not found in {path}"
    if _looks_like_whole_file(content, old_text):
        return (
            "Error: Refusing whole-file replacement in apply_patch exact replacement mode. "
            "Use old_text/new_text for only the smallest changed block, or provide a focused unified diff."
        )
    if _replacement_is_too_large(old_text, new_text):
        return (
            f"Error: Replacement block is too large for exact replacement mode "
            f"({MAX_REPLACEMENT_LINES} line limit). Use a focused unified diff with context instead."
        )
    before_by_path = {path: content}
    fp.write_text(content.replace(old_text, new_text, 1))
    return _format_operation_diff(f"Applied replacement patch to {path}.", before_by_path, workdir)


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
    workdir: Path | str | None = None,
) -> str:
    """Apply a unified diff or exact replacement patch after path validation."""
    try:
        workspace = workspace_for(workdir)
        if path or old_text or new_text:
            if not path or not old_text:
                return "Error: path and old_text are required for replacement patches"
            if not approved:
                return _edit_approval_required([path])
            return _apply_replacement(path, old_text, new_text, workspace.root)

        patch_text = _strip_fence(patch)
        if not patch_text.strip():
            return "Error: Patch is empty"
        if patch_text.lstrip().startswith("*** Begin Patch"):
            return "Error: apply_patch expects a unified diff patch, not Begin Patch format"
        if len(patch_text) > MAX_PATCH_CHARS:
            return f"Error: Patch exceeds {MAX_PATCH_CHARS} characters"

        changed_paths = _changed_paths(patch_text)
        _validate_paths(changed_paths, workspace.root)
        if not approved:
            return _edit_approval_required(sorted(changed_paths))
        before_by_path = {path: _read_snapshot(path, workspace.root) for path in sorted(changed_paths)}

        check = subprocess.run(
            ["git", "apply", "--check", "--whitespace=nowarn", "-"],
            input=patch_text,
            cwd=workspace.root,
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
            cwd=workspace.root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            return f"Error: {output or 'git apply failed'}"

        return _format_operation_diff("Applied patch.", before_by_path, workspace.root)
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
        "for exact replacements (old_text MUST contain ONLY the exact lines to be changed, "
        "NOT the entire file and not large unchanged blocks); use patch for focused unified diffs. Requires approved=true "
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
                "description": "Small exact text block to replace once. Do not pass the whole file or large unchanged blocks.",
            },
            "new_text": {
                "type": "string",
                "description": "Replacement text for the small changed block.",
            },
            "approved": {
                "type": "boolean",
                "description": "Set true only after the user explicitly approves this file edit.",
            },
        },
        "required": [],
    },
}
