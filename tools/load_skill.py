"""Load skill tool - tool definition only."""

load_skill_tool = {
    "name": "load_skill",
    "description": (
        "Load the full content of one or more local skills by name or path. "
        "Use this after list_skills when you need the full instructions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Skill names or paths to load.",
            },
        },
        "required": ["names"],
    },
}


def load_skill(names: list[str]) -> str:
    """Dummy load_skill handler - should be bound by the graph at runtime."""
    raise RuntimeError("load_skill tool handler should be created by SkillRegistry")
