"""Tests for safety approval blocking."""

import subprocess

import pytest

from tools.bash import bash
from agent.approval import ApprovalTargetMissing, approval_request_for_tool
from tools.safety import unsafe_command_response


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(repo):
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "sample.txt").write_text("old\n")
    _git(repo, "add", "sample.txt")
    _git(repo, "commit", "-m", "init")


def test_unsafe_command_response_formats_approval_required():
    result = unsafe_command_response("git reset --hard")

    assert result.startswith("approval_required:")
    assert "action: destructive_git" in result
    assert "command: git reset --hard" in result


def test_bash_blocks_dangerous_command_with_approval_required():
    result = bash("rm -rf build")

    assert result.startswith("approval_required:")
    assert "action: destructive_delete" in result


def test_bash_allows_dangerous_command_after_runtime_approval():
    result = bash("git reset -h", approved=True)

    assert not result.startswith("approval_required:")
    assert "status:" in result
    assert "exit_code:" in result
    assert "usage: git reset" in result.lower()


def test_bash_reports_success_for_command_with_no_output():
    result = bash("true")

    assert "status: success" in result
    assert "exit_code: 0" in result
    assert "stdout:\n(empty)" in result
    assert "stderr:\n(empty)" in result


def test_bash_reports_failure_with_exit_code_and_stderr():
    result = bash("python3 -c 'import sys; print(\"bad\", file=sys.stderr); sys.exit(7)'")

    assert "status: failed" in result
    assert "exit_code: 7" in result
    assert "stderr:\nbad" in result


def test_approval_request_detects_dangerous_bash_command():
    request = approval_request_for_tool("bash", {"command": "git reset --hard"})

    assert request is not None
    assert request.action == "run_command"
    assert request.command == "git reset --hard"


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


def test_approval_request_blocks_apply_patch_without_target_file():
    with pytest.raises(ApprovalTargetMissing) as exc:
        approval_request_for_tool("apply_patch", {"patch": "diff"})

    assert "no target file was detected" in str(exc.value)
    assert "Retry with an explicit target file" in str(exc.value)


def test_approval_request_blocks_write_file_without_target_file():
    with pytest.raises(ApprovalTargetMissing) as exc:
        approval_request_for_tool("write_file", {"content": "hello\n"})

    assert "File edit blocked for write_file" in str(exc.value)


def test_approval_request_includes_apply_patch_diff_preview(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)

    request = approval_request_for_tool(
        "apply_patch",
        {
            "path": "sample.txt",
            "old_text": "old\n",
            "new_text": "new\n",
        },
    )

    assert request is not None
    assert "--- a/sample.txt" in request.diff_preview
    assert "-old" in request.diff_preview
    assert "+new" in request.diff_preview
    assert (tmp_path / "sample.txt").read_text() == "old\n"
    assert "diff_preview:" in request.format()


def test_approval_request_includes_write_file_diff_preview(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    request = approval_request_for_tool(
        "write_file",
        {
            "path": "new.txt",
            "content": "hello\n",
        },
    )

    assert request is not None
    assert "--- /dev/null" in request.diff_preview
    assert "+++ b/new.txt" in request.diff_preview
    assert "+hello" in request.diff_preview
    assert not (tmp_path / "new.txt").exists()
