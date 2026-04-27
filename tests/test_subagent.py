"""Tests for subagent delegation."""

import asyncio

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agent.approval import ApprovalDenied
from agent.graph import create_llm_node, create_tools_node
from agent.providers.base import ChatResponse, LLMProvider, ToolCall
from agent.session import Session
from agent.streaming import StreamEvent
from agent.subagent import (
    ROLE_PROMPTS,
    SubagentRunner,
    build_subagent_system_prompt,
    filter_subagent_tool,
)
from agent.tool_retry import async_run_tool_with_retry
from agent.todo_manager import TodoManager
from tools import TOOLS


class FakeProvider(LLMProvider):
    """Fake provider that returns queued responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system_prompt": system_prompt,
            }
        )
        if stream_callback:
            await stream_callback("text_delta", "streamed")
        return self.responses.pop(0)

    async def close(self):
        return None


def test_subagent_tool_is_registered():
    tool_names = {tool["name"] for tool in TOOLS}
    subagent_tool = next(tool for tool in TOOLS if tool["name"] == "subagent")
    role_schema = subagent_tool["input_schema"]["properties"]["role"]

    assert "subagent" in tool_names
    assert set(role_schema["enum"]) == {
        "explorer",
        "architect",
        "worker",
        "tester",
        "security",
    }
    assert set(subagent_tool["input_schema"]["required"]) == {"role", "task"}
    assert set(subagent_tool["input_schema"]["properties"]) == {
        "role",
        "task",
        "context",
        "max_turns",
    }


def test_main_agent_prompt_describes_subagent_boundaries(tmp_path):
    session = Session(provider=FakeProvider([]), workdir=tmp_path)

    assert "Task State contract:" in session.system_prompt
    assert "Core workflow:" in session.system_prompt
    assert "Tools and editing:" in session.system_prompt
    assert "Subagent delegation:" in session.system_prompt
    assert "Skills:" in session.system_prompt
    assert "Final answer:" in session.system_prompt
    assert "Every user request must be represented in Task State" in session.system_prompt
    assert "Create todo even for simple work" in session.system_prompt
    assert "Keep exactly one active item in_progress" in session.system_prompt
    assert "Do not provide a final answer while any todo item is pending or in_progress" in session.system_prompt
    assert "check workspace_state and relevant git_diff" in session.system_prompt
    assert "git_diff" in session.system_prompt
    assert "Use a short execution plan, usually 1-7 concrete todo items" in session.system_prompt
    assert "do not expose long internal reasoning" in session.system_prompt
    assert "Use list_skills to discover available local skills" in session.system_prompt
    assert "Use explorer for investigation" in session.system_prompt
    assert "architect for design" in session.system_prompt
    assert "security for security review" in session.system_prompt
    assert "Give each subagent a specific task" in session.system_prompt
    assert "After a subagent returns, integrate its result yourself and update Task State" in session.system_prompt
    assert "Use apply_patch as the primary tool for editing existing files" in session.system_prompt
    assert "Use write_file" in session.system_prompt
    assert "brand-new files or generated artifacts" in session.system_prompt
    assert "run verify with the narrowest useful target" in session.system_prompt
    assert "Safety:" in session.system_prompt
    assert "Keep changes scoped to the user request" in session.system_prompt


def test_subagent_roles_include_architect_tester_and_security():
    assert set(ROLE_PROMPTS) == {"explorer", "architect", "worker", "tester", "security"}
    assert "technical approach" in ROLE_PROMPTS["architect"]
    assert "verification" in ROLE_PROMPTS["tester"]
    assert "security risks" in ROLE_PROMPTS["security"]
    assert "severity" in ROLE_PROMPTS["security"]


def test_subagent_prompt_is_concise_and_does_not_inherit_parent_prompt(tmp_path):
    prompt = build_subagent_system_prompt(
        role="explorer",
        workdir=tmp_path,
        parent_prompt="VERY VERBOSE PARENT PROMPT",
    )

    assert "VERY VERBOSE PARENT PROMPT" not in prompt
    assert "delegated coding subagent" in prompt
    assert "Do not use todo planning" in prompt
    assert "Use list_skills to discover skills" in prompt
    assert "Return only the information needed by the parent agent" in prompt
    assert "at most 5 bullets" in prompt


def test_async_retry_supports_sync_and_async_handlers():
    def sync_handler(value):
        return f"sync:{value}"

    async def async_handler(value):
        return f"async:{value}"

    assert (
        asyncio.run(async_run_tool_with_retry(sync_handler, "sync", value="ok"))
        == "sync:ok"
    )
    assert (
        asyncio.run(async_run_tool_with_retry(async_handler, "async", value="ok"))
        == "async:ok"
    )


def test_async_retry_times_out_sync_and_async_handlers():
    def slow_sync_handler():
        import time

        time.sleep(0.05)
        return "late"

    async def slow_async_handler():
        await asyncio.sleep(0.05)
        return "late"

    sync_result = asyncio.run(
        async_run_tool_with_retry(
            slow_sync_handler,
            "slow_sync",
            max_retries=0,
            timeout_seconds=0.01,
        )
    )
    async_result = asyncio.run(
        async_run_tool_with_retry(
            slow_async_handler,
            "slow_async",
            max_retries=0,
            timeout_seconds=0.01,
        )
    )

    assert sync_result == "Error executing tool slow_sync: Timeout after 0.01s"
    assert async_result == "Error executing tool slow_async: Timeout after 0.01s"


def test_filter_subagent_tool_prevents_recursive_delegation_and_todo_planning():
    filtered_tools = filter_subagent_tool(TOOLS)
    filtered_tool_names = {tool["name"] for tool in filtered_tools}
    all_tool_names = {tool["name"] for tool in TOOLS}

    assert "subagent" in all_tool_names
    assert "todo" in all_tool_names
    assert "subagent" not in filtered_tool_names
    assert "todo" not in filtered_tool_names


def test_subagent_runner_uses_filtered_tools_and_returns_summary(tmp_path):
    provider = FakeProvider([ChatResponse(content="found the answer")])
    runner = SubagentRunner(
        provider=provider,
        workdir=tmp_path,
        parent_system_prompt="parent prompt",
        tool_handlers={},
        tools=TOOLS,
    )

    result = asyncio.run(runner.run(role="explorer", task="inspect code"))

    assert "role: explorer" in result
    assert "status: completed" in result
    assert "found the answer" in result
    assert "subagent" not in {tool["name"] for tool in provider.calls[0]["tools"]}
    assert "todo" not in {tool["name"] for tool in provider.calls[0]["tools"]}


def test_subagent_runner_raises_approval_denied_for_self_approved_write(tmp_path):
    called = []
    provider = FakeProvider(
        [
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="write-1",
                        name="write_file",
                        args={"path": "new.py", "content": "x", "approved": True},
                    )
                ],
            ),
            ChatResponse(content="done"),
        ]
    )
    runner = SubagentRunner(
        provider=provider,
        workdir=tmp_path,
        parent_system_prompt="parent prompt",
        tool_handlers={"write_file": lambda **kwargs: called.append(kwargs) or "wrote"},
        tools=[
            {
                "name": "write_file",
                "description": "write",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        ],
    )

    with pytest.raises(ApprovalDenied) as exc:
        asyncio.run(runner.run(role="worker", task="write"))

    assert called == []
    assert exc.value.request.action == "create_file"


def test_subagent_runner_allows_write_after_runtime_approval(tmp_path):
    called = []

    async def approve(_request):
        return True

    provider = FakeProvider(
        [
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id="write-1",
                        name="write_file",
                        args={"path": "new.py", "content": "x"},
                    )
                ],
            ),
            ChatResponse(content="done"),
        ]
    )
    runner = SubagentRunner(
        provider=provider,
        workdir=tmp_path,
        parent_system_prompt="parent prompt",
        tool_handlers={"write_file": lambda **kwargs: called.append(kwargs) or "wrote"},
        tools=[
            {
                "name": "write_file",
                "description": "write",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        ],
        approval_callback=approve,
    )

    result = asyncio.run(runner.run(role="worker", task="write"))

    assert "done" in result
    assert called == [{"path": "new.py", "content": "x", "approved": True}]


def test_subagent_runner_emits_structured_stream_events(tmp_path):
    events: list[StreamEvent] = []

    async def collect_event(event: StreamEvent):
        events.append(event)

    provider = FakeProvider([
        ChatResponse(
            content="done",
            usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )
    ])
    runner = SubagentRunner(
        provider=provider,
        workdir=tmp_path,
        parent_system_prompt="parent prompt",
        tool_handlers={},
        tools=TOOLS,
        parent_session_id="parent-1",
        stream_callback=collect_event,
    )

    asyncio.run(runner.run(role="worker", task="stream progress"))

    assert len(events) == 4
    assert events[0].source == "subagent"
    assert events[0].role == "worker"
    assert events[0].parent_session_id == "parent-1"
    assert events[0].event_type == "subagent_started"
    assert events[0].title == "worker subagent started"
    assert events[0].phase == "implementing"
    assert events[1].event_type == "text_delta"
    assert events[1].content == "streamed"
    assert events[2].event_type == "usage"
    assert events[2].usage == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    assert events[3].event_type == "subagent_finished"
    assert events[3].status == "completed"


def test_main_llm_node_emits_structured_stream_events():
    events: list[StreamEvent] = []

    async def collect_event(event: StreamEvent):
        events.append(event)

    provider = FakeProvider([
        ChatResponse(
            content="done",
            usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )
    ])
    llm_node = create_llm_node(
        provider=provider,
        system_prompt="parent prompt",
        session_id="main-1",
        stream_callback=collect_event,
    )

    result = asyncio.run(llm_node({"messages": []}))

    assert result["messages"][0].content == "done"
    assert len(events) == 2
    assert events[0].source == "main"
    assert events[0].session_id == "main-1"
    assert events[0].role is None
    assert events[0].event_type == "text_delta"
    assert events[1].event_type == "usage"
    assert events[1].usage == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}


def test_tools_node_executes_subagent_tool_call(tmp_path, monkeypatch):
    provider = FakeProvider([ChatResponse(content="child result")])

    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {},
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            {
                "name": "subagent",
                "description": "delegate",
                "execution": {
                    "side_effects": "delegation",
                    "concurrency": "role_based",
                    "timeout_seconds": 300,
                },
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        ],
    )

    tools_node = create_tools_node(
        provider=provider,
        system_prompt="parent prompt",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="parent-1",
    )
    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(
            id="call-1",
            name="subagent",
            args={"role": "worker", "task": "do the work"},
        )
    ]

    result = asyncio.run(tools_node({"messages": [ai_msg]}))

    assert len(result["messages"]) == 1
    tool_msg = result["messages"][0]
    assert isinstance(tool_msg, ToolMessage)
    assert tool_msg.tool_call_id == "call-1"
    assert "role: worker" in tool_msg.content
    assert "child result" in tool_msg.content
    assert tool_msg.additional_kwargs["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
