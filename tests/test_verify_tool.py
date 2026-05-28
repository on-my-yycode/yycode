"""Tests for verify tool."""

import subprocess

from tools import TOOL_HANDLERS, TOOLS
from tools.verify import verify


def test_verify_tool_is_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert "verify" in tool_names
    assert "verify" in TOOL_HANDLERS


def test_verify_runs_pytest_target(tmp_path, monkeypatch):
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = verify(kind="tests", target="test_sample.py")

    assert "verify passed" in result
    assert "test_sample.py" in result


def test_verify_reports_invalid_kind():
    result = verify(kind="unknown")

    assert result.startswith("Error:")


def test_verify_blocks_workspace_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = verify(kind="tests", target="../outside.py")

    assert result.startswith("Error:")


def test_verify_does_not_inherit_terminal_stdin(tmp_path, monkeypatch):
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n")
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr("tools.verify.subprocess.run", fake_run)

    result = verify(kind="tests", target="test_sample.py")

    assert "verify passed" in result
    assert calls[0]["stdin"] is subprocess.DEVNULL
