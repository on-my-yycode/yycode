"""Single-page help content for the TUI :help command."""

from __future__ import annotations

from collections.abc import Iterable

from agent.tui.commands.base import TuiCommand


TUI_SHORTCUTS = [
    ("Ctrl+Enter / Ctrl+J", "Submit current input"),
    ("Ctrl+C", "Cancel current task / interrupt"),
    ("Ctrl+Shift+C", "Copy timeline"),
    ("Ctrl+Q", "Quit"),
    ("Ctrl+T", "Open task plan panel"),
    ("Ctrl+D", "Open changed files panel"),
    ("Ctrl+M", "Open message token manager"),
]

COMPLETION_SHORTCUTS = [
    ("/", "Open skill completion"),
    ("@", "Open subagent role completion"),
    (":", "Open TUI command completion"),
    ("Up/Down or Ctrl+P/Ctrl+N", "Select completion item"),
    ("Tab/Enter", "Accept selected completion"),
    ("Esc", "Close completion or focus input"),
]

TIMELINE_SHORTCUTS = [
    ("Up/Down", "Scroll timeline by line"),
    ("PageUp/PageDown", "Scroll timeline by page"),
    ("Home/End", "Jump to timeline top/bottom"),
]

APPROVAL_SHORTCUTS = [
    ("Y / Enter", "Approve current request"),
    ("N / Esc", "Deny current request"),
]

STARTUP_ARGUMENTS = [
    ("WORKDIR", "Workspace directory. Defaults to the current directory."),
    ("-d, --debug", "Enable debug logging to console."),
    ("--log-file", "Write logs to agent_debug.log."),
    ("-a, --auto", "Auto-approve risky actions where supported."),
    ("--silent", "Compatibility alias for --auto."),
    ("-r, --resume ID", "Resume messages from a persisted session id in the same workspace."),
    ("-s, --sessions", "List persisted sessions for WORKDIR and exit."),
    ("--list-sessions", "Compatibility alias for --sessions."),
    ("-t, --temp", "Temporary session; do not save messages."),
    ("--no-persist", "Compatibility alias for --temp."),
    ("-x, --delete ID", "Delete a persisted session id for WORKDIR and exit."),
]


def render_help_page(commands: Iterable[TuiCommand]) -> str:
    """Render the complete single-page TUI help text."""
    sections = [
        "YOYOAGENT Help",
        "",
        "TUI Commands",
        *_render_commands(commands),
        "",
        "Keyboard Shortcuts",
        *_render_rows(TUI_SHORTCUTS),
        "",
        "Input Completion",
        *_render_rows(COMPLETION_SHORTCUTS),
        "",
        "Timeline Navigation",
        *_render_rows(TIMELINE_SHORTCUTS),
        "",
        "Approval",
        *_render_rows(APPROVAL_SHORTCUTS),
        "",
        "Subagents",
        "  Use @role followed by a focused task. Type @ to complete a role.",
        "  Example: @tester verify the command system behavior",
        "  Example: @architect /plan design a safer cleanup flow",
        "",
        "Skills",
        "  Use /skill-name followed by the task instruction. Type / to complete a skill.",
        "  Example: /plan design a command registry",
        "  Example: /drawio-skill create an architecture diagram",
        "",
        "Startup Arguments",
        "  yoyoagent [WORKDIR] [options]",
        *_render_rows(STARTUP_ARGUMENTS),
        "",
        "More",
        "  Run `yoyoagent --help` for raw CLI help.",
    ]
    return "\n".join(sections)


def _render_commands(commands: Iterable[TuiCommand]) -> list[str]:
    lines: list[str] = []
    for command in sorted(commands, key=lambda item: item.name):
        usage = command.usage or f":{command.name}"
        description = command.description.rstrip(".")
        lines.append(f"  {usage:<18} {description}.")
        if command.name == "clear":
            lines.append("  :clear!            Confirm clearing current session history.")
    return lines or ["  No TUI commands registered."]


def _render_rows(rows: Iterable[tuple[str, str]]) -> list[str]:
    return [f"  {key:<24} {description}" for key, description in rows]
