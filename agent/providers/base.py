"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Callable


@dataclass
class ToolCall:
    """Represents a tool call request."""
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ChatResponse:
    """Represents a chat response from LLM."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    content_blocks: Optional[list[dict[str, Any]]] = None
    raw_response: Any = None
    usage: Optional[dict[str, int]] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: Optional[str] = None,
        stream_callback: Optional[Callable[[str, str], None]] = None,
    ) -> ChatResponse:
        """Send a chat request with tool support."""
        pass

    async def count_tokens(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> Optional[int]:
        """Return input token count when supported by the provider."""
        return None

    @abstractmethod
    async def close(self) -> None:
        """Close the provider client."""
        pass
