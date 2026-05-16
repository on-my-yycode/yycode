"""Tests for the ACP stdio server and adapters."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from agent.acp.approval_adapter import AcpApprovalAdapter
from agent.acp.content_adapter import content_blocks_to_text
from agent.acp.jsonrpc import decode_message, encode, response
from agent.acp.server import AcpServer
from agent.acp.session_manager import AcpSessionManager
from agent.acp.update_adapter import replay_event_to_updates, stream_event_to_updates
from agent.approval import ApprovalRequest
from agent.providers.base import ChatResponse, LLMProvider
from agent.session import Session
from agent.streaming import StreamEvent


class FakeProvider(LLMProvider):
    """Fake provider for ACP tests."""

    model = "fake-model"

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        if stream_callback:
            await stream_callback("text_delta", "hello")
        return ChatResponse(content="hello")

    async def close(self):
        return None


class FakeSession:
    """Small session double for ACP manager tests."""

    def __init__(self, workdir: Path, session_id: str = "fake-session", resume: bool = False):
        self.id = session_id
        self.workdir = workdir
        self.approval_callback = None
        self.stream_callback = None
        self._graph = None
        self.todo_manager = None
        self.skill_registry = _FakeSkillRegistry()
        self.sent_prompts = []
        self.messages = [HumanMessage(content="old"), AIMessage(content="answer")] if resume else []

    async def send(self, content: str):
        self.sent_prompts.append(content)
        if self.stream_callback:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="text_delta",
                    content="hello",
                )
            )
        return AIMessage(content="hello")

    def replay_view(self):
        session = Session(
            provider=FakeProvider(),
            workdir=self.workdir,
            persist_messages=False,
            stream_callback=None,
        )
        session.messages = self.messages
        return session.replay_view()

    async def close(self):
        return None


class _FakeSkillRegistry:
    def list_skills(self):
        return []


def test_jsonrpc_decodes_request_and_encodes_compact_response():
    message = decode_message('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')

    assert message.method == "initialize"
    assert message.is_request is True
    assert encode(response({"ok": True}, 1)) == '{"jsonrpc":"2.0","id":1,"result":{"ok":true}}'


def test_content_blocks_to_text_supports_text_and_embedded_context():
    text = content_blocks_to_text(
        [
            {"type": "text", "text": "Fix bug"},
            {"type": "resource_link", "name": "file", "uri": "file:///tmp/app.py"},
            {"type": "embedded_resource", "uri": "file:///tmp/log.txt", "text": "trace"},
        ]
    )

    assert "Fix bug" in text
    assert "Context resource: file" in text
    assert "file:///tmp/app.py" in text
    assert "Embedded context resource: file:///tmp/log.txt" in text
    assert "trace" in text


def test_stream_event_to_updates_maps_text_and_tool_events(tmp_path):
    text_updates = stream_event_to_updates(
        StreamEvent(source="main", session_id="s", event_type="text_delta", content="hi")
    )
    tool_updates = stream_event_to_updates(
        StreamEvent(
            source="main",
            session_id="s",
            event_type="tool_start",
            title="Search code",
            detail="Searching workspace",
            status="running",
            tool_name="grep",
            file_paths=["agent/session.py"],
            metadata={"args": {"pattern": "Session"}},
        ),
        workdir=tmp_path,
    )

    assert text_updates[0]["sessionUpdate"] == "agent_message_chunk"
    assert text_updates[0]["content"] == "hi"
    assert tool_updates[0]["sessionUpdate"] == "tool_call"
    assert tool_updates[0]["kind"] == "search"
    assert tool_updates[0]["locations"][0]["path"] == str(tmp_path / "agent/session.py")
    assert tool_updates[0]["rawInput"] == {"pattern": "Session"}


def test_replay_event_to_updates_uses_session_replay(tmp_path):
    session = Session(
        provider=FakeProvider(),
        workdir=tmp_path,
        persist_messages=False,
        stream_callback=None,
    )
    session.messages = [HumanMessage(content="hello"), AIMessage(content="answer")]

    updates = []
    for event in session.replay_view():
        updates.extend(replay_event_to_updates(event))

    assert [update["sessionUpdate"] for update in updates] == [
        "user_message_chunk",
        "agent_message_chunk",
    ]


def test_acp_approval_adapter_converts_permission_response(tmp_path):
    captured = {}

    async def requester(method, params):
        captured["method"] = method
        captured["params"] = params
        return {"optionId": "approve"}

    adapter = AcpApprovalAdapter("s", requester, workdir=tmp_path)
    request = ApprovalRequest(
        action="edit_file",
        tool_name="apply_patch",
        reason="edits files",
        risk="may overwrite work",
        path="agent/session.py",
    )

    approved = asyncio.run(adapter.callback(request))

    assert approved is True
    assert captured["method"] == "session/request_permission"
    assert captured["params"]["toolCall"]["kind"] == "edit"
    assert captured["params"]["toolCall"]["locations"][0]["path"] == str(tmp_path / "agent/session.py")


def test_acp_server_initialize_writes_jsonrpc_response():
    output = io.StringIO()
    server = AcpServer(stdin=io.StringIO(), stdout=output, stderr=io.StringIO())

    asyncio.run(server.handle_line('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'))

    payload = json.loads(output.getvalue())
    assert payload["id"] == 1
    assert payload["result"]["agentInfo"]["name"] == "yoyoagent"
    assert payload["result"]["agentCapabilities"]["loadSession"] is True


def test_acp_session_manager_new_prompt_cancel_and_load(tmp_path, monkeypatch):
    notifications = []
    requests = []

    async def notify(method, params):
        notifications.append((method, params))

    async def request_client(method, params):
        requests.append((method, params))
        return {"optionId": "approve"}

    manager = AcpSessionManager(notify, request_client)

    def fake_create_session(cwd: Path, *, session_id=None, resume=False):
        return FakeSession(cwd, session_id=session_id or "fake-session", resume=resume)

    monkeypatch.setattr(manager, "_create_session", fake_create_session)

    new_result = asyncio.run(manager.new_session({"cwd": str(tmp_path)}))
    prompt_result = asyncio.run(
        manager.prompt({"sessionId": new_result["sessionId"], "content": [{"type": "text", "text": "hi"}]})
    )
    cancel_result = asyncio.run(manager.cancel({"sessionId": new_result["sessionId"]}))
    load_result = asyncio.run(manager.load_session({"cwd": str(tmp_path), "sessionId": "loaded"}))

    assert prompt_result == {"stopReason": "end_turn"}
    assert cancel_result["status"] == "not_running"
    assert load_result == {"sessionId": "loaded"}
    assert any(item[0] == "session/update" for item in notifications)
    assert any(
        params["update"]["sessionUpdate"] == "agent_message_chunk"
        for method, params in notifications
        if method == "session/update"
    )


def test_acp_session_manager_auto_approve_skips_permission_request(tmp_path, monkeypatch):
    requests = []

    async def notify(_method, _params):
        return None

    async def request_client(method, params):
        requests.append((method, params))
        return {"optionId": "reject"}

    manager = AcpSessionManager(notify, request_client, auto_approve=True)

    def fake_create_session(cwd: Path, *, session_id=None, resume=False):
        return FakeSession(cwd, session_id=session_id or "fake-session", resume=resume)

    monkeypatch.setattr(manager, "_create_session", fake_create_session)

    new_result = asyncio.run(manager.new_session({"cwd": str(tmp_path)}))
    managed = manager.sessions[new_result["sessionId"]]
    approved = asyncio.run(
        managed.session.approval_callback(
            ApprovalRequest(
                action="edit_file",
                tool_name="apply_patch",
                reason="edits files",
                risk="may overwrite work",
                path="agent/session.py",
            )
        )
    )

    assert approved is True
    assert requests == []
