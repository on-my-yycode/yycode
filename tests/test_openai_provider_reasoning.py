import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.message_format import messages_to_provider_format
from agent.providers.base import ToolCall
from agent.providers.openai_provider import OpenAIProvider


def test_openai_message_conversion_keeps_reasoning_content_for_deepseek():
    provider = object.__new__(OpenAIProvider)

    converted = provider._convert_messages(
        [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll inspect it."},
                    {
                        "type": "tool_use",
                        "id": "call_123",
                        "name": "read_file",
                        "input": {"path": "main.py"},
                    },
                ],
                "reasoning_content": "Need to inspect the entrypoint first.",
            }
        ]
    )

    assert converted == [
        {
            "role": "assistant",
            "content": "I'll inspect it.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "main.py"}',
                    },
                }
            ],
            "reasoning_content": "Need to inspect the entrypoint first.",
        }
    ]


def test_openai_conversion_keeps_tool_call_before_tool_result_with_reasoning():
    assistant = AIMessage(content="")
    assistant.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="call_123", name="read_file", args={"path": "main.py"})
    ]
    assistant.additional_kwargs["provider_blocks"] = [
        {"type": "reasoning_content", "reasoning_content": "Need to inspect first."},
    ]
    provider = object.__new__(OpenAIProvider)

    converted = provider._convert_messages(
        messages_to_provider_format(
            [
                HumanMessage(content="inspect"),
                assistant,
                ToolMessage(content="file body", tool_call_id="call_123", name="read_file"),
            ]
        )
    )

    assert converted == [
        {"role": "user", "content": "inspect"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "main.py"}',
                    },
                }
            ],
            "reasoning_content": "Need to inspect first.",
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "file body",
        },
    ]


def test_openai_provider_stores_non_streaming_reasoning_content():
    async def run_test():
        provider = object.__new__(OpenAIProvider)
        provider.model = "deepseek-reasoner"
        captured = {}

        async def create(**kwargs):
            captured.update(kwargs)
            message = SimpleNamespace(
                content="Done",
                reasoning_content="Internal reasoning",
                tool_calls=None,
            )
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice], usage=None)

        provider.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        )

        response = await provider.chat([{"role": "user", "content": "hello"}], [])

        assert captured["messages"] == [{"role": "user", "content": "hello"}]
        assert response.content == "Done"
        assert response.content_blocks == [
            {"type": "reasoning_content", "reasoning_content": "Internal reasoning"},
            {"type": "text", "text": "Done"},
        ]

    asyncio.run(run_test())


def test_openai_provider_stores_streaming_reasoning_content():
    async def run_test():
        provider = object.__new__(OpenAIProvider)
        provider.model = "deepseek-reasoner"
        captured = {}

        class FakeStream:
            def __aiter__(self):
                async def iterator():
                    yield SimpleNamespace(
                        usage=None,
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    reasoning_content="Think",
                                    content=None,
                                    tool_calls=None,
                                )
                            )
                        ],
                    )
                    yield SimpleNamespace(
                        usage=None,
                        choices=[
                            SimpleNamespace(
                                delta=SimpleNamespace(
                                    reasoning_content=" more",
                                    content="Done",
                                    tool_calls=None,
                                )
                            )
                        ],
                    )

                return iterator()

        async def create(**kwargs):
            captured.update(kwargs)
            return FakeStream()

        provider.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        )
        deltas = []

        async def stream_callback(kind, value):
            deltas.append((kind, value))

        response = await provider.chat(
            [{"role": "user", "content": "hello"}],
            [],
            stream_callback=stream_callback,
        )

        assert captured["stream"] is True
        assert response.content == "Done"
        assert response.content_blocks == [
            {"type": "reasoning_content", "reasoning_content": "Think more"},
            {"type": "text", "text": "Done"},
        ]
        assert deltas == [("text_delta", "Done")]

    asyncio.run(run_test())
