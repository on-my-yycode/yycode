"""Tests for TUI state updates."""

from rich.text import Text
from textual.markup import to_content
from textual.widgets import TextArea

from agent.runtime.tool_events import format_tool_event_metadata
from agent.message_context_manager import MessageContextManager
from agent.streaming import StreamEvent
from agent.todo_manager import TodoManager
from agent.tui.app import (
    TIMELINE_TEXT_HEADER,
    _timeline_copy_text,
    _timeline_markup_to_plain_text,
)
from agent.tui.renderers import (
    render_brand_text,
    render_status_text,
    render_task_plan_panel,
    render_timeline_lines,
)
from agent.tui.state import TuiState


def test_timeline_markup_to_plain_text_keeps_dynamic_brackets():
    content = "[#7f8794]\\[latest] showing[/] [#d7dae0]1-24[/] [bold]events[/]"

    plain = _timeline_markup_to_plain_text(content)

    assert "[latest] showing" in plain
    assert "1-24" in plain
    assert "events" in plain
    assert "[#7f8794]" not in plain


def test_timeline_copy_text_uses_selection_when_present():
    text, label = _timeline_copy_text("full timeline", "selected block")

    assert text == "selected block"
    assert label == "selected text"


def test_timeline_copy_text_falls_back_to_full_timeline_without_selection():
    text, label = _timeline_copy_text("full timeline", "")

    assert text == "full timeline"
    assert label == "full timeline"


def test_timeline_text_header_documents_copy_shortcuts():
    assert "Ctrl+C/Cmd+C copy" in TIMELINE_TEXT_HEADER
    assert "Ctrl+A/Cmd+A select all" in TIMELINE_TEXT_HEADER
    assert "Esc close" in TIMELINE_TEXT_HEADER


def test_text_area_select_all_covers_full_timeline_text():
    body = TextArea("first line\nsecond line", read_only=True)

    body.select_all()

    assert body.selected_text == "first line\nsecond line"


def test_timeline_markup_is_parseable_for_bracket_heavy_content():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content="[Task Summary Memory]\ncovered_messages: 1129-1141\n[latest] should be escaped",
        )
    )

    rendered = render_timeline_lines(state, header_mode="main")

    Text.from_markup(rendered)


def test_timeline_renders_context_summarized_event():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="context_summarized",
            content="Task summary saved for messages 1-6",
        )
    )

    rendered = render_timeline_lines(state, header_mode="main")

    assert "[#7f8794][context]" in rendered
    assert "Task summary saved" in rendered
    Text.from_markup(rendered)


def test_tui_state_updates_message_context_header():
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        context_window_tokens=128_000,
        restored_message_count=3,
    )
    assert state.message_context_header.message_count == 3

    summary = MessageContextManager().analyze(
        [],
        system_prompt="system prompt",
        tools=[],
        context_window_tokens=128_000,
        total_tokens=32_000,
        token_source="exact",
    )
    state.update_message_context_header(message_count=12, summary=summary)

    assert state.message_context_header.message_count == 12
    assert state.message_context_header.total_tokens == 32_000
    assert state.message_context_header.token_source == "exact"
    assert state.message_context_header.pressure == "low"


def test_tui_brand_text_shows_message_context_summary():
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        workspace_path="/tmp/yoyoagent",
        context_window_tokens=128_000,
        restored_message_count=3,
    )
    state.update_git_header(branch="master", dirty=True, available=True)
    summary = MessageContextManager().analyze(
        [],
        system_prompt="system prompt",
        tools=[],
        context_window_tokens=128_000,
        total_tokens=32_000,
        token_source="exact",
    )
    state.update_message_context_header(message_count=12, summary=summary)

    brand = render_brand_text(state, width=140)

    assert "YYCode" in brand
    assert "" in brand
    assert "master" in brand
    assert "±" in brand
    assert "/tmp/yoyoagent" in brand
    assert "session" in brand
    assert "sess-1" in brand
    assert "msgs" in brand
    assert "12" in brand
    assert "restored" in brand
    assert "3" in brand
    assert "Ctx" in brand
    assert "32k/128k" in brand
    assert "25%" in brand
    assert "LOW" in brand
    assert "exact" in brand


