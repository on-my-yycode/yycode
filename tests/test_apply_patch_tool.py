"""Tests for apply_patch tool."""

import subprocess

from tools import TOOL_HANDLERS, TOOLS
from tools.apply_patch import apply_patch


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


def test_apply_patch_tool_is_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert "apply_patch" in tool_names
    assert "apply_patch" in TOOL_HANDLERS


def test_apply_patch_applies_unified_diff(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)
    patch = """diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1,1 +1,1 @@
-old
+new
"""

    result = apply_patch(patch)

    assert result.startswith("Applied patch.")
    assert (tmp_path / "sample.txt").read_text() == "new\n"


def test_apply_patch_rejects_deletions(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)
    patch = """diff --git a/sample.txt b/sample.txt
deleted file mode 100644
--- a/sample.txt
+++ /dev/null
@@ -1,1 +0,0 @@
-old
"""

    result = apply_patch(patch)

    assert "file deletion is not allowed" in result
    assert (tmp_path / "sample.txt").exists()


def test_apply_patch_rejects_begin_patch_format():
    result = apply_patch("*** Begin Patch\n*** End Patch")

    assert "unified diff" in result
