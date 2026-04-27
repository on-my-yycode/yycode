"""Tests for structured stream event serialization."""

from agent.streaming import StreamEvent
from agent.runtime.tool_events import file_paths_for_tool_call


class _ToolCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


def test_stream_event_serializes_timeline_fields():
    event = StreamEvent(
        source="main",
        session_id="session-1",
        event_type="tool_start",
        content="read_file: agent/session.py",
        title="Read file",
        detail="agent/session.py",
        phase="exploring",
        status="running",
        tool_name="read_file",
        file_paths=["agent/session.py"],
        elapsed_ms=12,
        metadata={"path": "agent/session.py"},
    )

    assert event.to_dict() == {
        "source": "main",
        "session_id": "session-1",
        "role": None,
        "parent_session_id": None,
        "event_type": "tool_start",
        "content": "read_file: agent/session.py",
        "usage": None,
        "title": "Read file",
        "detail": "agent/session.py",
        "phase": "exploring",
        "status": "running",
        "tool_name": "read_file",
        "file_paths": ["agent/session.py"],
        "elapsed_ms": 12,
        "metadata": {"path": "agent/session.py"},
    }


def test_file_paths_for_tool_call_extracts_unified_diff_paths():
    tool_call = _ToolCall(
        "apply_patch",
        {
            "patch": "\n".join(
                [
                    "diff --git a/agent/a.py b/agent/a.py",
                    "--- a/agent/a.py",
                    "+++ b/agent/a.py",
                    "@@ -1 +1 @@",
                    "-old",
                    "+new",
                ]
            )
        },
    )

    assert file_paths_for_tool_call(tool_call) == ["agent/a.py"]
