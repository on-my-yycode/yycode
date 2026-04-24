"""Tests for the grep tool."""

from pathlib import Path

from tools import TOOL_HANDLERS, TOOLS
from tools.grep import grep


def test_grep_tool_is_registered():
    tool_names = {tool["name"] for tool in TOOLS}
    grep_tool = next(tool for tool in TOOLS if tool["name"] == "grep")

    assert "grep" in tool_names
    assert TOOL_HANDLERS["grep"] is grep
    assert grep_tool["description"] == "A powerful search tool built on ripgrep"
    assert set(grep_tool["input_schema"]["required"]) == {"pattern"}


def test_grep_finds_matches(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.grep.WORKDIR", tmp_path)
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\nneedle here\nbeta\n")

    result = grep("needle", "sample.txt")

    assert "2:needle here" in result


def test_grep_reports_no_matches(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.grep.WORKDIR", tmp_path)
    (tmp_path / "sample.txt").write_text("alpha\n")

    result = grep("needle", ".")

    assert result == "No matches found."


def test_grep_blocks_paths_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.grep.WORKDIR", tmp_path)
    outside = Path(tmp_path).parent

    result = grep("needle", str(outside))

    assert result.startswith("Error: Path escapes workspace")
