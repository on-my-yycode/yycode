"""Tests for LLM timeout, heartbeat, and retry behavior."""

import asyncio

import pytest

from agent.llm_retry import LLMCallError, chat_with_retry
from agent.providers.base import ChatResponse, LLMProvider
from agent.session import Session
from agent.streaming import StreamEvent
from agent.tool_retry import async_run_tool_with_retry


class FakeProvider(LLMProvider):
    """Fake provider with a custom chat coroutine."""

    def __init__(self, chat_impl):
        self.chat_impl = chat_impl
        self.calls = 0

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        self.calls += 1
        return await self.chat_impl(messages, tools, system_prompt, stream_callback)

    async def close(self):
        return None


def test_chat_with_retry_retries_provider_errors():
    async def run():
        async def chat_impl(messages, tools, system_prompt, stream_callback):
            if provider.calls == 1:
                raise RuntimeError("temporary provider failure")
            return ChatResponse(content="ok")

        events: list[StreamEvent] = []

        async def collect(event: StreamEvent):
            events.append(event)

        provider = FakeProvider(chat_impl)
        response = await chat_with_retry(
            provider,
            messages=[],
            tools=[],
            event_callback=collect,
            timeout_seconds=1,
            max_retries=1,
            heartbeat_seconds=0.01,
        )
        return provider, response, events

    provider, response, events = asyncio.run(run())

    assert response.content == "ok"
    assert provider.calls == 2
    assert [event.event_type for event in events] == ["llm_error", "llm_retry"]


def test_chat_with_retry_emits_heartbeat_and_timeout():
    async def run():
        async def chat_impl(messages, tools, system_prompt, stream_callback):
            await asyncio.sleep(1)
            return ChatResponse(content="late")

        events: list[StreamEvent] = []

        async def collect(event: StreamEvent):
            events.append(event)

        provider = FakeProvider(chat_impl)
        with pytest.raises(LLMCallError) as exc:
            await chat_with_retry(
                provider,
                messages=[],
                tools=[],
                event_callback=collect,
                timeout_seconds=0.03,
                max_retries=0,
                heartbeat_seconds=0.01,
            )
        return provider, exc.value, events

    provider, exc, events = asyncio.run(run())

    event_types = [event.event_type for event in events]
    assert provider.calls == 1
    assert "llm_waiting" in event_types
    assert "llm_timeout" in event_types
    assert "Timeout after" in exc.last_error


def test_tool_retry_does_not_rerun_failed_llm_calls():
    async def handler():
        raise LLMCallError(
            message="failed",
            attempts=2,
            timeout_seconds=1,
            last_error="timeout",
        )

    with pytest.raises(LLMCallError):
        asyncio.run(async_run_tool_with_retry(handler, "subagent", max_retries=2))


def test_session_returns_clear_message_on_llm_failure(tmp_path):
    async def chat_impl(messages, tools, system_prompt, stream_callback):
        raise RuntimeError("provider unavailable")

    session = Session(
        provider=FakeProvider(chat_impl),
        workdir=tmp_path,
        system_prompt="test",
    )

    response = asyncio.run(session.send("hello"))

    assert "Task stopped because the model did not return" in response.content
    assert "provider unavailable" in response.content