def test_tui_state_updates_git_header():
    state = TuiState()

    state.update_git_header(branch="feature/top-panel", dirty=True, available=True)

    assert state.git_header.available is True
    assert state.git_header.branch == "feature/top-panel"
    assert state.git_header.dirty is True


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
            metadata={"skills": ["/plan", "plan"]},
        )
    )

    approval = state.next_pending_approval()
    assert approval is not None
    assert approval.approval_id == "edit|apply_patch|agent/tui/app.py"
    assert approval.diff_preview == "+new"
    assert state.subagents["sub-1"].role == "worker"
    assert state.subagents["sub-1"].status == "running"
    assert state.subagents["sub-1"].skills == ["plan"]

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


def test_tui_timeline_shows_subagent_explicit_skills():
    state = TuiState()
    state.apply_event(
        StreamEvent(
            source="subagent",
            session_id="sub-1",
            role="architect",
            parent_session_id="main-1",
            event_type="subagent_started",
            title="Start architect subagent",
            detail="Design plugin system",
            phase="exploring",
            status="running",
            metadata={"skills": ["plan"]},
        )
    )

    transcript = render_timeline_lines(state)

    assert "@architect" in transcript
    assert "using" in transcript
    assert "/plan" in transcript


def test_tui_timeline_shows_denied_approval_as_task_stopped():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="approval_resolved",
            title="Denied file edit",
            detail="README.md",
            status="denied",
            metadata={"approval_id": "edit_file|apply_patch|README.md"},
        )
    )

    transcript = render_timeline_lines(state)

    assert "Denied" in transcript
    assert "Task stopped because this approval was denied." in transcript
    assert "#ff8f8f" in transcript


def test_tui_renderers_show_initializing_state_before_session_ready():
    state = TuiState()

    status = render_status_text(state, width=140)
    assert "YYCode" in status
    assert "Model" in status
    assert "(initializing)" in status
    assert "Starting yoyoagent" in render_timeline_lines(state)


def test_tui_timeline_renders_config_warning():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="tui",
            session_id="sess-1",
            event_type="config_warning",
            title="Configuration required",
            content=(
                "Missing required model configuration: API_KEY, API_BASE\n"
                "Edit config file: /tmp/yycode/config.json\n"
                "Or set environment variables / .env. Priority: environment > config.json > .env > defaults.\n"
                "Empty strings in config.json are ignored."
            ),
            status="warning",
        )
    )

    transcript = render_timeline_lines(state)

    assert "[config]" in transcript
    assert "Configuration required" in transcript
    assert "Missing required model configuration: API_KEY, API_BASE" in transcript
    assert "Edit config file: /tmp/yycode/config.json" in transcript
    assert "real-secret-value" not in transcript


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

    assert "◇ Exploration" in transcript
    assert "explored 1 file" in transcript
    assert "Inspect file" in transcript
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


def test_tui_main_timeline_omits_full_task_plan_after_todo_starts():
    manager = TodoManager()
    manager.set_items(
        [
            {"id": "1", "text": "Inspect timeline rendering", "status": "completed"},
            {"id": "2", "text": "Move task plan into panel", "status": "in_progress"},
        ]
    )
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        todo_manager=manager,
    )
    state.add_user_input("sess-1", "Clean up task plan display")

    transcript = render_timeline_lines(state, header_mode="main")

    assert "You" in transcript
    assert "Clean up task plan display" in transcript
    assert "Task Plan" not in transcript
    assert "Move task plan into panel" not in transcript


