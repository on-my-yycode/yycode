"""Tests for write tool guardrails and diff output."""

import subprocess

from tools.edit_file import edit_file
from tools.write_file import write_file


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


def test_write_file_blocks_existing_files(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = write_file("sample.txt", "new\n")

    assert "blocked write_file for existing file" in result
    assert "Use apply_patch" in result
    assert (tmp_path / "sample.txt").read_text() == "old\n"


def test_write_file_requires_approval_for_new_files(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = write_file("new.txt", "new\n")

    assert result.startswith("approval_required:")
    assert "action: create_file" in result
    assert not (tmp_path / "new.txt").exists()


def test_write_file_allows_new_files_after_approval_and_returns_diff_preview(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = write_file("new.txt", "new\n", approved=True)

    assert result.startswith("Wrote")
    assert "diff_stat:" in result
    assert "diff:" in result
    assert "+new" in result
    assert (tmp_path / "new.txt").read_text() == "new\n"


def test_edit_file_is_blocked_and_requires_apply_patch(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)

    result = edit_file("sample.txt", "old", "new")

    assert "blocked edit_file" in result
    assert "Use apply_patch" in result
    assert (tmp_path / "sample.txt").read_text() == "old\n"
