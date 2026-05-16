"""Subagent runner for synchronous task delegation."""

import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent.approval import ApprovalCallback, ApprovalTargetMissing
from agent.llm_retry import chat_with_retry
from agent.logger import get_logger
from agent.message_format import messages_to_provider_format
from agent.providers.base import LLMProvider
from agent.runtime.approval_service import ApprovalService
from agent.runtime.context import AgentRuntimeContext, WorkflowState
from agent.runtime.tool_output import build_tool_output_view
from agent.runtime.tool_scheduler import execute_tool_calls
from agent.skills import LoadedSkill, SkillRegistry
from agent.streaming import StreamEvent, StreamEventCallback, make_provider_stream_callback
from agent.todo_manager import TodoManager
from tools import TOOLS


DEFAULT_MAX_TURNS = 30
MAX_OUTPUT_CHARS = 20_000
SUBAGENT_TOOL_TIMEOUT_SECONDS = 3600  # 1 hour for subagent tools
SUBAGENT_TOOL_RETRIES = 2
logger = get_logger(__name__)


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
    "security": (
        "You are a security subagent. Your job is to review code and changes for security "
        "risks. Look for unsafe input handling, injection paths, secret exposure, auth or "
        "permission flaws, insecure file/network operations, dependency risks, and unsafe "
        "command execution. Prefer read-only review unless explicitly asked to edit files, "
        "and report findings with severity, evidence, and concrete remediation."
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
    loaded_skills_prompt: str = "",
) -> str:
    """Build the role-specific system prompt for a child agent."""
    role_prompt = ROLE_PROMPTS[role]
    prompt = f"""You are a delegated coding subagent at {workdir}.
{role_prompt}

Important constraints:
- Stay scoped to the assigned task and use tools only when needed.
- You have an isolated conversation history.
- Do not use todo planning; the parent agent owns overall task planning.
- For semantic code navigation, prefer LSP tools when available:
  lsp_workspace_symbols, lsp_document_symbols, lsp_definition, lsp_references,
  lsp_hover, and lsp_diagnostics. Fall back to grep/read_file when LSP is
  unavailable, returns no_results, or plain text search is more appropriate.
- LSP line and character inputs are zero-based. Model-facing locations are
  displayed as one-based file:line:character.
- Use list_skills to discover skills and load_skill to load only the skill instructions
  you need for this task.
- You must not delegate to another subagent.
- Return only the information needed by the parent agent to continue.
- Be concise: return at most 5 bullets unless the task explicitly asks for detail."""
    if skill_catalog_prompt:
        prompt = f"{prompt}\n\n{skill_catalog_prompt}"
    if loaded_skills_prompt:
        prompt = f"{prompt}\n\n{loaded_skills_prompt}"
    return prompt

