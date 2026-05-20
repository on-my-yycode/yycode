"""Helpers for converting LangChain messages into provider-neutral payloads."""

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def messages_to_provider_format(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to the provider-neutral format used by providers."""
    provider_messages: list[dict] = []
    index = 0
    while index < len(messages):
        msg = messages[index]
        if isinstance(msg, HumanMessage):
            provider_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            assistant_message = {
                "role": "assistant",
                "content": _assistant_content(msg),
            }
            reasoning_content = _assistant_reasoning_content(msg)
            if reasoning_content:
                assistant_message["reasoning_content"] = reasoning_content
            provider_messages.append(assistant_message)
        elif isinstance(msg, ToolMessage):
            tool_results: list[dict[str, Any]] = []
            while index < len(messages) and isinstance(messages[index], ToolMessage):
                tool_msg = messages[index]
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_msg.tool_call_id,
                        "content": tool_msg.content,
                    }
                )
                index += 1
            provider_messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )
            continue
        index += 1
    return provider_messages


def _assistant_content(message: AIMessage) -> Any:
    provider_blocks = message.additional_kwargs.get("provider_blocks")
    tool_calls = message.additional_kwargs.get("tool_calls_data") or message.tool_calls or []
    if provider_blocks:
        content_blocks = [
            block
            for block in provider_blocks
            if not (
                isinstance(block, dict)
                and block.get("type") in {"reasoning_content", "tool_use"}
            )
        ]
        content_blocks.extend(_tool_use_blocks(tool_calls))
        return content_blocks or message.content

    if not tool_calls:
        return message.content

    content: list[dict[str, Any]] = []
    if message.content:
        content.append({"type": "text", "text": str(message.content)})
    content.extend(_tool_use_blocks(tool_calls))
    return content


def _assistant_reasoning_content(message: AIMessage) -> str | None:
    reasoning_content = message.additional_kwargs.get("reasoning_content")
    if reasoning_content:
        return str(reasoning_content)

    provider_blocks = message.additional_kwargs.get("provider_blocks") or []
    for block in provider_blocks:
        if not isinstance(block, dict) or block.get("type") != "reasoning_content":
            continue
        value = block.get("reasoning_content") or block.get("text")
        if value:
            return str(value)
    return None


def _tool_use_blocks(tool_calls: list[Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": _tool_call_field(tool_call, "id"),
                "name": _tool_call_field(tool_call, "name"),
                "input": _tool_call_field(tool_call, "args") or {},
            }
        )
    return blocks


def _tool_call_field(tool_call: Any, field: str) -> Any:
    if isinstance(tool_call, dict):
        return tool_call.get(field)
    return getattr(tool_call, field, None)
