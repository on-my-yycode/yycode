"""Help command for TUI commands."""

from __future__ import annotations

from dataclasses import dataclass

from agent.tui.help_content import render_help_page

from .base import CommandContext, CommandResult


@dataclass(frozen=True)
class HelpCommand:
    name: str = "help"
    description: str = "List available TUI commands"
    usage: str = ":help [command]"
    aliases: tuple[str, ...] = ("?",)
    destructive: bool = False

    async def execute(self, ctx: CommandContext, args: str) -> CommandResult:
        return CommandResult(
            title="yycode Help",
            content=render_help_page(ctx.registry.list_commands()),
        )


COMMAND = HelpCommand()
