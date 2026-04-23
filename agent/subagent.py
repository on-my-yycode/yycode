"""Subagent runner for synchronous task delegation."""

import uuid
from pathlib import Path
from typing import Callable, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent.providers.base import LLMProvider
from agent.skills import SkillRegistry
from agent.streaming import StreamEvent, StreamEventCallback, make_provider_stream_callback
from agent.tool_retry import async_run_tool_with_retry
from tools import TOOLS


DEFAULT_MAX_TURNS = 8
MAX_OUTPUT_CHARS = 20_000


ROLE_PROMPTS = {
    "explorer": (
        "You are an explorer subagent. Your job is to investigate the requested task in "
        "the codebase and return concise, evidence-backed findings. Prefer read-only "
        "actions and cite relevant files or commands. Do not modify files unless the task "
        "explicitly asks you to."
    ),
    "architect": (
        "You are an architect subagent. Your job is to design a focused technical approach "
        "for the requested task. Analyze architecture, interfaces, data flow, tradeoffs, "
        "risks, and migration concerns. Prefer plans and recommendations over code changes "
        "unless the task explicitly asks you to edit files."
    ),
    "tester": (
        "You are a tester subagent. Your job is to design or execute verification for the "
        "requested task. Identify important test scenarios, add or update focused tests "
        "when asked, run relevant checks when possible, and report coverage, failures, and "
        "remaining risk clearly."
    ),
    "worker": (
        "You are a worker subagent. Your job is to complete the requested implementation "
        "subtask in the shared workspace. Stay tightly scoped, avoid unrelated changes, "
        "and return a concise summary of changes plus any verification you ran."
    ),
}


def filter_subagent_tool(tools: list[dict]) -> list[dict]:
    """Return tools safe for focused subagent work."""
    blocked_tools = {"subagent", "todo"}
    return [tool for tool in tools if tool.get("name") not in blocked_tools]


def build_subagent_system_prompt(
    role: str,
    workdir: Path,
    parent_prompt: str,
    skill_catalog_prompt: str = "",
) -> str:
    """Build the role-specific system prompt for a child agent."""
    role_prompt = ROLE_PROMPTS[role]
    prompt = f"""You are a delegated coding subagent at {workdir}.
{role_prompt}

Important constraints:
- Stay scoped to the assigned task and use tools only when needed.
- You have an isolated conversation history.
- Do not use todo planning; the parent agent owns overall task planning.
- Use list_skills to discover skills and load_skill to load only the skill instructions
  you need for this task.
- You must not delegate to another subagent.
- Return only the information needed by the parent agent to continue.
- Be concise: return at most 5 bullets unless the task explicitly asks for detail."""
    if skill_catalog_prompt:
        prompt = f"{prompt}\n\n{skill_catalog_prompt}"
    return prompt


