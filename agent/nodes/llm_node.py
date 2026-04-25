"""LLM graph node."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.llm_retry import chat_with_retry
from agent.nodes.state import AgentState
from agent.runtime.context import AgentRuntimeContext
from agent.streaming import StreamEvent, make_provider_stream_callback


def messages_to_provider_format(messages) -> list[dict]:
    """Convert LangChain messages to the provider-neutral format used by providers."""
    provider_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            provider_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            provider_messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            provider_messages.append(
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
    return provider_messages


def create_llm_node(runtime: AgentRuntimeContext):
    """Create LLM node with given runtime."""
    provider_stream_callback = make_provider_stream_callback(
        runtime.stream_callback,
        source="main",
        session_id=runtime.session_id,
    )

    async def llm_node(state: AgentState) -> AgentState:
        response = await chat_with_retry(
            runtime.provider,
            messages=messages_to_provider_format(state["messages"]),
            tools=runtime.tools,
            system_prompt=runtime.system_prompt,
            stream_callback=provider_stream_callback,
            event_callback=runtime.stream_callback,
            source="main",
            session_id=runtime.session_id,
        )
        if runtime.stream_callback and response.usage:
            await runtime.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=runtime.session_id,
                    event_type="usage",
                    usage=response.usage,
                )
            )

        tool_calls = [
            {
                "name": tc.name,
                "args": dict(tc.args or {}),
                "id": tc.id,
            }
            for tc in response.tool_calls
        ]

        ai_msg = AIMessage(content=response.content, tool_calls=tool_calls)
        ai_msg.additional_kwargs["tool_calls_data"] = response.tool_calls
        ai_msg.additional_kwargs["raw_response"] = response.raw_response
        ai_msg.additional_kwargs["usage"] = response.usage
        return {"messages": [ai_msg]}

    return llm_node
