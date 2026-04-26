"""Tests for text-encoded tool call parsing."""

from agent.providers.text_tool_calls import (
    FUNCTION_CALL_BEGIN,
    FUNCTION_CALL_END,
    TextToolCallStreamFilter,
    parse_text_tool_calls,
)


def test_parse_text_tool_calls_extracts_tool_calls_and_cleans_content():
    content = (
        "Before\n"
        f"{FUNCTION_CALL_BEGIN}"
        '[{"name":"todo","parameters":{"items":[{"id":"1","text":"Verify","status":"in_progress"}]}}]'
        f"{FUNCTION_CALL_END}"
        "\nAfter"
    )

    cleaned, tool_calls = parse_text_tool_calls(content)

    assert cleaned == "Before\n\nAfter"
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "todo"
    assert tool_calls[0].args["items"][0]["status"] == "in_progress"


def test_parse_text_tool_calls_supports_arguments_string():
    content = (
        f"{FUNCTION_CALL_BEGIN}"
        '{"name":"bash","arguments":"{\\"command\\":\\"pwd\\"}"}'
        f"{FUNCTION_CALL_END}"
    )

    cleaned, tool_calls = parse_text_tool_calls(content)

    assert cleaned == ""
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "bash"
    assert tool_calls[0].args == {"command": "pwd"}


def test_text_tool_call_stream_filter_suppresses_split_marker_blocks():
    stream_filter = TextToolCallStreamFilter()
    chunks = [
        "hello ",
        FUNCTION_CALL_BEGIN[:5],
        FUNCTION_CALL_BEGIN[5:],
        '[{"name":"todo","parameters":{"items":[]}}]',
        FUNCTION_CALL_END[:8],
        FUNCTION_CALL_END[8:],
        " world",
    ]

    visible = []
    for chunk in chunks:
        visible.extend(stream_filter.feed(chunk))
    visible.extend(stream_filter.flush())

    output = "".join(visible)
    assert output == "hello  world"
    assert FUNCTION_CALL_BEGIN not in output
    assert FUNCTION_CALL_END not in output
