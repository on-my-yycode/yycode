"""Tests for TUI approval adapter."""

import asyncio

from agent.approval import ApprovalRequest
from agent.tui.approval import TuiApprovalAdapter, approval_id_for_request


def test_approval_id_for_request_uses_action_tool_and_target():
    request = ApprovalRequest(
        action="edit_file",
        tool_name="apply_patch",
        path="agent/tui/app.py",
        reason="test",
        risk="test",
    )

    assert approval_id_for_request(request) == "edit_file|apply_patch|agent/tui/app.py"


def test_tui_approval_adapter_resolves_pending_request():
    async def run():
        adapter = TuiApprovalAdapter()
        request = ApprovalRequest(
            action="create_file",
            tool_name="write_file",
            path="docs/full_tui_design.md",
            reason="test",
            risk="test",
        )
        task = asyncio.create_task(adapter.callback(request))
        await asyncio.sleep(0)
        resolved = adapter.resolve("create_file|write_file|docs/full_tui_design.md", True)
        return resolved, await task

    resolved, approved = asyncio.run(run())

    assert resolved is True
    assert approved is True
