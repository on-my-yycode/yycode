"""Single tool call execution pipeline."""

from langchain_core.messages import ToolMessage

from agent.approval import ApprovalDenied
from agent.logger import get_logger
from agent.runtime.approval_service import ApprovalService
from agent.runtime.context import AgentRuntimeContext
from agent.runtime.tool_events import diff_preview_from_output, format_tool_description
from agent.runtime.tool_registry import RuntimeToolRegistry
from agent.runtime.workflow_guard import WorkflowGuard
from agent.streaming import StreamEvent

logger = get_logger(__name__)


class ToolExecutor:
    """Execute one tool call with guardrails, approval, and stream events."""

    def __init__(
        self,
        runtime: AgentRuntimeContext,
        registry: RuntimeToolRegistry,
        workflow_guard: WorkflowGuard,
        approval_service: ApprovalService,
    ):
        self.runtime = runtime
        self.registry = registry
        self.workflow_guard = workflow_guard
        self.approval_service = approval_service

    async def execute(self, tc) -> ToolMessage:
        """Execute a tool call and return a ToolMessage."""
        await self._emit_tool_start(tc)
        try:
            logger.debug(f"Calling tool: {getattr(tc, 'name', 'unknown')}")
            logger.debug(f"Full tc object: {tc!r}")
            logger.debug(f"tc type: {type(tc)}")
            logger.debug(f"tc.name: {getattr(tc, 'name', 'N/A')!r}")
            logger.debug(f"tc.args: {getattr(tc, 'args', 'N/A')!r}")
            logger.debug(f"tc.id: {getattr(tc, 'id', 'N/A')!r}")

            if self.registry.is_workspace_write(tc.name) and not self.workflow_guard.has_preflight():
                output = await self.workflow_guard.run_preflight()
                return self._tool_message(tc, output)

            if self.workflow_guard.should_require_apply_patch(tc):
                return self._tool_message(
                    tc,
                    self.workflow_guard.apply_patch_required_message(tc),
                )

            approved_args = await self.approval_service.approve(tc.name, tc.args or {})
            runner = self.registry.create_subagent_runner() if tc.name == "subagent" else None
            handler = runner.run if runner else self.registry.resolve(tc.name)
            output = await self.runtime.run_tool(
                handler,
                tc.name,
                max_retries=3,
                timeout_seconds=self.registry.timeout_for(tc.name),
                **approved_args,
            )

            logger.debug(f"Tool output: {output[:200]}...")
            logger.debug(f"End tool: {getattr(tc, 'name', 'unknown')}")
            tool_message = self._tool_message(tc, output)
            if runner and runner.last_usage:
                tool_message.additional_kwargs["usage"] = dict(runner.last_usage)

            should_emit_diff = self.workflow_guard.update_after_tool(tc.name, output)
            if should_emit_diff:
                await self._emit_tool_result(diff_preview_from_output(output))
            return tool_message
        finally:
            await self._emit_tool_end(tc)

    def _tool_message(self, tc, output: str) -> ToolMessage:
        return ToolMessage(
            content=output,
            tool_call_id=tc.id,
            name=tc.name,
        )

    async def _emit_tool_start(self, tc) -> None:
        if not self.runtime.stream_callback:
            return
        await self.runtime.stream_callback(
            StreamEvent(
                source="main",
                session_id=self.runtime.session_id,
                event_type="tool_start",
                content=format_tool_description(tc),
            )
        )

    async def _emit_tool_end(self, tc) -> None:
        if not self.runtime.stream_callback:
            return
        await self.runtime.stream_callback(
            StreamEvent(
                source="main",
                session_id=self.runtime.session_id,
                event_type="tool_end",
                content=tc.name,
            )
        )

    async def _emit_tool_result(self, content: str) -> None:
        if not self.runtime.stream_callback:
            return
        await self.runtime.stream_callback(
            StreamEvent(
                source="main",
                session_id=self.runtime.session_id,
                event_type="tool_result",
                content=content,
            )
        )
