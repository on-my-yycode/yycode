"""Tests for Anthropic provider content block normalization."""

from agent.providers.anthropic_provider import AnthropicProvider


class _Block:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_normalize_content_blocks_preserves_thinking_and_tool_use():
    provider = AnthropicProvider(api_key="test", model="claude-test")

    normalized = provider._normalize_content_blocks(
        [
            _Block(type="thinking", thinking="reasoning", signature="sig-1"),
            _Block(type="text", text="answer"),
            _Block(type="tool_use", id="call-1", name="read_file", input={"path": "x.py"}),
        ]
    )

    assert normalized == [
        {"type": "thinking", "thinking": "reasoning", "signature": "sig-1"},
        {"type": "text", "text": "answer"},
        {"type": "tool_use", "id": "call-1", "name": "read_file", "input": {"path": "x.py"}},
    ]
