"""Shared helpers for thin LSP tool wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from agent.lsp.client import LspClientError
from agent.lsp.manager import LspUnavailable, get_lsp_manager

T = TypeVar("T")


async def run_lsp_tool(workdir: Path | str | None, action: Callable[[object], Awaitable[T]]) -> T | str:
    """Run an LSP action with model-friendly unavailable/error output."""
    try:
        manager = get_lsp_manager(workdir or Path.cwd())
        return await action(manager)
    except LspUnavailable as exc:
        return "status: unavailable\nreason: " + str(exc) + "\nfallback: use grep and read_file for text-based navigation"
    except (LspClientError, TimeoutError) as exc:
        return "status: error\nreason: " + str(exc) + "\nfallback: use grep and read_file for text-based navigation"
    except Exception as exc:
        return f"Error: {exc}"


def format_list(title: str, items: list) -> str:
    """Format LSP result items that expose format()."""
    if not items:
        return f"status: no_results\n{title}: none"
    return title + ":\n" + "\n".join(f"- {item.format()}" for item in items)


LSP_TOOL_EXECUTION = {
    "side_effects": "read_only",
    "concurrency": "safe",
    "timeout_seconds": 30,
}
