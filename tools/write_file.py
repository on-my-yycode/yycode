"""Write file tool."""

from difflib import unified_diff
from pathlib import Path

from .diff_utils import format_diff_result
from .read_file import safe_path
from .safety import approval_required


def _apply_patch_required_message(path: str) -> str:
    return (
        f"Code workflow guard blocked write_file for existing file: {path}\n\n"
        "Use apply_patch with path + old_text + new_text, or a unified diff, "
        "for existing file edits. write_file is only allowed for brand-new files."
    )


def write_file(
    path: str,
    content: str,
    approved: bool = False,
    workdir: Path | str | None = None,
) -> str:
    """Write content to file."""
    try:
        fp = safe_path(path, workdir)
        if fp.exists():
            return _apply_patch_required_message(path)
        if not approved:
            return approval_required(
                action="create_file",
                path=path,
                reason="write_file creates a new file and requires user approval before writing.",
                risk="Creating files changes the workspace and may add unwanted artifacts.",
            )
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return format_diff_result(f"Wrote {len(content)} bytes to {path}", [path], workdir=workdir)
    except Exception as e:
        return f"Error: {e}"


def preview_write_file_diff(path: str, content: str, workdir: Path | str | None = None) -> str:
    """Return the diff that write_file would create without writing."""
    try:
        fp = safe_path(path, workdir)
        if fp.exists():
            return ""
        lines = "\n".join(
            unified_diff(
                [],
                content.splitlines(),
                fromfile="/dev/null",
                tofile=f"b/{path}",
                lineterm="",
            )
        )
        return lines
    except Exception:
        return ""


write_file_tool = {
    "name": "write_file",
    "description": (
        "Create a brand-new file or generated artifact. Do not use this for existing "
        "file edits; use apply_patch for existing files so the diff is reviewable. "
        "Requires approved=true after explicit user approval."
    ),
    "execution": {
        "side_effects": "workspace_write",
        "concurrency": "serial",
        "timeout_seconds": 60,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "approved": {
                "type": "boolean",
                "description": "Set true only after the user explicitly approves this file creation.",
            },
        },
        "required": ["path", "content"],
    },
}
