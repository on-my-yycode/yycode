"""Subagent delegation tool - tool definition only."""

subagent_tool = {
    "name": "subagent",
    "description": (
        "Delegate a focused task to an isolated subagent and wait for its summary result. "
        "Use explorer for research, architect for design, worker for implementation, "
        "tester for verification, and security for security review."
    ),
    "execution": {
        "side_effects": "delegation",
        "concurrency": "role_based",
        "timeout_seconds": 300,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "role": {
                "type": "string",
                "enum": ["explorer", "architect", "worker", "tester", "security"],
                "description": "Subagent role to run.",
            },
            "task": {
                "type": "string",
                "description": "The concrete task the subagent should complete.",
            },
            "context": {
                "type": "string",
                "description": "Optional extra context, constraints, or relevant findings.",
            },
            "max_turns": {
                "type": "integer",
                "description": "Optional recursion limit for the subagent run. Defaults to 8.",
            },
        },
        "required": ["role", "task"],
    },
}


def subagent(role: str, task: str, context: str = "", max_turns: int = 8) -> str:
    """Dummy subagent handler - should be bound by the graph at runtime."""
    raise RuntimeError("Subagent tool handler should be created by SubagentRunner")
