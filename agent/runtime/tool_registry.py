"""Runtime tool registry and handler binding."""

from functools import wraps
from typing import Callable, Optional

from agent.runtime.context import AgentRuntimeContext
from agent.skills import SkillRegistry
from agent.subagent import SubagentRunner


CONCURRENT_SUBAGENT_ROLES = {"explorer", "architect", "tester", "security"}
DEFAULT_TOOL_TIMEOUT_SECONDS = 3600
DEFAULT_TOOL_EXECUTION = {
    "side_effects": "unknown",
    "concurrency": "serial",
    "timeout_seconds": DEFAULT_TOOL_TIMEOUT_SECONDS,
}

WORKSPACE_BOUND_TOOLS = {
    "read_file",
    "read_many_files",
    "write_file",
    "edit_file",
    "apply_patch",
    "grep",
    "list_files",
    "git_show",
    "git_diff",
    "workspace_state",
    "verify",
    "bash",
}


class RuntimeToolRegistry:
    """Resolve runtime-bound tool handlers and execution metadata."""

    def __init__(self, runtime: AgentRuntimeContext):
        self.runtime = runtime
        self.todo_handler = runtime.todo_manager.create_todo_handler()
        self.skill_registry = SkillRegistry(runtime.workdir, runtime.skill_dirs)
        self.tool_execution = {
            tool["name"]: tool.get("execution", {})
            for tool in runtime.tools
        }

    def resolve(self, tool_name: str) -> Optional[Callable]:
        """Return the handler for a tool name."""
        if tool_name == "todo":
            return self.todo_handler
        if tool_name == "list_skills":
            return self.skill_registry.format_skill_list
        if tool_name == "load_skill":
            return lambda names: self.skill_registry.format_loaded_skills(names)
        if tool_name == "subagent":
            return self.create_subagent_runner().run
        handler = self.runtime.tool_handlers.get(tool_name)
        if handler is not None and tool_name in WORKSPACE_BOUND_TOOLS:
            return self._bind_workdir(handler)
        return handler

    def _bind_workdir(self, handler: Callable) -> Callable:
        """Inject runtime workdir into workspace-bound tools without exposing it to models."""

        @wraps(handler)
        def wrapped(*args, **kwargs):
            kwargs.setdefault("workdir", self.runtime.workdir)
            return handler(*args, **kwargs)

        return wrapped

    def create_subagent_runner(self) -> SubagentRunner:
        """Create a subagent runner bound to the current runtime."""
        return SubagentRunner(
            provider=self.runtime.provider,
            workdir=self.runtime.workdir,
            parent_system_prompt=self.runtime.system_prompt,
            tool_handlers=self.runtime.tool_handlers,
            tools=self.runtime.tools,
            parent_session_id=self.runtime.session_id,
            skill_dirs=self.runtime.skill_dirs,
            app_root=self.runtime.app_root,
            stream_callback=self.runtime.stream_callback,
            approval_callback=self.runtime.approval_callback,
        )

    def execution_for(self, tool_name: str) -> dict:
        """Return execution policy for a tool."""
        return {**DEFAULT_TOOL_EXECUTION, **self.tool_execution.get(tool_name, {})}

    def timeout_for(self, tool_name: str) -> int:
        """Return timeout seconds for a tool."""
        return int(self.execution_for(tool_name)["timeout_seconds"])

    def is_workspace_write(self, tool_name: str) -> bool:
        """Return whether a tool mutates the workspace."""
        return self.execution_for(tool_name)["side_effects"] == "workspace_write"

    def can_run_concurrently(self, tool_call) -> bool:
        """Return whether a tool call may run in a concurrent batch."""
        if tool_call.name == "subagent":
            return tool_call.args.get("role") in CONCURRENT_SUBAGENT_ROLES
        execution = self.execution_for(tool_call.name)
        if execution["side_effects"] in {"workspace_write", "session_state"}:
            return False
        return execution["concurrency"] == "safe"
