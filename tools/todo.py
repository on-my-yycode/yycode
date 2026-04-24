"""Todo task tracking tool - tool definition only."""

todo_tool = {
    "name": "todo",
    "description": "Update task list. Track progress on multi-step tasks.",
    "execution": {
        "side_effects": "session_state",
        "concurrency": "serial",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                    },
                    "required": ["id", "text", "status"],
                },
            },
        },
        "required": ["items"],
    },
}


# Dummy handler - the real one is created by TodoManager
def todo(items):
    """Dummy todo handler - should not be called directly."""
    raise RuntimeError("Todo tool handler should be created by TodoManager")
