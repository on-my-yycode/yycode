"""Tests for the grep tool."""

from pathlib import Path

from tools import TOOL_HANDLERS, TOOLS
from tools.grep import grep


def test_grep_tool_is_registered():
    tool_names = {tool["name"] for tool in TOOLS}
    grep_tool = next(tool for tool in TOOLS if tool["name"] == "grep")

    assert "grep" in tool_names
    assert TOOL_HANDLERS["grep"] is grep
    assert grep_tool["description"] == (
        "A Python-powered grep tool for searching workspace files with regular expressions."
    )
    assert set(grep_tool["input_schema"]["required"]) == {"pattern"}


def test_grep_finds_matches(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    file_path = tmp_path / "sample.txt"
    file_path.write_text("alpha\nneedle here\nbeta\n")

    result = grep("needle", "sample.txt")

    assert "sample.txt:2:needle here" in result


def test_grep_reports_no_matches(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    (tmp_path / "sample.txt").write_text("alpha\n")

    result = grep("needle", ".")

    assert result == "No matches found."


def test_grep_blocks_paths_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    outside = Path(tmp_path).parent

    result = grep("needle", str(outside))

    assert result.startswith("Error: Path escapes workspace")


def test_grep_reports_invalid_regex(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    (tmp_path / "sample.txt").write_text("alpha\n")

    result = grep("[", ".")

    assert result.startswith("Error: invalid regex pattern:")


def test_grep_skips_binary_files(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    (tmp_path / "binary.bin").write_bytes(b"needle\x00here")
    (tmp_path / "sample.txt").write_text("needle\n")

    result = grep("needle", ".")

    assert "sample.txt:1:needle" in result
    assert "binary.bin" not in result


def test_grep_supports_context_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    (tmp_path / "sample.txt").write_text("alpha\nbeta\nneedle here\ngamma\ndelta\n")

    result = grep("needle", ".", before_context=1, after_context=2)

    assert "sample.txt:3:" in result
    assert "  2: beta" in result or " 2: beta" in result
    assert "> 3: needle here" in result
    assert "  4: gamma" in result or " 4: gamma" in result
    assert "  5: delta" in result or " 5: delta" in result
