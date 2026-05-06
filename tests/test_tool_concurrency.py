"""Tests for internal tools_node concurrency scheduling."""

import asyncio
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.approval import ApprovalDenied
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


def test_todo_reminder_resets_after_it_is_consumed():
    manager = TodoManager()
    manager.set_items([{"id": "1", "text": "Long task", "status": "in_progress"}])
    manager.record_tool_call("read_file")
    manager.record_tool_call("grep")
    manager.record_tool_call("read_file")

    assert manager.needs_reminder() is True
    reminder = manager.consume_reminder_message()

    assert "Long task" in reminder
    assert manager.consecutive_non_todo_rounds == 0
    assert manager.needs_reminder() is False


def test_tools_node_warns_when_todo_repeats_same_incomplete_state(tmp_path):
    manager = TodoManager()
    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=manager,
        workdir=tmp_path,
        session_id="session",
    )

    def todo_message(call_id):
        ai_msg = AIMessage(content="")
        ai_msg.additional_kwargs["tool_calls_data"] = [
            ToolCall(
                id=call_id,
                name="todo",
                args={
                    "items": [
                        {
                            "id": "1",
                            "text": "Verify game",
                            "status": "in_progress",
                        }
                    ]
                },
            )
        ]
        return ai_msg

    asyncio.run(tools_node({"messages": [todo_message("todo-1")]}))
    result = asyncio.run(tools_node({"messages": [todo_message("todo-2")]}))

    assert any(
        isinstance(message, HumanMessage) and "Task State did not change" in message.content
        for message in result["messages"]
    )


def test_todo_tool_emits_task_state_result_event(tmp_path):
    events = []

    async def collect_event(event):
        events.append(event)

    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="session",
        stream_callback=collect_event,
    )
    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(
            id="todo-1",
            name="todo",
            args={
                "items": [
                    {"id": "1", "text": "Inspect", "status": "completed"},
                    {"id": "2", "text": "Patch", "status": "in_progress"},
                ],
                "memory": {"user_goal": "Restore task display"},
            },
        )
    ]

    asyncio.run(tools_node({"messages": [ai_msg]}))

    result_events = [event for event in events if event.event_type == "tool_result"]
    assert len(result_events) == 1
    assert result_events[0].title == "Task State"
    assert "[X] [1] Inspect" in result_events[0].content
    assert "[~] [2] Patch" in result_events[0].content
    assert "Goal: Restore task display" in result_events[0].content


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
    events = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append(tool_name)
        if tool_name == "apply_patch":
            return "Applied patch.\n\ndiff:\n@@ -1 +1 @@\n-old\n+new"
        return f"{tool_name}:ok"

    async def collect_event(event):
        events.append(event)

    async def approve(_request):
        return True

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
        stream_callback=collect_event,
        approval_callback=approve,
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
    tool_result_events = [event for event in events if event.event_type == "tool_result"]
    assert len(tool_result_events) == 1
    assert tool_result_events[0].content == "@@ -1 +1 @@\n-old\n+new"
    tool_start_events = [event for event in events if event.event_type == "tool_start"]
    apply_patch_start = next(event for event in tool_start_events if event.tool_name == "apply_patch")
    assert apply_patch_start.title == "Apply patch"
    assert apply_patch_start.phase == "implementing"
    assert apply_patch_start.status == "running"
    file_changed_events = [event for event in events if event.event_type == "file_changed"]
    assert len(file_changed_events) == 1
    assert file_changed_events[0].title == "File changed"


