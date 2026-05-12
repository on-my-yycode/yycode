"""Shared cancellation controller for interactive runners."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Literal


CancelStatus = Literal["cancelled", "not_running", "already_finished"]


@dataclass(frozen=True)
class CancelResult:
    """Result of a cancellation attempt."""

    status: CancelStatus


class CancellationController:
    """Track and cancel one active asyncio task."""

    def __init__(self) -> None:
        self.current_task: asyncio.Task | None = None

    def set_task(self, task: asyncio.Task) -> None:
        """Set the currently active task."""
        self.current_task = task

    def clear_task(self, task: asyncio.Task | None = None) -> None:
        """Clear the active task if it matches."""
        if task is None or self.current_task is task:
            self.current_task = None

    def is_running(self) -> bool:
        """Return whether a task is currently running."""
        return self.current_task is not None and not self.current_task.done()

    async def cancel(self) -> CancelResult:
        """Cancel the active task and return a stable status."""
        task = self.current_task
        if task is None:
            return CancelResult("not_running")
        if task.done():
            self.current_task = None
            return CancelResult("already_finished")
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self.current_task = None
        return CancelResult("cancelled")
