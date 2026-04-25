#!/usr/bin/env python3
"""Main entry point with multi-provider support."""

import os
import sys
import argparse
from pathlib import Path
import asyncio
import contextlib


from dotenv import load_dotenv

from agent import Session
from agent.approval import ApprovalRequest
from agent.logger import setup_logging, debug_print
from agent.streaming import colorize_diff

# Try to enable readline for better input experience
try:
    import readline

    histfile = os.path.join(os.path.expanduser("~"), ".yoyoagent_history")
    try:
        readline.read_history_file(histfile)
    except FileNotFoundError:
        pass

    readline.set_history_length(1000)

    if 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
except ImportError:
    readline = None


LOGO = """
__  __                     ___                    __
\\ \\/ /___  __  ______     /   | ____ ____  ____  / /_
 \\  / __ \\/ / / / __ \\   / /| |/ __ `/ _ \\/ __ \\/ __/
 / / /_/ / /_/ / /_/ /  / ___ / /_/ /  __/ / / / /_
/_/\\____/\\__, /\\____/  /_/  |_\\__, /\\___/_/ /_/\\__/
        /____/               /____/
"""


PASTE_COMMANDS = {"/p", "/paste"}
READLINE_PROMPT_START = "\001"
READLINE_PROMPT_END = "\002"
ANSI_CYAN = "\033[36m"
ANSI_GRAY = "\033[90m"
ANSI_RESET = "\033[0m"


def _protect_prompt_color(sequence: str) -> str:
    """Mark ANSI escape sequences as zero-width for readline prompt editing."""
    if readline is None:
        return sequence
    return f"{READLINE_PROMPT_START}{sequence}{READLINE_PROMPT_END}"


def cyan(text: str) -> str:
    """Return cyan text, with ANSI escapes protected for readline prompts."""
    return f"{_protect_prompt_color(ANSI_CYAN)}{text}{_protect_prompt_color(ANSI_RESET)}"


def gray(text: str) -> str:
    """Return gray text, with ANSI escapes protected for readline prompts."""
    return f"{_protect_prompt_color(ANSI_GRAY)}{text}{_protect_prompt_color(ANSI_RESET)}"


def read_multiline_input(input_func=input) -> str:
    """Read pasted multiline input until a line containing only /end."""
    print("\033[90mPaste multiline input. Submit with /end on its own line.\033[0m")
    lines = []
    while True:
        line = input_func(cyan("... >> "))
        if line.strip() == "/end":
            break
        lines.append(line)
    return "\n".join(lines)


async def read_user_query(input_func=input) -> str:
    """Read a single-line query or a multiline paste block."""
    query = await asyncio.to_thread(input_func, cyan("yoyo >> "))
    if query.strip().lower() in PASTE_COMMANDS:
        query = await asyncio.to_thread(read_multiline_input, input_func)
    return query


def build_prompt(session: Session) -> str:
    """Build the interactive prompt with current context window pressure."""
    estimated_tokens = session.estimate_token_usage()
    formatted_used = format_token_count(estimated_tokens)
    formatted_window = format_token_count(session.context_window_tokens)
    percent = format_context_percent(session.estimate_context_window_percent())
    return f"{gray(f'[{formatted_used}/{formatted_window} {percent}]')} {cyan('yoyo >> ')}"


def format_token_count(count: int) -> str:
    """Format token counts using k/m suffixes."""
    if count < 1_000:
        return str(count)
    if count < 1_000_000:
        return _format_compact_number(count / 1_000, "k")
    return _format_compact_number(count / 1_000_000, "m")


def format_context_percent(percent: float) -> str:
    """Format context window usage percentage."""
    if percent < 10:
        return f"{percent:.1f}%"
    return f"{percent:.0f}%"


def _format_compact_number(value: float, suffix: str) -> str:
    """Format a compact number and trim a trailing .0."""
    formatted = f"{value:.1f}"
    if formatted.endswith(".0"):
        formatted = formatted[:-2]
    return f"{formatted}{suffix}"


async def read_user_query_with_session(session: Session, input_func=input) -> str:
    """Read a query using a prompt that includes current token usage."""
    prompt = build_prompt(session)
    query = await asyncio.to_thread(input_func, prompt)
    if query.strip().lower() in PASTE_COMMANDS:
        query = await asyncio.to_thread(read_multiline_input, input_func)
    return query


async def console_approval_callback(request: ApprovalRequest) -> bool:
    """Ask the user to approve a risky tool execution in the console."""
    print()
    print(request.format(include_diff=False))
    if request.diff_preview:
        print("\033[90mdiff_preview:\033[0m")
        print(colorize_diff(request.diff_preview))
    answer = await asyncio.to_thread(
        input,
        "\033[33mApprove this action? [y/N] \033[0m",
    )
    return answer.strip().lower() in {"y", "yes"}


async def auto_approval_callback(_request: ApprovalRequest) -> bool:
    """Approve runtime approval requests without prompting."""
    return True


def env_flag_enabled(name: str) -> bool:
    """Return whether an environment flag is truthy."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


async def run_agent_task(session: Session, query: str) -> bool:
    """Run one agent task and let Ctrl+C cancel the task without exiting the CLI."""
    task = asyncio.create_task(session.send(query))
    try:
        await task
        print("\n")
        return True
    except (KeyboardInterrupt, asyncio.CancelledError):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        print("\n\033[90m[current task cancelled]\033[0m\n")
        return False


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Yoyo Agent")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging to console",
    )
    parser.add_argument(
        "--log-file",
        action="store_true",
        help="Write logs to agent_debug.log",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Run without approval prompts; risky actions are automatically approved",
    )
    args = parser.parse_args()

    # Set up logging
    setup_logging(debug=args.debug, log_to_file=args.log_file)

    print("\033[33m" + LOGO + "\033[0m")
    print("Yoyo Agent - Ready!\n")
    if args.debug:
        print("\033[90m[DEBUG] Debug mode enabled. Logs written to agent_debug.log\033[0m\n")

    load_dotenv(override=True)

    # Create session from config/environment
    silent_mode = args.silent or env_flag_enabled("YOYO_SILENT") or env_flag_enabled("YOYO_AUTO_APPROVE")
    approval_callback = auto_approval_callback if silent_mode else console_approval_callback
    if silent_mode:
        print("\033[90m[SILENT] Approval prompts disabled; risky actions auto-approved.\033[0m\n")
    session = Session.from_config(approval_callback=approval_callback)
    print(f"\033[90mSession ID: {session.id}\033[0m")
    print("\033[90mSystem Prompt:\033[0m")
    print(session.system_prompt)
    print()

    try:
        while True:
            try:
                query = await read_user_query_with_session(session)
            except (EOFError, KeyboardInterrupt):
                print("\nExiting...")
                break
            if query.strip().lower() in ("q", "exit"):
                break
            if not query.strip():
                continue
            if query.strip().lower() == "clear":
                session.clear()
                print("History cleared.")
                continue

            if readline:
                readline.add_history(query)

            await run_agent_task(session, query)
    finally:
        if readline:
            try:
                readline.write_history_file(histfile)
            except Exception:
                pass
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
