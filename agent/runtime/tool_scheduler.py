"""Tool call scheduling helpers."""

import asyncio
from typing import Awaitable, Callable


async def execute_tool_calls(
    tool_calls,
    execute_tool_call: Callable[[object], Awaitable[object]],
    can_run_concurrently: Callable[[object], bool],
) -> list[object]:
    """Execute tool calls while preserving original result order."""
    results = [None] * len(tool_calls)
    concurrent_batch = []

    async def flush_concurrent_batch():
        if not concurrent_batch:
            return
        batch = list(concurrent_batch)
        concurrent_batch.clear()
        outputs = await asyncio.gather(
            *(execute_tool_call(tc) for _, tc in batch),
        )
        for (index, _), output in zip(batch, outputs):
            results[index] = output

    for index, tc in enumerate(tool_calls):
        if can_run_concurrently(tc):
            concurrent_batch.append((index, tc))
            continue
        await flush_concurrent_batch()
        results[index] = await execute_tool_call(tc)

    await flush_concurrent_batch()
    return results
