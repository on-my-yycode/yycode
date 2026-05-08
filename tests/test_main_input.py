"""Tests for startup helpers and async input handling."""

import asyncio
import types

from agent.providers.base import ChatResponse, LLMProvider, ToolCall
from agent.approval import ApprovalRequest
from langchain_core.messages import AIMessage, ToolMessage
from agent.context_compressor import ContextCompressor
from agent.session_store import FileSessionStore
from agent.session import (
    DOUBAO_CODE_CONTEXT_WINDOW_TOKENS,
    Session,
    infer_context_window_tokens,
    parse_context_window_tokens,
)
from main import (
    auto_approval_callback,
    build_prompt,
    env_flag_enabled,
    format_startup_info,
    format_context_percent,
    format_token_count,
    main,
    read_user_query,
    read_user_query_with_session,
    resolve_startup_workdir,
    run_agent_task,
)


class FakeInput:
    """Callable input replacement backed by predefined responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def __call__(self, prompt=""):
        self.prompts.append(prompt)
        return self.responses.pop(0)


class FakeProvider(LLMProvider):
    """Fake provider for session construction."""

    model = "fake-model"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        self.calls += 1
        if self.calls % 2 == 1:
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(
                        id=f"todo-{self.calls}",
                        name="todo",
                        args={
                            "items": [
                                {
                                    "id": "1",
                                    "text": "Handle test request",
                                    "status": "completed",
                                }
                            ]
                        },
                    )
                ],
            )
        return ChatResponse(
            content="",
            usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        )

    async def close(self):
        return None


class FakeCountingProvider(FakeProvider):
    """Fake provider that reports exact token counts."""

    async def count_tokens(self, messages, system_prompt=None, tools=None):
        has_compressed_output = "[Compressed old tool output]" in str(messages)
        return 100 if has_compressed_output else 900


class FakeApprovalProvider(FakeProvider):
    """Fake provider that asks for a write tool."""

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="write-1",
                    name="write_file",
                    args={"path": "new.txt", "content": "hello"},
                )
            ],
        )


class SlowSession:
    """Fake session that records task cancellation."""

    def __init__(self):
        self.cancelled = False
        self.started = asyncio.Event()

    async def send(self, query):
        try:
            self.started.set()
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def test_read_user_query_returns_single_line_input():
    fake_input = FakeInput(["hello"])

    query = asyncio.run(read_user_query(fake_input))

    assert query == "hello"
    assert len(fake_input.prompts) == 1


def test_read_user_query_supports_paste_mode():
    fake_input = FakeInput(["/paste", "line one", "line two", "/end"])

    query = asyncio.run(read_user_query(fake_input))

    assert query == "line one\nline two"
    assert len(fake_input.prompts) == 4


def test_read_user_query_supports_short_paste_command():
    fake_input = FakeInput(["/p", "line one", "line two", "/end"])

    query = asyncio.run(read_user_query(fake_input))

    assert query == "line one\nline two"
    assert len(fake_input.prompts) == 4


def test_build_prompt_includes_context_window_pressure(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="x" * 400,
        context_window_tokens=1_000,
    )
    prompt = build_prompt(session)

    assert "/1k" in prompt
    assert "%" in prompt
    assert "yoyo >>" in prompt


def test_build_prompt_uses_context_window_not_cumulative_usage(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="x" * 1_000,
        context_window_tokens=10_000,
    )
    session.cumulative_usage = {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 153_835,
    }
    prompt = build_prompt(session)

    assert "/10k" in prompt
    assert "153.8k" not in prompt


def test_read_user_query_with_session_uses_dynamic_prompt(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path, runtime_data_dir=tmp_path / "runtime")
    fake_input = FakeInput(["hello"])

    query = asyncio.run(read_user_query_with_session(session, fake_input))

    assert query == "hello"


def test_format_startup_info_includes_restored_messages(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        runtime_data_dir=tmp_path / "runtime",
        persist_messages=False,
    )
    session.restored_message_count = 3

    output = format_startup_info(session)

    assert "Restored messages: 3" in output


def test_session_resume_loads_persisted_messages(tmp_path):
    workdir = tmp_path / "workspace"
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir.mkdir()
    app_root.mkdir()
    store = FileSessionStore(app_root=app_root, workdir=workdir, root=runtime_data_dir / "sessions")
    store.save("sess-1", [AIMessage(content="old answer")])

    session = Session(
        provider=FakeProvider(),
        workdir=workdir,
        app_root=app_root,
        runtime_data_dir=runtime_data_dir,
        session_id="sess-1",
        resume=True,
    )

    assert session.restored_message_count == 1
    assert session.messages[0].content == "old answer"


def test_read_user_query_with_session_prompt_shows_context(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path, runtime_data_dir=tmp_path / "runtime")
    fake_input = FakeInput(["hello"])

    query = asyncio.run(read_user_query_with_session(session, fake_input))

    assert query == "hello"
    assert len(fake_input.prompts) == 1
    assert "/128k" in fake_input.prompts[0]
    assert "yoyo >>" in fake_input.prompts[0]


def test_run_agent_task_cancels_current_task_without_reraising():
    async def run():
        session = SlowSession()
        task = asyncio.create_task(run_agent_task(session, "long task"))
        await session.started.wait()
        task.cancel()
        result = await task
        return result, session.cancelled

    result, cancelled = asyncio.run(run())

    assert result is False
    assert cancelled is True


def test_format_token_count_supports_compact_units():
    assert format_token_count(987) == "987"
    assert format_token_count(1_000) == "1k"
    assert format_token_count(1_250) == "1.2k"
    assert format_token_count(153_835) == "153.8k"
    assert format_token_count(1_200_000) == "1.2m"


def test_format_context_percent():
    assert format_context_percent(2.45) == "2.5%"
    assert format_context_percent(10.4) == "10%"


def test_parse_context_window_tokens():
    assert parse_context_window_tokens("128000") == 128_000
    assert parse_context_window_tokens("200_000") == 200_000
    assert parse_context_window_tokens("bad") is None
    assert parse_context_window_tokens("-1") is None


def test_infer_context_window_tokens_supports_doubao_code():
    provider = FakeProvider()
    provider.model = "doubao-seed-2.0-code"

    assert infer_context_window_tokens(provider) == DOUBAO_CODE_CONTEXT_WINDOW_TOKENS


def test_session_compresses_old_tool_outputs_and_emits_event(tmp_path):
    events = []

    async def collect_event(event):
        events.append(event)

    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="short",
        context_window_tokens=1_000,
        stream_callback=collect_event,
    )
    session.context_compressor = ContextCompressor(
        context_window_tokens=1_000,
        keep_recent_messages=1,
        max_tool_chars=100,
    )
    session.add_message(ToolMessage(content="x" * 4_000, tool_call_id="call-1", name="bash"))

    asyncio.run(session.send("hello"))

    assert session.messages[0].additional_kwargs["context_compressed"] is True
    assert "[Compressed old tool output]" in session.messages[0].content
    assert any(event.event_type == "context_compressed" for event in events)


def test_session_uses_provider_token_count_for_compression(tmp_path):
    events = []

    async def collect_event(event):
        events.append(event)

    session = Session(
        provider=FakeCountingProvider(),
        workdir=tmp_path,
        system_prompt="short",
        context_window_tokens=1_000,
        stream_callback=collect_event,
    )
    session.context_compressor = ContextCompressor(
        context_window_tokens=1_000,
        keep_recent_messages=1,
        max_tool_chars=100,
    )
    session.add_message(ToolMessage(content="x" * 4_000, tool_call_id="call-1", name="bash"))

    asyncio.run(session.send("hello"))

    compression_event = next(event for event in events if event.event_type == "context_compressed")
    assert "(900 -> 100 tokens, exact)" in compression_event.content


def test_session_accumulates_real_usage(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)

    asyncio.run(session.send("hello"))
    asyncio.run(session.send("world"))

    assert session.last_usage == {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}
    assert session.cumulative_usage == {
        "input_tokens": 20,
        "output_tokens": 4,
        "total_tokens": 24,
    }


def test_session_accumulates_usage_from_tool_messages(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path)

    ai_msg = AIMessage(content="done")
    ai_msg.additional_kwargs["usage"] = {
        "input_tokens": 10,
        "output_tokens": 2,
        "total_tokens": 12,
    }
    tool_msg = ToolMessage(content="tool", tool_call_id="call-1", name="subagent")
    tool_msg.additional_kwargs["usage"] = {
        "input_tokens": 20,
        "output_tokens": 5,
        "total_tokens": 25,
    }

    session._accumulate_usage_from_messages([ai_msg, tool_msg])

    assert session.cumulative_usage == {
        "input_tokens": 30,
        "output_tokens": 7,
        "total_tokens": 37,
    }


def test_session_stops_when_approval_is_denied(tmp_path):
    approvals = []

    async def deny(request: ApprovalRequest):
        approvals.append(request)
        return False

    session = Session(
        provider=FakeApprovalProvider(),
        workdir=tmp_path,
        approval_callback=deny,
    )

    result = asyncio.run(session.send("create a file"))

    assert len(approvals) == 1
    assert approvals[0].action == "create_file"
    assert result.content.startswith("Task stopped because the requested action was not approved.")
    assert "approval_required:" in result.content
    assert not (tmp_path / "new.txt").exists()


def test_auto_approval_callback_allows_silent_mode():
    request = ApprovalRequest(
        action="edit_file",
        tool_name="apply_patch",
        path="x.py",
        reason="test",
        risk="test",
    )

    assert asyncio.run(auto_approval_callback(request)) is True


def test_env_flag_enabled_accepts_truthy_values(monkeypatch):
    monkeypatch.setenv("YOYO_SILENT", "true")

    assert env_flag_enabled("YOYO_SILENT") is True


def test_format_startup_info_includes_model_and_skills_without_prompt(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "testing.md").write_text(
        '---\nname: testing\ndescription: "Use focused tests."\n---\nSECRET PROMPT BODY'
    )
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="SECRET SYSTEM PROMPT",
        skill_dirs=["skills"],
    )

    output = format_startup_info(session)

    assert "Session ID:" in output
    assert "Model: fake-model" in output
    assert "testing" in output
    assert "SECRET SYSTEM PROMPT" not in output
    assert "SECRET PROMPT BODY" not in output


def test_main_launches_tui_on_main_thread(monkeypatch):
    captured = {}

    def fake_setup_logging(*, debug, log_to_file):
        captured["logging"] = (debug, log_to_file)

    def fake_load_dotenv(*, override):
        captured["dotenv_override"] = override

    def fake_run_tui(args):
        captured["args"] = args

    monkeypatch.setattr("main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("main.load_dotenv", fake_load_dotenv)
    monkeypatch.setattr("sys.argv", ["main.py", "--debug", "--silent"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fake_run_tui))

    main()

    assert captured["logging"] == (True, False)
    assert captured["dotenv_override"] is True
    assert captured["args"].debug is True
    assert captured["args"].silent is True


def test_main_resolves_positional_workdir(tmp_path, monkeypatch):
    captured = {}

    def fake_setup_logging(*, debug, log_to_file):
        captured["logging"] = (debug, log_to_file)

    def fake_load_dotenv(*, override):
        captured["dotenv_override"] = override

    def fake_run_tui(args):
        captured["args"] = args

    monkeypatch.setattr("main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("main.load_dotenv", fake_load_dotenv)
    monkeypatch.setattr("sys.argv", ["main.py", str(tmp_path)])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fake_run_tui))

    main()

    assert captured["args"].workdir == tmp_path.resolve()


def test_resolve_startup_workdir_defaults_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert resolve_startup_workdir(None) == tmp_path.resolve()


def test_resolve_startup_workdir_rejects_files(tmp_path):
    file_path = tmp_path / "README.md"
    file_path.write_text("not a workspace\n")

    try:
        resolve_startup_workdir(str(file_path))
    except SystemExit as exc:
        assert "workspace is not a directory" in str(exc)
    else:
        raise AssertionError("expected SystemExit")
