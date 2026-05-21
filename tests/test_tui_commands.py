"""Tests for extensible TUI commands."""

import asyncio
from argparse import Namespace
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from agent.message_context_manager import MessageContextManager
from agent.tui.app import _completion_context, _debug_tui_key_event
from agent.tui.commands import CommandRegistry, discover_commands
from agent.tui.commands.clear import COMMAND as CLEAR_COMMAND
from agent.tui.commands.help import COMMAND as HELP_COMMAND
from agent.tui.runner import AgentTuiRunner
from agent.tui.state import TuiState


class ClearableSession:
    def __init__(self):
        self.id = "sess-1"
        self.messages = [HumanMessage(content="hello")]
        self.system_prompt = "system"
        self.message_context_manager = MessageContextManager()
        self.clear_calls = 0
        self.send_calls = 0

    async def analyze_message_context(self):
        return self.message_context_manager.analyze(
            self.messages,
            system_prompt=self.system_prompt,
            tools=[],
            context_window_tokens=1_000,
        )

    def clear(self):
        self.clear_calls += 1
        self.messages = []

    async def send(self, text):
        self.send_calls += 1


def test_command_registry_discovers_per_file_commands():
    registry = discover_commands()
    names = [command.name for command in registry.list_commands()]

    assert "clear" in names
    assert "help" in names
    assert registry.get("?").name == "help"
    assert [command.name for command in registry.matching("cl")] == ["clear"]
    parsed = registry.parse(":clear!")
    assert parsed is not None
    assert parsed.command.name == "clear"
    assert parsed.confirmed is True


def test_command_registry_rejects_duplicate_names():
    registry = CommandRegistry([CLEAR_COMMAND])

    try:
        registry.register(CLEAR_COMMAND)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("duplicate command should fail")


def test_completion_context_detects_colon_commands():
    context = _completion_context(":cl", (0, 3))

    assert context is not None
    assert context[0] == "command"
    assert context[1] == "cl"


def test_tui_key_debug_disabled_by_default(tmp_path, monkeypatch):
    log_path = tmp_path / "keys.log"
    monkeypatch.delenv("YOYO_TUI_DEBUG_KEYS", raising=False)
    monkeypatch.setenv("YOYO_TUI_DEBUG_KEYS_FILE", str(log_path))

    _debug_tui_key_event(
        SimpleNamespace(key="a", name="a", character="a", aliases=["a"]),
        SimpleNamespace(id="prompt-input"),
        "received",
    )

    assert not log_path.exists()


def test_tui_key_debug_writes_key_event(tmp_path, monkeypatch):
    log_path = tmp_path / "keys.log"
    monkeypatch.setenv("YOYO_TUI_DEBUG_KEYS", "1")
    monkeypatch.setenv("YOYO_TUI_DEBUG_KEYS_FILE", str(log_path))

    _debug_tui_key_event(
        SimpleNamespace(key="unknown", name="unknown", character="你", aliases=["unknown"]),
        SimpleNamespace(id="prompt-input"),
        "received",
    )

    output = log_path.read_text(encoding="utf-8")
    assert "phase='received'" in output
    assert "focused_id='prompt-input'" in output
    assert "character='你'" in output
    assert "U+4F60" in output


def test_help_command_renders_single_page_usage_guide():
    async def run():
        registry = CommandRegistry([CLEAR_COMMAND, HELP_COMMAND])
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = ClearableSession()

        result = await runner.execute_command(":help anything", registry)

        assert result.title == "YOYOAGENT Help"
        assert "YOYOAGENT Help" in result.content
        assert "TUI Commands" in result.content
        assert ":clear" in result.content
        assert ":clear!" in result.content
        assert "Keyboard Shortcuts" in result.content
        assert "Ctrl+Enter" in result.content
        assert "Ctrl+Q" in result.content
        assert "Ctrl+T" in result.content
        assert "Ctrl+D" in result.content
        assert "Ctrl+M" in result.content
        assert "Input Completion" in result.content
        assert "Timeline Navigation" in result.content
        assert "PageUp/PageDown" in result.content
        assert "Home/End" in result.content
        assert "Subagents" in result.content
        assert "@role" in result.content
        assert "Skills" in result.content
        assert "/skill-name" in result.content
        assert "Startup Arguments" in result.content
        assert "yoyoagent [WORKDIR] [options]" in result.content
        assert "--resume ID" in result.content
        assert "--sessions" in result.content
        assert "--list-sessions" in result.content
        assert "--no-persist" in result.content
        assert "--delete ID" in result.content
        assert "No command named" not in result.content
        assert state.timeline[-1].event_type == "command_result"

    asyncio.run(run())


def test_clear_command_requires_confirmation_and_does_not_send_to_llm():
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = ClearableSession()
        registry = CommandRegistry([CLEAR_COMMAND, HELP_COMMAND])

        result = await runner.execute_command(":clear", registry)

        assert result.status == "waiting_for_confirmation"
        assert runner.session.clear_calls == 0
        assert runner.session.send_calls == 0
        assert runner.session.messages
        assert state.timeline[-1].event_type == "command_result"

    asyncio.run(run())


def test_clear_confirmed_command_clears_session_and_view():
    async def run():
        state = TuiState()
        state.set_startup_info(session_id="sess-1", model_name="fake", skills_text="(none)", context_window_tokens=1_000)
        state.add_user_input("sess-1", "old prompt")
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = ClearableSession()
        registry = CommandRegistry([CLEAR_COMMAND, HELP_COMMAND])

        result = await runner.execute_command(":clear!", registry)

        assert result.status == "completed"
        assert runner.session.clear_calls == 1
        assert runner.session.send_calls == 0
        assert runner.session.messages == []
        assert state.message_context_header.message_count == 0
        assert [item.event_type for item in state.timeline] == ["command_result"]
        assert state.timeline[0].title == "Session cleared"

    asyncio.run(run())


def test_unknown_command_returns_warning():
    async def run():
        state = TuiState()
        runner = AgentTuiRunner(Namespace(silent=False), state=state)
        runner.session = ClearableSession()
        registry = CommandRegistry([CLEAR_COMMAND])

        result = await runner.execute_command(":missing", registry)

        assert result.severity == "warning"
        assert "Unknown command" in result.content
        assert runner.session.send_calls == 0

    asyncio.run(run())
