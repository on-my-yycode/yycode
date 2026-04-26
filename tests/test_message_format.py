"""Tests for provider message formatting."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.message_format import messages_to_provider_format
from agent.providers.base import ToolCall


def test_messages_to_provider_format_preserves_assistant_tool_use_before_tool_result():
    assistant = AIMessage(content="Working on it")
    assistant.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="call_123", name="read_file", args={"path": "main.py"})
    ]
    tool_result = ToolMessage(content="file body", tool_call_id="call_123", name="read_file")

    formatted = messages_to_provider_format(
        [
            HumanMessage(content="inspect"),
            assistant,
            tool_result,
        ]
    )

    assert formatted == [
        {"role": "user", "content": "inspect"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Working on it"},
                {
                    "type": "tool_use",
                    "id": "call_123",
                    "name": "read_file",
                    "input": {"path": "main.py"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_123",
                    "content": "file body",
                }
            ],
        },
    ]


def test_messages_to_provider_format_combines_consecutive_tool_results_into_one_user_message():
    assistant = AIMessage(content="")
    assistant.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="call_a", name="read_file", args={"path": "a.py"}),
        ToolCall(id="call_b", name="read_file", args={"path": "b.py"}),
    ]

    formatted = messages_to_provider_format(
        [
            assistant,
            ToolMessage(content="A", tool_call_id="call_a", name="read_file"),
            ToolMessage(content="B", tool_call_id="call_b", name="read_file"),
        ]
    )

    assert formatted == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call_a",
                    "name": "read_file",
                    "input": {"path": "a.py"},
                },
                {
                    "type": "tool_use",
                    "id": "call_b",
                    "name": "read_file",
                    "input": {"path": "b.py"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_a",
                    "content": "A",
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "call_b",
                    "content": "B",
                },
            ],
        },
    ]


def test_messages_to_provider_format_keeps_plain_assistant_text_without_tool_calls():
    formatted = messages_to_provider_format([AIMessage(content="hello")])

    assert formatted == [{"role": "assistant", "content": "hello"}]


def test_messages_to_provider_format_prefers_provider_blocks_for_assistant_history():
    assistant = AIMessage(content="hidden")
    assistant.additional_kwargs["provider_blocks"] = [
        {"type": "thinking", "thinking": "step by step", "signature": "sig-1"},
        {"type": "text", "text": "visible"},
    ]

    formatted = messages_to_provider_format([assistant])

    assert formatted == [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "step by step", "signature": "sig-1"},
                {"type": "text", "text": "visible"},
            ],
        }
    ]
