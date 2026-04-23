"""Reusable Session class encapsulating agent state and streaming."""

import os
import math
import uuid
from pathlib import Path
from typing import Iterable, Optional, AsyncGenerator

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    BaseMessage,
)

from agent.graph import build_graph
from agent.providers.base import LLMProvider
from agent.providers import AnthropicProvider, OpenAIProvider
from agent.skills import DEFAULT_SKILL_DIRS, SkillRegistry, parse_skill_paths
from agent.streaming import StreamEventCallback, StreamPrinter
from agent.todo_manager import TodoManager


class Session:
    """Reusable agent session with message history and streaming."""

    def __init__(
        self,
        provider: LLMProvider,
        workdir: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        skill_dirs: Optional[Iterable[str]] = None,
        stream_callback: Optional[StreamEventCallback] = None,
        stream_printer: Optional[StreamPrinter] = None,
        todo_manager: Optional[TodoManager] = None,
        session_id: Optional[str] = None,
    ):
        self.id = session_id or str(uuid.uuid4())
        self.provider = provider
        self.workdir = workdir or Path.cwd()
        self.skill_dirs = list(DEFAULT_SKILL_DIRS if skill_dirs is None else skill_dirs)
        self.skill_registry = SkillRegistry(self.workdir, self.skill_dirs)
        self.skill_catalog_prompt = self.skill_registry.format_skill_catalog_prompt()
        self.system_prompt = system_prompt or self._default_system_prompt()
        if self.skill_catalog_prompt:
            self.system_prompt = f"{self.system_prompt}\n\n{self.skill_catalog_prompt}"
        self.messages: list[BaseMessage] = []
        self.stream_callback = stream_callback or (stream_printer or StreamPrinter()).callback
        self._graph = None
        self.todo_manager = todo_manager or TodoManager()
        self.last_usage: Optional[dict[str, int]] = None
        self.cumulative_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def _default_system_prompt(self) -> str:
        """Get default system prompt."""
        return f"""You are a coding agent at {self.workdir}.

Core workflow:
- Use tools to inspect and modify the workspace instead of guessing.
- Use the todo tool for multi-step tasks. Mark one item in_progress before starting,
  and mark items completed as work finishes.
- Prefer completing simple, local tasks directly. Do not delegate tasks that are small,
  obvious, or require only one or two tool calls.

Subagent delegation:
- Use the subagent tool only for focused subtasks that benefit from isolation, such as
  codebase research, comparing implementation options, or scoped implementation work.
- Use list_skills to discover available local skills, then use load_skill to load only
  the specific skill instructions you need.
- Use the subagent tool with explorer for investigation, architect for technical design,
  worker for implementation, and tester for verification.
- Give each subagent a specific task, relevant context, expected output, and clear boundaries.
- Do not ask subagents to make broad or unrelated changes.
- After a subagent returns, integrate its result yourself and verify the final outcome
  when appropriate.

Safety:
- Avoid destructive commands unless explicitly requested.
- Keep changes scoped to the user request.
- If unexpected file changes appear, avoid overwriting them.
Prefer concise final answers with what changed and how it was verified."""

    @classmethod
    def from_config(
        cls,
        provider_type: Optional[str] = None,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        workdir: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        skill_dirs: Optional[Iterable[str]] = None,
        session_id: Optional[str] = None,
    ) -> "Session":
        """Create a Session from configuration parameters or environment variables."""
        provider_type = (provider_type or os.environ.get("PROVIDER", "anthropic")).lower()
        api_key = api_key or os.environ.get("API_KEY", "")
        api_base = api_base or os.environ.get("API_BASE")
        if skill_dirs is None:
            skill_dirs = parse_skill_paths(os.environ.get("YOYO_SKILL_DIRS")) or None

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
            skill_dirs=skill_dirs,
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
                self.workdir,
                self.id,
                self.skill_dirs,
                self.stream_callback
            )
        return self._graph

    def reset(self) -> None:
        """Reset the session state."""
        self.messages = []
        self.stream_callback = StreamPrinter().callback
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

    def estimate_token_usage(self) -> int:
        """Estimate current prompt/history token usage with a lightweight heuristic."""
        total_chars = len(self.system_prompt)
        for message in self.messages:
            total_chars += self._estimate_message_chars(message)
        return math.ceil(total_chars / 4) if total_chars > 0 else 0

    def _estimate_message_chars(self, message: BaseMessage) -> int:
        """Estimate message size from its content and basic metadata."""
        total = 0
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for item in content:
                total += len(str(item))

        name = getattr(message, "name", None)
        if name:
            total += len(str(name))

        tool_call_id = getattr(message, "tool_call_id", None)
        if tool_call_id:
            total += len(str(tool_call_id))

        additional_kwargs = getattr(message, "additional_kwargs", None)
        if additional_kwargs:
            total += len(str(additional_kwargs))

        return total

    async def send(self, content: str) -> AIMessage:
        """Send a user message and get response."""
        # Clear todo for new planning session
        self.todo_manager.prepare_for_new_input()

        self.add_user_message(content)
        previous_message_count = len(self.messages)

        result = await self.graph.ainvoke({"messages": self.messages})
        self.messages = result["messages"]
        last_msg = self.messages[-1] if self.messages else None
        self.last_usage = self._extract_usage_from_message(last_msg)
        self._accumulate_usage_from_messages(self.messages[previous_message_count:])
        return last_msg

    async def send_stream(self, content: str) -> AsyncGenerator[str, None]:
        """Send a user message and stream response text."""
        self.add_user_message(content)
        previous_message_count = len(self.messages)
        result = await self.graph.ainvoke({"messages": self.messages})
        self.messages = result["messages"]
        last_msg = self.messages[-1] if self.messages else None
        self.last_usage = self._extract_usage_from_message(last_msg)
        self._accumulate_usage_from_messages(self.messages[previous_message_count:])
        if last_msg and hasattr(last_msg, "content"):
            yield last_msg.content

    def _extract_usage_from_message(
        self,
        message: Optional[BaseMessage],
    ) -> Optional[dict[str, int]]:
        """Extract normalized usage from a message if present."""
        if message is None:
            return None
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        usage = additional_kwargs.get("usage")
        return usage if isinstance(usage, dict) else None

    def has_real_usage(self) -> bool:
        """Return whether any real API usage has been accumulated."""
        return self.cumulative_usage["total_tokens"] > 0

    def _accumulate_usage(self, usage: Optional[dict[str, int]]) -> None:
        """Accumulate normalized usage totals."""
        if not usage:
            return
        self.cumulative_usage["input_tokens"] += usage.get("input_tokens", 0)
        self.cumulative_usage["output_tokens"] += usage.get("output_tokens", 0)
        self.cumulative_usage["total_tokens"] += usage.get("total_tokens", 0)

    def _accumulate_usage_from_messages(self, messages: list[BaseMessage]) -> None:
        """Accumulate usage from all newly added messages in a graph run."""
        for message in messages:
            self._accumulate_usage(self._extract_usage_from_message(message))
