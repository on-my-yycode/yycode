"""Runtime approval orchestration."""

from agent.approval import (
    ApprovalRequest,
    ApprovalCallback,
    ApprovalDenied,
    approval_cache_key,
    approval_request_for_tool,
)
from agent.runtime.context import WorkflowState
from agent.streaming import StreamEvent, StreamEventCallback


class ApprovalService:
    """Approve high-risk tool calls and inject approved=true."""

    def __init__(
        self,
        approval_callback: ApprovalCallback | None,
        workflow_state: WorkflowState,
        stream_callback: StreamEventCallback | None = None,
        session_id: str = "",
        source: str = "main",
    ):
        self.approval_callback = approval_callback
        self.workflow_state = workflow_state
        self.stream_callback = stream_callback
        self.session_id = session_id
        self.source = source

    async def approve(self, tool_name: str, args: dict | None) -> dict:
        """Return tool args after approval, injecting approved=true when needed."""
        args = dict(args or {})
        request = approval_request_for_tool(tool_name, args)
        if request is None:
            return args

        cache_key = approval_cache_key(request)
        if cache_key in self.workflow_state.approved_write_keys:
            args["approved"] = True
            await self._emit_approval_resolved(request, "cached_approved")
            return args

        await self._emit_approval_diff_preview(request)
        if self.approval_callback is None:
            await self._emit_approval_required(request)
            await self._emit_approval_resolved(request, "denied")
            raise ApprovalDenied(request)
        await self._emit_approval_required(request)
        approved = await self.approval_callback(request)
        if not approved:
            await self._emit_approval_resolved(request, "denied")
            raise ApprovalDenied(request)

        self.workflow_state.approved_write_keys.add(cache_key)
        args["approved"] = True
        await self._emit_approval_resolved(request, "approved")
        return args

    async def _emit_approval_required(self, request: ApprovalRequest) -> None:
        if self.stream_callback is None:
            return
        await self.stream_callback(
            StreamEvent(
                source=self.source,
                session_id=self.session_id,
                event_type="approval_required",
                content=request.format(include_diff=True),
                title=_approval_title(request, "Approve"),
                detail=_approval_detail(request),
                phase="blocked",
                status="waiting_for_user",
                tool_name=request.tool_name,
                file_paths=_approval_paths(request),
                metadata=_approval_metadata(request),
            )
        )

    async def _emit_approval_diff_preview(self, request: ApprovalRequest) -> None:
        if self.stream_callback is None or not request.diff_preview:
            return
        await self.stream_callback(
            StreamEvent(
                source=self.source,
                session_id=self.session_id,
                event_type="tool_result",
                content=request.diff_preview,
                title="Review diff before approval",
                detail=_approval_detail(request),
                phase="reviewing",
                status="waiting_for_user",
                tool_name=request.tool_name,
                file_paths=_approval_paths(request),
                metadata={
                    **_approval_metadata(request),
                    "approval_preview": True,
                },
            )
        )

    async def _emit_approval_resolved(self, request: ApprovalRequest, status: str) -> None:
        if self.stream_callback is None:
            return
        phase = "blocked" if status == "denied" else "implementing"
        await self.stream_callback(
            StreamEvent(
                source=self.source,
                session_id=self.session_id,
                event_type="approval_resolved",
                content=status,
                title=_approval_title(request, _approval_status_label(status)),
                detail=_approval_detail(request),
                phase=phase,
                status=status,
                tool_name=request.tool_name,
                file_paths=_approval_paths(request),
                metadata=_approval_metadata(request),
            )
        )


def _approval_title(request: ApprovalRequest, prefix: str) -> str:
    if request.action == "edit_file":
        return f"{prefix} file edit"
    if request.action == "create_file":
        return f"{prefix} file creation"
    if request.action == "run_command":
        return f"{prefix} command"
    return f"{prefix} action"


def _approval_status_label(status: str) -> str:
    return {
        "approved": "Approved",
        "cached_approved": "Approved",
        "denied": "Denied",
    }.get(status, status)


def _approval_detail(request: ApprovalRequest) -> str:
    if request.path:
        return request.path
    if request.command:
        return request.command
    return request.reason


def _approval_paths(request: ApprovalRequest) -> list[str] | None:
    if not request.path:
        return None
    return [path.strip() for path in request.path.split(",") if path.strip()]


def _approval_metadata(request: ApprovalRequest) -> dict:
    approval_id = "|".join(
        [
            request.action,
            request.tool_name,
            request.path or request.command,
        ]
    )
    return {
        "approval_id": approval_id,
        "action": request.action,
        "reason": request.reason,
        "risk": request.risk,
        "path": request.path,
        "command": request.command,
        "diff_preview": request.diff_preview,
    }
