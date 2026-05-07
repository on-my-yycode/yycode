"""Tests for TUI runner responsiveness."""

import asyncio
from argparse import Namespace

from langchain_core.messages import AIMessage

from agent.streaming import StreamEvent
from agent.tui.runner import AgentTuiRunner
from agent.tui.state import TuiState


class SlowSession:
    """Session stub that stays busy until cancelled."""

    def __init__(self):
        self.id = "sess-1"
        self.provider = type("Provider", (), {"model": "fake-model"})()
        self.skill_registry = type("Skills", (), {"list_skills": lambda self: []})()
        self.started = asyncio.Event()

    async def send(self, text):
        self.started.set()
        await asyncio.sleep(60)

    async def close(self):
        return None


class FinalOnlySession:
    """Session stub that returns final content without streaming text deltas."""

    def __init__(self):
        self.id = "sess-1"
        self.provider = type("Provider", (), {"model": "fake-model"})()
        self.skill_registry = type("Skills", (), {"list_skills": lambda self: []})()

    async def send(self, text):
        return AIMessage(content="Final answer from model")

    async def close(self):
        return None


class TwoTurnStreamingSession:
    """Session stub that emits tool and text events for each turn."""

    def __init__(self):
        self.id = "sess-1"
        self.provider = type("Provider", (), {"model": "fake-model"})()
        self.skill_registry = type("Skills", (), {"list_skills": lambda self: []})()
        self.stream_callback = None
        self.calls = 0

    async def send(self, text):
        self.calls += 1
        if self.stream_callback is not None:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="tool_start",
                    title=f"Read file {self.calls}",
                    detail=f"turn-{self.calls}.py",
                    status="running",
                    tool_name="read_file",
                )
            )
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="tool_end",
                    title=f"Read file {self.calls}",
                    detail=f"turn-{self.calls}.py",
                    status="completed",
                    tool_name="read_file",
                )
            )
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="text_delta",
                    content=f"answer {self.calls}",
                )
            )
        return AIMessage(content=f"answer {self.calls}")

    async def close(self):
        return None


class DiffStreamingSession:
    """Session stub that emits a write diff."""

    def __init__(self):
        self.id = "sess-1"
        self.provider = type("Provider", (), {"model": "fake-model"})()
        self.skill_registry = type("Skills", (), {"list_skills": lambda self: []})()
        self.stream_callback = None

    async def send(self, text):
        if self.stream_callback is not None:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="tool_result",
                    title="Apply patch result",
                    content=(
                        "Applied patch.\n\n"
                        "diff:\n"
                        "diff --git a/agent/tui/app.py b/agent/tui/app.py\n"
                        "--- a/agent/tui/app.py\n"
                        "+++ b/agent/tui/app.py\n"
                        "@@ -1 +1,2 @@\n"
                        " old\n"
                        "+new app\n"
                        "diff --git a/tests/test_tui_state.py b/tests/test_tui_state.py\n"
                        "--- a/tests/test_tui_state.py\n"
                        "+++ b/tests/test_tui_state.py\n"
                        "@@ -1,2 +1 @@\n"
                        "-old test\n"
                        " keep\n"
                    ),
                )
            )
        return AIMessage(content="done")

    async def close(self):
        return None


class FileChangedOnlySession:
    """Session stub that emits file_changed without a diff result."""

    def __init__(self):
        self.id = "sess-1"
        self.provider = type("Provider", (), {"model": "fake-model"})()
        self.skill_registry = type("Skills", (), {"list_skills": lambda self: []})()
        self.stream_callback = None

    async def send(self, text):
        if self.stream_callback is not None:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="file_changed",
                    title="File changed",
                    content="agent/tui/app.py",
                    file_paths=["agent/tui/app.py"],
                )
            )
        return AIMessage(content="done")

    async def close(self):
        return None


class WriteToolEndOnlySession:
    """Session stub that emits only a successful write tool_end."""

    def __init__(self):
        self.id = "sess-1"
        self.provider = type("Provider", (), {"model": "fake-model"})()
        self.skill_registry = type("Skills", (), {"list_skills": lambda self: []})()
        self.stream_callback = None

    async def send(self, text):
        if self.stream_callback is not None:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="tool_end",
                    title="Apply patch",
                    detail="",
                    status="completed",
                    tool_name="apply_patch",
                    file_paths=[],
                )
            )
        return AIMessage(content="done")

    async def close(self):
        return None


def test_submit_nowait_records_user_input_before_task_finishes():
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = SlowSession()
        state.set_startup_info(session_id="sess-1", model_name="fake-model", skills_text="(none)")

        await runner.submit_nowait("hello")

        assert state.timeline[-2].event_type == "user_message"
        assert state.timeline[-2].content == "hello"
        assert state.timeline[-1].event_type == "agent_thinking"
        assert state.timeline[-1].title == "Task running"
        assert state.timeline[-1].status == "running"
        assert state.active_phase == "executing"
        assert runner.current_task is not None
        assert not runner.current_task.done()
        await runner.cancel_current_task()

    asyncio.run(run())


