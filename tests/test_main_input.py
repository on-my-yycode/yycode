"""Tests for CLI input handling."""

import asyncio

from agent.providers.base import ChatResponse, LLMProvider
from agent.approval import ApprovalRequest
from langchain_core.messages import AIMessage, ToolMessage
from agent.context_compressor import ContextCompressor
from agent.session import (
    DOUBAO_CODE_CONTEXT_WINDOW_TOKENS,
    Session,
    infer_context_window_tokens,
    parse_context_window_tokens,
)
from main import (
    build_prompt,
    format_context_percent,
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

    model = "fake-model"

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(
            content="",
            usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )

    async def close(self):
        return None


class FakeCountingProvider(FakeProvider):
    """Fake provider that reports exact token counts."""

    async def count_tokens(self, messages, system_prompt=None, tools=None):
        has_compressed_output = "[Compressed old tool output]" in str(messages)
        return 100 if has_compressed_output else 900


class FakeApprovalProvider(FakeProvider):
    """Fake provider that asks for a write tool."""

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        from agent.providers.base import ToolCall

        return ChatResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="write-1",
                    name="write_file",
                    args={"path": "new.txt", "content": "hello"},
                )
            ],
        )


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


def test_build_prompt_includes_context_window_pressure(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="x" * 400,
        context_window_tokens=1_000,
    )
    prompt = build_prompt(session)

    assert "[100/1k 10%]" in prompt
    assert "yoyo >>" in prompt


def test_build_prompt_uses_context_window_not_cumulative_usage(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="x" * 1_000,
        context_window_tokens=10_000,
    )
    session.cumulative_usage = {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 153_835,
    }
    prompt = build_prompt(session)

    assert "[250/10k 2.5%]" in prompt
    assert "153.8k" not in prompt


def test_read_user_query_with_session_uses_dynamic_prompt(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)
    fake_input = FakeInput(["hello"])

    query = asyncio.run(read_user_query_with_session(session, fake_input))

    assert query == "hello"
    assert len(fake_input.prompts) == 1
    assert "/" in fake_input.prompts[0]
    assert "%" in fake_input.prompts[0]


def test_format_token_count_supports_compact_units():
    assert format_token_count(987) == "987"
    assert format_token_count(1_000) == "1k"
    assert format_token_count(1_250) == "1.2k"
    assert format_token_count(153_835) == "153.8k"
    assert format_token_count(1_200_000) == "1.2m"


def test_format_context_percent():
    assert format_context_percent(2.45) == "2.5%"
    assert format_context_percent(10.4) == "10%"


def test_parse_context_window_tokens():
    assert parse_context_window_tokens("128000") == 128_000
    assert parse_context_window_tokens("200_000") == 200_000
    assert parse_context_window_tokens("bad") is None
    assert parse_context_window_tokens("-1") is None


def test_infer_context_window_tokens_supports_doubao_code():
    provider = FakeProvider()
    provider.model = "doubao-seed-2.0-code"

    assert infer_context_window_tokens(provider) == DOUBAO_CODE_CONTEXT_WINDOW_TOKENS


def test_session_compresses_old_tool_outputs_and_emits_event(tmp_path):
    events = []

    async def collect_event(event):
        events.append(event)

    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="short",
        context_window_tokens=1_000,
        stream_callback=collect_event,
    )
    session.context_compressor = ContextCompressor(
        context_window_tokens=1_000,
        keep_recent_messages=1,
        max_tool_chars=100,
    )
    session.add_message(ToolMessage(content="x" * 4_000, tool_call_id="call-1", name="bash"))

    asyncio.run(session.send("hello"))

    assert session.messages[0].additional_kwargs["context_compressed"] is True
    assert "[Compressed old tool output]" in session.messages[0].content
    assert any(event.event_type == "context_compressed" for event in events)


def test_session_uses_provider_token_count_for_compression(tmp_path):
    events = []

    async def collect_event(event):
        events.append(event)

    session = Session(
        provider=FakeCountingProvider(),
        workdir=tmp_path,
        system_prompt="short",
        context_window_tokens=1_000,
        stream_callback=collect_event,
    )
    session.context_compressor = ContextCompressor(
        context_window_tokens=1_000,
        keep_recent_messages=1,
        max_tool_chars=100,
    )
    session.add_message(ToolMessage(content="x" * 4_000, tool_call_id="call-1", name="bash"))

    asyncio.run(session.send("hello"))

    compression_event = next(event for event in events if event.event_type == "context_compressed")
    assert "(900 -> 100 tokens, exact)" in compression_event.content


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


def test_session_stops_when_approval_is_denied(tmp_path):
    approvals = []

    async def deny(request: ApprovalRequest):
        approvals.append(request)
        return False

    session = Session(
        provider=FakeApprovalProvider(),
        workdir=tmp_path,
        approval_callback=deny,
    )

    result = asyncio.run(session.send("create a file"))

    assert len(approvals) == 1
    assert approvals[0].action == "create_file"
    assert result.content.startswith("Task stopped because the requested action was not approved.")
    assert "approval_required:" in result.content
    assert not (tmp_path / "new.txt").exists()
