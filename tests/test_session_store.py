"""Tests for session message persistence."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.session_store import FileSessionStore, SessionStoreError, workspace_hash


def test_file_session_store_round_trips_messages(tmp_path):
    app_root = tmp_path / "app"
    workdir = tmp_path / "workspace"
    app_root.mkdir()
    workdir.mkdir()
    store = FileSessionStore(app_root=app_root, workdir=workdir)
    messages = [
        HumanMessage(content="inspect"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call-1", "name": "read_file", "args": {"path": "README.md"}}],
            additional_kwargs={
                "provider_blocks": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "read_file",
                        "input": {"path": "README.md"},
                    }
                ]
            },
        ),
        ToolMessage(content="body", tool_call_id="call-1", name="read_file"),
    ]

    store.save("sess-1", messages, metadata={"model": "fake-model"})
    restored = store.load("sess-1")

    assert restored[0].content == "inspect"
    assert restored[1].tool_calls[0]["name"] == "read_file"
    assert restored[1].additional_kwargs["provider_blocks"][0]["id"] == "call-1"
    assert restored[2].tool_call_id == "call-1"


def test_file_session_store_groups_by_workspace_hash(tmp_path):
    app_root = tmp_path / "app"
    workdir_a = tmp_path / "a"
    workdir_b = tmp_path / "b"
    app_root.mkdir()
    workdir_a.mkdir()
    workdir_b.mkdir()

    store_a = FileSessionStore(app_root=app_root, workdir=workdir_a)
    store_b = FileSessionStore(app_root=app_root, workdir=workdir_b)
    store_a.save("same", [HumanMessage(content="a")])
    store_b.save("same", [HumanMessage(content="b")])

    assert store_a.load("same")[0].content == "a"
    assert store_b.load("same")[0].content == "b"
    assert store_a.workspace_hash == workspace_hash(workdir_a)
    assert store_b.workspace_hash == workspace_hash(workdir_b)


def test_file_session_store_rejects_workdir_mismatch(tmp_path):
    app_root = tmp_path / "app"
    workdir = tmp_path / "workspace"
    other = tmp_path / "other"
    app_root.mkdir()
    workdir.mkdir()
    other.mkdir()
    store = FileSessionStore(app_root=app_root, workdir=workdir)
    store.save("sess-1", [HumanMessage(content="hello")])
    payload_path = store.workspace_dir / "sess-1.json"
    other_store = FileSessionStore(app_root=app_root, workdir=other, root=store.root)
    other_path = other_store.workspace_dir / "sess-1.json"
    other_path.parent.mkdir(parents=True)
    other_path.write_text(payload_path.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(SessionStoreError, match="workdir mismatch"):
        other_store.load("sess-1")


def test_file_session_store_rejects_path_escape_session_id(tmp_path):
    app_root = tmp_path / "app"
    workdir = tmp_path / "workspace"
    app_root.mkdir()
    workdir.mkdir()
    store = FileSessionStore(app_root=app_root, workdir=workdir)

    with pytest.raises(SessionStoreError):
        store.save("../bad", [HumanMessage(content="hello")])
