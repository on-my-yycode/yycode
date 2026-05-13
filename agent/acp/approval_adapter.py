"""ACP permission request adapter."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

from agent.approval import ApprovalDecision, ApprovalRequest
from agent.acp.update_adapter import _tool_kind


PermissionRequester = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class AcpApprovalAdapter:
    """Convert runtime approval callbacks into ACP permission requests."""

    def __init__(
        self,
        session_id: str,
        requester: PermissionRequester,
        *,
        workdir: Path | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.session_id = session_id
        self.requester = requester
        self.workdir = workdir
        self.timeout_seconds = timeout_seconds
        self._pending: set[asyncio.Task] = set()

    async def callback(self, request: ApprovalRequest) -> bool:
        """Return True when the ACP client approves the requested action."""
        return (await self.decide(request)).approved

    async def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        """Request a permission decision from the ACP client."""
        task = asyncio.create_task(self.requester("session/request_permission", self.payload(request)))
        self._pending.add(task)
        try:
            if self.timeout_seconds is None:
                response = await task
            else:
                response = await asyncio.wait_for(task, timeout=self.timeout_seconds)
        except asyncio.CancelledError:
            return ApprovalDecision("cancelled")
        except TimeoutError:
            return ApprovalDecision("denied")
        finally:
            self._pending.discard(task)
        option_id = _response_option_id(response)
        if option_id in {"approve", "allow", "approved"}:
            return ApprovalDecision("approved")
        if option_id in {"cancel", "cancelled"}:
            return ApprovalDecision("cancelled")
        return ApprovalDecision("denied")

    def cancel_pending(self) -> int:
        """Cancel pending permission requests."""
        count = 0
        for task in list(self._pending):
            if not task.done():
                task.cancel()
                count += 1
        self._pending.clear()
        return count

    def payload(self, request: ApprovalRequest) -> dict[str, Any]:
        """Build the ACP permission request payload."""
        locations = []
        for path in _split_paths(request.path):
            location_path = str(path)
            if self.workdir is not None and path and not path.startswith("/"):
                location_path = str((self.workdir / path).resolve())
            locations.append({"path": location_path})
        return {
            "sessionId": self.session_id,
            "toolCall": {
                "title": _permission_title(request),
                "kind": _tool_kind(request.tool_name),
                "status": "waiting_for_user",
                "locations": locations,
                "rawInput": {
                    "action": request.action,
                    "toolName": request.tool_name,
                    "path": request.path,
                    "command": request.command,
                    "reason": request.reason,
                    "risk": request.risk,
                    "diffPreview": request.diff_preview,
                },
                "content": [
                    {
                        "type": "text",
                        "text": request.format(include_diff=bool(request.diff_preview)),
                    }
                ],
            },
            "options": [
                {"optionId": "approve", "name": "Approve", "kind": "allow"},
                {"optionId": "deny", "name": "Deny", "kind": "reject"},
            ],
        }


def _permission_title(request: ApprovalRequest) -> str:
    if request.action == "edit_file":
        return "Approve file edit"
    if request.action == "create_file":
        return "Approve file creation"
    if request.action == "run_command":
        return "Approve command"
    return "Approve action"


def _split_paths(path: str) -> list[str]:
    return [item.strip() for item in path.split(",") if item.strip()]


def _response_option_id(response: Any) -> str:
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return ""
    for key in ("optionId", "option_id", "decision", "status"):
        if response.get(key):
            return str(response[key])
    if response.get("approved") is True:
        return "approve"
    if response.get("approved") is False:
        return "deny"
    return ""

