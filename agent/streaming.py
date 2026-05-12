"""Structured streaming events and renderers."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional


StreamEventCallback = Callable[["StreamEvent"], Awaitable[None]]
ProviderStreamCallback = Callable[[str, str], Awaitable[None]]

ANSI_RESET = "\033[0m"
ANSI_DIM = "\033[90m"
ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_YELLOW = "\033[33m"
ANSI_CYAN = "\033[36m"
ANSI_BG_GREEN = "\033[48;5;22m"
ANSI_BG_RED = "\033[48;5;52m"
ANSI_BG_BLUE = "\033[48;5;24m"
ANSI_BG_GRAY = "\033[48;5;236m"


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
    title: Optional[str] = None
    detail: Optional[str] = None
    phase: Optional[str] = None
    status: Optional[str] = None
    tool_name: Optional[str] = None
    file_paths: Optional[list[str]] = None
    elapsed_ms: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None

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
            "title": self.title,
            "detail": self.detail,
            "phase": self.phase,
            "status": self.status,
            "tool_name": self.tool_name,
            "file_paths": self.file_paths,
            "elapsed_ms": self.elapsed_ms,
            "metadata": self.metadata,
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


def colorize_diff(diff: str) -> str:
    """Return a diff with background colors for changed line groups."""
    lines = []
    for line in diff.splitlines():
        if line.startswith("@@"):
            lines.append(f"{ANSI_BG_BLUE}{line}{ANSI_RESET}")
        elif line.startswith("diff --git") or line.startswith("index "):
            lines.append(f"{ANSI_BG_GRAY}{line}{ANSI_RESET}")
        elif line.startswith("+++") or line.startswith("---"):
            lines.append(f"{ANSI_BG_GRAY}{line}{ANSI_RESET}")
        elif line.startswith("+"):
            lines.append(f"{ANSI_BG_GREEN}{line}{ANSI_RESET}")
        elif line.startswith("-"):
            lines.append(f"{ANSI_BG_RED}{line}{ANSI_RESET}")
        else:
            lines.append(line)
    if diff.endswith("\n"):
        return "\n".join(lines) + "\n"
    return "\n".join(lines)


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
        elif event.event_type == "tool_start":
            if self.in_thinking_by_session.get(event.session_id):
                print("\033[90m [done]\033[0m")
                self.in_thinking_by_session[event.session_id] = False
            self._print_tool_start(event)
        elif event.event_type == "tool_end":
            self._print_tool_end(event)
        elif event.event_type == "tool_result":
            self._print_tool_result(event)
        elif event.event_type == "text_delta":
            if self.in_thinking_by_session.get(event.session_id):
                print("\033[90m [done]\033[0m")
                self.in_thinking_by_session[event.session_id] = False
            self._print_text_delta(event)
        elif event.event_type == "usage":
            self._print_usage(event)
        elif event.event_type == "context_compressed":
            self._print_context_compressed(event)
        elif event.event_type == "context_summarized":
            self._print_context_summarized(event)
        elif event.event_type in ["llm_waiting", "llm_timeout", "llm_retry", "llm_error"]:
            self._print_llm_status(event)

    def _print_tool_start(self, event: StreamEvent) -> None:
        if not self.first_line:
            print()
        description = event.title or event.content
        if event.detail and event.detail != description:
            description = f"{description}: {event.detail}"
        print(f"\033[90m{self._label(event)}▶ Starting {description}...\033[0m", end="", flush=True)
        self.first_line = False

    def _print_tool_end(self, event: StreamEvent) -> None:
        print("\033[90m [done]\033[0m", flush=True)

    def _print_tool_result(self, event: StreamEvent) -> None:
        if not event.content.strip():
            return
        if not self.first_line:
            print()
        print(f"\033[90m{self._label(event)}diff:\033[0m")
        print(colorize_diff(event.content), flush=True)
        self.first_line = False

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

    def _print_context_summarized(self, event: StreamEvent) -> None:
        if not self.first_line:
            print()
        print(f"\033[90m[context] {event.content}\033[0m", flush=True)
        self.first_line = False

    def _print_llm_status(self, event: StreamEvent) -> None:
        """Print LLM status updates so user knows the agent is still working."""
        if self.in_thinking_by_session.get(event.session_id):
            print("\033[90m [waiting]\033[0m")
            self.in_thinking_by_session[event.session_id] = False
        if not self.first_line:
            print()

        color = ANSI_DIM
        prefix = "[llm]"
        if event.event_type == "llm_error":
            color = ANSI_RED
            prefix = "[error]"
        elif event.event_type == "llm_timeout":
            color = ANSI_YELLOW
            prefix = "[timeout]"
        elif event.event_type == "llm_retry":
            color = ANSI_CYAN
            prefix = "[retry]"
        elif event.event_type == "llm_waiting":
            color = ANSI_DIM
            prefix = "[waiting]"

        print(f"{color}{self._label(event)}{prefix} {event.content}{ANSI_RESET}", flush=True)
        self.first_line = False


class StreamPrinter(ConsoleStreamRenderer):
    """Backward-compatible console stream printer."""
