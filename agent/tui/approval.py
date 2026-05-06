"""Approval adapter for the terminal UI."""

from __future__ import annotations

import asyncio
from typing import Optional

from agent.approval import ApprovalRequest


def approval_id_for_request(request: ApprovalRequest) -> str:
    """Build the approval identifier used by stream events and the TUI."""
    target = request.path or request.command
    return "|".join([request.action, request.tool_name, target])


class TuiApprovalAdapter:
    """Bridge runtime approval callbacks to TUI-driven user decisions."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[bool]] = {}

    async def callback(self, request: ApprovalRequest) -> bool:
        """Wait for the TUI to approve or deny the request."""
        approval_id = approval_id_for_request(request)
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[approval_id] = future
        try:
            return await future
        finally:
            self._pending.pop(approval_id, None)

    def resolve(self, approval_id: str, approved: bool) -> bool:
        """Resolve one pending approval request."""
        future: Optional[asyncio.Future[bool]] = self._pending.get(approval_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True
