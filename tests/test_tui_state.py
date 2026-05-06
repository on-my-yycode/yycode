"""Tests for TUI state updates."""

from textual.markup import to_content

from agent.streaming import StreamEvent
from agent.todo_manager import TodoManager
from agent.tui.renderers import render_status_text, render_timeline_lines
from agent.tui.state import TuiState


def test_tui_state_tracks_changed_files_and_usage():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="usage",
            usage={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            title="Usage updated",
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="file_changed",
            content="agent/tui/state.py",
            title="File changed",
            detail="agent/tui/state.py",
            phase="implementing",
            file_paths=["agent/tui/state.py"],
        )
    )

    assert state.model_name == "gpt-test"
    assert state.skills_text == "drawio"
    assert state.latest_usage == {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}
    assert state.changed_files == ["agent/tui/state.py"]
    assert state.active_phase == "implementing"
    assert state.status_line == "File changed: agent/tui/state.py"


def test_tui_state_tracks_pending_approval_and_subagent_status():
    state = TuiState()

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="main-1",
            event_type="approval_required",
            content="approval_required: edit file",
            title="Approve file edit",
            detail="agent/tui/app.py",
            phase="blocked",
            status="waiting_for_user",
            tool_name="apply_patch",
            file_paths=["agent/tui/app.py"],
            metadata={"approval_id": "edit|apply_patch|agent/tui/app.py", "diff_preview": "+new"},
        )
    )
    state.apply_event(
        StreamEvent(
            source="subagent",
            session_id="sub-1",
            role="worker",
            parent_session_id="main-1",
            event_type="subagent_started",
            title="Start worker subagent",
            detail="Implement TUI panel refresh",
            phase="implementing",
            status="running",
        )
    )

    approval = state.next_pending_approval()
    assert approval is not None
    assert approval.approval_id == "edit|apply_patch|agent/tui/app.py"
    assert approval.diff_preview == "+new"
    assert state.subagents["sub-1"].role == "worker"
    assert state.subagents["sub-1"].status == "running"

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="main-1",
            event_type="approval_resolved",
            title="Approved file edit",
            detail="agent/tui/app.py",
            status="approved",
            metadata={"approval_id": "edit|apply_patch|agent/tui/app.py"},
        )
    )

    assert state.next_pending_approval() is None


def test_tui_renderers_show_initializing_state_before_session_ready():
    state = TuiState()

    status = render_status_text(state, width=140)
    assert "YOYOAGENT" in status
    assert "Model" in status
    assert "(initializing)" in status
    assert "Starting yoyoagent" in render_timeline_lines(state)


def test_tui_renderers_show_compact_transcript_style_lines():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Read file",
            detail="agent/tui/app.py",
            phase="exploring",
            status="running",
        )
    )

    transcript = render_timeline_lines(state)

    assert "Read file" in transcript
    assert "running" in transcript
    assert "agent/tui/app.py" in transcript


def test_tui_state_records_user_input_in_transcript():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    item = state.add_user_input("sess-1", "Please inspect the startup flow")

    transcript = render_timeline_lines(state)

    assert item.event_type == "user_message"
    assert "You" in transcript
    assert "Please inspect the startup flow" in transcript


def test_tui_main_timeline_hides_task_plan_before_todo_starts():
    manager = TodoManager()
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        todo_manager=manager,
    )

    transcript = render_timeline_lines(state, header_mode="main")

    assert "Ready" in transcript
    assert "Task Plan" not in transcript
    assert "No task plan yet" not in transcript


def test_tui_state_merges_waiting_updates_into_thinking_item():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="agent_thinking",
            title="Task running",
            detail="Thinking / waiting for model response",
            phase="waiting",
            status="running",
        )
    )

    item = state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="llm_waiting",
            title="Waiting for model response",
            detail="Attempt 1/11, 15s since last token",
            phase="waiting",
            status="running",
            elapsed_ms=15_000,
        )
    )

    assert len(state.timeline) == 1
    assert item is state.timeline[0]
    assert item.event_type == "llm_waiting"
    assert item.title == "Waiting for model response"
    assert item.detail == "Attempt 1/11, 15s since last token"
    assert item.elapsed_ms == 15_000


