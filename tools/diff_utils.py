"""Helpers for rendering git diffs after workspace writes."""

import subprocess
from pathlib import Path

from . import read_file

MAX_DIFF_CHARS = 12_000


def _workspace(workdir: Path | str | None = None):
    return read_file.workspace_for(workdir)


def _relative_paths(paths: list[str] | None, workdir: Path | str | None = None) -> list[str]:
    if not paths:
        return []
    workspace = _workspace(workdir)
    return [str(workspace.safe_path(path).relative_to(workspace.root)) for path in paths]


def git_diff_stat(paths: list[str] | None = None, workdir: Path | str | None = None) -> str:
    """Return git diff stat for optional workspace-relative paths."""
    return _run_git_diff(["--stat"], paths, max_chars=4_000, workdir=workdir)


def git_diff_preview(
    paths: list[str] | None = None,
    max_chars: int = MAX_DIFF_CHARS,
    workdir: Path | str | None = None,
) -> str:
    """Return a capped git diff for optional workspace-relative paths."""
    return _run_git_diff([], paths, max_chars=max_chars, workdir=workdir)


def format_diff_result(
    action: str,
    paths: list[str] | None = None,
    workdir: Path | str | None = None,
) -> str:
    """Format a write-tool result with diff stat and capped diff preview."""
    stat = git_diff_stat(paths, workdir=workdir)
    diff = git_diff_preview(paths, workdir=workdir)
    if not diff and paths:
        stat = stat or _untracked_files_stat(paths, workdir=workdir)
        diff = _untracked_files_diff(paths, workdir=workdir)
    parts = [action]
    if stat:
        parts.append(f"diff_stat:\n{stat}")
    if diff:
        parts.append(f"diff:\n{diff}")
    if len(parts) == 1:
        parts.append("diff: No diff.")
    return "\n\n".join(parts)


def _run_git_diff(
    args: list[str],
    paths: list[str] | None,
    max_chars: int,
    workdir: Path | str | None = None,
) -> str:
    workspace = _workspace(workdir)
    command = ["git", "diff", *args, "--", *_relative_paths(paths, workdir)]
    result = subprocess.run(
        command,
        cwd=workspace.root,
        capture_output=True,
        text=True,
        errors="backslashreplace",
        timeout=30,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return f"Error: {output or f'git diff exited with {result.returncode}'}"
    if len(output) > max_chars:
        return output[:max_chars] + f"\n... diff truncated to {max_chars} chars"
    return output


def _untracked_files_diff(paths: list[str], workdir: Path | str | None = None) -> str:
    workspace = _workspace(workdir)
    sections = []
    for path in paths:
        file_path = workspace.safe_path(path)
        if not file_path.exists() or _is_tracked(path, workdir=workdir):
            continue
        try:
            text = file_path.read_text()
        except UnicodeDecodeError:
            text = "<binary or non-utf8 file>"
        relative_path = file_path.relative_to(workspace.root)
        lines = text.splitlines()
        sections.append(
            "\n".join(
                [
                    f"diff --git a/{relative_path} b/{relative_path}",
                    "new file mode 100644",
                    "--- /dev/null",
                    f"+++ b/{relative_path}",
                    f"@@ -0,0 +1,{len(lines)} @@",
                    *[f"+{line}" for line in lines],
                ]
            )
        )
    output = "\n".join(sections)
    if len(output) > MAX_DIFF_CHARS:
        return output[:MAX_DIFF_CHARS] + f"\n... diff truncated to {MAX_DIFF_CHARS} chars"
    return output


def _untracked_files_stat(paths: list[str], workdir: Path | str | None = None) -> str:
    workspace = _workspace(workdir)
    stats = []
    for path in paths:
        file_path = workspace.safe_path(path)
        if not file_path.exists() or _is_tracked(path, workdir=workdir):
            continue
        try:
            line_count = len(file_path.read_text().splitlines())
        except UnicodeDecodeError:
            line_count = 0
        relative_path = file_path.relative_to(workspace.root)
        stats.append(f" {relative_path} | {line_count} +")
    return "\n".join(stats)


def _is_tracked(path: str, workdir: Path | str | None = None) -> bool:
    workspace = _workspace(workdir)
    relative_path = str(workspace.safe_path(path).relative_to(workspace.root))
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative_path],
        cwd=workspace.root,
        capture_output=True,
        text=True,
        errors="backslashreplace",
        timeout=30,
    )
    return result.returncode == 0
