#!/usr/bin/env python3
"""Main entry point with TUI default startup."""

import os
import argparse
import asyncio
import contextlib
import textwrap
from datetime import datetime
from pathlib import Path


from dotenv import load_dotenv

from agent import Session
from agent.approval import ApprovalRequest
from agent.app_paths import resolve_app_root, resolve_runtime_data_dir
from agent.logger import setup_logging
from agent.session_store import FileSessionStore
from agent.streaming import colorize_diff
from agent.logger import LOG_FILE_NAME

# Try to enable readline for better input experience
try:
    import readline

    histfile = os.path.join(os.path.expanduser("~"), ".yycode_history")
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


def format_startup_info(session: Session) -> str:
    """Return non-sensitive startup details for the current session."""
    model = getattr(session.provider, "model", "(unknown)")
    skill_names = [skill.name for skill in session.skill_registry.list_skills()]
    skills = ", ".join(skill_names) if skill_names else "(none)"
    restored_message_count = getattr(session, "restored_message_count", 0)
    restore_line = (
        f"\033[90mRestored messages: {restored_message_count}\033[0m"
        if restored_message_count
        else None
    )
    lines = [
        f"\033[90mSession ID: {session.id}\033[0m",
        f"\033[90mModel: {model}\033[0m",
        f"\033[90mSkills: {skills}\033[0m",
    ]
    if restore_line:
        lines.append(restore_line)
    return "\n".join(
        lines
    )


def resolve_startup_workdir(raw_workdir: str | None) -> Path:
    """Resolve and validate the optional positional workspace argument."""
    workdir = Path(raw_workdir).expanduser().resolve() if raw_workdir else Path.cwd().resolve()
    if not workdir.exists():
        raise SystemExit(f"Error: workspace does not exist: {workdir}")
    if not workdir.is_dir():
        raise SystemExit(f"Error: workspace is not a directory: {workdir}")
    return workdir


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


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line parser with user-facing help text."""
    examples = """\
Examples:
  yycode
  yycode ~/project
  yycode --acp
  yycode acp
  yycode -s
  yycode -r bugfix-123
  yycode -x bugfix-123
  yycode ~/project -t
  yycode -a
  yycode --plain

Session data:
  Messages are saved by default under {app_root}/sessions/{workspace_hash}/{session_id}.json.
  Use -s/--sessions to inspect saved sessions for WORKDIR.
  Use -r/--resume ID to continue a previous conversation in the same workspace.
  Use -x/--delete ID to delete a saved session for WORKDIR.

Environment:
  PROVIDER                    LLM provider: anthropic or openai.
  API_KEY                     API key for the selected provider.
  API_BASE                    Optional custom API base URL.
  AI_MODEL                    Model name override.
  YOYO_APP_ROOT               yycode resource root; skills are loaded from this directory.
  YOYO_RUNTIME_DATA_DIR       Runtime data directory; defaults to the app/runtime root.
  YOYO_SESSION_DIR            Session messages directory override.
  YOYO_SKILL_DIRS             Extra skill directories appended after the default skills dir.
  YOYO_CONTEXT_WINDOW_TOKENS  Context window size override for token pressure.
  YOYO_SILENT                 Auto-approve risky actions when truthy.
  YOYO_AUTO_APPROVE           Alias for YOYO_SILENT.