def test_tui_task_plan_panel_renders_full_todo_state():
    manager = TodoManager()
    manager.set_items(
        [
            {"id": "1", "text": "Inspect timeline rendering", "status": "completed"},
            {"id": "2", "text": "Move task plan into panel", "status": "in_progress"},
            {"id": "3", "text": "Run focused tests", "status": "pending"},
        ]
    )
    manager.set_memory(
        {
            "user_goal": "Keep timeline focused on events",
            "constraints": ["Avoid duplicate task plan text", "Avoid duplicate task plan text"],
            "next_steps": [
                "Verify the TUI renderers",
                "Verify the TUI renderers",
                "Check the panel layout",
                "Run focused tests",
                "Review visual density",
                "Prepare summary",
            ],
        }
    )
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        todo_manager=manager,
    )

    panel = render_task_plan_panel(state)

    assert "Task Plan" not in panel
    assert "Goal" in panel
    assert "Checklist" in panel
    assert "1/3 done" in panel
    assert "Move task plan into panel" in panel
    assert "current" in panel
    assert "Keep timeline focused on events" in panel
    assert panel.count("Avoid duplicate task plan text") == 1
    assert "Verify the TUI renderers" in panel
    assert panel.count("Verify the TUI renderers") == 1
    assert "+1 more" in panel


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
    assert waiting.title == "Thinking"


def test_tui_timeline_renders_common_markdown_in_assistant_text():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content=(
                "## Summary\n"
                "- Updated `agent/tui/renderers.py`\n"
                "- **Tests** passed\n"
                "\n"
                "```bash\n"
                "pytest tests/test_tui_state.py -q\n"
                "```"
            ),
        )
    )

    transcript = render_timeline_lines(state)

    assert "Summary" in transcript
    assert "•" in transcript
    assert "[#9cdcfe]`agent/tui/renderers.py`[/]" in transcript
    assert "[bold #f0f2f5]Tests[/]" in transcript
    assert "code bash" in transcript
    assert "[bold #dcdcaa]pytest[/]" in transcript
    assert "tests/test_tui_state.py" in transcript
    assert "[#9cdcfe]-q[/]" in transcript
    to_content(transcript)


def test_tui_timeline_highlights_common_code_fence_languages():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content=(
                "```java\n"
                "public class Demo { return; }\n"
                "```\n"
                "```csharp\n"
                "public class Demo { return true; }\n"
                "```\n"
                "```go\n"
                "func main() { return }\n"
                "```"
            ),
        )
    )

    transcript = render_timeline_lines(state)

    assert "code java" in transcript
    assert "code csharp" in transcript
    assert "code go" in transcript
    assert "[bold #c586c0]public[/]" in transcript
    assert "[bold #c586c0]class[/]" in transcript
    assert "[bold #c586c0]func[/]" in transcript
    assert "[bold #c586c0]return[/]" in transcript
    to_content(transcript)


def test_tui_timeline_renders_plain_code_fence_without_language():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content="```\nplain text\n\n```\n```   \nmore plain text\n```",
        )
    )

    transcript = render_timeline_lines(state)

    assert "code" in transcript
    assert "plain text" in transcript
    assert "more plain text" in transcript
    to_content(transcript)


def test_tui_timeline_uses_light_markdown_while_task_is_running():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.add_user_input("sess-1", "stream markdown")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content=(
                "- Updated `agent/tui/renderers.py`\n"
                "- **Tests** passed\n"
                "```bash\n"
                "pytest tests/test_tui_state.py -q\n"
                "```"
            ),
        )
    )

    running_transcript = render_timeline_lines(state)

    assert "•" in running_transcript
    assert "`agent/tui/renderers.py`" in running_transcript
    assert "[#9cdcfe]`agent/tui/renderers.py`[/]" not in running_transcript
    assert "[bold #f0f2f5]Tests[/]" not in running_transcript
    assert "[bold #dcdcaa]pytest[/]" not in running_transcript

    state.end_active_task()
    completed_transcript = render_timeline_lines(state)

    assert "[#9cdcfe]`agent/tui/renderers.py`[/]" in completed_transcript
    assert "[bold #f0f2f5]Tests[/]" in completed_transcript
    assert "[bold #dcdcaa]pytest[/]" in completed_transcript
    to_content(completed_transcript)


def test_tui_timeline_reuses_render_cache_until_item_changes():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    item = state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content="hello `cache`",
        )
    )

    first = render_timeline_lines(state)
    first_key = item.render_cache_key
    first_rendered = item.rendered_text
    second = render_timeline_lines(state)

    assert second == first
    assert item.render_cache_key == first_key
    assert item.rendered_text is first_rendered

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="text_delta",
            content=" updated",
        )
    )
    assert item.render_cache_key is None

    updated = render_timeline_lines(state)

    assert "updated" in updated
    assert item.render_cache_key is not None


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


