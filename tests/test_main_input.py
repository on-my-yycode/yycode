"""Tests for startup helpers and async input handling."""

import asyncio
import types
from argparse import Namespace

from agent.providers.base import ChatResponse, LLMProvider, ToolCall
from agent.approval import ApprovalRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from agent.context_compressor import ContextCompressor
from agent.task_memory import is_task_summary_memory
from agent.session_store import FileSessionStore, workspace_hash
from agent.session import (
    DOUBAO_CODE_CONTEXT_WINDOW_TOKENS,
    Session,
    infer_context_window_tokens,
    parse_context_window_tokens,
)
from agent.tui.app import _completion_context, _is_message_tokens_key_event
from main import (
    auto_approval_callback,
    build_arg_parser,
    build_prompt,
    delete_session_for_workdir,
    env_flag_enabled,
    format_startup_info,
    format_context_percent,
    format_token_count,
    format_session_updated_at,
    list_sessions_for_workdir,
    main,
    read_user_query,
    read_user_query_with_session,
    resolve_log_file_path,
    resolve_startup_workdir,
    run_agent_task,
    run_plain_loop,
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


def test_arg_parser_supports_plain_mode():
    args = build_arg_parser().parse_args(["--plain"])

    assert args.plain is True


def test_run_plain_loop_uses_console_input_and_closes_session(tmp_path, monkeypatch):
    class PlainSession:
        created = None

        def __init__(self, **kwargs):
            PlainSession.created = self
            self.id = "plain-sess"
            self.workdir = kwargs["workdir"]
            self.provider = types.SimpleNamespace(model="fake-model")
            self.skill_registry = types.SimpleNamespace(list_skills=lambda: [])
            self.restored_message_count = 0
            self.context_window_tokens = 1_000
            self.closed = False
            self.sent = []

        @classmethod
        def from_config(cls, **kwargs):
            return cls(**kwargs)

        def estimate_token_usage(self):
            return 0

        def estimate_context_window_percent(self):
            return 0

        async def send(self, query):
            self.sent.append(query)

        async def close(self):
            self.closed = True

    fake_input = FakeInput(["hello", "q"])
    monkeypatch.setattr("main.Session", PlainSession)
    args = Namespace(
        workdir=tmp_path,
        session_id=None,
        auto=True,
        temp=True,
        resume=None,
    )

    asyncio.run(run_plain_loop(args, input_func=fake_input))

    assert PlainSession.created.sent == ["hello"]
    assert PlainSession.created.closed is True


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


def test_session_resume_corrupt_store_falls_back_to_memory_only(tmp_path):
    workdir = tmp_path / "workspace"
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir.mkdir()
    app_root.mkdir()
    session_file = runtime_data_dir / "sessions" / workspace_hash(workdir) / "sess-1.json"
    session_file.parent.mkdir(parents=True)
    session_file.write_text("{not-json", encoding="utf-8")

    session = Session(
        provider=FakeProvider(),
        workdir=workdir,
        app_root=app_root,
        runtime_data_dir=runtime_data_dir,
        session_id="sess-1",
        resume=True,
    )

    assert session.messages == []
    assert session.restored_message_count == 0
    assert session.persist_messages is False
    assert session.message_store is None
    assert "not valid JSON" in session._session_persistence_warning


def test_session_save_failure_falls_back_to_memory_only(tmp_path):
    class FailingStore:
        def load(self, session_id):
            return []

        def save(self, session_id, messages, metadata=None):
            raise OSError("session directory is not writable")

        def delete(self, session_id):
            return None

        def list_sessions(self):
            return []

    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        message_store=FailingStore(),
        persist_messages=True,
    )
    session.messages = [HumanMessage(content="hello")]

    session._save_messages()

    assert session.persist_messages is False
    assert session.message_store is None
    assert "not writable" in session._session_persistence_warning


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


def test_tui_completion_context_detects_subagent_role_token():
    assert _completion_context("@arch", (0, 5)) == (
        "role",
        "arch",
        (0, 0),
        (0, 5),
    )


def test_tui_completion_context_detects_skill_token_in_existing_text():
    assert _completion_context("please use /pl to design", (0, 14)) == (
        "skill",
        "pl",
        (0, 11),
        (0, 14),
    )


