"""Reusable Session class encapsulating agent state and streaming."""

import os
import uuid
from pathlib import Path
from typing import Optional, AsyncGenerator

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    BaseMessage,
)

from agent.graph import build_graph
from agent.providers.base import LLMProvider
from agent.providers import AnthropicProvider, OpenAIProvider
from agent.todo_manager import TodoManager


class StreamPrinter:
    """Handles streaming output with thinking display."""

    def __init__(self):
        self.in_thinking = False
        self.first_line = True

    async def callback(self, event_type: str, content: str):
        """Handle stream events."""
        if event_type == "thinking_start":
            if not self.first_line:
                print()
            print("\033[90m💭 Thinking...\033[0m", end="", flush=True)
            self.in_thinking = True
            self.first_line = False
        elif event_type == "thinking_delta":
            pass
        elif event_type == "thinking_end":
            if self.in_thinking:
                print("\033[90m [done]\033[0m", flush=True)
            self.in_thinking = False
        elif event_type == "text_delta":
            if self.in_thinking:
                print("\033[90m [done]\033[0m")
                self.in_thinking = False
            print(content, end="", flush=True)
            self.first_line = False


class Session:
    """Reusable agent session with message history and streaming."""

    def __init__(
        self,
        provider: LLMProvider,
        workdir: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        stream_printer: Optional[StreamPrinter] = None,
        todo_manager: Optional[TodoManager] = None,
        session_id: Optional[str] = None,
    ):
        self.id = session_id or str(uuid.uuid4())
        self.provider = provider
        self.workdir = workdir or Path.cwd()
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.messages: list[BaseMessage] = []
        self.stream_printer = stream_printer or StreamPrinter()
        self._graph = None
        self.todo_manager = todo_manager or TodoManager()

    def _default_system_prompt(self) -> str:
        """Get default system prompt."""
        return f"""You are a coding agent at {self.workdir}.
Use the todo tool to plan multi-step tasks. Mark in_progress before starting, completed when done.
Prefer tools over prose."""

    @classmethod
    def from_config(
        cls,
        provider_type: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        workdir: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> "Session":
        """Create a Session from configuration parameters or environment variables."""
        provider_type = (provider_type or os.environ.get("PROVIDER", "anthropic")).lower()
        api_key = api_key or os.environ.get("API_KEY", "")
        api_base = api_base or os.environ.get("API_BASE")

        if provider_type == "anthropic":
            model = model or os.environ.get("AI_MODEL", "claude-3-5-sonnet-20241022")
            provider = AnthropicProvider(
                api_key=api_key,
                model=model,
                base_url=api_base,
            )
        elif provider_type == "openai":
            model = model or os.environ.get("AI_MODEL", "gpt-4o")
            provider = OpenAIProvider(
                api_key=api_key,
                model=model,
                base_url=api_base,
            )
        else:
            raise ValueError(f"Unknown provider: {provider_type}")

        return cls(
            provider=provider,
            workdir=workdir,
            system_prompt=system_prompt,
            session_id=session_id,
        )

    async def close(self) -> None:
        """Close the session and cleanup resources."""
        self.todo_manager.clear()
        await self.provider.close()

    @property
    def graph(self):
        """Lazy build the graph."""
        if self._graph is None:
            self._graph = build_graph(
                self.provider,
                self.system_prompt,
                self.todo_manager,
                self.stream_printer.callback
            )
        return self._graph

    def reset(self) -> None:
        """Reset the session state."""
        self.messages = []
        self.stream_printer = StreamPrinter()
        self._graph = None  # Graph needs to be rebuilt as it binds to session state
        self.todo_manager.reset()

    def clear(self) -> None:
        """Clear message history only."""
        self.messages = []

    def add_message(self, message: BaseMessage) -> None:
        """Add a message to the history."""
        self.messages.append(message)

    def add_user_message(self, content: str) -> None:
        """Add a user message to the history."""
        self.add_message(HumanMessage(content=content))

    def add_ai_message(self, content: str) -> None:
        """Add an AI message to the history."""
        self.add_message(AIMessage(content=content))

    def get_history(self) -> list[BaseMessage]:
        """Get the message history."""
        return self.messages.copy()

    async def send(self, content: str) -> AIMessage:
        """Send a user message and get response."""
        # Clear todo for new planning session
        self.todo_manager.prepare_for_new_input()

        self.add_user_message(content)

        result = await self.graph.ainvoke({"messages": self.messages})
        self.messages = result["messages"]
        return self.messages[-1] if self.messages else None

    async def send_stream(self, content: str) -> AsyncGenerator[str, None]:
        """Send a user message and stream response text."""
        self.add_user_message(content)
        result = await self.graph.ainvoke({"messages": self.messages})
        self.messages = result["messages"]
        last_msg = self.messages[-1] if self.messages else None
        if last_msg and hasattr(last_msg, "content"):
            yield last_msg.content
