"""Task State guard graph node."""

from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.graph import END

from agent.nodes.state import AgentState
from agent.todo_manager import TodoManager


def create_task_guard_node(todo_manager: TodoManager):
    """Create a guard node that prevents finishing before Task State is complete."""

    async def task_guard_node(state: AgentState) -> AgentState:
        if not todo_manager.has_incomplete_task_state():
            return {"messages": []}
        return {
            "messages": [
                HumanMessage(
                    content=todo_manager.get_finish_blocker_message(),
                    additional_kwargs={
                        "context_ephemeral": True,
                        "ephemeral_kind": "task_guard",
                    },
                )
            ]
        }

    return task_guard_node


def route_after_llm(state: AgentState) -> Literal["tools", "task_guard"]:
    """Route to tools when the model requested tools, otherwise to task guard."""
    last_msg = state["messages"][-1]
    tool_calls_data = last_msg.additional_kwargs.get("tool_calls_data", [])
    return "tools" if tool_calls_data else "task_guard"


def route_after_tools(state: AgentState) -> Literal["llm", END]:
    """End when tools preserved a final answer after completing Task State."""
    last_msg = state["messages"][-1]
    if last_msg.additional_kwargs.get("task_completed_final") is True:
        return END
    return "llm"


def route_after_task_guard(state: AgentState, todo_manager: TodoManager) -> Literal["llm", END]:
    """Route after task guard."""
    return END if not todo_manager.has_incomplete_task_state() else "llm"