def test_tui_state_updates_single_waiting_item_for_repeated_heartbeats():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    first = state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="llm_waiting",
            title="Waiting for model response",
            detail="Attempt 1/11, 15s since last token",
            phase="waiting",
            status="running",
            elapsed_ms=15_000,
            metadata={"attempt": 1, "attempts": 11, "since_last_token_ms": 15_000},
            usage={"input_tokens": 230, "output_tokens": 147, "total_tokens": 377},
        )
    )
    second = state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="llm_waiting",
            title="Waiting for model response",
            detail="Attempt 1/11, 30s since last token",
            phase="waiting",
            status="running",
            elapsed_ms=30_000,
            metadata={"attempt": 1, "attempts": 11, "since_last_token_ms": 30_000},
        )
    )

    assert first is second
    waiting_items = [item for item in state.timeline if item.event_type == "llm_waiting"]
    assert len(waiting_items) == 1
    assert waiting_items[0].detail == "Attempt 1/11, 30s since last token"
    assert waiting_items[0].metadata["since_last_token_ms"] == 30_000
    transcript = render_timeline_lines(state)
    assert "elapsed" in transcript
    assert "last token 30.0s" in transcript
    assert "attempt 1/11" in transcript
    assert "Tokens 377" in transcript


def test_tui_state_completes_waiting_item_when_model_starts_responding():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="llm_waiting",
            title="Waiting for model response",
            status="running",
            elapsed_ms=15_000,
        )
    )

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content="hello",
        )
    )

    waiting = next(item for item in state.timeline if item.event_type == "llm_waiting")
    assert waiting.status == "completed"
    assert waiting.title == "Model response started"


def test_tui_status_panel_shows_prominent_task_running_state():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.add_user_input("sess-1", "Please inspect the startup flow")

    status = render_status_text(state)

    assert "⏺" in status
    assert "Task running" in status
    assert "Elapsed" in status
    assert "Tokens" in status


def test_tui_status_panel_shows_last_run_after_task_finishes():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.add_user_input("sess-1", "Please inspect the startup flow")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="usage",
            usage={"input_tokens": 20, "output_tokens": 5, "total_tokens": 25},
        )
    )

    state.end_active_task()
    status = render_status_text(state)

    assert "Ready" in status
    assert "Last run" in status
    assert "25" in status
    assert state.last_task["elapsed_ms"] is not None


def test_tui_status_bar_uses_configured_context_window_and_explicit_usage_labels():
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="deepseek-v4-pro",
        skills_text="drawio",
        context_window_tokens=224_000,
    )
    state.latest_usage = {"input_tokens": 230, "output_tokens": 147, "total_tokens": 377}

    status = render_status_text(state)

    assert "Context" in status
    assert "377/224k" in status
    assert "Last run" in status
    assert "0s" in status
    assert "Tokens" in status
    assert "(input" in status
    assert "230" in status
    assert "output" in status
    assert "147" in status


def test_tui_timeline_shows_tool_call_and_return_details():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Read file",
            detail="agent/tui/state.py",
            phase="exploring",
            status="running",
            tool_name="read_file",
        )
    )

    item = state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="Read file",
            detail="agent/tui/state.py",
            phase="exploring",
            status="completed",
            tool_name="read_file",
            elapsed_ms=42,
        )
    )

    transcript = render_timeline_lines(state)

    assert len(state.timeline) == 2
    assert item is state.timeline[1]
    assert item.event_type == "tool_end"
    assert item.status == "completed"
    assert item.elapsed_ms == 42
    assert "⏺" in transcript
    assert "Read file" in transcript
    assert "Tool call" not in transcript
    assert "Tool returned" not in transcript
    assert "completed" in transcript
    assert "42ms" in transcript


def test_tui_timeline_hides_todo_tool_return_when_task_state_result_is_present():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="Update task state",
            detail="1 item(s)",
            status="completed",
            tool_name="todo",
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_result",
            title="Task State",
            content="Task State:\n----------------------------------------\n[~] [1] Patch",
        )
    )

    transcript = render_timeline_lines(state)

    assert "Tool returned" not in transcript
    assert "Task State" in transcript
    assert "Patch" in transcript


def test_tui_timeline_shows_tool_result_content():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_result",
            content="diff --git a/a.py b/a.py\n+new line",
            title="Review diff",
            phase="reviewing",
        )
    )

    transcript = render_timeline_lines(state)

    assert "Review full diff" in transcript
    assert "diff --git" in transcript
    assert "+new line" in transcript
    parsed = to_content(transcript)
    assert any(str(span.style) == "bold green" for span in parsed.spans)


def test_tui_timeline_groups_tool_activity_and_keeps_full_diff():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    diff = "\n".join(
        [
            "diff --git a/a.py b/a.py",
            "--- a/a.py",
            "+++ b/a.py",
            "@@ -1,2 +1,3 @@",
            " old line",
            "-removed line",
            "+added line",
            "+another added line",
        ]
    )

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Apply patch",
            detail="agent/tui/renderers.py",
            status="running",
            tool_name="apply_patch",
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="Apply patch",
            detail="agent/tui/renderers.py",
            status="completed",
            tool_name="apply_patch",
            elapsed_ms=87,
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_result",
            title="Review diff",
            content=diff,
        )
    )

    transcript = render_timeline_lines(state)

    assert "Edit file" in transcript
    assert "87ms" in transcript
    assert transcript.count("Apply patch") == 1
    assert "Review full diff" in transcript
    assert "-removed line" in transcript
    assert "+added line" in transcript
    assert "+another added line" in transcript


