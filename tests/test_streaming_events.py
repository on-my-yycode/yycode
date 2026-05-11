"""Tests for structured stream event serialization."""

from agent.streaming import StreamEvent
from agent.runtime.tool_events import file_paths_for_tool_call, format_tool_event_metadata


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


def test_format_tool_event_metadata_identifies_drawio_export_commands():
    tool_call = _ToolCall(
        "bash",
        {
            "command": (
                "draw.io -x -f png -e -s 2 "
                "-o docs/diagram.drawio.png docs/diagram.drawio"
            )
        },
    )

    metadata = format_tool_event_metadata(tool_call)

    assert metadata["title"] == "Export draw.io diagram"
    assert metadata["phase"] == "implementing"
    assert metadata["tool_name"] == "bash"


def test_format_tool_event_metadata_identifies_lsp_tools():
    tool_call = _ToolCall(
        "lsp_definition",
        {"path": "agent/session.py", "line": 36, "character": 6},
    )

    metadata = format_tool_event_metadata(tool_call)

    assert metadata["title"] == "LSP definition"
    assert metadata["detail"] == "agent/session.py · position=36:6"
    assert metadata["phase"] == "semantic_navigation"
    assert metadata["tool_name"] == "lsp_definition"
    assert metadata["file_paths"] == ["agent/session.py"]


def test_stream_event_serializes_waiting_metadata():
    event = StreamEvent(
        source="main",
        session_id="session-1",
        event_type="llm_waiting",
        content="waiting for model response... 15s elapsed",
        title="Waiting for model response",
        detail="Attempt 1/11, 15s since last token",
        phase="waiting",
        status="running",
        elapsed_ms=15000,
        metadata={"attempt": 1, "attempts": 11},
    )

    payload = event.to_dict()

    assert payload["title"] == "Waiting for model response"
    assert payload["phase"] == "waiting"
    assert payload["elapsed_ms"] == 15000
    assert payload["metadata"] == {"attempt": 1, "attempts": 11}