def test_tools_node_reuses_approval_for_same_action_and_path(tmp_path, monkeypatch):
    approvals = []
    captured = []
    events = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append((tool_name, kwargs))
        if tool_name == "apply_patch":
            return "Applied patch.\n\ndiff:\n@@ -1 +1 @@\n-old\n+new"
        return f"{tool_name}:ok"

    async def approve(request):
        approvals.append(request)
        return True

    async def collect_event(event):
        events.append(event)

    monkeypatch.setattr("agent.graph.async_run_tool_with_retry", fake_run_tool)
    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {
            "workspace_state": lambda: "state",
            "git_diff": lambda: "diff",
            "apply_patch": lambda **kwargs: "patched",
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
        stream_callback=collect_event,
        approval_callback=approve,
    )
    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="1", name="workspace_state", args={}),
        ToolCall(id="2", name="git_diff", args={}),
        ToolCall(
            id="3",
            name="apply_patch",
            args={
                "patch": "\n".join(
                    [
                        "diff --git a/example.py b/example.py",
                        "--- a/example.py",
                        "+++ b/example.py",
                        "@@ -1 +1 @@",
                        "-old",
                        "+new",
                    ]
                )
            },
        ),
        ToolCall(
            id="4",
            name="apply_patch",
            args={"path": "example.py", "old_text": "old", "new_text": "new"},
        ),
    ]

    asyncio.run(tools_node({"messages": [ai_msg]}))

    assert len(approvals) == 1
    assert approvals[0].path == "example.py"
    approval_events = [event for event in events if event.event_type.startswith("approval_")]
    assert [event.event_type for event in approval_events] == [
        "approval_required",
        "approval_resolved",
        "approval_resolved",
    ]
    preview_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "tool_result" and event.metadata and event.metadata.get("approval_preview")
    )
    approval_index = next(index for index, event in enumerate(events) if event.event_type == "approval_required")
    assert preview_index < approval_index
    assert events[preview_index].title == "Review diff before approval"
    assert "-old" in events[preview_index].content
    assert "+new" in events[preview_index].content
    assert approval_events[0].status == "waiting_for_user"
    assert approval_events[0].metadata["action"] == "edit_file"
    assert approval_events[1].status == "approved"
    assert approval_events[2].status == "cached_approved"
    apply_patch_calls = [kwargs for tool_name, kwargs in captured if tool_name == "apply_patch"]
    assert len(apply_patch_calls) == 2
    assert all(kwargs["approved"] is True for kwargs in apply_patch_calls)


def test_tools_node_raises_approval_denied_for_rejected_write(tmp_path, monkeypatch):
    captured = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append(tool_name)
        if tool_name == "apply_patch":
            return "approval_required:\naction: edit_file"
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
        ToolCall(id="1", name="workspace_state", args={}),
        ToolCall(id="2", name="git_diff", args={}),
        ToolCall(id="3", name="apply_patch", args={"patch": "diff"}),
    ]

    with pytest.raises(ApprovalDenied) as exc:
        asyncio.run(tools_node({"messages": [ai_msg]}))

    assert captured == ["workspace_state", "git_diff"]
    assert exc.value.request.action == "edit_file"


def test_tools_node_requires_apply_patch_for_existing_file_write(tmp_path, monkeypatch):
    (tmp_path / "existing.py").write_text("old\n")
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
            "write_file": lambda path, content: "wrote",
        },
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            _tool_def("workspace_state", "read_only", "safe"),
            _tool_def("git_diff", "read_only", "safe"),
            _tool_def("write_file", "workspace_write", "serial", 60),
        ],
    )
    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="session",
    )

    preflight_msg = AIMessage(content="")
    preflight_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="1", name="workspace_state", args={}),
        ToolCall(id="2", name="git_diff", args={}),
    ]
    asyncio.run(tools_node({"messages": [preflight_msg]}))

    write_msg = AIMessage(content="")
    write_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="3", name="write_file", args={"path": "existing.py", "content": "new\n"}),
    ]
    result = asyncio.run(tools_node({"messages": [write_msg]}))

    assert captured == ["workspace_state", "git_diff"]
    assert len(result["messages"]) == 1
    assert "blocked write_file for existing file" in result["messages"][0].content
    assert "Use apply_patch" in result["messages"][0].content


def test_tools_node_allows_write_file_for_new_file(tmp_path, monkeypatch):
    captured = []

    async def fake_run_tool(handler, tool_name, max_retries=2, timeout_seconds=None, **kwargs):
        captured.append(tool_name)
        return f"{tool_name}:ok"

    async def approve(_request):
        return True

    monkeypatch.setattr("agent.graph.async_run_tool_with_retry", fake_run_tool)
    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {
            "workspace_state": lambda: "state",
            "git_diff": lambda: "diff",
            "write_file": lambda path, content: "wrote",
        },
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            _tool_def("workspace_state", "read_only", "safe"),
            _tool_def("git_diff", "read_only", "safe"),
            _tool_def("write_file", "workspace_write", "serial", 60),
        ],
    )
    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="session",
        approval_callback=approve,
    )

    preflight_msg = AIMessage(content="")
    preflight_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="1", name="workspace_state", args={}),
        ToolCall(id="2", name="git_diff", args={}),
    ]
    asyncio.run(tools_node({"messages": [preflight_msg]}))

    write_msg = AIMessage(content="")
    write_msg.additional_kwargs["tool_calls_data"] = [
        ToolCall(id="3", name="write_file", args={"path": "new.py", "content": "new\n"}),
    ]
    result = asyncio.run(tools_node({"messages": [write_msg]}))

    assert captured == ["workspace_state", "git_diff", "write_file"]
    assert result["messages"][0].name == "write_file"
