"""Shared helpers for local eval tasks."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Callable

from agent.providers.base import ChatResponse, LLMProvider


@dataclass(frozen=True)
class EvalCheck:
    """A single deterministic eval check."""

    name: str
    description: str
    run: Callable[[], None]


@dataclass(frozen=True)
class EvalResult:
    """Result for one deterministic eval check."""

    name: str
    passed: bool
    error: str = ""


class QueueProvider(LLMProvider):
    """Fake provider that returns queued responses and records model inputs."""

    model = "eval-fake-model"

    def __init__(self, responses: list[ChatResponse], *, exact_tokens: int | None = None) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict]] = []
        self.exact_tokens = exact_tokens

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("provider response queue is empty")
        return self.responses.pop(0)

    async def count_tokens(self, messages, system_prompt=None, tools=None):
        return self.exact_tokens

    async def close(self):
        return None


def run_checks(checks: list[EvalCheck]) -> list[EvalResult]:
    """Run eval checks and capture assertion failures as structured results."""
    results: list[EvalResult] = []
    for check in checks:
        try:
            check.run()
        except Exception:
            results.append(
                EvalResult(
                    name=check.name,
                    passed=False,
                    error=traceback.format_exc(limit=6).strip(),
                )
            )
        else:
            results.append(EvalResult(name=check.name, passed=True))
    return results
