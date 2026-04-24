"""Tests for workspace state and git diff tools."""

import subprocess

from tools import TOOL_HANDLERS, TOOLS
from tools.git_diff import git_diff
from tools.workspace_state import workspace_state


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
    (repo / "tracked.txt").write_text("hello\n")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "init")


def test_workspace_tools_are_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert "workspace_state" in tool_names
    assert "git_diff" in tool_names
    assert "workspace_state" in TOOL_HANDLERS
    assert "git_diff" in TOOL_HANDLERS


def test_workspace_state_reports_branch_and_changes(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("hello\nchanged\n")
    monkeypatch.setattr("tools.workspace_state.WORKDIR", tmp_path)

    result = workspace_state()

    assert "branch:" in result
    assert "changed_files: 1" in result
    assert "tracked.txt" in result


def test_git_diff_returns_scoped_diff(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("hello\nchanged\n")
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.git_diff.WORKDIR", tmp_path)

    result = git_diff(paths=["tracked.txt"])

    assert "diff --git" in result
    assert "+changed" in result


def test_git_diff_blocks_workspace_escape(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.git_diff.WORKDIR", tmp_path)

    result = git_diff(paths=["../outside.txt"])

    assert result.startswith("Error:")
