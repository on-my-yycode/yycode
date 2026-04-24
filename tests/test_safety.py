"""Tests for safety approval blocking."""

from tools.bash import bash
from agent.approval import approval_request_for_tool
from tools.safety import unsafe_command_response


def test_unsafe_command_response_formats_approval_required():
    result = unsafe_command_response("git reset --hard")

    assert result.startswith("approval_required:")
    assert "action: destructive_git" in result
    assert "command: git reset --hard" in result


def test_bash_blocks_dangerous_command_with_approval_required():
    result = bash("rm -rf build")

    assert result.startswith("approval_required:")
    assert "action: destructive_delete" in result


def test_approval_request_extracts_path_from_unified_diff():
    request = approval_request_for_tool(
        "apply_patch",
        {
            "patch": "\n".join(
                [
                    "diff --git a/example.py b/example.py",
                    "--- a/example.py",
                    "+++ b/example.py",
                    "@@ -1 +1 @@",
                    "-old",
                    "+new",
                ]
            )
        },
    )

    assert request.path == "example.py"