def test_tui_completion_context_uses_current_line_only():
    text = "first line\n@sec"
    assert _completion_context(text, (1, 4)) == (
        "role",
        "sec",
        (1, 0),
        (1, 4),
    )


def test_tui_completion_context_ignores_plain_text_tokens():
    assert _completion_context("please use skill", (0, 10)) is None


def test_tui_message_tokens_key_event_accepts_ctrl_m_key_or_name():
    assert _is_message_tokens_key_event(types.SimpleNamespace(key="ctrl+m", name=""))
    assert _is_message_tokens_key_event(types.SimpleNamespace(key="", name="ctrl+m"))
    assert not _is_message_tokens_key_event(types.SimpleNamespace(key="m", name="m"))


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


def test_session_manual_message_compression_saves_and_emits_event(tmp_path):
    events = []

    async def collect_event(event):
        events.append(event)

    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        system_prompt="short",
        context_window_tokens=1_000,
        stream_callback=collect_event,
        runtime_data_dir=tmp_path / "runtime",
    )
    session.message_context_manager.keep_recent_messages = 1
    session.message_context_manager.min_tool_tokens = 10
    session.add_message(ToolMessage(content="x" * 4_000, tool_call_id="call-1", name="bash"))
    session.add_user_message("latest")

    compressed = asyncio.run(session.compress_message_context([0]))

    assert compressed == 1
    assert session.messages[0].additional_kwargs["context_compressed"] is True
    assert "manually compressed by Message Token Manager" in session.messages[0].content
    assert any(
        event.event_type == "context_compressed"
        and "manually compressed 1 old tool outputs" in event.content
        for event in events
    )
    assert session.message_store.load(session.id)[0].additional_kwargs["context_compressed"] is True


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


def test_session_prunes_ephemeral_context_after_completed_task(tmp_path):
    session = Session(provider=FakeProvider(), workdir=tmp_path, runtime_data_dir=tmp_path / "runtime")
    session.add_user_message("hello")
    task_start_index = len(session.messages)
    session.messages.extend(
        [
            HumanMessage(
                content="Task State is required before you can finish this user request.",
                additional_kwargs={
                    "context_ephemeral": True,
                    "ephemeral_kind": "task_guard",
                },
            ),
            AIMessage(
                content="",
                additional_kwargs={
                    "tool_calls_data": [
                        ToolCall(id="todo-1", name="todo", args={"items": []}),
                        ToolCall(id="read-1", name="read_file", args={"path": "README.md"}),
                    ]
                },
            ),
            ToolMessage(content="Task State:\n[X] done", tool_call_id="todo-1", name="todo"),
            ToolMessage(content="readme", tool_call_id="read-1", name="read_file"),
            HumanMessage(
                content="Code changes were made. Run verify with the narrowest useful target.",
                additional_kwargs={
                    "context_ephemeral": True,
                    "ephemeral_kind": "verify_reminder",
                },
            ),
            AIMessage(content="done"),
        ]
    )

    session._prune_todo_artifacts(task_start_index)

    assert not any(
        isinstance(message, ToolMessage) and message.name == "todo"
        for message in session.messages
    )
    assert not any(
        getattr(message, "additional_kwargs", {}).get("context_ephemeral")
        for message in session.messages
    )
    remaining_ai = next(
        message
        for message in session.messages
        if isinstance(message, AIMessage)
        and message.additional_kwargs.get("tool_calls_data")
    )
    tool_names = [tool_call.name for tool_call in remaining_ai.additional_kwargs["tool_calls_data"]]
    assert tool_names == ["read_file"]
    assert any(
        isinstance(message, ToolMessage) and message.name == "read_file"
        for message in session.messages
    )


def test_session_adds_summary_memory_before_pruning_completed_task(tmp_path):
    events = []

    async def capture_event(event):
        events.append(event)

    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        runtime_data_dir=tmp_path / "runtime",
        stream_callback=capture_event,
    )

    asyncio.run(session.send("hello"))

    summaries = [message for message in session.messages if is_task_summary_memory(message)]
    assert len(summaries) == 1
    summary = summaries[0]
    assert "## Current Plan" in summary.content
    assert "Handle test request" in summary.content
    assert not any(
        isinstance(message, ToolMessage) and message.name == "todo"
        for message in session.messages
    )
    assert any(event.event_type == "context_summarized" for event in events)


