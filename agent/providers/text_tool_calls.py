"""Parse text-encoded tool calls emitted by some OpenAI-compatible models."""

import json
import re
from typing import Any

from agent.providers.base import ToolCall


FUNCTION_CALL_BEGIN = "<|FunctionCallBegin|>"
FUNCTION_CALL_END = "<|FunctionCallEnd|>"

_TEXT_TOOL_CALL_RE = re.compile(
    rf"{re.escape(FUNCTION_CALL_BEGIN)}(.*?){re.escape(FUNCTION_CALL_END)}",
    re.DOTALL,
)


def parse_text_tool_calls(content: str) -> tuple[str, list[ToolCall]]:
    """Extract text-encoded tool calls and return cleaned assistant text."""
    tool_calls: list[ToolCall] = []

    for index, match in enumerate(_TEXT_TOOL_CALL_RE.finditer(content)):
        payload = match.group(1).strip()
        for call_index, item in enumerate(_load_call_items(payload)):
            name = item.get("name")
            if not name:
                continue
            args = _extract_args(item)
            tool_calls.append(
                ToolCall(
                    id=f"text-tool-{index}-{call_index}",
                    name=str(name),
                    args=args,
                )
            )

    cleaned = _TEXT_TOOL_CALL_RE.sub("", content).strip()
    return cleaned, tool_calls


def _load_call_items(payload: str) -> list[dict[str, Any]]:
    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if isinstance(loaded, dict):
        return [loaded]
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    return []


def _extract_args(item: dict[str, Any]) -> dict[str, Any]:
    args = (
        item.get("parameters")
        or item.get("arguments")
        or item.get("args")
        or item.get("input")
        or {}
    )
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return {}
    return args if isinstance(args, dict) else {}


class TextToolCallStreamFilter:
    """Suppress text-encoded tool call blocks from streamed text deltas."""

    def __init__(self):
        self.buffer = ""

    def feed(self, chunk: str) -> list[str]:
        """Return safe chunks that can be shown to the user."""
        self.buffer += chunk
        output: list[str] = []

        while self.buffer:
            begin = self.buffer.find(FUNCTION_CALL_BEGIN)
            if begin >= 0:
                if begin > 0:
                    output.append(self.buffer[:begin])
                end = self.buffer.find(FUNCTION_CALL_END, begin)
                if end < 0:
                    self.buffer = self.buffer[begin:]
                    break
                self.buffer = self.buffer[end + len(FUNCTION_CALL_END):]
                continue

            keep = self._partial_begin_suffix_len(self.buffer)
            if keep:
                output.append(self.buffer[:-keep])
                self.buffer = self.buffer[-keep:]
                break

            output.append(self.buffer)
            self.buffer = ""

        return [text for text in output if text]

    def flush(self) -> list[str]:
        """Flush remaining safe text at stream end."""
        if self.buffer.startswith(FUNCTION_CALL_BEGIN):
            self.buffer = ""
            return []
        output = [self.buffer] if self.buffer else []
        self.buffer = ""
        return output

    def _partial_begin_suffix_len(self, text: str) -> int:
        max_len = min(len(text), len(FUNCTION_CALL_BEGIN) - 1)
        for length in range(max_len, 0, -1):
            if FUNCTION_CALL_BEGIN.startswith(text[-length:]):
                return length
        return 0