def _messages_to_provider_format(messages: list[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to the provider-neutral format used by this project."""
    provider_messages = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            provider_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            provider_messages.append({"role": "assistant", "content": msg.content})
        elif isinstance(msg, ToolMessage):
            provider_messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id,
                            "content": msg.content,
                        }
                    ],
                }
            )
    return provider_messages


def format_subagent_result(
    role: str,
    session_id: str,
    hit_turn_limit: bool,
    content: str,
) -> str:
    """Format a subagent result for the parent agent."""
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS] + "\n\n[Subagent output truncated.]"

    status = "hit_turn_limit" if hit_turn_limit else "completed"
    return (
        f"Subagent result\n"
        f"role: {role}\n"
        f"session_id: {session_id}\n"
        f"status: {status}\n\n"
        f"{content}"
    )


class SubagentRunner:
    """Run isolated child agents with bounded tool loops."""

    def __init__(
        self,
        provider: LLMProvider,
        workdir: Path,
        parent_system_prompt: str,
        tool_handlers: dict[str, Callable],
        tools: Optional[list[dict]] = None,
        parent_session_id: Optional[str] = None,
        skill_dirs: Optional[list[str]] = None,
        stream_callback: Optional[StreamEventCallback] = None,
    ):
        self.provider = provider
        self.workdir = workdir
        self.parent_system_prompt = parent_system_prompt
        self.parent_session_id = parent_session_id
        self.skill_registry = SkillRegistry(workdir, skill_dirs)
        self.skill_catalog_prompt = self.skill_registry.format_skill_catalog_prompt()
        self.list_skills_handler = lambda: self.skill_registry.format_skill_list()
        self.load_skill_handler = lambda names: self.skill_registry.format_loaded_skills(names)
        self.stream_callback = stream_callback
        self.last_usage: Optional[dict[str, int]] = None
        self.tool_handlers = {
            name: handler
            for name, handler in tool_handlers.items()
            if name != "subagent"
        }
        self.tools = filter_subagent_tool(tools or TOOLS)

    async def run(
        self,
        role: str,
        task: str,
        context: str = "",
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> str:
        """Run a subagent and return a formatted summary result."""
        if role not in ROLE_PROMPTS:
            return f"Error: Unknown subagent role: {role}"

        max_turns = self._normalize_max_turns(max_turns)
        self.last_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        session_id = str(uuid.uuid4())
        provider_stream_callback = make_provider_stream_callback(
            self.stream_callback,
            source="subagent",
            session_id=session_id,
            role=role,
            parent_session_id=self.parent_session_id,
        )
        system_prompt = build_subagent_system_prompt(
            role,
            self.workdir,
            self.parent_system_prompt,
            self.skill_catalog_prompt,
        )
        prompt = self._build_user_prompt(task, context)
        messages: list[BaseMessage] = [HumanMessage(content=prompt)]
        hit_turn_limit = True

        for _ in range(max_turns):
            provider_messages = _messages_to_provider_format(messages)
            response = await self.provider.chat(
                messages=provider_messages,
                tools=self.tools,
                system_prompt=system_prompt,
                stream_callback=provider_stream_callback,
            )
            self._accumulate_usage(response.usage)
            if self.stream_callback and response.usage:
                await self.stream_callback(
                    StreamEvent(
                        source="subagent",
                        session_id=session_id,
                        role=role,
                        parent_session_id=self.parent_session_id,
                        event_type="usage",
                        usage=response.usage,
                    )
                )
            tool_calls = [
                {
                    "name": tc.name,
                    "args": tc.args,
                    "id": tc.id,
                }
                for tc in response.tool_calls
            ]
            ai_msg = AIMessage(content=response.content, tool_calls=tool_calls)
            ai_msg.additional_kwargs["tool_calls_data"] = response.tool_calls
            messages.append(ai_msg)

            if not response.tool_calls:
                hit_turn_limit = False
                break

            for tc in response.tool_calls:
                if tc.name == "list_skills":
                    handler = self.list_skills_handler
                elif tc.name == "load_skill":
                    handler = self.load_skill_handler
                else:
                    handler = self.tool_handlers.get(tc.name)
                output = await self._run_tool(handler, tc.name, **tc.args)
                messages.append(
                    ToolMessage(content=output, tool_call_id=tc.id, name=tc.name)
                )

        final_content = self._last_ai_content(messages)
        return format_subagent_result(role, session_id, hit_turn_limit, final_content)

    async def _run_tool(self, handler: Optional[Callable], tool_name: str, **kwargs) -> str:
        return await async_run_tool_with_retry(handler, tool_name, max_retries=2, **kwargs)

    def _build_user_prompt(self, task: str, context: str) -> str:
        if context:
            return f"Task:\n{task}\n\nContext:\n{context}"
        return f"Task:\n{task}"

    def _last_ai_content(self, messages: list[BaseMessage]) -> str:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return str(msg.content or "")
        return ""

    def _normalize_max_turns(self, max_turns: int) -> int:
        try:
            max_turns = int(max_turns)
        except (TypeError, ValueError):
            max_turns = DEFAULT_MAX_TURNS
        return min(max(max_turns, 1), 20)

    def _accumulate_usage(self, usage: Optional[dict[str, int]]) -> None:
        """Accumulate real provider usage across the subagent run."""
        if not usage or self.last_usage is None:
            return
        self.last_usage["input_tokens"] += usage.get("input_tokens", 0)
        self.last_usage["output_tokens"] += usage.get("output_tokens", 0)
        self.last_usage["total_tokens"] += usage.get("total_tokens", 0)
