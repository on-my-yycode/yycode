"""Runtime approval helpers for high-risk tool calls."""

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

from tools.safety import approval_required
from tools.safety import unsafe_command_response
from tools.apply_patch import preview_apply_patch_diff
from tools.write_file import preview_write_file_diff


ApprovalCallback = Callable[["ApprovalRequest"], Awaitable[bool]]


class ApprovalDenied(Exception):
    """Raised when the user denies a runtime approval request."""

    def __init__(self, request: "ApprovalRequest"):
        self.request = request
        super().__init__(request.format())


class ApprovalTargetMissing(Exception):
    """Raised when a file approval cannot identify the target path."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(missing_file_target_message(tool_name))


@dataclass(frozen=True)
class ApprovalRequest:
    """A request to approve a risky tool execution."""

    action: str
    tool_name: str
    reason: str
    risk: str
    path: str = ""
    command: str = ""
    diff_preview: str = ""

    def format(self, include_diff: bool = True) -> str:
        """Format the request using the stable tool response shape."""
        formatted = approval_required(
            action=self.action,
            command=self.command,
            path=self.path,
            reason=self.reason,
            risk=self.risk,
        )
        if include_diff and self.diff_preview:
            formatted = f"{formatted}\n\ndiff_preview:\n{self.diff_preview}"
        return formatted


def approval_request_for_tool(
    tool_name: str,
    args: dict,
    workdir: Path | str | None = None,
) -> Optional[ApprovalRequest]:
    """Return an approval request for tool calls that require runtime confirmation."""
    if tool_name == "bash":
        command = args.get("command", "")
        if unsafe_command_response(command):
            return ApprovalRequest(
                action="run_command",
                tool_name=tool_name,
                command=command,
                reason="bash command matches a high-risk command pattern.",
                risk="This operation may be destructive or affect files outside the intended task.",
            )
        return None
    if tool_name == "apply_patch":
        path = args.get("path") or _paths_from_unified_diff(args.get("patch", ""))
        if not path:
            raise ApprovalTargetMissing(tool_name)
        return ApprovalRequest(
            action="edit_file",
            tool_name=tool_name,
            path=path,
            reason="apply_patch edits workspace files.",
            risk="File edits can overwrite user work or introduce unintended code changes.",
            diff_preview=preview_apply_patch_diff(
                patch=args.get("patch", ""),
                path=args.get("path", ""),
                old_text=args.get("old_text", ""),
                new_text=args.get("new_text", ""),
                workdir=workdir,
            ),
        )
    if tool_name == "write_file":
        if not args.get("path"):
            raise ApprovalTargetMissing(tool_name)
        return ApprovalRequest(
            action="create_file",
            tool_name=tool_name,
            path=args.get("path", ""),
            reason="write_file creates a new workspace file.",
            risk="Creating files changes the workspace and may add unwanted artifacts.",
            diff_preview=preview_write_file_diff(
                args.get("path", ""),
                args.get("content", ""),
                workdir=workdir,
            ),
        )
    return None


def missing_file_target_message(tool_name: str) -> str:
    """Return a model-facing correction when a write tool has no target path."""
    return (
        f"File edit blocked for {tool_name}: no target file was detected.\n\n"
        "Retry with an explicit target file using one of these formats:\n"
        "- apply_patch with path + old_text + new_text\n"
        "- apply_patch with a unified diff that includes ---/+++ file headers\n"
        "- apply_patch with Begin Patch lines such as *** Update File: path\n"
        "- write_file with a path for a brand-new file"
    )


def approval_cache_key(request: ApprovalRequest) -> tuple[str, str, str]:
    """Return the cache key for approvals within one agent run."""
    return (request.action, request.tool_name, request.path)


def _paths_from_unified_diff(patch: str) -> str:
    paths = []
    for line in patch.splitlines():
        path = None
        begin_patch_match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)$", line)
        if begin_patch_match:
            path = begin_patch_match.group(1).strip()
        elif line.startswith("*** Move to: "):
            path = line[len("*** Move to: "):].strip()
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            if match:
                path = match.group(2)
        elif line.startswith("+++ "):
            raw = line[4:].split("\t", 1)[0].strip()
            if raw != "/dev/null":
                path = raw[2:] if raw.startswith("b/") else raw
        if path and path not in paths:
            paths.append(path)
    return ", ".join(paths)
