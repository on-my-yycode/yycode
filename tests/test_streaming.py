"""Tests for console streaming helpers."""

from agent.streaming import (
    ANSI_BG_BLUE,
    ANSI_BG_GRAY,
    ANSI_BG_GREEN,
    ANSI_BG_RED,
    ANSI_RESET,
    colorize_diff,
)


def test_colorize_diff_uses_backgrounds_for_changed_and_metadata_lines():
    diff = "\n".join(
        [
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            " context",
        ]
    )

    result = colorize_diff(diff)

    assert f"{ANSI_BG_GRAY}diff --git a/a.py b/a.py{ANSI_RESET}" in result
    assert f"{ANSI_BG_GRAY}--- a/a.py{ANSI_RESET}" in result
    assert f"{ANSI_BG_GRAY}+++ b/a.py{ANSI_RESET}" in result
    assert f"{ANSI_BG_BLUE}@@ -1 +1 @@{ANSI_RESET}" in result
    assert f"{ANSI_BG_RED}-old{ANSI_RESET}" in result
    assert f"{ANSI_BG_GREEN}+new{ANSI_RESET}" in result
    assert " context" in result