def test_session_collapses_completed_task_history_to_summary_memory(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        runtime_data_dir=tmp_path / "runtime",
    )

    asyncio.run(session.send("hello"))

    assert len(session.messages) == 2
    assert isinstance(session.messages[0], HumanMessage)
    assert session.messages[0].content == "hello"
    assert is_task_summary_memory(session.messages[1])
    assert not any(isinstance(message, AIMessage) for message in session.messages)
    assert not any(isinstance(message, ToolMessage) for message in session.messages)


def test_session_persists_summary_memory(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        runtime_data_dir=tmp_path / "runtime",
    )

    asyncio.run(session.send("hello"))

    restored = session.message_store.load(session.id)
    summaries = [message for message in restored if is_task_summary_memory(message)]
    assert len(summaries) == 1
    assert summaries[0].additional_kwargs["summary_memory"] is True


def test_session_merges_old_task_summaries_when_context_remains_high(tmp_path):
    events = []

    async def capture_event(event):
        events.append(event)

    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        context_window_tokens=400,
        runtime_data_dir=tmp_path / "runtime",
        stream_callback=capture_event,
    )
    session.context_compressor.keep_recent_messages = 2
    session.context_compressor.compression_ratio = 0.2
    builder = session.task_summary_memory_builder
    first = builder.build(
        [HumanMessage(content="task one"), AIMessage(content="done")],
        start_index=0,
        task_state={
            "items": [{"id": "1", "text": "task one", "status": "completed"}],
            "memory": {
                "user_goal": "task one",
                "files_modified": ["one.py"],
            },
        },
    ).to_message()
    second = builder.build(
        [HumanMessage(content="task two"), AIMessage(content="done")],
        start_index=0,
        task_state={
            "items": [{"id": "1", "text": "task two", "status": "completed"}],
            "memory": {
                "user_goal": "task two",
                "files_modified": ["two.py"],
            },
        },
    ).to_message()
    session.messages = [
        HumanMessage(content="task one"),
        first,
        HumanMessage(content="task two"),
        second,
        HumanMessage(content="latest request"),
        AIMessage(content="latest response"),
    ]

    asyncio.run(session._merge_old_task_summary_context_if_needed())

    assert len(session.messages) == 3
    assert is_task_summary_memory(session.messages[0])
    assert "source: automatic_merge" in session.messages[0].content
    assert "- task one" in session.messages[0].content
    assert "- task two" in session.messages[0].content
    assert "- one.py" in session.messages[0].content
    assert "- two.py" in session.messages[0].content
    assert session.messages[1].content == "latest request"
    assert session.messages[2].content == "latest response"
    assert any(
        event.event_type == "context_summarized"
        and "merged completed task history" in event.content
        for event in events
    )


