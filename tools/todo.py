"""Task state tracking tool - tool definition only."""


TASK_MEMORY_PROPERTIES = {
    "user_goal": {
        "type": "string",
        "description": "The current user goal in one concise sentence.",
    },
    "constraints": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Important constraints, preferences, or non-goals.",
    },
    "files_inspected": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Files or paths already inspected.",
    },
    "files_modified": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Files or paths modified during this task.",
    },
    "decisions": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Design or implementation decisions already made.",
    },
    "test_results": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Verification commands run and their results.",
    },
    "open_risks": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Known risks, uncertainties, or follow-up concerns.",
    },
    "next_steps": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Immediate next steps if the task continues.",
    },
}

todo_tool = {
    "name": "todo",
    "description": (
        "Update Task State for multi-step work. Track todo items plus compact task "
        "memory such as goal, constraints, inspected/modified files, decisions, "
        "test results, risks, and next steps."
    ),
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
                "description": "Current ordered task checklist.",
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
            "memory": {
                "type": "object",
                "description": "Optional compact task memory to preserve progress across long tool loops.",
                "properties": TASK_MEMORY_PROPERTIES,
                "additionalProperties": False,
            },
        },
        "required": ["items"],
    },
}


# Dummy handler - the real one is created by TodoManager
def todo(items, memory=None):
    """Dummy todo handler - should not be called directly."""
    raise RuntimeError("Todo tool handler should be created by TodoManager")
