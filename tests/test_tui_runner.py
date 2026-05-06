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
