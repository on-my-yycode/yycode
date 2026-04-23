"""List skills tool - tool definition only."""

list_skills_tool = {
    "name": "list_skills",
    "description": (
        "List available local skills with their names and descriptions. "
        "Use this before loading a skill when you are unsure what exists."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def list_skills() -> str:
    """Dummy list_skills handler - should be bound by the graph at runtime."""
    raise RuntimeError("list_skills tool handler should be created by SkillRegistry")
