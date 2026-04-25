"""Runtime approval orchestration."""

from agent.approval import (
    ApprovalCallback,
    ApprovalDenied,
    approval_cache_key,
    approval_request_for_tool,
)
from agent.runtime.context import WorkflowState


class ApprovalService:
    """Approve high-risk tool calls and inject approved=true."""

    def __init__(
        self,
        approval_callback: ApprovalCallback | None,
        workflow_state: WorkflowState,
    ):
        self.approval_callback = approval_callback
        self.workflow_state = workflow_state

    async def approve(self, tool_name: str, args: dict | None) -> dict:
        """Return tool args after approval, injecting approved=true when needed."""
        args = dict(args or {})
        request = approval_request_for_tool(tool_name, args)
        if request is None:
            return args

        cache_key = approval_cache_key(request)
        if cache_key in self.workflow_state.approved_write_keys:
            args["approved"] = True
            return args

        if self.approval_callback is None:
            raise ApprovalDenied(request)
        approved = await self.approval_callback(request)
        if not approved:
            raise ApprovalDenied(request)

        self.workflow_state.approved_write_keys.add(cache_key)
        args["approved"] = True
        return args
