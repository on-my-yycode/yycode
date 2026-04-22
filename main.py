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


async def main():
    print("\033[33m" + LOGO + "\033[0m")
    print("Yoyo Agent - Ready!\n")

    load_dotenv(override=True)

    # Create session from config/environment
    session = Session.from_config()
    print(f"\033[90mSession ID: {session.id}\033[0m")

    try:
        while True:
            try:
                query = await asyncio.to_thread(
                    input, "\033[36myoyo >> \033[0m"
                )
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