def test_tui_status_header_uses_compact_two_column_layout():
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="deepseek-reasoner-with-a-very-long-name",
        skills_text="drawio",
        workspace_path="/Users/yoyofx/Documents/github/yoyoagent",
    )

    status = render_status_text(state, width=140)

    assert "YOYOAGENT" in status
    assert "Model" in status
    assert "Status" in status
    assert "┬" not in status
    assert "│" not in status


def test_tui_status_header_shows_idle_todo_placeholder_before_plan_exists():
    manager = TodoManager()
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        todo_manager=manager,
    )

    status = render_status_text(state, width=140)

    assert "Todo" in status
    assert "planning..." not in status
    assert "-" in status


def test_tui_status_header_shows_todo_progress_summary():
    manager = TodoManager()
    manager.set_items(
        [
            {"id": "1", "text": "Inspect timeline rendering", "status": "completed"},
            {"id": "2", "text": "Fix header todo summary", "status": "in_progress"},
            {"id": "3", "text": "Run focused tests", "status": "pending"},
        ]
    )
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        todo_manager=manager,
    )

    status = render_status_text(state, width=140)

    assert "Todo 1/3" in status
    assert "doing" in status
    assert "Fix header todo summary" in status
    assert "Inspect timeline rendering" not in status


def test_tui_status_header_truncates_long_todo_summary_to_fit_one_line():
    manager = TodoManager()
    manager.set_items(
        [
            {
                "id": "1",
                "text": "Patch the status bar rendering with a very long item that should not overflow the terminal width",
                "status": "in_progress",
            },
            {"id": "2", "text": "Run focused tests", "status": "pending"},
        ]
    )
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        context_window_tokens=224_000,
        todo_manager=manager,
    )

    status = render_status_text(state, width=90)

    assert "Todo 0/2" in status
    assert "doing:" in status
    assert "..." in status
    assert "terminal width" not in status


def test_tui_status_header_shows_completed_todo_state_after_clear():
    manager = TodoManager()
    manager.set_items(
        [
            {"id": "1", "text": "Inspect", "status": "completed"},
            {"id": "2", "text": "Patch", "status": "completed"},
        ]
    )
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        todo_manager=manager,
    )

    status = render_status_text(state, width=100)

    assert "Todo" in status
    assert "completed" in status


def test_tui_main_timeline_shows_compact_tool_and_model_updates():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Read file",
            detail="agent/tui/state.py",
            status="running",
            tool_name="read_file",
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="Read file",
            detail="agent/tui/state.py",
            status="completed",
            tool_name="read_file",
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_result",
            content="diff --git a/a.py b/a.py\n+new line",
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content="Done reviewing the TUI timeline.",
        )
    )

    transcript = render_timeline_lines(state, limit=8, header_mode="main")

    assert "Ctrl+H full history" in transcript
    assert "Read file" in transcript
    assert "Tool call" not in transcript
    assert "Tool returned" not in transcript
    assert "Review full diff" in transcript
    assert "Yoyo" in transcript
    assert "Done reviewing" in transcript


def test_tui_main_timeline_keeps_latest_detailed_event_block_intact_when_height_is_limited():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    for index in range(6):
        state.apply_event(
            StreamEvent(
                source="main",
                session_id="sess-1",
                event_type="tool_start",
                title=f"Read file {index}",
                detail=f"agent/tui/file_{index}.py",
                status="running",
                tool_name="read_file",
                metadata={"args": {"path": f"agent/tui/file_{index}.py"}},
            )
        )

    transcript = render_timeline_lines(state, limit=20, max_lines=8, header_mode="main")

    assert "Read file" in transcript
    assert "Read file 5" in transcript
    assert "agent/tui/file_5.py" in transcript
    assert "Input" in transcript
    assert "agent/tui/file_4.py" not in transcript


def test_tui_timeline_escapes_nested_tool_args_for_textual_markup():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Update memory",
            phase="planning",
            status="running",
            tool_name="memory",
            metadata={
                "args": {
                    "memory": {
                        "user_goal": "Greeting / introduction",
                        "constraints": [],
                        "files_inspected": ["agent/tui/renderers.py"],
                    }
                }
            },
        )
    )

    transcript = render_timeline_lines(state)

    to_content(transcript)
    assert "Greeting / introduction" in transcript
    assert "files_inspected" in transcript
