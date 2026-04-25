"""Tests for Task State finish guard."""

import asyncio

from agent.providers.base import ChatResponse, LLMProvider, ToolCall
from agent.session import Session


class FakeProvider(LLMProvider):
    """Fake provider that returns queued responses and records inputs."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        self.calls.append(messages)
        return self.responses.pop(0)

    async def close(self):
        return None


def test_session_forces_todo_creation_and_completion_before_exit(tmp_path):
    provider = FakeProvider(
        [
            ChatResponse(content="premature final"),
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="todo-1",
                        name="todo",
                        args={
                            "items": [
                                {
                                    "id": "1",
                                    "text": "Complete the requested task",
                                    "status": "in_progress",
                                }
                            ]
                        },
                    )
                ],
            ),
            ChatResponse(content="still premature"),
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="todo-2",
                        name="todo",
                        args={
                            "items": [
                                {
                                    "id": "1",
                                    "text": "Complete the requested task",
                                    "status": "completed",
                                }
                            ]
                        },
                    )
                ],
            ),
            ChatResponse(content="final answer"),
        ]
    )
    session = Session(provider=provider, workdir=tmp_path, system_prompt="test")

    result = asyncio.run(session.send("do a task"))

    assert result.content == "final answer"
    assert len(provider.calls) == 5
    assert "Task State is required" in str(provider.calls[1])
    assert "Task State still has unfinished work" in str(provider.calls[3])
    assert session.todo_manager.can_finish_task() is True


def test_session_ends_when_todo_completion_already_has_final_answer(tmp_path):
    provider = FakeProvider(
        [
            ChatResponse(
                content="All work is complete. Final answer.",
                tool_calls=[
                    ToolCall(
                        id="todo-1",
                        name="todo",
                        args={
                            "items": [
                                {
                                    "id": "1",
                                    "text": "Complete the requested task",
                                    "status": "completed",
                                }
                            ]
                        },
                    )
                ],
            ),
        ]
    )
    session = Session(provider=provider, workdir=tmp_path, system_prompt="test")

    result = asyncio.run(session.send("do a task"))

    assert result.content == "All work is complete. Final answer."
    assert len(provider.calls) == 1
    assert session.todo_manager.can_finish_task() is True
