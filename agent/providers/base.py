"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, AsyncGenerator, Callable


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
    raw_response: Any = None


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

    @abstractmethod
    async def close(self) -> None:
        """Close the provider client."""
        pass
