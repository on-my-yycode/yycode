"""Retry utilities for tool execution."""

import time
from typing import Callable, TypeVar, Optional

T = TypeVar("T")


def run_with_retry(
    func: Callable[..., T],
    max_retries: int = 2,
    retry_delay: float = 0.5,
    backoff_factor: float = 2.0,
) -> T:
    """
    Run a function with automatic retry on failure.

    Args:
        func: Function to execute
        max_retries: Maximum number of retries (default 2)
        retry_delay: Initial delay in seconds (default 0.5)
        backoff_factor: Backoff multiplier for delay (default 2.0)

    Returns:
        The function's return value

    Raises:
        The last exception if all retries fail
    """
    retry_count = 0

    while True:
        try:
            return func()
        except Exception:
            retry_count += 1
            if retry_count > max_retries:
                raise
            # Exponential backoff
            delay = retry_delay * (backoff_factor ** (retry_count - 1))
            time.sleep(delay)


def run_tool_with_retry(
    handler: Callable[..., str],
    tool_name: str,
    max_retries: int = 2,
    **kwargs
) -> str:
    """
    Run a tool handler with retry and error handling.

    Args:
        handler: Tool handler function
        tool_name: Name of the tool (for error messages)
        max_retries: Maximum number of retries
        **kwargs: Arguments to pass to handler

    Returns:
        Tool output string, or error message
    """
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
            # Wait before retrying
            time.sleep(0.5 * retry_count)
