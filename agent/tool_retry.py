"""Retry utilities for agent tool execution."""

import asyncio
import inspect
import time
from typing import Callable, TypeVar

T = TypeVar("T")


def run_with_retry(
    func: Callable[..., T],
    max_retries: int = 2,
    retry_delay: float = 0.5,
    backoff_factor: float = 2.0,
) -> T:
    """Run a function with automatic retry on failure."""
    retry_count = 0

    while True:
        try:
            return func()
        except Exception:
            retry_count += 1
            if retry_count > max_retries:
                raise
            delay = retry_delay * (backoff_factor ** (retry_count - 1))
            time.sleep(delay)


def run_tool_with_retry(
    handler: Callable[..., str],
    tool_name: str,
    max_retries: int = 2,
    **kwargs
) -> str:
    """Run a synchronous tool handler with retry and error handling."""
    retry_count = 0

    while retry_count <= max_retries:
        try:
            if not handler:
                return f"Unknown tool: {tool_name}"
            return handler(**kwargs)
        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                return f"Error executing tool {tool_name}: {str(e)}"
            time.sleep(0.5 * retry_count)


async def async_run_tool_with_retry(
    handler: Callable[..., str],
    tool_name: str,
    max_retries: int = 2,
    **kwargs
) -> str:
    """Run a sync or async tool handler with retry and error handling."""
    retry_count = 0

    while retry_count <= max_retries:
        try:
            if not handler:
                return f"Unknown tool: {tool_name}"
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                return f"Error executing tool {tool_name}: {str(e)}"
            await asyncio.sleep(0.5 * retry_count)
