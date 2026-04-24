"""Tests for internal tools_node concurrency scheduling."""

import asyncio
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.graph import create_tools_node, execute_tool_calls
from agent.providers.base import ChatResponse, LLMProvider, ToolCall
from agent.todo_manager import TodoManager


class FakeToolCall:
    """Minimal tool call object for scheduler tests."""

    def __init__(self, name: str, call_id: str, args: dict | None = None):
        self.name = name
        self.id = call_id
        self.args = args or {}


class FakeProvider(LLMProvider):
    """Fake provider for graph construction."""

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(content="")

    async def close(self):
        return None


def test_execute_tool_calls_runs_concurrent_batches_and_preserves_order():
    calls = [
        FakeToolCall("read_file", "slow", {"delay": 0.05, "value": "first"}),
        FakeToolCall("list_skills", "fast", {"delay": 0.01, "value": "second"}),
    ]

    async def execute(tc):
        await asyncio.sleep(tc.args["delay"])
        return tc.args["value"]

    started = time.perf_counter()
    result = asyncio.run(execute_tool_calls(calls, execute, lambda tc: True))
    elapsed = time.perf_counter() - started

    assert result == ["first", "second"]
    assert elapsed < 0.08


def test_execute_tool_calls_flushes_before_serial_tools():
    calls = [
        FakeToolCall("read_file", "a", {"value": "a"}),
        FakeToolCall("todo", "todo", {"value": "todo"}),
        FakeToolCall("read_file", "b", {"value": "b"}),
    ]
    execution_groups = []
    current_group = []

    async def execute(tc):
        current_group.append(tc.id)
        return tc.args["value"]

    async def run():
        result = []
        nonlocal current_group

        async def wrapped_execute(tc):
            return await execute(tc)

        output = await execute_tool_calls(
            calls,
            wrapped_execute,
            lambda tc: tc.name != "todo",
        )
        result.extend(output)
        return result

    result = asyncio.run(run())

    # The serial todo call should preserve order and split the two read batches.
    assert result == ["a", "todo", "b"]
    assert current_group == ["a", "todo", "b"]


def test_execute_tool_calls_keeps_worker_subagent_serial():
    calls = [
        FakeToolCall("subagent", "explorer", {"role": "explorer"}),
        FakeToolCall("subagent", "worker", {"role": "worker"}),
        FakeToolCall("subagent", "security", {"role": "security"}),
    ]
    serial_roles = []

    async def execute(tc):
        serial_roles.append(tc.args["role"])
        return tc.args["role"]

    def can_run_concurrently(tc):
        return tc.name != "subagent" or tc.args.get("role") != "worker"

    result = asyncio.run(execute_tool_calls(calls, execute, can_run_concurrently))

    assert result == ["explorer", "worker", "security"]
    assert serial_roles == ["explorer", "worker", "security"]


def test_tools_node_passes_default_tool_timeouts(tmp_path, monkeypatch):
    captured = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append((tool_name, timeout_seconds))
        return f"{tool_name}:ok"

    monkeypatch.setattr("agent.graph.async_run_tool_with_retry", fake_run_tool)
    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {
            "read_file": lambda path: "read",
            "bash": lambda command: "bash",
        },
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            {
                "name": "read_file",
                "description": "read",
                "execution": {
                    "side_effects": "read_only",
                    "concurrency": "safe",
                    "timeout_seconds": 30,
                },
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "bash",
                "description": "bash",
                "execution": {
                    "side_effects": "process",
                    "concurrency": "serial",
                    "timeout_seconds": 130,
                },
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "subagent",
                "description": "delegate",
                "execution": {
                    "side_effects": "delegation",
                    "concurrency": "role_based",
                    "timeout_seconds": 300,
                },
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
        ],
    )
    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="session",
    )
    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="1", name="read_file", args={"path": "x"}),
        ToolCall(id="2", name="bash", args={"command": "pwd"}),
        ToolCall(id="3", name="subagent", args={"role": "security", "task": "review"}),
    ]

    asyncio.run(tools_node({"messages": [ai_msg]}))

    assert captured == [
        ("read_file", 30),
        ("bash", 130),
        ("subagent", 300),
    ]


def _tool_def(name, side_effects, concurrency="serial", timeout_seconds=30):
    return {
        "name": name,
        "description": name,
        "execution": {
            "side_effects": side_effects,
            "concurrency": concurrency,
            "timeout_seconds": timeout_seconds,
        },
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }


def test_tools_node_blocks_workspace_write_until_preflight(tmp_path, monkeypatch):
    captured = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append(tool_name)
        return f"{tool_name}:ok"

    monkeypatch.setattr("agent.graph.async_run_tool_with_retry", fake_run_tool)
    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {
            "workspace_state": lambda: "state",
            "git_diff": lambda: "diff",
            "apply_patch": lambda patch: "patched",
        },
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            _tool_def("workspace_state", "read_only", "safe"),
            _tool_def("git_diff", "read_only", "safe"),
            _tool_def("apply_patch", "workspace_write", "serial", 60),
        ],
    )
    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="session",
    )
    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="1", name="apply_patch", args={"patch": "diff"}),
    ]

    result = asyncio.run(tools_node({"messages": [ai_msg]}))

    assert captured == ["workspace_state", "git_diff"]
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)
    assert "Code workflow guard blocked this write" in result["messages"][0].content
    assert "workspace_state:" in result["messages"][0].content
    assert "git_diff:" in result["messages"][0].content


def test_tools_node_allows_write_after_preflight_and_reminds_verify(tmp_path, monkeypatch):
    captured = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append(tool_name)
        return f"{tool_name}:ok"

    monkeypatch.setattr("agent.graph.async_run_tool_with_retry", fake_run_tool)
    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {
            "workspace_state": lambda: "state",
            "git_diff": lambda: "diff",
            "apply_patch": lambda patch: "patched",
        },
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            _tool_def("workspace_state", "read_only", "safe"),
            _tool_def("git_diff", "read_only", "safe"),
            _tool_def("apply_patch", "workspace_write", "serial", 60),
            _tool_def("verify", "process", "serial", 300),
        ],
    )
    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="session",
    )
    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="1", name="workspace_state", args={}),
        ToolCall(id="2", name="git_diff", args={}),
        ToolCall(id="3", name="apply_patch", args={"patch": "diff"}),
    ]

    result = asyncio.run(tools_node({"messages": [ai_msg]}))

    assert captured == ["workspace_state", "git_diff", "apply_patch"]
    assert [msg.name for msg in result["messages"][:3]] == [
        "workspace_state",
        "git_diff",
        "apply_patch",
    ]
    assert isinstance(result["messages"][3], HumanMessage)
    assert "Run verify" in result["messages"][3].content
