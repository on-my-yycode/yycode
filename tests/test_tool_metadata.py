"""Tests for tool execution metadata."""

from tools import TOOLS


def test_all_tools_declare_execution_metadata():
    for tool in TOOLS:
        execution = tool.get("execution")
        assert execution, f"{tool['name']} missing execution metadata"
        assert execution["side_effects"] in {
            "read_only",
            "workspace_write",
            "session_state",
            "process",
            "delegation",
        }
        assert execution["concurrency"] in {"safe", "serial", "role_based"}
        assert isinstance(execution["timeout_seconds"], int)
        assert execution["timeout_seconds"] > 0


def test_mvp_tools_are_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert {"workspace_state", "git_diff", "apply_patch", "verify"} <= tool_names
