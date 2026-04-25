"""Runtime context objects for graph execution."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from agent.approval import ApprovalCallback
from agent.providers.base import LLMProvider
from agent.streaming import StreamEventCallback
from agent.tool_retry import async_run_tool_with_retry
from agent.todo_manager import TodoManager


@dataclass
class WorkflowState:
    """Mutable workflow state scoped to a single graph run."""

    workspace_state_checked: bool = False
    git_diff_checked: bool = False
    needs_verify: bool = False
    approved_write_keys: set[tuple[str, str, str]] = field(default_factory=set)


@dataclass
class AgentRuntimeContext:
    """Dependencies and runtime state needed by graph nodes."""

    provider: LLMProvider
    system_prompt: str
    todo_manager: TodoManager
    workdir: Path
    session_id: str
    skill_dirs: list[str] | None = None
    stream_callback: Optional[StreamEventCallback] = None
    approval_callback: Optional[ApprovalCallback] = None
    tools: list[dict] = field(default_factory=list)
    tool_handlers: dict[str, Callable] = field(default_factory=dict)
    workflow_state: WorkflowState = field(default_factory=WorkflowState)
    run_tool: Callable = async_run_tool_with_retry
