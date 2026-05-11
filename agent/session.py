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

from agent.approval import ApprovalCallback, ApprovalDenied
from agent.app_paths import resolve_app_root, resolve_runtime_data_dir
from agent.graph import build_graph
from agent.llm_retry import LLMCallError
from agent.message_format import messages_to_provider_format
from agent.message_context_manager import MessageContextManager, MessageContextSummary
from agent.lsp import shutdown_lsp_managers
from agent.providers.base import LLMProvider
from agent.providers import AnthropicProvider, OpenAIProvider
from agent.skills import SkillRegistry, parse_skill_paths
from agent.session_store import FileSessionStore, SessionStore, SessionStoreError
from agent.context_compressor import ContextCompressor
from agent.streaming import StreamEvent, StreamEventCallback, StreamPrinter
from agent.todo_manager import TodoManager
from tools import TOOLS


DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000
DOUBAO_CODE_CONTEXT_WINDOW_TOKENS = 224_000


class Session:
    """Reusable agent session with message history and streaming."""

    def __init__(
        self,
        provider: LLMProvider,
        workdir: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        skill_dirs: Optional[Iterable[str]] = None,
        stream_callback: Optional[StreamEventCallback] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        stream_printer: Optional[StreamPrinter] = None,
        todo_manager: Optional[TodoManager] = None,
        session_id: Optional[str] = None,
        context_window_tokens: Optional[int] = None,
        app_root: Optional[Path] = None,
        runtime_data_dir: Optional[Path] = None,
        persist_messages: bool = True,
        resume: bool = False,
        message_store: Optional[SessionStore] = None,
    ):
        self.id = session_id or str(uuid.uuid4())
        self.provider = provider
        self.workdir = (workdir or Path.cwd()).expanduser().resolve()
        self.app_root = resolve_app_root(app_root)
        self.runtime_data_dir = resolve_runtime_data_dir(self.app_root, runtime_data_dir)
        self.skill_dirs = self._resolve_skill_dirs(skill_dirs)
        self.skill_registry = SkillRegistry(self.workdir, self.skill_dirs)
        self.skill_catalog_prompt = self.skill_registry.format_skill_catalog_prompt()
        self.system_prompt = system_prompt or self._default_system_prompt()
        if self.skill_catalog_prompt:
            self.system_prompt = f"{self.system_prompt}\n\n{self.skill_catalog_prompt}"
        self.persist_messages = persist_messages
        self.message_store = message_store
        if self.persist_messages and self.message_store is None:
            session_root = None if os.environ.get("YOYO_SESSION_DIR") else self.runtime_data_dir / "sessions"
            self.message_store = FileSessionStore(self.app_root, self.workdir, root=session_root)
        self.messages: list[BaseMessage] = []
        if self.persist_messages and resume and self.message_store is not None:
            try:
                self.messages = self.message_store.load(self.id)
            except SessionStoreError as exc:
                self.persist_messages = False
                self.message_store = None
                self.messages = []
                if stream_callback:
                    self.stream_callback = stream_callback
                else:
                    self.stream_callback = (stream_printer or StreamPrinter()).callback
                # Defer normal callback initialization below by preserving the warning event.
                self._session_persistence_warning = str(exc)
            else:
                self._session_persistence_warning = None
        else:
            self._session_persistence_warning = None
        self.restored_message_count = len(self.messages)
        self.stream_callback = getattr(self, "stream_callback", None) or stream_callback or (stream_printer or StreamPrinter()).callback
        self.approval_callback = approval_callback
        self._graph = None
        self.todo_manager = todo_manager or TodoManager()
        self.last_usage: Optional[dict[str, int]] = None
        self.cumulative_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        self.context_window_tokens = context_window_tokens or infer_context_window_tokens(provider)
        self.context_compressor = ContextCompressor(
            context_window_tokens=self.context_window_tokens,
        )
        self.message_context_manager = MessageContextManager()

    def _resolve_skill_dirs(self, skill_dirs: Optional[Iterable[str]]) -> list[str]:
        default_dir = str(self.app_root / "skills")
        if skill_dirs is None:
            return [default_dir]
        return [default_dir, *[str(path) for path in skill_dirs]]

    def _default_system_prompt(self) -> str:
        """Get default system prompt."""
        return f"""You are a coding agent at {self.workdir}. Use tools to inspect, modify, verify, and summarize work in the shared workspace.

Task State contract:
- Every user request must be represented in Task State with the todo tool before the task can finish.
- Create todo even for simple work; if the task only has one step, create one item.
- Keep exactly one active item in_progress while work remains.
- Keep Task State memory current: user_goal, constraints, files_inspected, files_modified, decisions, test_results, open_risks, and next_steps.
- Do not provide a final answer while any todo item is pending or in_progress.
- When work and verification are complete, call todo with all items marked completed, then give the final answer.

Core workflow:
- Before the first tool call for a new user request, briefly state your understood intent and execution approach in user-facing text: goal, likely files or areas, whether you expect to edit files, and how you plan to verify. Keep this to 1-3 short sentences or 2-4 bullets.
- For simple informational requests, this intent preview can be one sentence. For risky, destructive, ambiguous, or broad changes, ask for confirmation before making changes.
- Inspect before changing. For code changes, check workspace_state and relevant git_diff first so you do not overwrite user work.
- Prefer direct execution for small local tasks; use subagents only for focused subtasks that benefit from isolation.
- For ambiguous or multi-step work, identify goal, constraints, affected files, verification path, and risks before implementation.
- Use a short execution plan, usually 1-7 concrete todo items.
- Reconcile findings against Task State after major tool results: continue, revise, delegate, verify, or stop and ask if risk appears.
- Keep user-facing updates concise; explain intent and decisions, but do not expose long internal reasoning.

Tools and editing:
- Prefer code-navigation tools: list_files, grep, read_file, read_many_files, git_show, git_diff.
- For semantic code navigation, prefer LSP tools when available: lsp_workspace_symbols, lsp_document_symbols, lsp_definition, lsp_references, lsp_hover, and lsp_diagnostics. Fall back to grep/read_file when LSP is unavailable or plain text search is more appropriate.
- Use bash for workspace inspection only when the built-in navigation tools cannot express the query.
- Use apply_patch as the primary tool for editing existing files.
- Use write_file only for brand-new files or generated artifacts.
- When using apply_patch path/old_text/new_text mode, old_text must contain only the exact lines being changed, not the whole file.
- Never rewrite an existing file wholesale to make a small edit. Read the relevant section, then patch only the minimal changed block.
- After code changes, run verify with the narrowest useful target first, then broader checks when appropriate.

Subagent delegation:
- Use subagent only for focused, bounded subtasks.
- Use explorer for investigation, architect for design, worker for implementation, tester for verification, and security for security review.
- If the user writes an explicit delegation like "@architect /plan design X", call subagent with role="architect", skills=["plan"], and task="design X" instead of loading that skill in the main context.
- Give each subagent a specific task, relevant context, expected output, and clear boundaries.
- Do not delegate small one-or-two-tool-call tasks.
- After a subagent returns, integrate its result yourself and update Task State.

Skills:
- You only have skill names and descriptions by default.
- Use list_skills to discover available local skills.
- Use load_skill to load only the specific skill instructions needed for the current task.

Safety:
- Avoid destructive commands unless explicitly requested.
- If approval is required and silent mode is not enabled, wait for user approval before retrying.
- Set approved=true only after runtime approval has allowed the specific create/edit/command operation.
- Keep changes scoped to the user request.
- If unexpected file changes appear, avoid overwriting them.

Final answer:
- Final answer is allowed only after Task State is completed.
- Keep the final answer concise: what changed, how it was verified, and any remaining risk or follow-up."""

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
        context_window_tokens: Optional[int] = None,
        approval_callback: Optional[ApprovalCallback] = None,
        app_root: Optional[Path] = None,
        runtime_data_dir: Optional[Path] = None,
        persist_messages: bool = True,
        resume: bool = False,
        message_store: Optional[SessionStore] = None,
    ) -> "Session":
        """Create a Session from configuration parameters or environment variables."""
        provider_type = (provider_type or os.environ.get("PROVIDER", "anthropic")).lower()
        api_key = api_key or os.environ.get("API_KEY", "")
        api_base = api_base or os.environ.get("API_BASE")
        context_window_tokens = context_window_tokens or parse_context_window_tokens(
            os.environ.get("YOYO_CONTEXT_WINDOW_TOKENS")
        )
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
            context_window_tokens=context_window_tokens,
            approval_callback=approval_callback,
            app_root=app_root,
            runtime_data_dir=runtime_data_dir,
            persist_messages=persist_messages,
            resume=resume,
            message_store=message_store,
        )

    async def close(self) -> None:
        """Close the session and cleanup resources."""
        self.todo_manager.clear()
        try:
            await shutdown_lsp_managers()
        except Exception as exc:
            self._session_lsp_shutdown_warning = str(exc)
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
                self.app_root,
                self.stream_callback,
                self.approval_callback,
            )
        return self._graph

    def reset(self) -> None:
        """Reset the session state."""
        self.messages = []
        self._save_messages()
        self.stream_callback = StreamPrinter().callback
        self._graph = None  # Graph needs to be rebuilt as it binds to session state
        self.todo_manager.reset()

    def clear(self) -> None:
        """Clear message history only."""
        self.messages = []
        self._save_messages()

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
        return self.estimate_messages_token_usage(self.messages)

    def estimate_messages_token_usage(self, messages: list[BaseMessage]) -> int:
        """Estimate token usage for the system prompt plus the provided messages."""
        total_chars = len(self.system_prompt)
        for message in messages:
            total_chars += self._estimate_message_chars(message)
        return math.ceil(total_chars / 4) if total_chars > 0 else 0

    async def count_context_tokens(
        self,
        messages: Optional[list[BaseMessage]] = None,
    ) -> tuple[int, bool]:
        """Count context tokens with provider support, falling back to estimation."""
        messages = self.messages if messages is None else messages
        try:
            exact = await self.provider.count_tokens(
                messages=self._messages_to_provider_format(messages),
                system_prompt=self.system_prompt,
                tools=TOOLS,
            )
        except Exception:
            exact = None
        if exact is not None:
            return exact, True
        return self.estimate_messages_token_usage(messages), False

    async def analyze_message_context(self) -> MessageContextSummary:
        """Analyze current message token pressure for user-facing management."""
        total_tokens, exact = await self.count_context_tokens()
        return self.message_context_manager.analyze(
            self.messages,
            system_prompt=self.system_prompt,
            tools=TOOLS,
            context_window_tokens=self.context_window_tokens,
            total_tokens=total_tokens,
            token_source="exact" if exact else "estimated",
        )

    async def compress_message_context(self, indexes: list[int]) -> int:
        """Manually compact selected old tool outputs and persist the session."""
        if not indexes:
            return 0
        before = self.messages
        after = self.message_context_manager.compress_selected(before, indexes)
        compressed_count = sum(1 for old, new in zip(before, after) if old is not new)
        if compressed_count == 0:
            return 0
        original_tokens, original_exact = await self.count_context_tokens(before)
        self.messages = after
        self._save_messages()
        compressed_tokens, compressed_exact = await self.count_context_tokens(after)
        token_source = "exact" if original_exact and compressed_exact else "estimated"
        if self.stream_callback:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="context_compressed",
                    content=(
                        f"manually compressed {compressed_count} old tool outputs "
                        f"({original_tokens} -> {compressed_tokens} tokens, {token_source})"
                    ),
                )
            )
        return compressed_count

    def estimate_context_window_percent(self) -> float:
        """Estimate how much of the configured context window is currently used."""
        if self.context_window_tokens <= 0:
            return 0.0
        return min((self.estimate_token_usage() / self.context_window_tokens) * 100, 999.9)

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

    def _messages_to_provider_format(self, messages: list[BaseMessage]) -> list[dict]:
        """Convert LangChain messages to the provider-neutral format used by providers."""
        return messages_to_provider_format(messages)

    async def send(self, content: str) -> AIMessage:
        """Send a user message and get response."""
        # Clear todo for new planning session
        self.todo_manager.prepare_for_new_input()
        self._graph = None  # Reset per-turn workflow and approval caches.

        self.add_user_message(content)
        await self._compress_context_if_needed()
        previous_message_count = len(self.messages)
        task_start_index = previous_message_count

        completed_normally = False
        try:
            result = await self.graph.ainvoke({"messages": self.messages})
            self.messages = result["messages"]
            completed_normally = self.todo_manager.can_finish_task()
        except ApprovalDenied as exc:
            self.messages.append(self._approval_denied_message(exc))
        except LLMCallError as exc:
            self.messages.append(self._llm_failed_message(exc))
        if completed_normally:
            self._prune_todo_artifacts(task_start_index)
        self._save_messages()
        last_msg = self.messages[-1] if self.messages else None
        self.last_usage = self._extract_usage_from_message(last_msg)
        self._accumulate_usage_from_messages(self.messages[previous_message_count:])
        return last_msg

    async def send_stream(self, content: str) -> AsyncGenerator[str, None]:
        """Send a user message and stream response text."""
        self._graph = None  # Reset per-turn workflow and approval caches.
        self.add_user_message(content)
        await self._compress_context_if_needed()
        previous_message_count = len(self.messages)
        task_start_index = previous_message_count
        completed_normally = False
        try:
            result = await self.graph.ainvoke({"messages": self.messages})
            self.messages = result["messages"]
            completed_normally = self.todo_manager.can_finish_task()
        except ApprovalDenied as exc:
            self.messages.append(self._approval_denied_message(exc))
        except LLMCallError as exc:
            self.messages.append(self._llm_failed_message(exc))
        if completed_normally:
            self._prune_todo_artifacts(task_start_index)
        self._save_messages()
        last_msg = self.messages[-1] if self.messages else None
        self.last_usage = self._extract_usage_from_message(last_msg)
        self._accumulate_usage_from_messages(self.messages[previous_message_count:])
        if last_msg and hasattr(last_msg, "content"):
            yield last_msg.content

    def _approval_denied_message(self, exc: ApprovalDenied) -> AIMessage:
        """Create a terminal assistant message when the user denies approval."""
        return AIMessage(
            content=(
                "Task stopped because the requested action was not approved.\n\n"
                f"{exc.request.format()}"
            )
        )

    def _llm_failed_message(self, exc: LLMCallError) -> AIMessage:
        """Create a terminal assistant message when model calls fail."""
        return AIMessage(
            content=(
                "Task stopped because the model did not return a usable response.\n\n"
                f"{exc}"
            )
        )

    def _prune_todo_artifacts(self, start_index: int) -> None:
        """Remove todo tool-call artifacts produced after start_index."""
        if start_index >= len(self.messages):
            return
        preserved = self.messages[:start_index]
        for message in self.messages[start_index:]:
            if self._is_ephemeral_context_message(message):
                continue
            if isinstance(message, ToolMessage) and message.name == "todo":
                continue
            if isinstance(message, AIMessage):
                filtered = self._without_todo_tool_calls(message)
                if filtered is None:
                    continue
                preserved.append(filtered)
                continue
            preserved.append(message)
        self.messages = preserved

    def _is_ephemeral_context_message(self, message: BaseMessage) -> bool:
        """Return whether a runtime-only reminder should be dropped after task completion."""
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        return bool(additional_kwargs.get("context_ephemeral"))

    def _without_todo_tool_calls(self, message: AIMessage) -> AIMessage | None:
        """Return an AIMessage with todo tool calls removed, or None if empty."""
        tool_calls = list(getattr(message, "tool_calls", []) or [])
        tool_calls_data = list(message.additional_kwargs.get("tool_calls_data") or [])
        provider_blocks = list(message.additional_kwargs.get("provider_blocks") or [])

        filtered_tool_calls = [
            tool_call for tool_call in tool_calls
            if self._tool_call_name(tool_call) != "todo"
        ]
        filtered_tool_calls_data = [
            tool_call for tool_call in tool_calls_data
            if self._tool_call_name(tool_call) != "todo"
        ]
        filtered_provider_blocks = [
            block for block in provider_blocks
            if not (isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "todo")
        ]

        had_todo = (
            len(filtered_tool_calls) != len(tool_calls)
            or len(filtered_tool_calls_data) != len(tool_calls_data)
            or len(filtered_provider_blocks) != len(provider_blocks)
        )
        if not had_todo:
            return message

        content = message.content
        if not content and not filtered_tool_calls and not filtered_tool_calls_data and not filtered_provider_blocks:
            return None

        additional_kwargs = dict(message.additional_kwargs)
        if tool_calls_data:
            if filtered_tool_calls_data:
                additional_kwargs["tool_calls_data"] = filtered_tool_calls_data
            else:
                additional_kwargs.pop("tool_calls_data", None)
        if provider_blocks:
            if filtered_provider_blocks:
                additional_kwargs["provider_blocks"] = filtered_provider_blocks
            else:
                additional_kwargs.pop("provider_blocks", None)

        return AIMessage(
            content=content,
            tool_calls=filtered_tool_calls,
            additional_kwargs=additional_kwargs,
            response_metadata=dict(getattr(message, "response_metadata", {}) or {}),
            id=getattr(message, "id", None),
            name=getattr(message, "name", None),
        )

    def _tool_call_name(self, tool_call) -> str | None:
        if isinstance(tool_call, dict):
            return tool_call.get("name")
        return getattr(tool_call, "name", None)

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

    async def _compress_context_if_needed(self) -> None:
        """Compress canonical session history before invoking the graph."""
        original_tokens, original_exact = await self.count_context_tokens()
        result = self.context_compressor.maybe_compress(
            self.messages,
            original_tokens,
            self.estimate_messages_token_usage,
        )
        if not result.did_compress:
            return

        self.messages = result.messages
        compressed_tokens, compressed_exact = await self.count_context_tokens(result.messages)
        token_source = "exact" if original_exact and compressed_exact else "estimated"
        if self.stream_callback:
            await self.stream_callback(
                StreamEvent(
                    source="main",
                    session_id=self.id,
                    event_type="context_compressed",
                    content=(
                        f"compressed {result.compressed_messages} old tool outputs "
                        f"({original_tokens} -> {compressed_tokens} tokens, {token_source})"
                    ),
                )
            )

    def _save_messages(self) -> None:
        """Persist canonical message history when configured."""
        if not self.persist_messages or self.message_store is None:
            return
        try:
            self.message_store.save(
                self.id,
                self.messages,
                metadata={"model": getattr(self.provider, "model", None)},
            )
        except (OSError, SessionStoreError) as exc:
            self.persist_messages = False
            self.message_store = None
            self._session_persistence_warning = str(exc)


def parse_context_window_tokens(value: Optional[str]) -> Optional[int]:
    """Parse an optional context window token setting."""
    if not value:
        return None
    try:
        parsed = int(value.replace("_", "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def infer_context_window_tokens(provider: LLMProvider) -> int:
    """Infer a reasonable context window from the configured provider/model."""
    model = str(getattr(provider, "model", "")).lower()
    if "doubao" in model and "code" in model:
        return DOUBAO_CODE_CONTEXT_WINDOW_TOKENS
    if "claude" in model:
        return 200_000
    if any(name in model for name in ("gpt-4o", "gpt-4.1", "gpt-5")):
        return 128_000
    return DEFAULT_CONTEXT_WINDOW_TOKENS
