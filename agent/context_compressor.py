"""Lightweight context compression for long-running sessions."""

from dataclasses import dataclass

from langchain_core.messages import BaseMessage, ToolMessage


DEFAULT_COMPRESSION_RATIO = 0.7
DEFAULT_KEEP_RECENT_MESSAGES = 20
DEFAULT_MAX_TOOL_CHARS = 2_000
AUTO_COMPRESSION_REASON = "context window usage crossed the compression threshold."
MANUAL_COMPRESSION_REASON = "manually compressed by Message Token Manager."


@dataclass(frozen=True)
class CompressionResult:
    """Result of a context compression pass."""

    messages: list[BaseMessage]
    did_compress: bool
    original_tokens: int
    compressed_tokens: int
    compressed_messages: int


class ContextCompressor:
    """Conservative compressor that trims old tool outputs."""

    def __init__(
        self,
        *,
        context_window_tokens: int,
        compression_ratio: float = DEFAULT_COMPRESSION_RATIO,
        keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
        max_tool_chars: int = DEFAULT_MAX_TOOL_CHARS,
    ):
        self.context_window_tokens = context_window_tokens
        self.compression_ratio = compression_ratio
        self.keep_recent_messages = keep_recent_messages
        self.max_tool_chars = max_tool_chars

    def maybe_compress(
        self,
        messages: list[BaseMessage],
        estimated_tokens: int,
        estimate_tokens,
    ) -> CompressionResult:
        """Compress old tool outputs when context usage crosses the threshold."""
        if estimated_tokens < self.threshold_tokens:
            return CompressionResult(messages, False, estimated_tokens, estimated_tokens, 0)

        compressed_messages = []
        compressed_count = 0
        cutoff = max(len(messages) - self.keep_recent_messages, 0)
        for index, message in enumerate(messages):
            if index < cutoff and self._should_trim_tool_message(message):
                compressed_messages.append(self._trim_tool_message(message))
                compressed_count += 1
            else:
                compressed_messages.append(message)

        if compressed_count == 0:
            return CompressionResult(messages, False, estimated_tokens, estimated_tokens, 0)

        compressed_tokens = estimate_tokens(compressed_messages)
        return CompressionResult(
            compressed_messages,
            compressed_tokens < estimated_tokens,
            estimated_tokens,
            compressed_tokens,
            compressed_count,
        )

    @property
    def threshold_tokens(self) -> int:
        """Token threshold that triggers compression."""
        return int(self.context_window_tokens * self.compression_ratio)

    def _should_trim_tool_message(self, message: BaseMessage) -> bool:
        if not isinstance(message, ToolMessage):
            return False
        content = message.content
        return isinstance(content, str) and len(content) > self.max_tool_chars

    def _trim_tool_message(self, message: ToolMessage) -> ToolMessage:
        return compress_tool_message(message, reason=AUTO_COMPRESSION_REASON)


def compress_tool_message(
    message: ToolMessage,
    *,
    reason: str,
    estimated_original_tokens: int | None = None,
) -> ToolMessage:
    """Return a compact marker ToolMessage while preserving tool linkage."""
    original_chars = len(str(message.content))
    name = message.name or "unknown"
    lines = [
        "[Compressed old tool output]",
        f"tool: {name}",
        f"original_chars: {original_chars}",
    ]
    if estimated_original_tokens is not None:
        lines.append(f"estimated_original_tokens: {estimated_original_tokens}")
    lines.append(f"reason: {reason}")
    trimmed = ToolMessage(
        content="\n".join(lines),
        tool_call_id=message.tool_call_id,
        name=message.name,
    )
    trimmed.additional_kwargs.update(getattr(message, "additional_kwargs", {}) or {})
    trimmed.additional_kwargs["context_compressed"] = True
    trimmed.additional_kwargs["original_chars"] = original_chars
    if estimated_original_tokens is not None:
        trimmed.additional_kwargs["estimated_original_tokens"] = estimated_original_tokens
    return trimmed