def test_tui_status_bar_uses_explicit_usage_labels_without_context_duplication():
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="deepseek-v4-pro",
        skills_text="drawio",
        context_window_tokens=224_000,
    )
    state.latest_usage = {"input_tokens": 230, "output_tokens": 147, "total_tokens": 377}

    status = render_status_text(state)

    assert "Context" not in status
    assert "377/224k" not in status
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
    assert "◇ Exploration" in transcript
    assert "explored 1 file" in transcript
    assert "Inspect file" in transcript
    assert "Tool call" not in transcript
    assert "Tool returned" not in transcript
    assert "42ms" in transcript


def test_tui_timeline_shows_lsp_tool_usage_explicitly():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    metadata = {"args": {"path": "agent/session.py", "line": 36, "character": 6}}
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="LSP definition",
            detail="agent/session.py · position=36:6",
            phase="semantic_navigation",
            status="running",
            tool_name="lsp_definition",
            metadata=metadata,
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="LSP definition",
            detail="agent/session.py · position=36:6",
            phase="semantic_navigation",
            status="completed",
            tool_name="lsp_definition",
            elapsed_ms=18,
            metadata=metadata,
        )
    )

    transcript = render_timeline_lines(state)

    assert "◇ Semantic Navigation" in transcript
    assert "LSP definition" in transcript
    assert "agent/session.py" in transcript
    assert "position=36:6" in transcript
    assert "18ms" in transcript


def test_tui_timeline_hides_todo_tool_return_when_task_state_result_is_present():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="Update task plan",
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
            title="Task Plan",
            content=(
                "Task State:\n"
                "----------------------------------------\n"
                "[X] [1] Inspect\n"
                "[~] [2] Patch\n"
                "Goal: keep timeline concise\n"
                "Constraints: avoid duplicate task plan output"
            ),
        )
    )

    transcript = render_timeline_lines(state)

    assert "Tool returned" not in transcript
    assert "● Plan Progress" in transcript
    assert "1/2 done" in transcript
    assert "current" not in transcript
    assert "Patch" in transcript
    assert "[Ctrl+T]" in transcript
    assert transcript.count("Plan Progress") == 1
    assert "Goal: keep timeline concise" not in transcript
    assert "Constraints:" not in transcript


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

    assert "◇ Edit" in transcript
    assert "Edited 1 file" in transcript
    assert "Edit file" in transcript
    assert "agent/tui/renderers.py" in transcript
    assert "87ms" in transcript
    assert "Apply patch" not in transcript
    assert "Review full diff" in transcript
    assert "-removed line" in transcript
    assert "+added line" in transcript
    assert "+another added line" in transcript


def test_tui_timeline_shows_changed_files_summary_after_full_diff():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    diff = "\n".join(
        [
            "diff --git a/agent/tui/app.py b/agent/tui/app.py",
            "--- a/agent/tui/app.py",
            "+++ b/agent/tui/app.py",
            "@@ -1,3 +1,4 @@",
            " keep",
            "+new app line",
            "+another app line",
            "-old app line",
            "diff --git a/agent/tui/styles.tcss b/agent/tui/styles.tcss",
            "--- a/agent/tui/styles.tcss",
            "+++ b/agent/tui/styles.tcss",
            "@@ -4,3 +4,4 @@",
            "+new style line",
            "-old style line",
            "-another old style line",
        ]
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

    assert "Review full diff" in transcript
    assert "+new app line" in transcript
    assert "-another old style line" in transcript
    assert "2 files changed" in transcript
    assert "+3" in transcript
    assert "-3" in transcript
    assert "agent/tui/app.py" in transcript
    assert "agent/tui/styles.tcss" in transcript
    assert "+2" in transcript
    assert "-1" in transcript
    assert "+1" in transcript
    assert "-2" in transcript


def test_tui_timeline_renders_end_of_task_changed_files_table():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    diff = "\n".join(
        [
            "diff --git a/agent/tui/app.py b/agent/tui/app.py",
            "--- a/agent/tui/app.py",
            "+++ b/agent/tui/app.py",
            "@@ -1,2 +1,3 @@",
            " keep",
            "+new app line",
            "-old app line",
            "diff --git a/tests/test_tui_state.py b/tests/test_tui_state.py",
            "--- a/tests/test_tui_state.py",
            "+++ b/tests/test_tui_state.py",
            "@@ -1 +1,2 @@",
            "+new test line",
        ]
    )

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="files_changed_summary",
            title="Files changed",
            content=diff,
        )
    )

    transcript = render_timeline_lines(state)

    assert "2 files changed" in transcript
    assert "+2" in transcript
    assert "-1" in transcript
    assert "Ctrl+D open changed files and diffs" in transcript
    assert "agent/tui/app.py" in transcript
    assert "tests/test_tui_state.py" in transcript


