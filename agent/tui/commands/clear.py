"""Clear session history command."""

from __future__ import annotations

from dataclasses import dataclass

from .base import CommandContext, CommandResult


@dataclass(frozen=True)
class ClearCommand:
    name: str = "clear"
    description: str = "Clear current session message history and TUI timeline"
    usage: str = ":clear"
    aliases: tuple[str, ...] = ()
    destructive: bool = True

    async def execute(self, ctx: CommandContext, args: str) -> CommandResult:
        if args.strip():
            return CommandResult(
                title="Usage: :clear",
                content="The :clear command does not accept arguments.",
                severity="warning",
                status="warning",
            )
        if not ctx.confirmed:
            return CommandResult(
                title="Confirm clear",
                content="Clear session history? Type :clear! to confirm.",
                severity="warning",
                status="waiting_for_confirmation",
            )
        await ctx.runner.clear_session_history()
        return CommandResult(title="Session cleared", content="Session history cleared.")


COMMAND = ClearCommand()
