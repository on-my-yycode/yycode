"""Runtime approval helpers for high-risk tool calls."""

from dataclasses import dataclass
import re
from typing import Awaitable, Callable, Optional

from tools.safety import approval_required


ApprovalCallback = Callable[["ApprovalRequest"], Awaitable[bool]]


class ApprovalDenied(Exception):
    """Raised when the user denies a runtime approval request."""

    def __init__(self, request: "ApprovalRequest"):
        self.request = request
        super().__init__(request.format())


@dataclass(frozen=True)
class ApprovalRequest:
    """A request to approve a risky tool execution."""

    action: str
    tool_name: str
    reason: str
    risk: str
    path: str = ""
    command: str = ""

    def format(self) -> str:
        """Format the request using the stable tool response shape."""
        return approval_required(
            action=self.action,
            command=self.command,
            path=self.path,
            reason=self.reason,
            risk=self.risk,
        )


def approval_request_for_tool(tool_name: str, args: dict) -> Optional[ApprovalRequest]:
    """Return an approval request for tool calls that require runtime confirmation."""
    if tool_name == "apply_patch":
        path = args.get("path") or _paths_from_unified_diff(args.get("patch", ""))
        return ApprovalRequest(
            action="edit_file",
            tool_name=tool_name,
            path=path,
            reason="apply_patch edits workspace files.",
            risk="File edits can overwrite user work or introduce unintended code changes.",
        )
    if tool_name == "write_file":
        return ApprovalRequest(
            action="create_file",
            tool_name=tool_name,
            path=args.get("path", ""),
            reason="write_file creates a new workspace file.",
            risk="Creating files changes the workspace and may add unwanted artifacts.",
        )
    return None


def approval_cache_key(request: ApprovalRequest) -> tuple[str, str, str]:
    """Return the cache key for approvals within one agent run."""
    return (request.action, request.tool_name, request.path)


def _paths_from_unified_diff(patch: str) -> str:
    paths = []
    for line in patch.splitlines():
        path = None
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
    return ", ".join(paths) if paths else "(unified diff)"
