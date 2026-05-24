"""LLM chat timeout, heartbeat, and retry helpers."""

import asyncio
import contextlib
import os
import math
import sys
import time
from dataclasses import dataclass
from typing import Optional

from agent.providers.base import ChatResponse, LLMProvider
from agent.streaming import ProviderStreamCallback, StreamEvent, StreamEventCallback
from agent.logger import get_logger


logger = get_logger(__name__)


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
    estimated_tokens = _estimate_context_tokens(messages, system_prompt)
    provider_name = provider.__class__.__name__
    model_name = str(getattr(provider, "model", "(unknown)"))
    request_id = f"{source}:{session_id or '-'}:{int(time.time() * 1000) % 1_000_000}"

    logger.debug(
        "LLM request start request_id=%s source=%s role=%s provider=%s model=%s "
        "messages=%d tools=%d context_est_tokens=%d stream=%s timeout_s=%.3f "
        "heartbeat_s=%.3f max_retries=%d attempts=%d",
        request_id,
        source,
        role or "",
        provider_name,
        model_name,
        len(messages),
        len(tools),
        estimated_tokens,
        stream_callback is not None,
        timeout_seconds,
        heartbeat_seconds,
        max_retries,
        attempts,
    )

    # Debug log to confirm actual values
    if _debug_enabled() and event_callback:
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
            response = await _chat_once_with_heartbeat(
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
                request_id=request_id,
            )
            logger.debug(
                "LLM request success request_id=%s attempt=%d/%d",
                request_id,
                attempt,
                attempts,
            )
            return response
        except asyncio.TimeoutError:
            last_error = f"Timeout after {timeout_seconds:g}s"
            logger.warning(
                "LLM request timeout request_id=%s attempt=%d/%d timeout_s=%.3f",
                request_id,
                attempt,
                attempts,
                timeout_seconds,
            )
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_timeout",
                content=f"{last_error} (attempt {attempt}/{attempts})",
                title="Model request timed out",
                detail=f"Attempt {attempt}/{attempts}",
                phase="waiting",
                status="timeout",
                metadata={"attempt": attempt, "attempts": attempts},
            )
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
            logger.warning(
                "LLM request error request_id=%s attempt=%d/%d error_type=%s error=%s",
                request_id,
                attempt,
                attempts,
                exc.__class__.__name__,
                last_error,
            )
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_error",
                content=f"{last_error} (attempt {attempt}/{attempts})",
                title="Model request failed",
                detail=f"Attempt {attempt}/{attempts}",
                phase="waiting",
                status="failed",
                metadata={"attempt": attempt, "attempts": attempts},
            )

        if attempt < attempts:
            logger.debug(
                "LLM request retry scheduled request_id=%s next_attempt=%d/%d",
                request_id,
                attempt + 1,
                attempts,
            )
            await _emit_llm_event(
                event_callback,
                source=source,
                session_id=session_id,
                role=role,
                parent_session_id=parent_session_id,
                event_type="llm_retry",
                content=f"retrying model request ({attempt + 1}/{attempts})",
                title="Retrying model request",
                detail=f"Attempt {attempt + 1}/{attempts}",
                phase="waiting",
                status="retrying",
                metadata={"attempt": attempt + 1, "attempts": attempts},
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
    request_id: str,
) -> ChatResponse:
    last_activity = time.monotonic()
    first_stream_event_at: Optional[float] = None
    stream_event_count = 0

    async def activity_stream_callback(event_type: str, content: str) -> None:
        nonlocal first_stream_event_at, last_activity, stream_event_count
        now = time.monotonic()
        if first_stream_event_at is None:
            first_stream_event_at = now
            logger.debug(
                "LLM first stream event request_id=%s attempt=%d/%d event_type=%s "
                "first_token_latency_s=%.3f",
                request_id,
                attempt,
                attempts,
                event_type,
                now - start,
            )
        stream_event_count += 1
        last_activity = time.monotonic()
        if stream_callback is not None:
            await stream_callback(event_type, content)

    # Update activity before starting to avoid idle_seconds jumping
    last_activity = time.monotonic()
    start = time.monotonic()

    task = asyncio.create_task(
        provider.chat(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            stream_callback=activity_stream_callback if stream_callback else None,
        )
    )
    logger.debug(
        "LLM attempt started request_id=%s attempt=%d/%d timeout_s=%.3f",
        request_id,
        attempt,
        attempts,
        timeout_seconds,
    )

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
                response = await task
                elapsed_seconds = time.monotonic() - start
                logger.debug(
                    "LLM attempt completed request_id=%s attempt=%d/%d elapsed_s=%.3f "
                    "stream_events=%d first_token_latency_s=%s content_chars=%d "
                    "tool_calls=%d usage=%s",
                    request_id,
                    attempt,
                    attempts,
                    elapsed_seconds,
                    stream_event_count,
                    (
                        f"{first_stream_event_at - start:.3f}"
                        if first_stream_event_at is not None
                        else "none"
                    ),
                    len(response.content or ""),
                    len(response.tool_calls or []),
                    response.usage,
                )
                return response

            idle_seconds = int(time.monotonic() - last_activity)
            elapsed_seconds = int(time.monotonic() - start)
            logger.debug(
                "LLM still waiting request_id=%s attempt=%d/%d elapsed_s=%d "
                "idle_s=%d stream_events=%d remaining_s=%.3f",
                request_id,
                attempt,
                attempts,
                elapsed_seconds,
                idle_seconds,
                stream_event_count,
                remaining,
            )
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
                title="Waiting for model response",
                detail=f"Attempt {attempt}/{attempts}, {idle_seconds}s since last token",
                phase="waiting",
                status="running",
                elapsed_ms=elapsed_seconds * 1000,
                metadata={
                    "attempt": attempt,
                    "attempts": attempts,
                    "idle_seconds": idle_seconds,
                    "since_last_token_ms": idle_seconds * 1000,
                    "elapsed_seconds": elapsed_seconds,
                    "elapsed_ms": elapsed_seconds * 1000,
                    "source": source,
                    "role": role,
                },
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
    title: Optional[str] = None,
    detail: Optional[str] = None,
    phase: Optional[str] = None,
    status: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
    metadata: Optional[dict] = None,
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
            title=title,
            detail=detail,
            phase=phase,
            status=status,
            elapsed_ms=elapsed_ms,
            metadata=metadata,
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


def _debug_enabled() -> bool:
    logger_module = sys.modules.get("agent.logger")
    return bool(getattr(logger_module, "DEBUG_ENABLED", False))
