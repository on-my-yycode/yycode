"""Agent graph definition using LangGraph with provider abstraction."""

import asyncio
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    BaseMessage,
)

from agent.providers.base import LLMProvider
from agent.skills import SkillRegistry
from agent.subagent import SubagentRunner
from agent.tool_retry import async_run_tool_with_retry
from agent.streaming import StreamEvent, StreamEventCallback, make_provider_stream_callback
from tools import TOOL_HANDLERS, TOOLS


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


CONCURRENT_SUBAGENT_ROLES = {"explorer", "architect", "tester", "security"}
DEFAULT_TOOL_TIMEOUT_SECONDS = 60
DEFAULT_TOOL_EXECUTION = {
    "side_effects": "unknown",
    "concurrency": "serial",
    "timeout_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS,
}


def create_llm_node(
    provider: LLMProvider,
    system_prompt: str,
    session_id: str,
    stream_callback: StreamEventCallback = None,
):
    """Create LLM node with given provider."""
    provider_stream_callback = make_provider_stream_callback(
        stream_callback,
        source="main",
        session_id=session_id,
    )

    async def llm_node(state: AgentState) -> AgentState:
        """Call the LLM with tool support and streaming."""
        anthropic_messages = []
        for msg in state["messages"]:
            if isinstance(msg, HumanMessage):
                anthropic_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                anthropic_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, ToolMessage):
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

        response = await provider.chat(
            messages=anthropic_messages,
            tools=TOOLS,
            system_prompt=system_prompt,
            stream_callback=provider_stream_callback,
        )
        if stream_callback and response.usage:
            await stream_callback(
                StreamEvent(
                    source="main",
                    session_id=session_id,
                    event_type="usage",
                    usage=response.usage,
                )
            )

        tool_calls = [
            {
                "name": tc.name,
                "args": tc.args,
                "id": tc.id,
            }
            for tc in response.tool_calls
        ]

        ai_msg = AIMessage(
            content=response.content,
            tool_calls=tool_calls,
        )

        ai_msg.additional_kwargs["tool_calls_data"] = response.tool_calls
        ai_msg.additional_kwargs["raw_response"] = response.raw_response
        ai_msg.additional_kwargs["usage"] = response.usage

        return {"messages": [ai_msg]}

    return llm_node


