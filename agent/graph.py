"""Agent graph definition using LangGraph with provider abstraction."""

from pathlib import Path

from langgraph.graph import StateGraph, START

from agent.approval import ApprovalCallback
from agent.nodes.llm_node import create_llm_node as _create_llm_node
from agent.nodes.state import AgentState
from agent.nodes.task_guard_node import (
    create_task_guard_node,
    route_after_llm,
    route_after_tools,
    route_after_task_guard,
)
from agent.nodes.tools_node import create_tools_node as _create_tools_node
from agent.providers.base import LLMProvider
from agent.runtime.context import AgentRuntimeContext, WorkflowState
from agent.runtime.tool_scheduler import execute_tool_calls
from agent.streaming import StreamEventCallback
from agent.tool_retry import async_run_tool_with_retry
from tools import TOOL_HANDLERS, TOOLS


def create_runtime(
    provider: LLMProvider,
    system_prompt: str,
    todo_manager,
    workdir: Path,
    session_id: str,
    skill_dirs: list[str] | None = None,
    stream_callback: StreamEventCallback = None,
    approval_callback: ApprovalCallback = None,
) -> AgentRuntimeContext:
    """Create runtime context for a graph run."""
    return AgentRuntimeContext(
        provider=provider,
        system_prompt=system_prompt,
        todo_manager=todo_manager,
        workdir=workdir,
        session_id=session_id,
        skill_dirs=skill_dirs,
        stream_callback=stream_callback,
        approval_callback=approval_callback,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
        workflow_state=WorkflowState(),
        run_tool=async_run_tool_with_retry,
    )


def create_llm_node(
    provider: LLMProvider,
    system_prompt: str,
    session_id: str,
    stream_callback: StreamEventCallback = None,
):
    """Backward-compatible LLM node factory."""
    runtime = AgentRuntimeContext(
        provider=provider,
        system_prompt=system_prompt,
        todo_manager=None,
        workdir=Path.cwd(),
        session_id=session_id,
        stream_callback=stream_callback,
        tools=TOOLS,
        tool_handlers=TOOL_HANDLERS,
    )
    return _create_llm_node(runtime)


def create_tools_node(
    provider: LLMProvider,
    system_prompt: str,
    todo_manager,
    workdir: Path,
    session_id: str,
    skill_dirs: list[str] | None = None,
    stream_callback: StreamEventCallback = None,
    approval_callback: ApprovalCallback = None,
):
    """Backward-compatible tools node factory."""
    return _create_tools_node(
        create_runtime(
            provider=provider,
            system_prompt=system_prompt,
            todo_manager=todo_manager,
            workdir=workdir,
            session_id=session_id,
            skill_dirs=skill_dirs,
            stream_callback=stream_callback,
            approval_callback=approval_callback,
        )
    )


def build_graph(
    provider: LLMProvider,
    system_prompt: str,
    todo_manager,
    workdir: Path,
    session_id: str,
    skill_dirs: list[str] | None = None,
    stream_callback: StreamEventCallback = None,
    approval_callback: ApprovalCallback = None,
):
    """Build the agent graph."""
    runtime = create_runtime(
        provider=provider,
        system_prompt=system_prompt,
        todo_manager=todo_manager,
        workdir=workdir,
        session_id=session_id,
        skill_dirs=skill_dirs,
        stream_callback=stream_callback,
        approval_callback=approval_callback,
    )

    builder = StateGraph(AgentState)
    builder.add_node("llm", _create_llm_node(runtime))
    builder.add_node("tools", _create_tools_node(runtime))
    builder.add_node("task_guard", create_task_guard_node(todo_manager))

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", route_after_llm)
    builder.add_conditional_edges("tools", route_after_tools)
    builder.add_conditional_edges(
        "task_guard",
        lambda state: route_after_task_guard(state, todo_manager),
    )

    return builder.compile()