def test_submit_emits_final_response_when_provider_does_not_stream_text():
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = FinalOnlySession()
        state.set_startup_info(session_id="sess-1", model_name="fake-model", skills_text="(none)")

        await runner.submit("hello")

        text_items = [item for item in state.timeline if item.event_type == "text_delta"]
        assert len(text_items) == 1
        assert text_items[0].content == "Final answer from model"
        assert state.active_task["is_running"] is False
        assert state.last_task["elapsed_ms"] is not None

    asyncio.run(run())


def test_runner_emits_changed_files_summary_after_task_diff():
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = DiffStreamingSession()
        runner.session.stream_callback = runner.handle_stream_event
        state.set_startup_info(session_id="sess-1", model_name="fake-model", skills_text="(none)")

        await runner.submit("patch files")

        summary = [item for item in state.timeline if item.event_type == "files_changed_summary"]
        assert len(summary) == 1
        assert "agent/tui/app.py" in summary[0].content
        assert "tests/test_tui_state.py" in summary[0].content
        assert summary[0].metadata["files"][0]["path"] == "agent/tui/app.py"
        assert [item.path for item in state.latest_changed_file_diffs] == [
            "agent/tui/app.py",
            "tests/test_tui_state.py",
        ]
        assert state.latest_changed_file_diffs[0].added == 1
        assert state.latest_changed_file_diffs[0].removed == 0
        assert state.latest_changed_file_diffs[1].added == 0
        assert state.latest_changed_file_diffs[1].removed == 1

    asyncio.run(run())


def test_runner_falls_back_to_git_diff_for_changed_file_summary(monkeypatch):
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = FileChangedOnlySession()
        runner.session.stream_callback = runner.handle_stream_event
        state.set_startup_info(session_id="sess-1", model_name="fake-model", skills_text="(none)")

        monkeypatch.setattr(
            "agent.tui.runner.git_diff",
            lambda paths: (
                "diff --git a/agent/tui/app.py b/agent/tui/app.py\n"
                "--- a/agent/tui/app.py\n"
                "+++ b/agent/tui/app.py\n"
                "@@ -1 +1 @@\n"
                "-old\n"
                "+new\n"
            ),
        )

        await runner.submit("patch files")

        summary = [item for item in state.timeline if item.event_type == "files_changed_summary"]
        assert len(summary) == 1
        assert "agent/tui/app.py" in summary[0].content
        assert state.latest_changed_file_diffs[0].added == 1
        assert state.latest_changed_file_diffs[0].removed == 1

    asyncio.run(run())


def test_runner_falls_back_to_full_git_diff_after_successful_write_tool(monkeypatch):
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = WriteToolEndOnlySession()
        runner.session.stream_callback = runner.handle_stream_event
        state.set_startup_info(session_id="sess-1", model_name="fake-model", skills_text="(none)")

        captured = []
        monkeypatch.setattr(
            "agent.tui.runner.git_diff",
            lambda paths: captured.append(paths) or (
                "diff --git a/README.md b/README.md\n"
                "--- a/README.md\n"
                "+++ b/README.md\n"
                "@@ -1 +1 @@\n"
                "-old\n"
                "+new\n"
            ),
        )

        await runner.submit("patch files")

        summary = [item for item in state.timeline if item.event_type == "files_changed_summary"]
        assert len(summary) == 1
        assert captured == [None]
        assert state.latest_changed_file_diffs[0].path == "README.md"

    asyncio.run(run())


def test_changed_files_parser_splits_consecutive_file_headers_without_diff_git():
    from agent.tui.runner import _changed_files_from_diff

    diff = "\n".join(
        [
            "--- a/examples/README.md",
            "+++ b/examples/README.md",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            "--- a/examples/math_game/README.md",
            "+++ b/examples/math_game/README.md",
            "@@ -2 +2 @@",
            "-old math",
            "+new math",
            "--- a/examples/snake_game/README.md",
            "+++ b/examples/snake_game/README.md",
            "@@ -3 +3 @@",
            "-old snake",
            "+new snake",
        ]
    )

    files = _changed_files_from_diff(diff)

    assert [item["path"] for item in files] == [
        "examples/README.md",
        "examples/math_game/README.md",
        "examples/snake_game/README.md",
    ]
    assert sum(item["added"] for item in files) == 3
    assert sum(item["removed"] for item in files) == 3


def test_runner_keeps_second_turn_tool_and_text_events_in_timeline():
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = TwoTurnStreamingSession()
        runner.session.stream_callback = runner.handle_stream_event
        state.set_startup_info(session_id="sess-1", model_name="fake-model", skills_text="(none)")

        await runner.submit("first")
        await runner.submit("second")

        transcript = [(item.event_type, item.content or item.detail) for item in state.timeline]
        assert ("user_message", "first") in transcript
        assert ("user_message", "second") in transcript
        assert ("tool_start", "turn-1.py") in transcript
        assert ("tool_start", "turn-2.py") in transcript
        assert ("text_delta", "answer 1") in transcript
        assert ("text_delta", "answer 2") in transcript

    asyncio.run(run())
