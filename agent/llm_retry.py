"""LLM chat timeout, heartbeat, and retry helpers."""

import asyncio
import contextlib
import os
import math
import time
from dataclasses import dataclass
from typing import Optional

from agent.providers.base import ChatResponse, LLMProvider
from agent.streaming import ProviderStreamCallback, StreamEvent, StreamEventCallback
from agent.logger import DEBUG_ENABLED


DEFAULT_LLM_TIMEOUT_SECONDS = 3600.0  # 1 hour for very long tasks
DEFAULT_LLM_MAX_RETRIES = 10        # More retries for reliability
DEFAULT_LLM_HEARTBEAT_SECONDS = 15.0  # Reduce noise but still visible


def _estimate_context_tokens(messages: list[dict], system_prompt: Optional[str] = None) -> int:
    """Estimate token count using a lightweight heuristic (1 token ≈ 4 chars)."""
    total_chars = 0
    if system_prompt:
        total_chars += len(system_prompt)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for item in content:
                total_chars += len(str(item))
        if msg.get("role"):
            total_chars += len(msg["role"])
    return math.ceil(total_chars / 4) if total_chars > 0 else 0


@dataclass
class LLMCallError(Exception):
    """Raised when an LLM call fails after retries."""

    message: str
    attempts: int
    timeout_seconds: float
    last_error: str

    def __str__(self) -> str:
        return self.message


async def chat_with_retry(
    provider: LLMProvider,
    *,
    messages: list[dict],
    tools: list[dict],
    system_prompt: Optional[str] = None,
    stream_callback: Optional[ProviderStreamCallback] = None,
    event_callback: Optional[StreamEventCallback] = None,
    source: str = "main",
    session_id: str = "",
    role: Optional[str] = None,
    parent_session_id: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    max_retries: Optional[int] = None,
    heartbeat_seconds: Optional[float] = None,
) -> ChatResponse:
    """Call a provider with bounded waiting, visible heartbeat, and retry."""
    timeout_seconds = _resolve_float_env(
        "YOYO_LLM_TIMEOUT_SECONDS",
        timeout_seconds,
        DEFAULT_LLM_TIMEOUT_SECONDS,
    )
    heartbeat_seconds = _resolve_float_env(
        "YOYO_LLM_HEARTBEAT_SECONDS",
        heartbeat_seconds,
        DEFAULT_LLM_HEARTBEAT_SECONDS,
    )
    max_retries = _resolve_int_env(
        "YOYO_LLM_MAX_RETRIES",
        max_retries,
        DEFAULT_LLM_MAX_RETRIES,
    )
    attempts = max_retries + 1

    # Debug log to confirm actual values
    if DEBUG_ENABLED and event_callback:
        estimated_tokens = _estimate_context_tokens(messages, system_prompt)
        await _emit_llm_event(
            event_callback,
            source=source,
            session_id=session_id,
            role=role,
            parent_session_id=parent_session_id,
            event_type="llm_waiting",
            content=f"[debug] Starting request, context≈{estimated_tokens} tokens, timeout={timeout_seconds:.0f}s, max_retries={max_retries}, total_attempts={attempts}",
        )
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            return await _chat_once_with_heartbeat(
                provider,
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                stream_callback=stream_callback,
                event_callback=event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                timeout_seconds=timeout_seconds,
                heartbeat_seconds=heartbeat_seconds,
                attempt=attempt,
                attempts=attempts,
            )
        except asyncio.TimeoutError:
            last_error = f"Timeout after {timeout_seconds:g}s"
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_timeout",
                content=f"{last_error} (attempt {attempt}/{attempts})",
            )
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_error",
                content=f"{last_error} (attempt {attempt}/{attempts})",
            )

        if attempt < attempts:
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_retry",
                content=f"retrying model request ({attempt + 1}/{attempts})",
            )
            await asyncio.sleep(min(2.0, 0.5 * attempt))

    raise LLMCallError(
        message=f"Model request failed after {attempts} attempt(s): {last_error}",
        attempts=attempts,
        timeout_seconds=timeout_seconds,
        last_error=last_error,
    )


async def _chat_once_with_heartbeat(
    provider: LLMProvider,
    *,
    messages: list[dict],
    tools: list[dict],
    system_prompt: Optional[str],
    stream_callback: Optional[ProviderStreamCallback],
    event_callback: Optional[StreamEventCallback],
    source: str,
    session_id: str,
    role: Optional[str],
    parent_session_id: Optional[str],
    timeout_seconds: float,
    heartbeat_seconds: float,
    attempt: int,
    attempts: int,
) -> ChatResponse:
    last_activity = time.monotonic()

    async def activity_stream_callback(event_type: str, content: str) -> None:
        nonlocal last_activity
        last_activity = time.monotonic()
        if stream_callback is not None:
            await stream_callback(event_type, content)

    # Update activity before starting to avoid idle_seconds jumping
    last_activity = time.monotonic()

    task = asyncio.create_task(
        provider.chat(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            stream_callback=activity_stream_callback if stream_callback else None,
        )
    )
    start = time.monotonic()

    try:
        while True:
            remaining = timeout_seconds - (time.monotonic() - start)
            if remaining <= 0:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                raise asyncio.TimeoutError()

            done, _ = await asyncio.wait({task}, timeout=min(heartbeat_seconds, remaining))
            if done:
                return await task

            idle_seconds = int(time.monotonic() - last_activity)
            elapsed_seconds = int(time.monotonic() - start)
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_waiting",
                content=(
                    "waiting for model response... "
                    f"{elapsed_seconds}s elapsed, {idle_seconds}s since last token "
                    f"(attempt {attempt}/{attempts})"
                ),
            )
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _emit_llm_event(
    event_callback: Optional[StreamEventCallback],
    *,
    source: str,
    session_id: str,
    role: Optional[str],
    parent_session_id: Optional[str],
    event_type: str,
    content: str,
) -> None:
    if event_callback is None:
        return
    await event_callback(
        StreamEvent(
            source=source,
            session_id=session_id,
            role=role,
            parent_session_id=parent_session_id,
            event_type=event_type,
            content=content,
        )
    )


def _resolve_float_env(name: str, explicit: Optional[float], default: float) -> float:
    if explicit is not None:
        return max(float(explicit), 0.001)
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(float(raw), 0.001)
    except ValueError:
        return default


def _resolve_int_env(name: str, explicit: Optional[int], default: int) -> int:
    if explicit is not None:
        return max(int(explicit), 0)
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(int(raw), 0)
    except ValueError:
        return default
