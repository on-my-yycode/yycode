"""Tests for shared compatibility primitives used by future protocol adapters."""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.approval import ApprovalDecision, ApprovalRequest
from agent.cancellation import CancellationController
from agent.change_snapshot import build_changed_files_snapshot
from agent.plan_snapshot import build_plan_snapshot
from agent.session import Session
from agent.session_replay import build_session_replay
from agent.task_memory import TaskSummaryMemoryBuilder
from agent.todo_manager import TodoManager
from agent.providers.base import ChatResponse, LLMProvider


class FakeProvider(LLMProvider):
    """Fake provider for compatibility primitive tests."""

    model = "fake-model"

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(content="ok")

    async def close(self):
        return None


def test_session_set_model_updates_provider_window_and_graph(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path, context_window_tokens=1_000)
    session._graph = object()

    session.set_model("doubao-seed-2.0-code")

    assert session.provider.model == "doubao-seed-2.0-code"
    assert session.context_window_tokens == 224_000
    assert session.context_compressor.context_window_tokens == 224_000
    assert session._graph is None


def test_plan_snapshot_exports_entries_and_memory():
    manager = TodoManager()
    manager.set_memory({"user_goal": "ship acp prerequisites", "files_modified": ["agent/session.py"]})
    manager.set_items(
        [
            {"id": "1", "text": "model switching", "status": "completed"},
            {"id": "2", "text": "plan snapshot", "status": "in_progress"},
        ]
    )

    snapshot = build_plan_snapshot(manager)

    assert [entry.status for entry in snapshot.entries] == ["completed", "in_progress"]
    assert snapshot.entries[1].priority == "high"
    assert snapshot.memory["user_goal"] == "ship acp prerequisites"
    assert snapshot.task_started is True
    assert snapshot.task_completed is False


def test_changed_files_snapshot_parses_and_merges_diff_sections():
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1 +1,2 @@
 old
+new
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -5,2 +6 @@
-gone
 keep
"""

    snapshot = build_changed_files_snapshot(diff, source="test")

    assert snapshot.source == "test"
    assert len(snapshot.files) == 1
    assert snapshot.files[0].path == "app.py"
    assert snapshot.files[0].added == 1
    assert snapshot.files[0].removed == 1
    assert snapshot.total_added == 1
    assert snapshot.total_removed == 1


def test_session_replay_view_identifies_summary_and_skips_large_raw_tool_output():
    summary = TaskSummaryMemoryBuilder().build(
        [HumanMessage(content="do work"), AIMessage(content="done")],
        start_index=0,
        task_state={"items": [], "memory": {"user_goal": "do work"}},
    ).to_message()
    messages = [
        HumanMessage(content="hello"),
        summary,
        AIMessage(content="final"),
        ToolMessage(content="x" * 3_000, tool_call_id="tool-1", name="read_file"),
        ToolMessage(
            content="[Compressed old tool output]",
            tool_call_id="tool-2",
            name="grep",
            additional_kwargs={"context_compressed": True},
        ),
    ]

    replay = build_session_replay(messages)

    assert [(event.role, event.kind) for event in replay] == [
        ("user", "message"),
        ("system", "summary"),
        ("assistant", "message"),
        ("tool", "tool"),
    ]
    assert replay[-1].metadata["tool_name"] == "grep"


def test_cancellation_controller_returns_stable_statuses():
    async def run():
        controller = CancellationController()
        assert (await controller.cancel()).status == "not_running"

        async def sleep_forever():
            await asyncio.sleep(60)

        task = asyncio.create_task(sleep_forever())
        controller.set_task(task)
        assert controller.is_running() is True
        assert (await controller.cancel()).status == "cancelled"
        assert controller.is_running() is False

        done_task = asyncio.create_task(asyncio.sleep(0))
        await done_task
        controller.set_task(done_task)
        assert (await controller.cancel()).status == "already_finished"

    asyncio.run(run())


def test_approval_decision_exposes_bool_compatibility():
    request = ApprovalRequest(
        action="edit_file",
        tool_name="apply_patch",
        reason="edits files",
        risk="may overwrite work",
        path="agent/session.py",
    )

    assert request.path == "agent/session.py"
    assert ApprovalDecision("approved").approved is True
    assert ApprovalDecision("denied").approved is False
    assert ApprovalDecision("cancelled").approved is False