"""
    parser = argparse.ArgumentParser(
        prog="yycode",
        description="yycode - terminal coding assistant with workspace tools and session persistence.",
        epilog=textwrap.dedent(examples),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "workdir",
        nargs="?",
        metavar="WORKDIR",
        help="Workspace directory to operate on. Defaults to the current directory.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Enable debug logging to console.",
    )
    parser.add_argument(
        "--acp",
        action="store_true",
        help="Run the Agent Client Protocol stdio server.",
    )
    parser.add_argument(
        "--log-file",
        action="store_true",
        help="Write logs to agent_debug.log.",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Use plain terminal input mode instead of the Textual TUI.",
    )
    parser.add_argument(
        "-a",
        "--auto",
        dest="auto",
        action="store_true",
        help="Auto-approve risky actions.",
    )
    parser.add_argument(
        "--silent",
        dest="auto",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-r",
        "--resume",
        metavar="ID",
        help="Resume messages from the persisted session id in the same workspace.",
    )
    parser.add_argument(
        "-s",
        "--sessions",
        dest="sessions",
        action="store_true",
        help="List persisted sessions for WORKDIR and exit.",
    )
    parser.add_argument(
        "--list-sessions",
        dest="sessions",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-t",
        "--temp",
        dest="temp",
        action="store_true",
        help="Temporary session; do not save messages.",
    )
    parser.add_argument(
        "-x",
        "--delete",
        metavar="ID",
        help="Delete a persisted session id for WORKDIR and exit.",
    )
    parser.add_argument(
        "--no-persist",
        dest="temp",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


async def run_plain_loop(args: argparse.Namespace, input_func=input) -> None:
    """Run the agent with ordinary terminal input as a TUI fallback."""
    approval_callback = auto_approval_callback if args.auto else console_approval_callback
    session = Session.from_config(
        workdir=args.workdir,
        session_id=args.session_id,
        approval_callback=approval_callback,
        persist_messages=not args.temp,
        resume=bool(args.resume),
    )
    print(format_startup_info(session))
    print("\033[90mPlain input mode. Type q or exit to quit. Use /paste and /end for multiline input.\033[0m\n")
    try:
        while True:
            try:
                query = await read_user_query_with_session(session, input_func)
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print("\n\033[90mInterrupted. Type q or exit to quit.\033[0m\n")
                continue
            if query.strip().lower() in {"q", "exit"}:
                break
            if not query.strip():
                continue
            await run_agent_task(session, query)
    finally:
        await session.close()


def list_sessions_for_workdir(workdir: Path) -> str:
    """Return a display table of persisted sessions for a workspace."""
    store = create_session_store_for_workdir(workdir)
    records = store.list_sessions()
    if not records:
        return f"No sessions found for workspace: {workdir}"

    lines = [
        f"Sessions for workspace: {workdir}",
        "",
        f"{'Session ID':<40}  {'Updated':<25}  Workdir",
        f"{'-' * 40}  {'-' * 25}  {'-' * 7}",
    ]
    for record in records:
        lines.append(f"{record.session_id:<40}  {format_session_updated_at(record.updated_at):<25}  {record.workdir}")
    return "\n".join(lines)


def delete_session_for_workdir(workdir: Path, session_id: str) -> str:
    """Delete a persisted session for a workspace."""
    store = create_session_store_for_workdir(workdir)
    before = {record.session_id for record in store.list_sessions()}
    store.delete(session_id)
    if session_id not in before:
        return f"No session found for workspace {workdir}: {session_id}"
    return f"Deleted session for workspace {workdir}: {session_id}"


def create_session_store_for_workdir(workdir: Path) -> FileSessionStore:
    """Create the default file session store for a workspace."""
    app_root = resolve_app_root()
    runtime_data_dir = resolve_runtime_data_dir(app_root)
    session_root = None if os.environ.get("YOYO_SESSION_DIR") else runtime_data_dir / "sessions"
    return FileSessionStore(app_root=app_root, workdir=workdir, root=session_root)


def resolve_log_file_path() -> Path:
    """Return the fixed application log file path."""
    app_root = resolve_app_root()
    runtime_data_dir = resolve_runtime_data_dir(app_root)
    return runtime_data_dir / "logs" / LOG_FILE_NAME


def format_session_updated_at(value: str) -> str:
    """Format persisted session timestamps for CLI display."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M")


def main() -> None:
    """Parse startup args and launch the TUI on the main thread."""
    parser = build_arg_parser()
    args = parser.parse_args()
    log_file_path = resolve_log_file_path()
    if args.acp or args.workdir == "acp":
        setup_logging(debug=args.debug, log_to_file=args.log_file, log_file=log_file_path)
        load_dotenv(override=True)
        auto_approve = args.auto or env_flag_enabled("YOYO_SILENT") or env_flag_enabled("YOYO_AUTO_APPROVE")
        from agent.acp.server import main as acp_main

        acp_main(auto_approve=auto_approve)
        return
    args.workdir = resolve_startup_workdir(args.workdir)
    args.session_id = args.resume

    if args.sessions:
        print(list_sessions_for_workdir(args.workdir))
        return
    if args.delete:
        print(delete_session_for_workdir(args.workdir, args.delete))
        return

    # Set up logging
    setup_logging(debug=args.debug, log_to_file=args.log_file, log_file=log_file_path)

    print("\033[33m" + LOGO + "\033[0m")
    startup_mode = "plain input" if args.plain else "TUI"
    print(f"yycode - Starting {startup_mode}...\n")
    if args.debug:
        print(f"\033[90m[DEBUG] Debug mode enabled. Logs written to {log_file_path}\033[0m\n")

    load_dotenv(override=True)
    if args.auto or env_flag_enabled("YOYO_SILENT") or env_flag_enabled("YOYO_AUTO_APPROVE"):
        args.auto = True
        print("\033[90m[SILENT] Approval prompts disabled; risky actions auto-approved.\033[0m\n")

    if args.plain:
        asyncio.run(run_plain_loop(args))
        return

    from agent.tui.app import run_tui

    run_tui(args)


if __name__ == "__main__":
    main()
