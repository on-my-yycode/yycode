"""Analyze and compact current session message token usage."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from agent.context_compressor import MANUAL_COMPRESSION_REASON, compress_tool_message


DEFAULT_KEEP_RECENT_MESSAGES = 20
DEFAULT_MIN_TOOL_TOKENS = 500
COMPACT_MARKER_TOKENS = 80

RiskLevel = Literal["low", "medium", "high"]
PressureLevel = Literal["low", "medium", "high", "critical"]
TokenSource = Literal["exact", "estimated"]


@dataclass(frozen=True)
class MessageTokenStat:
    index: int
    role: str
    message_type: str
    estimated_tokens: int
    percent: float
    preview: str
    protected: bool
    compressible: bool
    recommendation: str
    risk: RiskLevel
    context_policy: str
    ephemeral_kind: str


@dataclass(frozen=True)
class ContextBlockStat:
    name: str
    estimated_tokens: int
    protected: bool
    preview: str


@dataclass(frozen=True)
class MessageContextSummary:
    total_tokens: int
    token_source: TokenSource
    context_window_tokens: int
    remaining_tokens: int
    pressure: PressureLevel
    by_role: dict[str, int]
    by_type: dict[str, int]
    largest_messages: list[int]
    compression_savings_estimate: int


@dataclass(frozen=True)
class CompressionSuggestion:
    message_indexes: list[int]
    strategy: str
    reason: str
    original_tokens: int
    estimated_after_tokens: int
    saved_tokens: int
    risk: RiskLevel


class MessageContextManager:
    """Read-only token analysis plus deterministic old-tool compression."""

    def __init__(
        self,
        *,
        keep_recent_messages: int = DEFAULT_KEEP_RECENT_MESSAGES,
        min_tool_tokens: int = DEFAULT_MIN_TOOL_TOKENS,
    ) -> None:
        self.keep_recent_messages = keep_recent_messages
        self.min_tool_tokens = min_tool_tokens

    def analyze(
        self,
        messages: list[BaseMessage],
        *,
        system_prompt: str,
        tools: list[dict],
        context_window_tokens: int,
        total_tokens: int | None = None,
        token_source: TokenSource = "estimated",
    ) -> MessageContextSummary:
        """Return aggregate token pressure and breakdowns."""
        blocks = self.context_blocks(system_prompt, tools)
        stats = self.message_stats(messages)
        estimated_total = sum(block.estimated_tokens for block in blocks) + sum(
            stat.estimated_tokens for stat in stats
        )
        total = max(0, int(total_tokens if total_tokens is not None else estimated_total))
        by_role: dict[str, int] = {block.name: block.estimated_tokens for block in blocks}
        by_type: dict[str, int] = {block.name: block.estimated_tokens for block in blocks}
        for stat in stats:
            by_role[stat.role] = by_role.get(stat.role, 0) + stat.estimated_tokens
            by_type[stat.message_type] = by_type.get(stat.message_type, 0) + stat.estimated_tokens
        remaining = max(context_window_tokens - total, 0) if context_window_tokens > 0 else 0
        suggestions = self.suggest_compression(messages)
        return MessageContextSummary(
            total_tokens=total,
            token_source=token_source,
            context_window_tokens=max(0, int(context_window_tokens or 0)),
            remaining_tokens=remaining,
            pressure=self._pressure(total, context_window_tokens),
            by_role=by_role,
            by_type=by_type,
            largest_messages=[
                stat.index
                for stat in sorted(stats, key=lambda item: item.estimated_tokens, reverse=True)[:5]
            ],
            compression_savings_estimate=sum(item.saved_tokens for item in suggestions),
        )

    def context_blocks(self, system_prompt: str, tools: list[dict]) -> list[ContextBlockStat]:
        """Return protected non-message context blocks."""
        return [
            ContextBlockStat(
                name="system_prompt",
                estimated_tokens=_estimate_text_tokens(system_prompt),
                protected=True,
                preview=_preview(system_prompt),
            ),
            ContextBlockStat(
                name="tools_schema",
                estimated_tokens=_estimate_text_tokens(str(tools or [])),
                protected=True,
                preview=f"{len(tools or [])} tool definitions",
            ),
        ]

    def message_stats(self, messages: list[BaseMessage]) -> list[MessageTokenStat]:
        """Return per-message estimated token stats."""
        total = sum(_estimate_message_tokens(message) for message in messages)
        latest_user = self._latest_user_index(messages)
        return [
            self._message_stat(index, message, total, latest_user, len(messages))
            for index, message in enumerate(messages)
        ]

    def suggest_compression(self, messages: list[BaseMessage]) -> list[CompressionSuggestion]:
        """Suggest deterministic compression for old large tool outputs."""
        suggestions = []
        for index, message in enumerate(messages):
            if not self._is_compressible_tool(index, message, len(messages)):
                continue
            original = _estimate_message_tokens(message)
            if original < self.min_tool_tokens:
                continue
            after = min(original, COMPACT_MARKER_TOKENS)
            suggestions.append(
                CompressionSuggestion(
                    message_indexes=[index],
                    strategy="old_tool_outputs",
                    reason="old tool output outside recent message window",
                    original_tokens=original,
                    estimated_after_tokens=after,
                    saved_tokens=max(original - after, 0),
                    risk="low",
                )
            )
        return suggestions

    def compress_selected(
        self,
        messages: list[BaseMessage],
        indexes: list[int],
    ) -> list[BaseMessage]:
        """Return messages with selected compressible ToolMessages compacted."""
        selected = set(indexes)
        compressed: list[BaseMessage] = []
        for index, message in enumerate(messages):
            if index in selected and self._is_compressible_tool(index, message, len(messages)):
                compressed.append(
                    compress_tool_message(
                        message,
                        reason=MANUAL_COMPRESSION_REASON,
                        estimated_original_tokens=_estimate_message_tokens(message),
                    )
                )
            else:
                compressed.append(message)
        return compressed

    def _message_stat(
        self,
        index: int,
        message: BaseMessage,
        total_tokens: int,
        latest_user_index: int | None,
        message_count: int,
    ) -> MessageTokenStat:
        estimated = _estimate_message_tokens(message)
        compressible = self._is_compressible_tool(index, message, message_count)
        protected = index == latest_user_index or self._is_recent(index, message_count)
        if _is_compressed(message):
            recommendation = "keep compressed"
        elif compressible and estimated >= self.min_tool_tokens:
            recommendation = "compress"
        elif protected:
            recommendation = "protected"
        else:
            recommendation = "keep"
        return MessageTokenStat(
            index=index,
            role=_message_role(message),
            message_type=type(message).__name__,
            estimated_tokens=estimated,
            percent=(estimated / total_tokens * 100) if total_tokens else 0.0,
            preview=_preview(_message_content_text(message)),
            protected=protected,
            compressible=compressible,
            recommendation=recommendation,
            risk="low" if compressible else "medium",
            context_policy=_context_policy(message),
            ephemeral_kind=_ephemeral_kind(message),
        )

    def _latest_user_index(self, messages: list[BaseMessage]) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                return index
        return None

    def _is_recent(self, index: int, message_count: int) -> bool:
        return index >= max(message_count - self.keep_recent_messages, 0)

    def _is_compressible_tool(self, index: int, message: BaseMessage, message_count: int) -> bool:
        if self._is_recent(index, message_count):
            return False
        if not isinstance(message, ToolMessage):
            return False
        if _is_compressed(message):
            return False
        content = message.content
        return isinstance(content, str) and bool(content.strip())

    def _pressure(self, total_tokens: int, context_window_tokens: int) -> PressureLevel:
        if context_window_tokens <= 0:
            return "low"
        percent = total_tokens / context_window_tokens * 100
        if percent >= 90:
            return "critical"
        if percent >= 75:
            return "high"
        if percent >= 50:
            return "medium"
        return "low"


def _estimate_message_tokens(message: BaseMessage) -> int:
    total_chars = len(_message_content_text(message))
    name = getattr(message, "name", None)
    if name:
        total_chars += len(str(name))
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        total_chars += len(str(tool_call_id))
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if additional_kwargs:
        total_chars += len(str(additional_kwargs))
    return _estimate_chars_as_tokens(total_chars)


def _estimate_text_tokens(text: object) -> int:
    return _estimate_chars_as_tokens(len(str(text or "")))


def _estimate_chars_as_tokens(chars: int) -> int:
    return math.ceil(chars / 4) if chars > 0 else 0


def _message_content_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


def _message_role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, ToolMessage):
        return "tool"
    if isinstance(message, SystemMessage):
        return "system"
    return "other"


def _preview(text: object, limit: int = 120) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _is_compressed(message: BaseMessage) -> bool:
    kwargs = getattr(message, "additional_kwargs", {}) or {}
    return bool(kwargs.get("context_compressed"))


def _context_policy(message: BaseMessage) -> str:
    kwargs = getattr(message, "additional_kwargs", {}) or {}
    return str(kwargs.get("context_policy") or "full")


def _ephemeral_kind(message: BaseMessage) -> str:
    kwargs = getattr(message, "additional_kwargs", {}) or {}
    if not kwargs.get("context_ephemeral"):
        return ""
    return str(kwargs.get("ephemeral_kind") or "ephemeral")
