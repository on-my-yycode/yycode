"""Tests for provider-level token counting."""

import asyncio
import types

from agent.providers.anthropic_provider import AnthropicProvider
from agent.providers.base import ChatResponse, LLMProvider
from agent.providers.openai_provider import OpenAIProvider


class MinimalProvider(LLMProvider):
    """Provider that relies on the base count_tokens fallback."""

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(content="")

    async def close(self):
        return None


class FakeAnthropicMessages:
    """Capture Anthropic count_tokens kwargs."""

    def __init__(self):
        self.kwargs = None

    async def count_tokens(self, **kwargs):
        self.kwargs = kwargs
        return types.SimpleNamespace(input_tokens=123)


class FakeEncoding:
    """Small deterministic tokenizer for tests."""

    def encode(self, text):
        return str(text).split()


def test_base_provider_count_tokens_defaults_to_none():
    provider = MinimalProvider()

    assert asyncio.run(provider.count_tokens(messages=[], system_prompt=None, tools=None)) is None


def test_anthropic_provider_count_tokens_uses_messages_endpoint():
    messages = FakeAnthropicMessages()
    provider = object.__new__(AnthropicProvider)
    provider.model = "claude-test"
    provider.client = types.SimpleNamespace(messages=messages)

    count = asyncio.run(
        provider.count_tokens(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="system",
            tools=[{"name": "tool"}],
        )
    )

    assert count == 123
    assert messages.kwargs == {
        "model": "claude-test",
        "messages": [{"role": "user", "content": "hello"}],
        "system": "system",
        "tools": [{"name": "tool"}],
    }


def test_openai_provider_count_tokens_counts_messages_system_and_tools():
    provider = object.__new__(OpenAIProvider)
    provider.model = "gpt-4o"
    provider._encoding_for_model = lambda: FakeEncoding()

    count_without_tools = asyncio.run(
        provider.count_tokens(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="system",
            tools=None,
        )
    )
    count_with_tools = asyncio.run(
        provider.count_tokens(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="system",
            tools=[
                {
                    "name": "demo",
                    "description": "Demo tool",
                    "input_schema": {"type": "object", "properties": {}},
                }
            ],
        )
    )

    assert isinstance(count_without_tools, int)
    assert count_without_tools > 0
    assert count_with_tools > count_without_tools


def test_openai_provider_count_tokens_returns_none_when_encoding_unavailable():
    provider = object.__new__(OpenAIProvider)
    provider.model = "gpt-4o"
    provider._encoding_for_model = lambda: None

    count = asyncio.run(
        provider.count_tokens(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="system",
            tools=None,
        )
    )

    assert count is None