def create_tools_node(
    provider: LLMProvider,
    system_prompt: str,
    todo_manager,
    workdir: Path,
    session_id: str,
    skill_dirs: list[str] | None = None,
    stream_callback: StreamEventCallback = None,
):
    """Create tools node with todo manager access."""
    # Create a todo handler bound to this manager
    session_todo_handler = todo_manager.create_todo_handler()
    skill_registry = SkillRegistry(workdir, skill_dirs)
    list_skills_handler = lambda: skill_registry.format_skill_list()
    load_skill_handler = lambda names: skill_registry.format_loaded_skills(names)
    tool_execution = {tool["name"]: tool.get("execution", {}) for tool in TOOLS}
    workflow_guard = {
        "workspace_state_checked": False,
        "git_diff_checked": False,
        "needs_verify": False,
    }

    def create_subagent_runner():
        return SubagentRunner(
            provider=provider,
            workdir=workdir,
            parent_system_prompt=system_prompt,
            tool_handlers=TOOL_HANDLERS,
            tools=TOOLS,
            parent_session_id=session_id,
            skill_dirs=skill_dirs,
            stream_callback=stream_callback,
        )

    def resolve_handler(tool_name: str):
        if tool_name == "todo":
            return session_todo_handler
        if tool_name == "list_skills":
            return list_skills_handler
        if tool_name == "load_skill":
            return load_skill_handler
        if tool_name == "subagent":
            return create_subagent_runner().run
        return TOOL_HANDLERS.get(tool_name)

    def execution_for_tool(tool_name: str) -> dict:
        return {**DEFAULT_TOOL_EXECUTION, **tool_execution.get(tool_name, {})}

    def can_run_concurrently(tool_call) -> bool:
        if tool_call.name == "subagent":
            return tool_call.args.get("role") in CONCURRENT_SUBAGENT_ROLES
        execution = execution_for_tool(tool_call.name)
        if execution["side_effects"] in {"workspace_write", "session_state"}:
            return False
        return execution["concurrency"] == "safe"

    def timeout_for_tool(tool_name: str) -> int:
        return int(execution_for_tool(tool_name)["timeout_seconds"])

    def is_workspace_write(tool_name: str) -> bool:
        return execution_for_tool(tool_name)["side_effects"] == "workspace_write"

    def has_preflight() -> bool:
        return workflow_guard["workspace_state_checked"] and workflow_guard["git_diff_checked"]

    def _format_tool_description(tc) -> str:
        """Format a tool call for display."""
        tool_name = tc.name
        args = tc.args or {}
        # Show brief args summary
        if tool_name == "bash":
            cmd = args.get("command", "")
            cmd_preview = cmd[:40] + "..." if len(cmd) > 40 else cmd
            return f"{tool_name}: {cmd_preview}"
        elif tool_name in {"read_file", "write_file", "edit_file"}:
            path = args.get("path", "")
            return f"{tool_name}: {path}"
        elif tool_name == "todo":
            items = args.get("items", [])
            return f"{tool_name}: {len(items)} item(s)"
        elif tool_name == "subagent":
            role = args.get("role", "")
            task = args.get("task", "")
            if role and task:
                task_preview = task[:30] + "..." if len(task) > 30 else task
                return f"{tool_name} @{role}: {task_preview}"
            return f"{tool_name}"
        else:
            return f"{tool_name}"

    async def run_guard_preflight() -> str:
        """Collect workspace state and diff before allowing a write tool."""
        workspace_output = await async_run_tool_with_retry(
            resolve_handler("workspace_state"),
            "workspace_state",
            max_retries=0,
            timeout_seconds=timeout_for_tool("workspace_state"),
        )
        diff_output = await async_run_tool_with_retry(
            resolve_handler("git_diff"),
            "git_diff",
            max_retries=0,
            timeout_seconds=timeout_for_tool("git_diff"),
        )
        workflow_guard["workspace_state_checked"] = True
        workflow_guard["git_diff_checked"] = True
        return (
            "Code workflow guard blocked this write because workspace preflight "
            "had not been reviewed yet.\n\n"
            "workspace_state:\n"
            f"{workspace_output}\n\n"
            "git_diff:\n"
            f"{diff_output}\n\n"
            "Review the existing changes, then retry the write with the smallest safe patch."
        )

    async def execute_tool_call(tc):
        # Send tool start event
        if stream_callback:
            tool_desc = _format_tool_description(tc)
            await stream_callback(
                StreamEvent(
                    source="main",
                    session_id=session_id,
                    event_type="tool_start",
                    content=tool_desc,
                )
            )

        try:
            if is_workspace_write(tc.name) and not has_preflight():
                output = await run_guard_preflight()
                return ToolMessage(
                    content=output,
                    tool_call_id=tc.id,
                    name=tc.name,
                )

            runner = create_subagent_runner() if tc.name == "subagent" else None
            handler = runner.run if runner else resolve_handler(tc.name)
            output = await async_run_tool_with_retry(
                handler,
                tc.name,
                max_retries=2,
                timeout_seconds=timeout_for_tool(tc.name),
                **tc.args,
            )
            tool_message = ToolMessage(
                content=output,
                tool_call_id=tc.id,
                name=tc.name,
            )
            if runner and runner.last_usage:
                tool_message.additional_kwargs["usage"] = dict(runner.last_usage)
            if tc.name == "workspace_state":
                workflow_guard["workspace_state_checked"] = True
            if tc.name == "git_diff":
                workflow_guard["git_diff_checked"] = True
            if is_workspace_write(tc.name):
                workflow_guard["needs_verify"] = True
            if tc.name == "verify":
                workflow_guard["needs_verify"] = False
            return tool_message
        finally:
            # Send tool end event
            if stream_callback:
                await stream_callback(
                    StreamEvent(
                        source="main",
                        session_id=session_id,
                        event_type="tool_end",
                        content=tc.name,
                    )
                )

    async def tools_node(state: AgentState) -> AgentState:
        """Execute the tools requested by the LLM."""
        last_msg = state["messages"][-1]

        tool_calls_data = last_msg.additional_kwargs.get("tool_calls_data", [])

        tool_messages = await execute_tool_calls(tool_calls_data, execute_tool_call, can_run_concurrently)

        # Record tool calls for todo reminder tracking
        if tool_calls_data:
            if any(tc.name == "todo" for tc in tool_calls_data):
                todo_manager.record_tool_call("todo")
            else:
                todo_manager.record_tool_call(tool_calls_data[0].name)

        # Check if we need to add a todo reminder
        additional_messages = []
        if todo_manager.needs_reminder():
            reminder = todo_manager.get_reminder_message()
            additional_messages.append(HumanMessage(content=reminder))
        if workflow_guard["needs_verify"] and not any(tc.name == "verify" for tc in tool_calls_data):
            additional_messages.append(
                HumanMessage(
                    content=(
                        "Code changes were made. Run verify with the narrowest useful "
                        "target before providing the final answer."
                    )
                )
            )

        return {"messages": tool_messages + additional_messages}

    return tools_node


async def execute_tool_calls(tool_calls, execute_tool_call, can_run_concurrently):
    """Execute tool calls while preserving original result order."""
    results = [None] * len(tool_calls)
    concurrent_batch = []

    async def flush_concurrent_batch():
        if not concurrent_batch:
            return
        batch = list(concurrent_batch)
        concurrent_batch.clear()
        outputs = await asyncio.gather(
            *(execute_tool_call(tc) for _, tc in batch),
        )
        for (index, _), output in zip(batch, outputs):
            results[index] = output

    for index, tc in enumerate(tool_calls):
        if can_run_concurrently(tc):
            concurrent_batch.append((index, tc))
            continue
        await flush_concurrent_batch()
        results[index] = await execute_tool_call(tc)

    await flush_concurrent_batch()
    return results


def should_continue(state: AgentState) -> Literal["tools", END]:
    """Determine if we should continue tool execution or end."""
    last_msg = state["messages"][-1]
    tool_calls_data = last_msg.additional_kwargs.get("tool_calls_data", [])
    return "tools" if tool_calls_data else END


def build_graph(
    provider: LLMProvider,
    system_prompt: str,
    todo_manager,
    workdir: Path,
    session_id: str,
    skill_dirs: list[str] | None = None,
    stream_callback: StreamEventCallback = None,
):
    """Build the agent graph."""
    builder = StateGraph(AgentState)
    builder.add_node("llm", create_llm_node(provider, system_prompt, session_id, stream_callback))
    builder.add_node(
        "tools",
        create_tools_node(
            provider,
            system_prompt,
            todo_manager,
            workdir,
            session_id,
            skill_dirs,
            stream_callback,
        ),
    )

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", should_continue)
    builder.add_edge("tools", "llm")

    return builder.compile()
