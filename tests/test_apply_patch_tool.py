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


def test_apply_patch_requires_approval_for_unified_diff(tmp_path, monkeypatch):
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

    assert result.startswith("approval_required:")
    assert "action: edit_file" in result
    assert (tmp_path / "sample.txt").read_text() == "old\n"


def test_apply_patch_applies_unified_diff_after_approval(tmp_path, monkeypatch):
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

    result = apply_patch(patch, approved=True)

    assert result.startswith("Applied patch.")
    assert "diff:" in result
    assert "-old" in result
    assert "+new" in result
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

    assert result.startswith("approval_required:")
    assert "action: delete_file" in result
    assert (tmp_path / "sample.txt").exists()


def test_apply_patch_rejects_begin_patch_format():
    result = apply_patch("*** Begin Patch\n*** End Patch")

    assert "unified diff" in result


def test_apply_patch_supports_exact_replacement_mode(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)

    result = apply_patch(path="sample.txt", old_text="old\n", new_text="new\n", approved=True)

    assert result.startswith("Applied replacement patch to sample.txt.")
    assert "diff:" in result
    assert "-old" in result
    assert "+new" in result
    assert (tmp_path / "sample.txt").read_text() == "new\n"


def test_apply_patch_replacement_diff_shows_only_current_operation(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)
    (tmp_path / "sample.txt").write_text("first changed\nsecond\n")

    result = apply_patch(
        path="sample.txt",
        old_text="second\n",
        new_text="second changed\n",
        approved=True,
    )

    assert "-second" in result
    assert "+second changed" in result
    assert "-old" not in result
    assert "+first changed" not in result


def test_apply_patch_rejects_whole_file_replacement(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)
    content = "\n".join(f"line {index}" for index in range(100)) + "\n"
    (tmp_path / "sample.txt").write_text(content)

    result = apply_patch(
        path="sample.txt",
        old_text=content,
        new_text=content.replace("line 99", "changed"),
        approved=True,
    )

    assert "Refusing whole-file replacement" in result


def test_apply_patch_rejects_large_replacement_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)
    old_text = "\n".join(f"line {index}" for index in range(81)) + "\n"
    content = old_text + "tail\n"
    (tmp_path / "sample.txt").write_text(content)

    result = apply_patch(
        path="sample.txt",
        old_text=old_text,
        new_text=old_text.replace("line 80", "changed"),
        approved=True,
    )

    assert "Replacement block is too large" in result


def test_apply_patch_replacement_requires_path_and_old_text():
    result = apply_patch(path="sample.txt", new_text="new\n")

    assert result == "Error: path and old_text are required for replacement patches"


def test_apply_patch_replacement_requires_approval(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.setattr("tools.read_file.WORKDIR", tmp_path)
    monkeypatch.setattr("tools.apply_patch.WORKDIR", tmp_path)

    result = apply_patch(path="sample.txt", old_text="old\n", new_text="new\n")

    assert result.startswith("approval_required:")
    assert "action: edit_file" in result
    assert (tmp_path / "sample.txt").read_text() == "old\n"
