"""Single tool call execution pipeline."""

import time

from langchain_core.messages import ToolMessage

from agent.approval import ApprovalDenied, ApprovalTargetMissing
from agent.logger import get_logger
from agent.runtime.approval_service import ApprovalService
from agent.runtime.context import AgentRuntimeContext
from agent.runtime.tool_events import (
    diff_preview_from_output,
    file_paths_for_tool_call,
    format_tool_description,
    format_tool_event_metadata,
)
from agent.runtime.tool_output import build_tool_output_view, compact_preflight_output
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
        start_time = time.perf_counter()
        status = "completed"
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
                return self._tool_message(tc, compact_preflight_output(output))

            if self.workflow_guard.should_require_apply_patch(tc):
                return self._tool_message(
                    tc,
                    self.workflow_guard.apply_patch_required_message(tc),
                )

            try:
                approved_args = await self.approval_service.approve(tc.name, tc.args or {})
            except ApprovalTargetMissing as exc:
                status = "failed"
                await self._emit_tool_result(
                    str(exc),
                    title="File edit blocked",
                    detail="No target file detected",
                    phase="blocked",
                )
                return self._tool_message(tc, str(exc))
            runner = self.registry.create_subagent_runner() if tc.name == "subagent" else None
            handler = runner.run if runner else self.registry.resolve(tc.name)
            output = await self.runtime.run_tool(
                handler,
                tc.name,
                max_retries=3,
                timeout_seconds=self.registry.timeout_for(tc.name),
                **approved_args,
            )
            output_view = build_tool_output_view(tc.name, output, tc)

            logger.debug(f"Tool output: {output[:200]}...")
            logger.debug(f"End tool: {getattr(tc, 'name', 'unknown')}")
            tool_message = self._tool_message(tc, output_view.model)
            if output_view.context_policy != "full":
                tool_message.additional_kwargs["context_policy"] = output_view.context_policy
            if runner and runner.last_usage:
                tool_message.additional_kwargs["usage"] = dict(runner.last_usage)

            if tc.name == "todo":
                await self._emit_tool_result(
                    output_view.display,
                    title="Task Plan",
                    detail="Updated todo items and task memory",
                    phase="planning",
                )

            should_emit_diff = self.workflow_guard.update_after_tool(tc, output)
            if should_emit_diff:
                await self._emit_tool_result(diff_preview_from_output(output_view.display))
                await self._emit_file_changed(tc)
            return tool_message
        except ApprovalDenied:
            status = "failed"
            raise
        except Exception as exc:
            status = "failed"
            output = f"Error executing tool {tc.name}: {exc}"
            logger.exception("Tool execution failed: %s", getattr(tc, "name", "unknown"))
            await self._emit_tool_result(
                output,
                title="Tool failed",
                detail=tc.name,
                phase="blocked",
            )
            return self._tool_message(tc, output)
        finally:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            await self._emit_tool_end(tc, status, elapsed_ms)

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
                status="running",
                **format_tool_event_metadata(tc),
            )
        )

    async def _emit_tool_end(self, tc, status: str, elapsed_ms: int) -> None:
        if not self.runtime.stream_callback:
            return
        await self.runtime.stream_callback(
            StreamEvent(
                source="main",
                session_id=self.runtime.session_id,
                event_type="tool_end",
                content=tc.name,
                status=status,
                elapsed_ms=elapsed_ms,
                **format_tool_event_metadata(tc),
            )
        )

    async def _emit_tool_result(
        self,
        content: str,
        *,
        title: str = "Review diff",
        detail: str = "Workspace changes produced a diff preview",
        phase: str = "reviewing",
    ) -> None:
        if not self.runtime.stream_callback:
            return
        await self.runtime.stream_callback(
            StreamEvent(
                source="main",
                session_id=self.runtime.session_id,
                event_type="tool_result",
                content=content,
                title=title,
                detail=detail,
                phase=phase,
            )
        )

    async def _emit_file_changed(self, tc) -> None:
        if not self.runtime.stream_callback:
            return
        file_paths = file_paths_for_tool_call(tc)
        await self.runtime.stream_callback(
            StreamEvent(
                source="main",
                session_id=self.runtime.session_id,
                event_type="file_changed",
                content=", ".join(file_paths),
                title="File changed",
                detail=", ".join(file_paths),
                phase="implementing",
                status="completed",
                tool_name=tc.name,
                file_paths=file_paths,
                metadata={"tool_call_id": tc.id},
            )
        )