def format_subagent_result(
    role: str,
    session_id: str,
    hit_turn_limit: bool,
    content: str,
    skills: Optional[list[str]] = None,
) -> str:
    """Format a subagent result for the parent agent."""
    if len(content) > MAX_OUTPUT_CHARS:
        content = content[:MAX_OUTPUT_CHARS] + "\n\n[Subagent output truncated.]"

    status = "hit_turn_limit" if hit_turn_limit else "completed"
    return (
        f"Subagent result\n"
        f"role: {role}\n"
        f"skills: {', '.join(skills) if skills else 'none'}\n"
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
        app_root: Path | None = None,
        stream_callback: Optional[StreamEventCallback] = None,
        approval_callback: Optional[ApprovalCallback] = None,
    ):
        self.provider = provider
        self.workdir = workdir
        self.app_root = app_root
        self.parent_system_prompt = parent_system_prompt
        self.parent_session_id = parent_session_id
        self.skill_dirs = skill_dirs
        self.skill_registry = SkillRegistry(workdir, skill_dirs)
        self.skill_catalog_prompt = self.skill_registry.format_skill_catalog_prompt()
        self.list_skills_handler = lambda: self.skill_registry.format_skill_list()
        self.load_skill_handler = lambda names: self.skill_registry.format_loaded_skills(names)
        self.stream_callback = stream_callback
        self.approval_callback = approval_callback
        self.last_usage: Optional[dict[str, int]] = None
        self.workflow_state = WorkflowState()
        self._active_session_id: Optional[str] = None
        self._active_role: Optional[str] = None
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
        skills: Optional[list[str]] = None,
    ) -> str:
        """Run a subagent and return a formatted summary result."""
        if role not in ROLE_PROMPTS:
            return f"Error: Unknown subagent role: {role}"
        explicit_skills = self._normalize_skills(skills)
        loaded_skills = self._load_explicit_skills(explicit_skills)
        if isinstance(loaded_skills, str):
            return loaded_skills

        max_turns = self._normalize_max_turns(max_turns)
        self.last_usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        self.workflow_state = WorkflowState()
        session_id = str(uuid.uuid4())
        self._active_session_id = session_id
        self._active_role = role
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
            self._format_explicit_skills_prompt(loaded_skills),
        )
        prompt = self._build_user_prompt(task, context, explicit_skills)
        messages: list[BaseMessage] = [HumanMessage(content=prompt)]
        hit_turn_limit = True
        start_time = time.perf_counter()
        await self._emit_subagent_started(session_id, role, task, explicit_skills)

        try:
            for _ in range(max_turns):
                provider_messages = messages_to_provider_format(messages)
                response = await chat_with_retry(
                    self.provider,
                    messages=provider_messages,
                    tools=self.tools,
                    system_prompt=system_prompt,
                    stream_callback=provider_stream_callback,
                    event_callback=self.stream_callback,
                    source="subagent",
                    session_id=session_id,
                    role=role,
                    parent_session_id=self.parent_session_id,
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
                        "args": dict(tc.args or {}),
                        "id": tc.id,
                    }
                    for tc in response.tool_calls
                ]
                ai_msg = AIMessage(content=response.content, tool_calls=tool_calls)
                ai_msg.additional_kwargs["tool_calls_data"] = response.tool_calls
                if response.content_blocks:
                    ai_msg.additional_kwargs["provider_blocks"] = response.content_blocks
                messages.append(ai_msg)

                if not response.tool_calls:
                    hit_turn_limit = False
                    break

                tool_messages = await self._run_tool_calls(response.tool_calls, session_id, role)
                messages.extend(tool_messages)
        except Exception:
            await self._emit_subagent_finished(
                session_id,
                role,
                task,
                "failed",
                int((time.perf_counter() - start_time) * 1000),
                explicit_skills,
            )
            self._active_session_id = None
            self._active_role = None
            raise

        if hit_turn_limit:
            try:
                await self._synthesize_after_turn_limit(
                    messages,
                    system_prompt,
                    provider_stream_callback,
                    session_id,
                    role,
                )
            except Exception as exc:
                logger.debug("Subagent turn-limit synthesis failed; falling back to tool output: %s", exc)
        final_content = self._final_content(messages)
        status = "hit_turn_limit" if hit_turn_limit else "completed"
        await self._emit_subagent_finished(
            session_id,
            role,
            task,
            status,
            int((time.perf_counter() - start_time) * 1000),
            explicit_skills,
        )
        result = format_subagent_result(role, session_id, hit_turn_limit, final_content, explicit_skills)
        self._active_session_id = None
        self._active_role = None
        return result

    async def _run_tool_calls(self, tool_calls, session_id: str, role: str) -> list[ToolMessage]:
        """Execute subagent tool calls through shared runtime registry/scheduler/approval."""
        from agent.runtime.tool_registry import RuntimeToolRegistry

        runtime = AgentRuntimeContext(
            provider=self.provider,
            system_prompt=self.parent_system_prompt,
            todo_manager=TodoManager(),
            workdir=self.workdir,
            session_id=session_id,
            source="subagent",
            role=role,
            parent_session_id=self.parent_session_id,
            skill_dirs=self.skill_dirs,
            app_root=self.app_root,
            stream_callback=self.stream_callback,
            approval_callback=self.approval_callback,
            tools=self.tools,
            tool_handlers=self.tool_handlers,
            workflow_state=self.workflow_state,
            run_tool=self._run_runtime_tool,
        )
        registry = RuntimeToolRegistry(runtime)
        approval_service = ApprovalService(
            self.approval_callback,
            self.workflow_state,
            self.stream_callback,
            session_id,
            source="subagent",
            role=role,
            parent_session_id=self.parent_session_id,
            workdir=self.workdir,
        )

        async def execute(tc) -> ToolMessage:
            return await self._execute_tool_call(tc, registry, approval_service)

        return await execute_tool_calls(tool_calls, execute, registry.can_run_concurrently)

    async def _execute_tool_call(
        self,
        tc,
        registry,
        approval_service: ApprovalService,
    ) -> ToolMessage:
        handler = registry.resolve(tc.name)
        try:
            approved_args = await approval_service.approve(tc.name, tc.args or {})
        except ApprovalTargetMissing as exc:
            await self._emit_tool_blocked(tc.name, str(exc))
            return self._tool_message(tc, str(exc))
        output = await self._run_runtime_tool(
            handler,
            tc.name,
            max_retries=SUBAGENT_TOOL_RETRIES,
            timeout_seconds=registry.timeout_for(tc.name),
            **approved_args,
        )
        output_view = build_tool_output_view(tc.name, output, tc)
        tool_message = self._tool_message(tc, output_view.model)
        if output_view.context_policy != "full":
            tool_message.additional_kwargs["context_policy"] = output_view.context_policy
        return tool_message

    async def _run_runtime_tool(self, handler: Optional[Callable], tool_name: str, **kwargs) -> str:
        from agent.tool_retry import async_run_tool_with_retry

        return await async_run_tool_with_retry(
            handler,
            tool_name,
            max_retries=kwargs.pop("max_retries", SUBAGENT_TOOL_RETRIES),
            timeout_seconds=kwargs.pop("timeout_seconds", SUBAGENT_TOOL_TIMEOUT_SECONDS),
            **kwargs,
        )

    def _tool_message(self, tc, output: str) -> ToolMessage:
        return ToolMessage(content=output, tool_call_id=tc.id, name=tc.name)

    async def _synthesize_after_turn_limit(
        self,
        messages: list[BaseMessage],
        system_prompt: str,
        provider_stream_callback,
        session_id: str,
        role: str,
    ) -> None:
        """Ask for a final no-tool summary after the delegated tool budget is exhausted."""
        messages.append(
            HumanMessage(
                content=(
                    "You have reached the delegated tool-turn limit. Do not call any tools. "
                    "Based only on the information already gathered in this subagent conversation, "
                    "return a concise final summary for the parent agent. Include key findings, "
                    "evidence, and any remaining uncertainty."
                )
            )
        )
        response = await chat_with_retry(
            self.provider,
            messages=messages_to_provider_format(messages),
            tools=[],
            system_prompt=system_prompt,
            stream_callback=provider_stream_callback,
            event_callback=self.stream_callback,
            source="subagent",
            session_id=session_id,
            role=role,
            parent_session_id=self.parent_session_id,
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
        ai_msg = AIMessage(content=response.content)
        if response.content_blocks:
            ai_msg.additional_kwargs["provider_blocks"] = response.content_blocks
        messages.append(ai_msg)

    async def _emit_tool_blocked(self, tool_name: str, content: str) -> None:
        if self.stream_callback is None:
            return
        await self.stream_callback(
            StreamEvent(
                source="subagent",
                session_id=self._active_session_id or "",
                role=self._active_role,
                parent_session_id=self.parent_session_id,
                event_type="tool_result",
                content=content,
                title="File edit blocked",
                detail="No target file detected",
                phase="blocked",
                status="failed",
                tool_name=tool_name,
            )
        )

    def _build_user_prompt(self, task: str, context: str, skills: list[str] | None = None) -> str:
        explicit = ""
        if skills:
            explicit = "Explicit skills:\n" + "\n".join(f"- {skill}" for skill in skills) + "\n\n"
        if context:
            return f"{explicit}Task:\n{task}\n\nContext:\n{context}"
        return f"{explicit}Task:\n{task}"

    def _normalize_skills(self, skills: Optional[list[str]]) -> list[str]:
        normalized: list[str] = []
        for skill in skills or []:
            name = str(skill).strip()
            if name.startswith("/"):
                name = name[1:]
            if name and name not in normalized:
                normalized.append(name)
        return normalized

    def _load_explicit_skills(self, skills: list[str]) -> list[LoadedSkill] | str:
        if not skills:
            return []
        loaded = self.skill_registry.load_skills(skills)
        loaded_names = {skill.name for skill in loaded}
        missing = [skill for skill in skills if skill not in loaded_names]
        if not missing:
            return loaded
        available = ", ".join(skill.name for skill in self.skill_registry.list_skills()) or "(none)"
        return (
            f"Error: Unknown skill: /{missing[0]}\n"
            f"Available skills: {available}"
        )

    def _format_explicit_skills_prompt(self, skills: list[LoadedSkill]) -> str:
        if not skills:
            return ""
        sections = [
            "Explicit skills selected by the parent:",
            *[f"- {skill.name}" for skill in skills],
            "",
            "Loaded skill instructions:",
        ]
        for skill in skills:
            sections.append("")
            sections.append(f"## {skill.name}")
            sections.append(f"Source: {skill.path}")
            if skill.description:
                sections.append(f"Description: {skill.description}")
            sections.append("")
            sections.append(skill.content)
        sections.append("")
        sections.append("You must follow the loaded skill instructions for this delegated task.")
        sections.append("If a selected skill is not suitable for the task, mention that in your result.")
        return "\n".join(sections).rstrip()

    def _last_ai_content(self, messages: list[BaseMessage]) -> str:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return str(msg.content or "")
        return ""

    def _final_content(self, messages: list[BaseMessage]) -> str:
        content = self._last_ai_content(messages).strip()
        if content:
            return content
        tool_outputs = [
            str(msg.content or "").strip()
            for msg in messages
            if isinstance(msg, ToolMessage) and str(msg.content or "").strip()
        ]
        if not tool_outputs:
            return "Subagent stopped without producing a final text response."
        recent_outputs = tool_outputs[-3:]
        return (
            "Subagent stopped without producing a final text response. "
            "Recent tool output is included so the parent can continue:\n\n"
            + "\n\n---\n\n".join(recent_outputs)
        )

    def _normalize_max_turns(self, max_turns: int) -> int:
        try:
            max_turns = int(max_turns)
        except (TypeError, ValueError):
            max_turns = DEFAULT_MAX_TURNS
        return min(max(max_turns, 1), DEFAULT_MAX_TURNS)

    def _accumulate_usage(self, usage: Optional[dict[str, int]]) -> None:
        """Accumulate real provider usage across the subagent run."""
        if not usage or self.last_usage is None:
            return
        self.last_usage["input_tokens"] += usage.get("input_tokens", 0)
        self.last_usage["output_tokens"] += usage.get("output_tokens", 0)
        self.last_usage["total_tokens"] += usage.get("total_tokens", 0)

    async def _emit_subagent_started(
        self,
        session_id: str,
        role: str,
        task: str,
        skills: Optional[list[str]] = None,
    ) -> None:
        if self.stream_callback is None:
            return
        await self.stream_callback(
            StreamEvent(
                source="subagent",
                session_id=session_id,
                role=role,
                parent_session_id=self.parent_session_id,
                event_type="subagent_started",
                content=task,
                title=f"{role} subagent started",
                detail=task,
                phase="implementing" if role == "worker" else "exploring",
                status="running",
                metadata={"task": task, "skills": skills or []},
            )
        )

    async def _emit_subagent_finished(
        self,
        session_id: str,
        role: str,
        task: str,
        status: str,
        elapsed_ms: int,
        skills: Optional[list[str]] = None,
    ) -> None:
        if self.stream_callback is None:
            return
        await self.stream_callback(
            StreamEvent(
                source="subagent",
                session_id=session_id,
                role=role,
                parent_session_id=self.parent_session_id,
                event_type="subagent_finished",
                content=status,
                title=f"{role} subagent finished",
                detail=task,
                phase="implementing" if role == "worker" else "exploring",
                status=status,
                elapsed_ms=elapsed_ms,
                metadata={"task": task, "skills": skills or []},
            )
        )

    async def _emit_approval_required(self, request) -> None:
        if self.stream_callback is None:
            return
        await self.stream_callback(
            StreamEvent(
                source="subagent",
                session_id=self._active_session_id or self.parent_session_id or "",
                role=self._active_role,
                parent_session_id=self.parent_session_id,
                event_type="approval_required",
                content=request.format(include_diff=False),
                title="Approve subagent action",
                detail=request.path or request.command or request.reason,
                phase="blocked",
                status="waiting_for_user",
                tool_name=request.tool_name,
                file_paths=[request.path] if request.path else None,
                metadata={
                    "action": request.action,
                    "reason": request.reason,
                    "risk": request.risk,
                    "diff_preview": request.diff_preview,
                },
            )
        )

    async def _emit_approval_resolved(self, request, status: str) -> None:
        if self.stream_callback is None:
            return
        await self.stream_callback(
            StreamEvent(
                source="subagent",
                session_id=self._active_session_id or self.parent_session_id or "",
                role=self._active_role,
                parent_session_id=self.parent_session_id,
                event_type="approval_resolved",
                content=status,
                title="Subagent approval resolved",
                detail=request.path or request.command or request.reason,
                phase="blocked" if status == "denied" else "implementing",
                status=status,
                tool_name=request.tool_name,
                file_paths=[request.path] if request.path else None,
                metadata={"action": request.action},
            )
        )
