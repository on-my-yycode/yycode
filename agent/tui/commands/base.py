"""Base types for TUI-only commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from agent.tui.runner import AgentTuiRunner

    from .registry import CommandRegistry


Severity = Literal["information", "warning", "error"]


@dataclass(frozen=True)
class CommandContext:
    """Execution dependencies passed to TUI commands."""

    runner: "AgentTuiRunner"
    registry: "CommandRegistry"
    confirmed: bool = False
    raw_text: str = ""


@dataclass(frozen=True)
class CommandResult:
    """Result displayed in the TUI after a command executes."""

    title: str
    content: str = ""
    severity: Severity = "information"
    status: str = "completed"
    clear_input: bool = True


class TuiCommand(Protocol):
    """Protocol implemented by TUI-only commands."""

    name: str
    description: str
    usage: str
    aliases: tuple[str, ...]
    destructive: bool

    async def execute(self, ctx: CommandContext, args: str) -> CommandResult:
        """Execute the command without sending it to the LLM."""
