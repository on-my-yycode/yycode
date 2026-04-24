"""Structured streaming events and renderers."""

from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


StreamEventCallback = Callable[["StreamEvent"], Awaitable[None]]
ProviderStreamCallback = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True)
class StreamEvent:
    """Structured event emitted by agents during streaming."""

    source: str
    session_id: str
    event_type: str
    content: str = ""
    role: Optional[str] = None
    parent_session_id: Optional[str] = None
    usage: Optional[dict[str, int]] = None

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return {
            "source": self.source,
            "session_id": self.session_id,
            "role": self.role,
            "parent_session_id": self.parent_session_id,
            "event_type": self.event_type,
            "content": self.content,
            "usage": self.usage,
        }


def make_provider_stream_callback(
    event_callback: Optional[StreamEventCallback],
    *,
    source: str,
    session_id: str,
    role: Optional[str] = None,
    parent_session_id: Optional[str] = None,
) -> Optional[ProviderStreamCallback]:
    """Wrap provider callbacks into structured stream events."""
    if event_callback is None:
        return None

    async def callback(event_type: str, content: str) -> None:
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

    return callback


class ConsoleStreamRenderer:
    """Render structured stream events to the console."""

    def __init__(self):
        self.in_thinking_by_session: dict[str, bool] = {}
        self.first_line = True
        self.active_label_by_session: dict[str, str] = {}

    async def callback(self, event: StreamEvent) -> None:
        """Render a structured stream event."""
        if event.event_type == "thinking_start":
            if not self.first_line:
                print()
            print(f"\033[90m{self._label(event)}Thinking...\033[0m", end="", flush=True)
            self.in_thinking_by_session[event.session_id] = True
            self.first_line = False
        elif event.event_type == "thinking_delta":
            pass
        elif event.event_type == "thinking_end":
            if self.in_thinking_by_session.get(event.session_id):
                print("\033[90m [done]\033[0m", flush=True)
            self.in_thinking_by_session[event.session_id] = False
        elif event.event_type == "text_delta":
            if self.in_thinking_by_session.get(event.session_id):
                print("\033[90m [done]\033[0m")
                self.in_thinking_by_session[event.session_id] = False
            self._print_text_delta(event)
        elif event.event_type == "usage":
            self._print_usage(event)
        elif event.event_type == "context_compressed":
            self._print_context_compressed(event)

    def _print_text_delta(self, event: StreamEvent) -> None:
        label = self._label(event)
        active_label = self.active_label_by_session.get(event.session_id)
        if label and active_label != label:
            if not self.first_line:
                print()
            print(label, end="", flush=True)
            self.active_label_by_session[event.session_id] = label
        print(event.content, end="", flush=True)
        self.first_line = False

    def _label(self, event: StreamEvent) -> str:
        if event.source != "subagent":
            return ""
        role = event.role or "unknown"
        return f"\033[90m@{role} \033[0m"

    def _print_usage(self, event: StreamEvent) -> None:
        usage = event.usage or {}
        label = self._label(event)
        if not self.first_line:
            print()
        print(
            f"\033[90m{label}[usage] "
            f"input={usage.get('input_tokens', 0)} "
            f"output={usage.get('output_tokens', 0)} "
            f"total={usage.get('total_tokens', 0)}\033[0m",
            flush=True,
        )
        self.first_line = False

    def _print_context_compressed(self, event: StreamEvent) -> None:
        if not self.first_line:
            print()
        print(f"\033[90m[context] {event.content}\033[0m", flush=True)
        self.first_line = False


class StreamPrinter(ConsoleStreamRenderer):
    """Backward-compatible console stream printer."""