def test_tui_timeline_renders_changed_files_table_from_metadata():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="files_changed_summary",
            title="Files changed",
            content="",
            metadata={
                "files": [
                    {"path": "agent/tui/app.py", "added": 30, "removed": 4, "diff": ""},
                    {"path": "tests/test_tui_state.py", "added": 3, "removed": 1, "diff": ""},
                ]
            },
        )
    )

    transcript = render_timeline_lines(state)

    assert "2 files changed" in transcript
    assert "+33" in transcript
    assert "-5" in transcript
    assert "Ctrl+D open changed files and diffs" in transcript
    assert "agent/tui/app.py" in transcript
    assert "tests/test_tui_state.py" in transcript


def test_tui_timeline_splits_consecutive_diff_file_headers():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    diff = "\n".join(
        [
            "--- a/examples/README.md",
            "+++ b/examples/README.md",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            "--- a/examples/math_game/README.md",
            "+++ b/examples/math_game/README.md",
            "@@ -1 +1 @@",
            "-old math",
            "+new math",
            "--- a/examples/snake_game/README.md",
            "+++ b/examples/snake_game/README.md",
            "@@ -1 +1 @@",
            "-old snake",
            "+new snake",
        ]
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="files_changed_summary",
            title="Files changed",
            content=diff,
        )
    )

    transcript = render_timeline_lines(state)

    assert "3 files changed" in transcript
    assert "+3" in transcript
    assert "-3" in transcript
    assert "examples/README.md" in transcript
    assert "examples/math_game/README.md" in transcript
    assert "examples/snake_game/README.md" in transcript


def test_tui_timeline_shows_diff_preview_before_approval_request():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="drawio")
    diff = "diff --git a/docs/usage.md b/docs/usage.md\n--- a/docs/usage.md\n+++ b/docs/usage.md\n@@ -1 +1 @@\n-old\n+new"
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_result",
            title="Review diff before approval",
            content=diff,
            detail="docs/usage.md",
            status="waiting_for_user",
            tool_name="apply_patch",
            file_paths=["docs/usage.md"],
            metadata={"approval_preview": True, "diff_preview": diff},
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="approval_required",
            content="approval_required:\naction: edit_file\npath: docs/usage.md",
            title="Approve file edit",
            detail="docs/usage.md",
            status="waiting_for_user",
            tool_name="apply_patch",
            file_paths=["docs/usage.md"],
            metadata={"approval_id": "edit_file|apply_patch|docs/usage.md", "diff_preview": diff},
        )
    )

    transcript = render_timeline_lines(state)

    assert "Review full diff before approval" in transcript
    assert "Needs your approval" not in transcript
    assert "-old" in transcript
    assert "+new" in transcript
    assert "docs/usage.md" in transcript


def test_tui_status_header_uses_compact_two_column_layout():
    state = TuiState()
    state.set_startup_info(
        session_id="12345678-1234-5678-1234-567812345678",
        model_name="deepseek-reasoner-with-a-very-long-name",
        skills_text="drawio",
        workspace_path="/Users/yoyofx/Documents/github/yoyoagent",
    )

    status = render_status_text(state, width=140)

    assert "YYCode" in status
    assert "session" in status
    assert "12345678-1234-5678-1234-567812345678" in status
    assert "git -" in status
    assert "/Users/yoyofx/Documents/github/yoyoagent" in status
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