def test_session_does_not_merge_raw_tool_chain_without_summary(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        context_window_tokens=400,
        runtime_data_dir=tmp_path / "runtime",
    )
    session.context_compressor.keep_recent_messages = 1
    session.context_compressor.compression_ratio = 0.2
    session.messages = [
        HumanMessage(content="old task"),
        AIMessage(
            content="",
            tool_calls=[{"id": "read-1", "name": "read_file", "args": {"path": "README.md"}}],
        ),
        ToolMessage(content="readme" * 200, tool_call_id="read-1", name="read_file"),
        HumanMessage(content="latest request"),
    ]

    before = list(session.messages)

    asyncio.run(session._merge_old_task_summary_context_if_needed())

    assert session.messages == before


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

    def fake_setup_logging(*, debug, log_to_file, log_file=None):
        captured["logging"] = (debug, log_to_file, log_file)

    def fake_load_dotenv(*, override):
        captured["dotenv_override"] = override

    def fake_run_tui(args):
        captured["args"] = args

    monkeypatch.setattr("main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("main.load_dotenv", fake_load_dotenv)
    monkeypatch.setattr("sys.argv", ["main.py", "-d", "-a"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fake_run_tui))

    main()

    assert captured["logging"][:2] == (True, False)
    assert captured["dotenv_override"] is True
    assert captured["args"].debug is True
    assert captured["args"].auto is True


def test_main_acp_mode_initializes_logging(monkeypatch):
    captured = {}

    def fake_setup_logging(*, debug, log_to_file, log_file=None):
        captured["logging"] = (debug, log_to_file, log_file)

    def fake_load_dotenv(*, override):
        captured["dotenv_override"] = override

    def fake_acp_main(*, auto_approve):
        captured["auto_approve"] = auto_approve

    monkeypatch.setattr("main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("main.load_dotenv", fake_load_dotenv)
    monkeypatch.setattr("sys.argv", ["main.py", "--acp", "-a", "--log-file"])
    monkeypatch.setitem(__import__("sys").modules, "agent.acp.server", types.SimpleNamespace(main=fake_acp_main))

    main()

    assert captured["logging"][:2] == (False, True)
    assert captured["logging"][2].name == "agent_debug.log"
    assert captured["logging"][2].parent.name == "logs"
    assert captured["dotenv_override"] is True
    assert captured["auto_approve"] is True


def test_resolve_log_file_path_uses_runtime_data_dir(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setenv("YOYO_RUNTIME_DATA_DIR", str(runtime_dir))

    assert resolve_log_file_path() == runtime_dir.resolve() / "logs" / "agent_debug.log"


def test_arg_parser_help_includes_examples_and_session_options():
    help_text = build_arg_parser().format_help()

    assert "Examples:" in help_text
    assert "yycode ~/project" in help_text
    assert "yycode -r bugfix-123" in help_text
    assert "-r" in help_text
    assert "--resume ID" in help_text
    assert "-s" in help_text
    assert "--sessions" in help_text
    assert "-x" in help_text
    assert "--delete" in help_text
    assert "-t" in help_text
    assert "--temp" in help_text
    assert "-a" in help_text
    assert "--auto" in help_text
    assert "--session-id" not in help_text
    assert "--list-sessions" not in help_text
    assert "--no-persist" not in help_text
    assert "--silent" not in help_text
    assert "YOYO_SESSION_DIR" in help_text
    assert "Session messages directory override." in help_text
    assert "LLM provider: anthropic or openai." in help_text


def test_arg_parser_resume_sets_session_id_for_tui(tmp_path, monkeypatch):
    captured = {}

    def fake_setup_logging(*, debug, log_to_file, log_file=None):
        captured["logging"] = (debug, log_to_file, log_file)

    def fake_load_dotenv(*, override):
        captured["dotenv_override"] = override

    def fake_run_tui(args):
        captured["args"] = args

    monkeypatch.setattr("main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("main.load_dotenv", fake_load_dotenv)
    monkeypatch.setattr("sys.argv", ["main.py", str(tmp_path), "--resume", "sess-1"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fake_run_tui))

    main()

    assert captured["args"].session_id == "sess-1"
    assert captured["args"].resume == "sess-1"


def test_list_sessions_for_workdir_outputs_saved_sessions(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    app_root.mkdir()
    workdir.mkdir()
    monkeypatch.setenv("YOYO_APP_ROOT", str(app_root))
    monkeypatch.setenv("YOYO_RUNTIME_DATA_DIR", str(runtime_data_dir))
    store = FileSessionStore(app_root=app_root, workdir=workdir, root=runtime_data_dir / "sessions")
    store.save("sess-1", [AIMessage(content="hello")])

    output = list_sessions_for_workdir(workdir)

    assert "Sessions for workspace:" in output
    assert "sess-1" in output
    assert "Workdir" in output
    assert str(workdir.resolve()) in output
    assert ".json" not in output
    assert "T03:" not in output


def test_format_session_updated_at_uses_minute_precision():
    assert format_session_updated_at("2026-02-05T03:04:59.123Z") == "2026-02-05 03:04"
    assert format_session_updated_at("not-a-date") == "not-a-date"


def test_main_list_sessions_exits_before_tui(tmp_path, monkeypatch, capsys):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    app_root.mkdir()
    workdir.mkdir()
    monkeypatch.setenv("YOYO_APP_ROOT", str(app_root))
    monkeypatch.setenv("YOYO_RUNTIME_DATA_DIR", str(runtime_data_dir))
    store = FileSessionStore(app_root=app_root, workdir=workdir, root=runtime_data_dir / "sessions")
    store.save("sess-1", [AIMessage(content="hello")])

    def fail_run_tui(args):
        raise AssertionError("TUI should not start when listing sessions")

    monkeypatch.setattr("sys.argv", ["main.py", str(workdir), "-s"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fail_run_tui))

    main()

    assert "sess-1" in capsys.readouterr().out


def test_delete_session_for_workdir_removes_saved_session(tmp_path, monkeypatch):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    app_root.mkdir()
    workdir.mkdir()
    monkeypatch.setenv("YOYO_APP_ROOT", str(app_root))
    monkeypatch.setenv("YOYO_RUNTIME_DATA_DIR", str(runtime_data_dir))
    store = FileSessionStore(app_root=app_root, workdir=workdir, root=runtime_data_dir / "sessions")
    store.save("sess-1", [AIMessage(content="hello")])

    output = delete_session_for_workdir(workdir, "sess-1")

    assert "Deleted session" in output
    assert store.load("sess-1") == []


def test_main_delete_session_exits_before_tui(tmp_path, monkeypatch, capsys):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    app_root.mkdir()
    workdir.mkdir()
    monkeypatch.setenv("YOYO_APP_ROOT", str(app_root))
    monkeypatch.setenv("YOYO_RUNTIME_DATA_DIR", str(runtime_data_dir))
    store = FileSessionStore(app_root=app_root, workdir=workdir, root=runtime_data_dir / "sessions")
    store.save("sess-1", [AIMessage(content="hello")])

    def fail_run_tui(args):
        raise AssertionError("TUI should not start when deleting sessions")

    monkeypatch.setattr("sys.argv", ["main.py", str(workdir), "-x", "sess-1"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fail_run_tui))

    main()

    assert "Deleted session" in capsys.readouterr().out
    assert store.load("sess-1") == []


def test_update_default_skills_command_syncs_and_exits(tmp_path, monkeypatch, capsys):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    (app_root / "skills").mkdir(parents=True)
    (app_root / "skills" / "plan.md").write_text("bundled plan", encoding="utf-8")
    (runtime_data_dir / "skills").mkdir(parents=True)
    (runtime_data_dir / "skills" / "plan.md").write_text("old plan", encoding="utf-8")
    (runtime_data_dir / "skills" / "custom.md").write_text("custom", encoding="utf-8")
    workdir.mkdir()
    monkeypatch.setenv("YOYO_APP_ROOT", str(app_root))
    monkeypatch.setenv("YOYO_RUNTIME_DATA_DIR", str(runtime_data_dir))

    def fail_run_tui(args):
        raise AssertionError("TUI should not start when updating skills")

    monkeypatch.setattr("sys.argv", ["main.py", str(workdir), "--update-skills"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fail_run_tui))

    main()

    output = capsys.readouterr().out
    assert "Updated yycode skills." in output
    assert "Updated: 1" in output
    assert (runtime_data_dir / "skills" / "plan.md").read_text(encoding="utf-8") == "bundled plan"
    assert (runtime_data_dir / "skills" / "custom.md").read_text(encoding="utf-8") == "custom"


def test_main_resolves_positional_workdir(tmp_path, monkeypatch):
    captured = {}

    def fake_setup_logging(*, debug, log_to_file, log_file=None):
        captured["logging"] = (debug, log_to_file, log_file)

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


def test_main_plain_mode_skips_tui(tmp_path, monkeypatch):
    captured = {}

    def fake_setup_logging(*, debug, log_to_file, log_file=None):
        captured["logging"] = (debug, log_to_file, log_file)

    def fake_load_dotenv(*, override):
        captured["dotenv_override"] = override

    async def fake_run_plain_loop(args):
        captured["args"] = args

    def fail_run_tui(args):
        raise AssertionError("TUI should not start in plain mode")

    monkeypatch.setattr("main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("main.load_dotenv", fake_load_dotenv)
    monkeypatch.setattr("main.run_plain_loop", fake_run_plain_loop)
    monkeypatch.setattr("sys.argv", ["main.py", str(tmp_path), "--plain"])
    monkeypatch.setitem(__import__("sys").modules, "agent.tui.app", types.SimpleNamespace(run_tui=fail_run_tui))

    main()

    assert captured["args"].plain is True
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
