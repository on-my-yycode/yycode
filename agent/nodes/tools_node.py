"""Tools graph node."""

from langchain_core.messages import AIMessage, HumanMessage

from agent.nodes.state import AgentState
from agent.runtime.approval_service import ApprovalService
from agent.runtime.context import AgentRuntimeContext
from agent.runtime.tool_executor import ToolExecutor
from agent.runtime.tool_registry import RuntimeToolRegistry
from agent.runtime.tool_scheduler import execute_tool_calls
from agent.runtime.workflow_guard import WorkflowGuard


def create_tools_node(runtime: AgentRuntimeContext):
    """Create tools node with runtime-bound handlers."""
    registry = RuntimeToolRegistry(runtime)
    workflow_guard = WorkflowGuard(runtime, registry)
    approval_service = ApprovalService(
        runtime.approval_callback,
        runtime.workflow_state,
        runtime.stream_callback,
        runtime.session_id,
    )
    executor = ToolExecutor(runtime, registry, workflow_guard, approval_service)

    async def tools_node(state: AgentState) -> AgentState:
        last_msg = state["messages"][-1]
        tool_calls_data = last_msg.additional_kwargs.get("tool_calls_data", [])
        tool_messages = await execute_tool_calls(
            tool_calls_data,
            executor.execute,
            registry.can_run_concurrently,
        )

        if tool_calls_data:
            if any(tc.name == "todo" for tc in tool_calls_data):
                runtime.todo_manager.record_tool_call("todo")
            else:
                runtime.todo_manager.record_tool_call(tool_calls_data[0].name)

        additional_messages = workflow_guard.after_batch_messages(tool_calls_data)
        repeated_todo_message = runtime.todo_manager.consume_repeated_incomplete_message()
        if repeated_todo_message:
            additional_messages.append(HumanMessage(content=repeated_todo_message))
        if (
            any(tc.name == "todo" for tc in tool_calls_data)
            and runtime.todo_manager.can_finish_task()
            and str(last_msg.content or "").strip()
        ):
            additional_messages.append(
                AIMessage(
                    content=last_msg.content,
                    additional_kwargs={"task_completed_final": True},
                )
            )
        return {"messages": tool_messages + additional_messages}

    return tools_node
