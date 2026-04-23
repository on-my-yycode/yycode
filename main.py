#!/usr/bin/env python3
"""Main entry point with multi-provider support."""

import os
import sys
from pathlib import Path
import asyncio


from dotenv import load_dotenv

from agent import Session

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
\ \/ /___  __  ______     /   | ____ ____  ____  / /_
 \  / __ \/ / / / __ \   / /| |/ __ `/ _ \/ __ \/ __/
 / / /_/ / /_/ / /_/ /  / ___ / /_/ /  __/ / / / /_  
/_/\____/\__, /\____/  /_/  |_\__, /\___/_/ /_/\__/  
        /____/               /____/                    
"""


def read_multiline_input(input_func=input) -> str:
    """Read pasted multiline input until a line containing only /end."""
    print("\033[90mPaste multiline input. Submit with /end on its own line.\033[0m")
    lines = []
    while True:
        line = input_func("\033[36m... >> \033[0m")
        if line.strip() == "/end":
            break
        lines.append(line)
    return "\n".join(lines)


async def read_user_query(input_func=input) -> str:
    """Read a single-line query or a multiline paste block."""
    query = await asyncio.to_thread(input_func, "\033[36myoyo >> \033[0m")
    if query.strip().lower() == "/paste":
        query = await asyncio.to_thread(read_multiline_input, input_func)
    return query


def build_prompt(session: Session) -> str:
    """Build the interactive prompt with cumulative token usage."""
    if session.has_real_usage():
        total_tokens = session.cumulative_usage["total_tokens"]
        formatted_tokens = format_token_count(total_tokens)
        return f"\033[90m[{formatted_tokens} tokens]\033[0m \033[36myoyo >> \033[0m"
    estimated_tokens = session.estimate_token_usage()
    formatted_tokens = format_token_count(estimated_tokens)
    return f"\033[90m[est {formatted_tokens} tokens]\033[0m \033[36myoyo >> \033[0m"


def format_token_count(count: int) -> str:
    """Format token counts using k/m suffixes."""
    if count < 1_000:
        return str(count)
    if count < 1_000_000:
        return _format_compact_number(count / 1_000, "k")
    return _format_compact_number(count / 1_000_000, "m")


def _format_compact_number(value: float, suffix: str) -> str:
    """Format a compact number and trim a trailing .0."""
    formatted = f"{value:.1f}"
    if formatted.endswith(".0"):
        formatted = formatted[:-2]
    return f"{formatted}{suffix}"


async def read_user_query_with_session(session: Session, input_func=input) -> str:
    """Read a query using a prompt that includes current token usage."""
    query = await asyncio.to_thread(input_func, build_prompt(session))
    if query.strip().lower() == "/paste":
        query = await asyncio.to_thread(read_multiline_input, input_func)
    return query


async def main():
    print("\033[33m" + LOGO + "\033[0m")
    print("Yoyo Agent - Ready!\n")

    load_dotenv(override=True)

    # Create session from config/environment
    session = Session.from_config()
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

            await session.send(query)
            print("\n")
    finally:
        if readline:
            try:
                readline.write_history_file(histfile)
            except Exception:
                pass
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
