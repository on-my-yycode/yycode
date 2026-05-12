"""Tests for deterministic task summary memory."""

from langchain_core.messages import AIMessage, HumanMessage

from agent.task_memory import (
    MERGED_SUMMARY_SOURCE,
    SUMMARY_CONTEXT_POLICY,
    SUMMARY_MARKER,
    TaskSummaryMemoryBuilder,
    build_merged_task_summary_memory,
    is_task_summary_memory,
)


def test_task_summary_memory_builder_formats_task_memory():
    builder = TaskSummaryMemoryBuilder()
    summary = builder.build(
        [HumanMessage(content="do work"), AIMessage(content="done")],
        start_index=1,
        task_state={
            "items": [{"id": "1", "text": "finish implementation", "status": "completed"}],
            "memory": {
                "user_goal": "implement long task summary memory",
                "constraints": ["deterministic first"],
                "files_inspected": ["agent/session.py"],
                "files_modified": ["agent/task_memory.py"],
                "decisions": ["use HumanMessage marker"],
                "test_results": ["pytest tests/test_task_memory.py -q: passed"],
                "open_risks": ["model summary not implemented"],
                "next_steps": ["wire into Session"],
            },
        },
    )
    message = summary.to_message()

    assert summary.content.startswith(SUMMARY_MARKER)
    assert "## User Goal\nimplement long task summary memory" in summary.content
    assert "- deterministic first" in summary.content
    assert "- agent/session.py" in summary.content
    assert "- agent/task_memory.py" in summary.content
    assert "- use HumanMessage marker" in summary.content
    assert "- pytest tests/test_task_memory.py -q: passed" in summary.content
    assert message.additional_kwargs["context_policy"] == SUMMARY_CONTEXT_POLICY
    assert message.additional_kwargs["summary_memory"] is True
    assert is_task_summary_memory(message)


def test_task_summary_memory_builder_skips_when_no_range_or_existing_summary():
    builder = TaskSummaryMemoryBuilder(min_messages=1)
    existing = builder.build(
        [HumanMessage(content="old")],
        start_index=0,
        task_state={"items": [], "memory": {"user_goal": "old"}},
    ).to_message()

    assert not builder.should_summarize(
        [],
        start_index=0,
        task_state={"items": [], "memory": {"user_goal": "x"}},
    )
    assert not builder.should_summarize(
        [HumanMessage(content="new"), existing],
        start_index=0,
        task_state={"items": [], "memory": {"user_goal": "x"}},
    )


def test_build_merged_task_summary_memory_combines_old_summaries_and_requests():
    builder = TaskSummaryMemoryBuilder()
    first = builder.build(
        [HumanMessage(content="update docs"), AIMessage(content="done")],
        start_index=0,
        task_state={
            "items": [{"id": "1", "text": "update docs", "status": "completed"}],
            "memory": {
                "user_goal": "update docs",
                "constraints": ["docs only"],
                "files_modified": ["docs/code_agent_roadmap.md"],
                "test_results": ["git diff --check: passed"],
            },
        },
    ).to_message()
    second = builder.build(
        [HumanMessage(content="fix ui"), AIMessage(content="done")],
        start_index=0,
        task_state={
            "items": [{"id": "1", "text": "fix ui", "status": "completed"}],
            "memory": {
                "user_goal": "fix ui",
                "decisions": ["show context summarized event"],
                "files_modified": ["agent/tui/renderers.py"],
            },
        },
    ).to_message()

    merged = build_merged_task_summary_memory(
        [HumanMessage(content="update docs"), first, HumanMessage(content="fix ui"), second],
        covered_start_index=0,
        covered_end_index=3,
    )
    message = merged.to_message()

    assert merged.source == MERGED_SUMMARY_SOURCE
    assert "source: automatic_merge" in merged.content
    assert "## Previous Requests" in merged.content
    assert "- update docs" in merged.content
    assert "- fix ui" in merged.content
    assert "- docs only" in merged.content
    assert "- docs/code_agent_roadmap.md" in merged.content
    assert "- agent/tui/renderers.py" in merged.content
    assert "- git diff --check: passed" in merged.content
    assert "- show context summarized event" in merged.content
    assert message.additional_kwargs["summary_memory"] is True