def test_tui_status_header_shows_auto_mode_badge():
    state = TuiState()
    state.set_startup_info(
        session_id="sess-1",
        model_name="gpt-test",
        skills_text="drawio",
        auto_mode=True,
    )

    status = render_brand_text(state, width=120)

    assert "Mode" not in status
    assert "AUTO" not in status
    assert "session" in status
    assert "sess-1" in status


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

    assert "Ctrl+T task plan" in transcript
    assert "Ctrl+H full history" not in transcript
    assert "◇ Exploration" in transcript
    assert "explored 1 file" in transcript
    assert "Inspect file" in transcript
    assert "Tool call" not in transcript
    assert "Tool returned" not in transcript
    assert "Review full diff" in transcript
    assert "Yoyo" not in transcript
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

    assert "explored 6 files" not in transcript
    assert "Inspect file" in transcript
    assert "agent/tui/file_5.py" in transcript
    assert "agent/tui/file_4.py" in transcript
    assert "agent/tui/file_3.py" not in transcript


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


def test_tui_timeline_formats_load_skill_input_readably():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="plan")

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Load skill",
            phase="planning",
            status="running",
            tool_name="load_skill",
            metadata={"args": {"names": ["plan", "code_workflow"]}},
        )
    )

    transcript = render_timeline_lines(state)

    plain = to_content(transcript).plain
    assert "Input names=plan, code_workflow" in plain
    assert "\\['plan'" not in transcript


def test_tui_timeline_renders_grep_search_semantically():
    state = TuiState()
    state.set_startup_info(session_id="sess-1", model_name="gpt-test", skills_text="plan")
    state.add_user_input("sess-1", "find timeline renderer")
    pattern = (
        "_render_task_state_summary|_activity_line|_detail_line|_status_badge|"
        "_render_files_changed_table|colorize_diff_for_tui|_indent_block"
    )
    metadata = {
        "args": {"pattern": pattern, "path": "agent/tui/renderers.py"},
        "search_display": "Searching agent/tui/renderers.py · 7 keywords",
        "pattern_preview": "_render_task_state_summary|_activity_line|_detail_line|_status_badge...",
        "search_terms": [
            "_render_task_state_summary",
            "_activity_line",
            "_detail_line",
            "_status_badge",
            "_render_files_changed_table",
        ],
        "term_count": 7,
        "path": "agent/tui/renderers.py",
    }

    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_start",
            title="Search code",
            detail="Searching agent/tui/renderers.py · 7 keywords",
            status="running",
            tool_name="grep",
            file_paths=["agent/tui/renderers.py"],
            metadata=metadata,
        )
    )
    state.apply_event(
        StreamEvent(
            source="main",
            session_id="sess-1",
            event_type="tool_end",
            title="Search code",
            detail="Searching agent/tui/renderers.py · 7 keywords",
            status="completed",
            tool_name="grep",
            file_paths=["agent/tui/renderers.py"],
            metadata=metadata,
            elapsed_ms=2,
        )
    )

    transcript = render_timeline_lines(state)
    plain = to_content(transcript).plain

    assert "searched 7 keywords in 1 file" in plain
    assert "Searching agent/tui/renderers.py · 7 keywords" in plain
    assert "terms: _render_task_state_summary, _activity_line, _detail_line..." in plain
    assert "2ms" in plain
    assert pattern not in plain
    assert state.active_task["current_action"] == "Searching code..."


def test_grep_tool_event_metadata_preserves_raw_pattern_and_adds_ui_summary():
    class ToolCall:
        name = "grep"
        args = {
            "pattern": "alpha|beta|gamma|delta",
            "path": ".",
        }

    event = format_tool_event_metadata(ToolCall())
    metadata = event["metadata"]

    assert metadata["args"]["pattern"] == "alpha|beta|gamma|delta"
    assert metadata["path"] == "workspace"
    assert metadata["term_count"] == 4
    assert metadata["search_terms"] == ["alpha", "beta", "gamma", "delta"]
    assert event["detail"] == "Searching workspace · 4 keywords"
