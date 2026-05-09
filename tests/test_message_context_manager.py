"""Tests for message token analysis and manual compression."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.message_context_manager import MessageContextManager


def test_message_context_manager_keeps_system_prompt_as_context_block():
    manager = MessageContextManager(keep_recent_messages=1, min_tool_tokens=10)
    messages = [
        HumanMessage(content="hello"),
        AIMessage(content="answer"),
        ToolMessage(content="x" * 400, tool_call_id="call-1", name="read_file"),
    ]

    blocks = manager.context_blocks("system prompt", [{"name": "read_file"}])
    stats = manager.message_stats(messages)
    summary = manager.analyze(
        messages,
        system_prompt="system prompt",
        tools=[{"name": "read_file"}],
        context_window_tokens=1_000,
        total_tokens=200,
        token_source="exact",
    )

    assert [block.name for block in blocks] == ["system_prompt", "tools_schema"]
    assert [stat.index for stat in stats] == [0, 1, 2]
    assert summary.total_tokens == 200
    assert summary.token_source == "exact"
    assert summary.by_role["system_prompt"] > 0
    assert summary.by_role["user"] > 0
    assert summary.by_role["tool"] > 0


def test_message_context_manager_suggests_old_large_tool_outputs_only():
    manager = MessageContextManager(keep_recent_messages=2, min_tool_tokens=50)
    messages = [
        ToolMessage(content="x" * 1_000, tool_call_id="old", name="bash"),
        ToolMessage(
            content="[Compressed old tool output]",
            tool_call_id="compressed",
            name="bash",
            additional_kwargs={"context_compressed": True},
        ),
        HumanMessage(content="latest"),
        ToolMessage(content="x" * 1_000, tool_call_id="recent", name="bash"),
    ]

    suggestions = manager.suggest_compression(messages)

    assert len(suggestions) == 1
    assert suggestions[0].message_indexes == [0]
    assert suggestions[0].saved_tokens > 0


def test_message_context_manager_compress_selected_preserves_tool_linkage():
    manager = MessageContextManager(keep_recent_messages=1, min_tool_tokens=10)
    original = ToolMessage(content="x" * 1_000, tool_call_id="call-1", name="read_file")
    messages = [original, HumanMessage(content="latest")]

    compressed = manager.compress_selected(messages, [0])

    assert compressed[0] is not original
    assert compressed[0].tool_call_id == "call-1"
    assert compressed[0].name == "read_file"
    assert "[Compressed old tool output]" in compressed[0].content
    assert "manually compressed by Message Token Manager" in compressed[0].content
    assert compressed[0].additional_kwargs["context_compressed"] is True
    assert compressed[1] is messages[1]
