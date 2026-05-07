"""Tests for Task State finish guard."""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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


def _tool_call_name(tool_call):
    if isinstance(tool_call, dict):
        return tool_call.get("name")
    return getattr(tool_call, "name", None)


def _todo_artifact_messages(messages):
    artifacts = []
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == "todo":
            artifacts.append(message)
        if isinstance(message, AIMessage):
            tool_calls = list(getattr(message, "tool_calls", []) or [])
            tool_calls_data = list(message.additional_kwargs.get("tool_calls_data") or [])
            provider_blocks = list(message.additional_kwargs.get("provider_blocks") or [])
            if any(_tool_call_name(tool_call) == "todo" for tool_call in tool_calls):
                artifacts.append(message)
            if any(_tool_call_name(tool_call) == "todo" for tool_call in tool_calls_data):
                artifacts.append(message)
            if any(
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "todo"
                for block in provider_blocks
            ):
                artifacts.append(message)
    return artifacts


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
    assert not _todo_artifact_messages(session.messages)


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
    assert not _todo_artifact_messages(session.messages)


def test_prune_todo_artifacts_preserves_non_todo_history(tmp_path):
    provider = FakeProvider([])
    session = Session(provider=provider, workdir=tmp_path, system_prompt="test")
    todo_ai = AIMessage(
        content="",
        tool_calls=[
            {"id": "todo-1", "name": "todo", "args": {"items": []}},
            {"id": "read-1", "name": "read_file", "args": {"path": "README.md"}},
        ],
    )
    todo_ai.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="todo-1", name="todo", args={"items": []}),
        ToolCall(id="read-1", name="read_file", args={"path": "README.md"}),
    ]
    session.messages = [
        HumanMessage(content="do a task"),
        todo_ai,
        ToolMessage(content="Task State: ...", tool_call_id="todo-1", name="todo"),
        ToolMessage(content="README", tool_call_id="read-1", name="read_file"),
        AIMessage(content="final answer"),
    ]

    session._prune_todo_artifacts(1)

    assert not _todo_artifact_messages(session.messages)
    assert any(isinstance(message, ToolMessage) and message.name == "read_file" for message in session.messages)
    kept_ai = next(message for message in session.messages if isinstance(message, AIMessage) and message.tool_calls)
    assert [_tool_call_name(tool_call) for tool_call in kept_ai.tool_calls] == ["read_file"]
