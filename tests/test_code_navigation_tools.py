"""Tests for code navigation tools."""

import subprocess

from tools import TOOL_HANDLERS, TOOLS
from tools.git_show import git_show
from tools.list_files import list_files
from tools.read_file import read_file
from tools.read_many_files import read_many_files


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
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')\n")
    (repo / "README.md").write_text("# demo\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")


def test_code_navigation_tools_are_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert {"list_files", "read_many_files", "git_show"} <= tool_names
    assert TOOL_HANDLERS["list_files"] is list_files
    assert TOOL_HANDLERS["read_many_files"] is read_many_files
    assert TOOL_HANDLERS["git_show"] is git_show


def test_list_files_filters_by_glob(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n")
    (tmp_path / "README.md").write_text("# demo\n")
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = list_files(pattern="*.py")

    assert result == "src/app.py"


def test_read_many_files_adds_headers_and_limits_lines(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("one\ntwo\n")
    (tmp_path / "b.py").write_text("three\nfour\n")
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = read_many_files(["a.py", "b.py"], limit=1)

    assert "--- a.py ---\none\n... (1 more lines)" in result
    assert "--- b.py ---\nthree\n... (1 more lines)" in result


def test_read_file_supports_line_ranges(tmp_path, monkeypatch):
    (tmp_path / "sample.py").write_text("one\ntwo\nthree\nfour\n")
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = read_file("sample.py", start_line=2, end_line=3)

    assert result == "two\nthree"


def test_git_show_reads_file_at_ref(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = git_show(ref="HEAD", path="src/app.py")

    assert "print('hello')" in result


def test_git_show_blocks_workspace_escape(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = git_show(ref="HEAD", path="../outside.py")

    assert result.startswith("Error:")
