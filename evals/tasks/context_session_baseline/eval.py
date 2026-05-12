"""Context/session behavior baseline before long-task summary memory."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.context_compressor import ContextCompressor
from agent.providers.base import ChatResponse, ToolCall
from agent.session import Session
from agent.session_store import FileSessionStore
from evals.common import EvalCheck, QueueProvider, run_checks


TASK_NAME = "context_session_baseline"


def evaluate():
    """Run deterministic baseline checks for context/session behavior."""
    return run_checks(
        [
            EvalCheck(
                name="completed_task_prunes_todo_artifacts",
                description="Completed tasks must not leave todo tool artifacts in history.",
                run=_completed_task_prunes_todo_artifacts,
            ),
            EvalCheck(
                name="resume_restores_key_messages",
                description="Session resume must restore canonical persisted messages.",
                run=_resume_restores_key_messages,
            ),
            EvalCheck(
                name="tool_output_compression_preserves_linkage",
                description="Old tool output compression must preserve tool name and call id.",
                run=_tool_output_compression_preserves_linkage,
            ),
            EvalCheck(
                name="unfinished_task_keeps_todo_artifacts",
                description="Unfinished task state must not be pruned as completed history.",
                run=_unfinished_task_keeps_todo_artifacts,
            ),
            EvalCheck(
                name="task_memory_facts_are_structured",
                description="Todo memory fields must keep files, tests, risks, and next steps.",
                run=_task_memory_facts_are_structured,
            ),
        ]
    )


def _completed_task_prunes_todo_artifacts() -> None:
    async def run(tmp_path: Path):
        provider = QueueProvider(
            [
                ChatResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="todo-1",
                            name="todo",
                            args={
                                "items": [
                                    {"id": "1", "text": "finish work", "status": "completed"}
                                ],
                                "memory": {
                                    "user_goal": "finish work",
                                    "decisions": ["completed through eval"],
                                },
                            },
                        )
                    ],
                ),
                ChatResponse(content="final answer"),
            ]
        )
        session = Session(provider=provider, workdir=tmp_path, persist_messages=False)

        await session.send("finish the task")

        assert session.todo_manager.can_finish_task()
        assert not _has_todo_artifact(session.messages)

    _run_with_tmp(run)


def _resume_restores_key_messages() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        workdir = root / "workspace"
        app_root = root / "app"
        store_root = root / "sessions"
        workdir.mkdir()
        app_root.mkdir()
        store = FileSessionStore(app_root=app_root, workdir=workdir, root=store_root)
        store.save(
            "eval-session",
            [
                HumanMessage(content="original goal"),
                AIMessage(content="changed files: agent/session.py; tests/test_main_input.py"),
            ],
        )

        session = Session(
            provider=QueueProvider([]),
            workdir=workdir,
            app_root=app_root,
            runtime_data_dir=root / "runtime",
            session_id="eval-session",
            resume=True,
            message_store=store,
        )

        assert session.restored_message_count == 2
        assert "original goal" in str(session.messages[0].content)
        assert "changed files" in str(session.messages[1].content)


def _tool_output_compression_preserves_linkage() -> None:
    async def run(tmp_path: Path):
        provider = QueueProvider([])
        session = Session(
            provider=provider,
            workdir=tmp_path,
            context_window_tokens=1_000,
            persist_messages=False,
        )
        session.context_compressor = ContextCompressor(
            context_window_tokens=1_000,
            compression_ratio=0.5,
            keep_recent_messages=1,
            max_tool_chars=100,
        )
        session.messages = [
            ToolMessage(
                content="large output\n" + ("x" * 5_000),
                tool_call_id="read-1",
                name="read_file",
            ),
            AIMessage(content="old assistant note"),
        ]

        await session._compress_context_if_needed()

        compressed = session.messages[0]
        assert isinstance(compressed, ToolMessage)
        assert compressed.name == "read_file"
        assert compressed.tool_call_id == "read-1"
        assert compressed.additional_kwargs["context_compressed"] is True
        assert "[Compressed old tool output]" in str(compressed.content)

    _run_with_tmp(run)


def _unfinished_task_keeps_todo_artifacts() -> None:
    def run(tmp_path: Path):
        session = Session(provider=QueueProvider([]), workdir=tmp_path, persist_messages=False)
        session.todo_manager.set_items(
            [{"id": "1", "text": "still working", "status": "in_progress"}]
        )
        session.messages = [
            HumanMessage(content="start a task"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "todo-1", "name": "todo", "args": {"items": []}},
                ],
            ),
            ToolMessage(content="Task State:\n[~] still working", tool_call_id="todo-1", name="todo"),
        ]

        assert not session.todo_manager.can_finish_task()
        assert _has_todo_artifact(session.messages)

    _run_with_tmp_sync(run)


def _task_memory_facts_are_structured() -> None:
    async def run(tmp_path: Path):
        provider = QueueProvider(
            [
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
                                        "text": "update context docs",
                                        "status": "completed",
                                    }
                                ],
                                "memory": {
                                    "user_goal": "prepare long task summary memory",
                                    "constraints": ["do evals first"],
                                    "files_modified": [
                                        "docs/long_task_summary_memory_design.md",
                                        "evals/run.py",
                                    ],
                                    "test_results": ["python evals/run.py: passed"],
                                    "open_risks": ["summary implementation not started"],
                                    "next_steps": ["implement deterministic summary"],
                                },
                            },
                        )
                    ],
                ),
                ChatResponse(content="done"),
            ]
        )
        session = Session(provider=provider, workdir=tmp_path, persist_messages=False)

        await session.send("prepare the plan")

        memory = session.todo_manager.get_memory()
        assert memory["user_goal"] == "prepare long task summary memory"
        assert "do evals first" in memory["constraints"]
        assert "evals/run.py" in memory["files_modified"]
        assert "python evals/run.py: passed" in memory["test_results"]
        assert "implement deterministic summary" in memory["next_steps"]

    _run_with_tmp(run)


def _has_todo_artifact(messages) -> bool:
    for message in messages:
        if isinstance(message, ToolMessage) and message.name == "todo":
            return True
        if isinstance(message, AIMessage):
            tool_calls = list(getattr(message, "tool_calls", []) or [])
            tool_calls_data = list(message.additional_kwargs.get("tool_calls_data") or [])
            if any(_tool_call_name(tool_call) == "todo" for tool_call in tool_calls):
                return True
            if any(_tool_call_name(tool_call) == "todo" for tool_call in tool_calls_data):
                return True
    return False


def _tool_call_name(tool_call) -> str | None:
    if isinstance(tool_call, dict):
        return tool_call.get("name")
    return getattr(tool_call, "name", None)


def _run_with_tmp(fn) -> None:
    with tempfile.TemporaryDirectory() as raw:
        asyncio.run(fn(Path(raw)))


def _run_with_tmp_sync(fn) -> None:
    with tempfile.TemporaryDirectory() as raw:
        fn(Path(raw))
