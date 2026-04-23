"""Tests for CLI input handling."""

import asyncio

from agent.providers.base import ChatResponse, LLMProvider
from langchain_core.messages import AIMessage, ToolMessage
from agent.session import Session
from main import (
    build_prompt,
    format_token_count,
    read_user_query,
    read_user_query_with_session,
)


class FakeInput:
    """Callable input replacement backed by predefined responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        return self.responses.pop(0)


class FakeProvider(LLMProvider):
    """Fake provider for session construction."""

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(
            content="",
            usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )

    async def close(self):
        return None


def test_read_user_query_returns_single_line_input():
    fake_input = FakeInput(["hello"])

    query = asyncio.run(read_user_query(fake_input))

    assert query == "hello"
    assert len(fake_input.prompts) == 1


def test_read_user_query_supports_paste_mode():
    fake_input = FakeInput(["/paste", "line one", "line two", "/end"])

    query = asyncio.run(read_user_query(fake_input))

    assert query == "line one\nline two"
    assert len(fake_input.prompts) == 4


def test_build_prompt_includes_estimated_tokens(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)
    prompt = build_prompt(session)

    assert "[" in prompt
    assert "tokens" in prompt
    assert "yoyo >>" in prompt


def test_build_prompt_prefers_cumulative_real_usage(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)
    session.cumulative_usage = {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 153_835,
    }
    prompt = build_prompt(session)

    assert "[153.8k tokens]" in prompt
    assert "est" not in prompt


def test_read_user_query_with_session_uses_dynamic_prompt(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)
    fake_input = FakeInput(["hello"])

    query = asyncio.run(read_user_query_with_session(session, fake_input))

    assert query == "hello"
    assert len(fake_input.prompts) == 1
    assert "tokens" in fake_input.prompts[0]


def test_format_token_count_supports_compact_units():
    assert format_token_count(987) == "987"
    assert format_token_count(1_000) == "1k"
    assert format_token_count(1_250) == "1.2k"
    assert format_token_count(153_835) == "153.8k"
    assert format_token_count(1_200_000) == "1.2m"


def test_session_accumulates_real_usage(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)

    asyncio.run(session.send("hello"))
    asyncio.run(session.send("world"))

    assert session.last_usage == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    assert session.cumulative_usage == {
        "input_tokens": 20,
        "output_tokens": 4,
        "total_tokens": 24,
    }


def test_session_accumulates_usage_from_tool_messages(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)

    ai_msg = AIMessage(content="done")
    ai_msg.additional_kwargs["usage"] = {
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
    }
    tool_msg = ToolMessage(content="tool", tool_call_id="call-1", name="subagent")
    tool_msg.additional_kwargs["usage"] = {
        "input_tokens": 20,
        "output_tokens": 5,
        "total_tokens": 25,
    }

    session._accumulate_usage_from_messages([ai_msg, tool_msg])

    assert session.cumulative_usage == {
        "input_tokens": 30,
        "output_tokens": 7,
        "total_tokens": 37,
    }
