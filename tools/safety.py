"""Safety helpers for tools that need approval-style blocking."""

import re


class ApprovalRequired(Exception):
    """Raised when an action should be blocked until user approval exists."""


def approval_required(action: str, reason: str, risk: str, command: str = "", path: str = "") -> str:
    """Format a stable approval_required response for tools."""
    lines = [
        "approval_required:",
        f"action: {action}",
    ]
    if command:
        lines.append(f"command: {command}")
    if path:
        lines.append(f"path: {path}")
    lines.extend(
        [
            f"reason: {reason}",
            f"risk: {risk}",
        ]
    )
    return "\n".join(lines)


DANGEROUS_COMMAND_PATTERNS = [
    (r"\bsudo\b", "privileged_command", "sudo can run commands with elevated privileges."),
    (r"\brm\s+.*(-r|-f|--recursive|--force)", "destructive_delete", "recursive or forced deletion can remove user work."),
    (r"\bgit\s+reset\b", "destructive_git", "git reset can discard commits or local changes."),
    (r"\bgit\s+checkout\b", "destructive_git", "git checkout can overwrite working tree files."),
    (r"\bgit\s+clean\b", "destructive_git", "git clean deletes untracked files."),
    (r"\bchmod\b|\bchown\b", "permission_change", "permission changes can break the workspace or expose files."),
    (r">\s*/dev/", "device_write", "writing to device paths can damage the system."),
]


def unsafe_command_response(command: str) -> str | None:
    """Return an approval_required message if command matches high-risk patterns."""
    for pattern, action, reason in DANGEROUS_COMMAND_PATTERNS:
        if re.search(pattern, command):
            return approval_required(
                action=action,
                command=command,
                reason=reason,
                risk="This operation may be destructive or affect files outside the intended task.",
            )
    return None
