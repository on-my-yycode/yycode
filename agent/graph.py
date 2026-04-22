"""Agent graph definition using LangGraph with provider abstraction."""

from typing import Annotated, Literal, TypedDict, Callable, Optional

from utils import run_tool_with_retry

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    BaseMessage,
)

from agent.providers.base import LLMProvider
from tools import TOOL_HANDLERS, TOOLS


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def create_llm_node(
    provider: LLMProvider,
    system_prompt: str,
    stream_callback=None,
):
    """Create LLM node with given provider."""

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
            stream_callback=stream_callback,
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

        return {"messages": [ai_msg]}

    return llm_node


def create_tools_node(todo_manager):
    """Create tools node with todo manager access."""
    # Create a todo handler bound to this manager
    session_todo_handler = todo_manager.create_todo_handler()

    async def tools_node(state: AgentState) -> AgentState:
        """Execute the tools requested by the LLM."""
        last_msg = state["messages"][-1]
        tool_messages = []

        tool_calls_data = last_msg.additional_kwargs.get("tool_calls_data", [])

        has_todo_call = False

        for tc in tool_calls_data:
            if tc.name == "todo":
                has_todo_call = True
                handler = session_todo_handler
            else:
                handler = TOOL_HANDLERS.get(tc.name)

            output = run_tool_with_retry(handler, tc.name, max_retries=2, **tc.args)
            tool_messages.append(
                ToolMessage(
                    content=output,
                    tool_call_id=tc.id,
                    name=tc.name,
                )
            )

        # Record tool calls for todo reminder tracking
        if tool_calls_data:
            if has_todo_call:
                todo_manager.record_tool_call("todo")
            else:
                todo_manager.record_tool_call(tool_calls_data[0].name)

        # Check if we need to add a todo reminder
        additional_messages = []
        if todo_manager.needs_reminder():
            reminder = todo_manager.get_reminder_message()
            additional_messages.append(HumanMessage(content=reminder))

        return {"messages": tool_messages + additional_messages}

    return tools_node


def should_continue(state: AgentState) -> Literal["tools", END]:
    """Determine if we should continue tool execution or end."""
    last_msg = state["messages"][-1]
    tool_calls_data = last_msg.additional_kwargs.get("tool_calls_data", [])
    return "tools" if tool_calls_data else END


def build_graph(
    provider: LLMProvider,
    system_prompt: str,
    todo_manager,
    stream_callback=None,
):
    """Build the agent graph."""
    builder = StateGraph(AgentState)
    builder.add_node("llm", create_llm_node(provider, system_prompt, stream_callback))
    builder.add_node("tools", create_tools_node(todo_manager))

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", should_continue)
    builder.add_edge("tools", "llm")

    return builder.compile()
