"""Registry and auto-discovery for TUI-only commands."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from dataclasses import dataclass

from .base import TuiCommand


@dataclass(frozen=True)
class ParsedCommand:
    """Parsed command line."""

    command: TuiCommand
    args: str = ""
    confirmed: bool = False
    raw_text: str = ""


class CommandRegistry:
    """Lookup table for TUI commands."""

    def __init__(self, commands: Iterable[TuiCommand] = ()) -> None:
        self._commands: dict[str, TuiCommand] = {}
        self._aliases: dict[str, TuiCommand] = {}
        for command in commands:
            self.register(command)

    def register(self, command: TuiCommand) -> None:
        """Register one command by its lowercase name and aliases."""
        name = command.name.strip().lower()
        if not name:
            raise ValueError("Command name cannot be empty")
        if name in self._commands or name in self._aliases:
            raise ValueError(f"Duplicate TUI command name: {name}")
        self._commands[name] = command
        for alias in getattr(command, "aliases", ()) or ():
            normalized = alias.strip().lower()
            if not normalized:
                continue
            if normalized in self._commands or normalized in self._aliases:
                raise ValueError(f"Duplicate TUI command alias: {normalized}")
            self._aliases[normalized] = command

    def get(self, name: str) -> TuiCommand | None:
        """Return a command by name or alias, if present."""
        normalized = name.strip().lower().lstrip(":").rstrip("!")
        return self._commands.get(normalized) or self._aliases.get(normalized)

    def list_commands(self) -> list[TuiCommand]:
        """Return commands sorted by name."""
        return [self._commands[name] for name in sorted(self._commands)]

    def matching(self, token: str, limit: int = 8) -> list[TuiCommand]:
        """Return commands matching a completion token."""
        normalized = token.strip().lower().lstrip(":")
        commands = self.list_commands()
        rows = [command for command in commands if command.name.startswith(normalized)]
        if normalized and not rows:
            rows = [command for command in commands if normalized in command.name]
        return rows[:limit]

    def parse(self, text: str) -> ParsedCommand | None:
        """Parse a command line such as ':clear!' or ':help clear'."""
        stripped = text.strip()
        if not stripped.startswith(":"):
            return None
        command_text = stripped[1:].strip()
        if not command_text:
            return None
        name, _, args = command_text.partition(" ")
        confirmed = name.endswith("!")
        name = name.rstrip("!")
        command = self.get(name)
        if command is None:
            return None
        return ParsedCommand(command=command, args=args.strip(), confirmed=confirmed, raw_text=stripped)


def discover_commands(package_name: str = "agent.tui.commands") -> CommandRegistry:
    """Discover COMMAND instances from command modules in this package."""
    package = importlib.import_module(package_name)
    registry = CommandRegistry()
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_") or module_info.name in {"base", "registry"}:
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}")
        command = getattr(module, "COMMAND", None)
        if command is not None:
            registry.register(command)
    return registry
