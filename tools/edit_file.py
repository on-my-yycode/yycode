"""Edit file tool."""

def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace exact text in file."""
    return (
        f"Code workflow guard blocked edit_file for: {path}\n\n"
        "Use apply_patch with path + old_text + new_text, or a unified diff, "
        "for code edits so the change is reviewable and the diff can be shown to the user."
    )


edit_file_tool = {
    "name": "edit_file",
    "description": (
        "Fallback exact-text replacement for exceptional cases. Prefer apply_patch "
        "for normal code edits so changes are reviewable as a diff."
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
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        "required": ["path", "old_text", "new_text"],
    },
}
